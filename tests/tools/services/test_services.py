"""tools.services: the customer's servers and apps, the request parser, and nimbus_services.run_action through
the real executor, identity and audit log: it carries out only the signed-in customer's own offer, once,
audited, and the change settles a few seconds later without anything running in the background."""

import subprocess
from pathlib import Path

import psycopg
import pytest
from pydantic import ValidationError

from channels import sessions
from channels.identity.service import Identity
from data.migrate import migrate, psql
from safety.screening.pipeline import Screener
from safety.screening.scorers import pattern_injection
from tools import audit as audit_module
from tools import services
from tools.execution import Executor, ToolFailure
from tools.execution.calls import ToolCall
from tools.registry import Registry, Risk

ROOT = Path(__file__).resolve().parents[3]
DB = "test_services"
DSN = f"postgresql://agent:change-me@127.0.0.1:5432/{DB}"  # credentials from .env.example


def connect():
    return psycopg.connect(DSN, autocommit=True)


@pytest.fixture(scope="module")
def stack():
    subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env.example", "up",
                    "-d", "--wait", "postgres"], cwd=ROOT, check=True, capture_output=True)
    psql("postgres", f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
    psql("postgres", f'CREATE DATABASE "{DB}"')
    migrate("main", DB)
    for module in (sessions, audit_module, services):
        module.apply_schema(DB)
    psql(DB, "INSERT INTO tenants (id, name, region) VALUES ('t_us', 'Acme', 'US'), ('t_eu', 'G', 'EU');")
    for principal in ("sarah", "bob"):
        services.seed(connect, "t_us", principal)
    identity = Identity(connect)
    return identity, services.register(Registry(), connect, identity).freeze()


def named(name, principal="sarah"):
    return next(s for s in services.services(connect, "t_us", principal) if s["name"] == name)


def offer(name, action, principal="sarah", key=None, replicas=None):
    service = named(name, principal)
    return services.propose(connect, "t_us", principal, f"c-{principal}", key or f"{name}:{action}",
                            service["service_id"], action, replicas)


def settle(name, principal="sarah"):
    psql(DB, f"UPDATE nimbus_services SET settles_at = now() - interval '1 second' WHERE name = '{name}' "
             f"AND principal_id = '{principal}' AND settles_at IS NOT NULL")


def run(stack, proposal, principal="sarah", tier="T1_VERIFIED", tenant="t_us", call_id="call-1"):
    """One call through the executor on a fresh live session -> (result or ToolFailure, the call's audit)."""
    identity, registry = stack
    audit_log = audit_module.AuditLog(connect, lambda: None)
    executor = Executor(registry, services.SYSTEMS, Screener(lambda text: (0.0, []), pattern_injection),
                        identity=identity, audit=audit_log)
    with connect() as conn:
        session = sessions.start(conn, tenant, principal, tier)
    case_id = f"case-{session}"
    try:
        outcome = executor.run(ToolCall(tool_call_id=call_id, tool_id=services.RUN,
                                        arguments={"proposal": proposal}, tenant_id=tenant,
                                        principal_id=principal, case_id=case_id, checkpoint_id="cp-1",
                                        session_id=session))
    except ToolFailure as failure:
        outcome = failure
    return outcome, audit_log.read(tenant, case_id)


# Parsing, in code ------------------------------------------------------------------------------------------

OWN = [{"service_id": "s1", "name": "payments-api-01", "kind": "server", "region": "eu-central-1",
        "status": "running", "replicas": None},
       {"service_id": "s2", "name": "batch-worker-02", "kind": "server", "region": "eu-central-1",
        "status": "running", "replicas": None},
       {"service_id": "s3", "name": "staging-web-01", "kind": "server", "region": "eu-central-1",
        "status": "stopped", "replicas": None},
       {"service_id": "s4", "name": "checkout-worker", "kind": "app", "region": "eu-central-1",
        "status": "running", "replicas": 2}]


@pytest.mark.parametrize("text, action, service, replicas", [
    ("Please stop payments-api-01", "stop", "s1", None),
    ("close the payments server", "stop", "s1", None),
    ("can you shut down batch-worker-02 now", "stop", "s2", None),
    ("start staging-web-01 again", "start", "s3", None),
    ("reboot payments-api-01", "restart", "s1", None),
    ("restart checkout-worker", "restart", "s4", None),
    ("scale checkout-worker to 4", "scale", "s4", 4),
    ("I need 3 replicas of checkout-worker, scale it", "scale", "s4", 3)])
def test_an_action_word_and_one_own_service_make_an_offer(text, action, service, replicas):
    wanted = services.understand(text, OWN)
    got = (wanted["action"], wanted["service"]["service_id"], wanted["replicas"])
    assert got == (action, service, replicas)


@pytest.mark.parametrize("text", ["How do I stop payments-api-01?", "my VPN keeps dropping",
                                  "stop charging me twice", "restart the database please"])
def test_a_question_or_no_own_service_named_is_not_a_request(text):
    assert services.understand(text, OWN) is None


HOW_MANY = "How many replicas should checkout-worker run? Between 1 and 10; it runs 2 now."


@pytest.mark.parametrize("text, asks", [
    ("stop the worker", "Which one do you mean: batch-worker-02, checkout-worker?"),
    ("stop checkout-worker", "checkout-worker is a container app: I can restart or scale it, not stop it."),
    ("start payments-api-01", "payments-api-01 is running right now, so there is nothing to start."),
    ("scale checkout-worker", HOW_MANY),
    ("scale checkout-worker to 40", HOW_MANY)])
def test_anything_unclear_gets_one_question_instead_of_an_offer(text, asks):
    assert services.understand(text, OWN) == {"reply": asks}


# The tool --------------------------------------------------------------------------------------------------

def test_the_tool_is_a_low_risk_write_from_tier_one_that_nothing_offers(stack):
    tool = stack[1].tools[services.RUN]
    assert (tool.risk, tool.min_tier.name, tool.stages) == (Risk.LOW_RISK_WRITE, "T1_VERIFIED",
                                                           frozenset({"CUSTOMER_ACTION"}))
    for stage in ("TRIAGED", "DELIBERATING", "EXECUTING_SOP", "ESCALATED_HITL"):
        assert stack[1].permitted("T2_SSO", (), stage) == []


def test_a_confirmed_stop_runs_once_is_audited_and_settles(stack):
    proposal = offer("payments-api-01", "stop")
    result, audit = run(stack, proposal)
    assert result.data["action"] == "stop" and result.data["service"]["status"] == "stopping"
    again, _ = run(stack, proposal, call_id="call-2")                     # a retry or a second click
    assert again.data["service"]["status"] == "stopping"
    assert [(a["tool"], a["outcome"], a["risk_class"]) for a in audit] == [
        (services.RUN, "ok", "low_risk_write")]
    settle("payments-api-01")
    assert named("payments-api-01")["status"] == "stopped"
    assert [a["action_id"] for a in services.activity(connect, "t_us", "sarah")].count(proposal) == 1
    assert named("payments-api-01", "bob")["status"] == "running"            # bob's own server is untouched


def test_scaling_changes_the_replicas(stack):
    result, _ = run(stack, offer("checkout-worker", "scale", replicas=4))
    assert (result.data["service"]["status"], result.data["service"]["replicas"]) == ("scaling", 4)
    settle("checkout-worker")
    assert (named("checkout-worker")["status"], named("checkout-worker")["replicas"]) == ("running", 4)


def test_an_offer_for_a_service_that_changed_since_is_refused_and_changes_nothing(stack):
    first, second = offer("batch-worker-02", "stop", key="a"), offer("batch-worker-02", "stop", key="b")
    assert run(stack, first)[0].data["service"]["status"] == "stopping"
    result, audit = run(stack, second)
    assert isinstance(result, ToolFailure) and result.code == "REJECTED"
    assert [a["outcome"] for a in audit] == ["failed"]


@pytest.mark.parametrize("who, code", [({"principal": "bob"}, "REJECTED"),
                                       ({"tenant": "t_eu"}, "REJECTED"),
                                       ({"tier": "T0_ANON"}, "STEP_UP_REQUIRED")])
def test_only_the_customer_who_owns_the_offer_can_confirm_it_and_not_as_a_guest(stack, who, code):
    proposal = offer("staging-web-01", "start", key=f"other-{code}-{next(iter(who.values()))}")
    result, _ = run(stack, proposal, **who)
    assert isinstance(result, ToolFailure) and result.code == code
    assert named("staging-web-01")["status"] == "stopped"


def test_an_expired_offer_is_refused(stack):
    proposal = offer("notifications", "restart")
    psql(DB, f"UPDATE service_actions SET expires_at = now() - interval '1 second' "
             f"WHERE id = {services.number_id(proposal)}")
    result, _ = run(stack, proposal)
    assert isinstance(result, ToolFailure) and result.code == "REJECTED"
    assert named("notifications")["status"] == "running"


def test_an_argument_that_is_not_an_offer_number_is_refused_before_anything_runs(stack):
    with pytest.raises(ValidationError):
        run(stack, "TKT-00001")


def test_staff_act_directly_with_the_same_rules_and_the_customer_sees_who_did_it(stack):
    worker = named("batch-worker-02", "bob")
    after = services.staff_act(connect, "t_us", worker["service_id"], "stop")
    assert after["status"] == "stopping"
    with pytest.raises(services.Refused, match="stopping now"):              # a double click changes nothing
        services.staff_act(connect, "t_us", worker["service_id"], "stop")
    settle("batch-worker-02", "bob")
    assert named("batch-worker-02", "bob")["status"] == "stopped"
    done = services.activity(connect, "t_us", "bob")[0]
    assert (done["service"], done["action"], done["actor"]) == ("batch-worker-02", "stop", "staff:demo")
    assert services.activity(connect, "t_us")[0]["principal_id"] == "bob"    # staff see whose it is
    app = named("checkout-worker", "bob")
    for action, replicas, why in (("stop", None, "cannot stop"), ("scale", None, "1-10 replicas"),
                                  ("scale", 11, "1-10 replicas"), ("explode", None, "unknown action")):
        with pytest.raises(services.Refused, match=why):
            services.staff_act(connect, "t_us", app["service_id"], action, replicas)
    with pytest.raises(services.Refused, match="no such service"):
        services.staff_act(connect, "t_eu", app["service_id"], "restart")     # another tenant's service
    assert services.staff_act(connect, "t_us", app["service_id"], "scale", 3)["replicas"] == 3
    owners = {s["principal_id"] for s in services.everyone(connect, "t_us")}
    assert owners == {"sarah", "bob"} and services.everyone(connect, "t_eu") == []