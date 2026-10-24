"""M2-07: sagas over fake systems with a failure midway, hardened: no credential, principal, handler or role
in the workflow input; identity and roles resolved from trusted sources inside the activities; compensations
authorized like forward steps; every tool call audited, failures included (FR-24). Runs against the compose
Postgres, OpenBao and Temporal with the real Identity, Cedar and approval gate; Jev is scripted."""

import asyncio
import base64
import dataclasses
import json
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import httpx
import psycopg
import pytest
from pydantic import BaseModel
from temporalio.client import Client, WorkflowFailureError

from channels import sessions
from channels.identity.service import AGENT, Identity
from core.orchestrator.decisions import Answer, DecisionEngine, Masked
from core.secrets import OpenBao
from data.keys import KeyStore, OpenBaoTransit
from data.migrate import PsqlError, migrate, psql
from safety.authz.cedar import POLICY_DIR, Authorizer, entity
from safety.screening.pipeline import Screener
from safety.screening.scorers import pattern_injection
from tools import audit as audit_module
from tools.audit import AuditLog
from tools.execution import Executor, System, current
from tools.registry import Registry
from tools.sagas.activities import SagaActivities, check_plan, gated_tool, worker
from tools.sagas.workflow import SagaStart, SagaStep, start_saga
from tools.schemas import arg
from tools.validation import approvals
from tools.validation.approvals import ApprovalGate, Approver, CallContext, NotApproved, UnverifiedApprover

ROOT = Path(__file__).resolve().parents[3]
MAIN, KEYS = "test_sagas", "test_sagas_keys"
DSN = "postgresql://agent:change-me@127.0.0.1:5432/{}"  # credentials from .env.example


class AccountArgs(BaseModel):
    account_id: str = arg(sensitive=True)


class NoticeArgs(BaseModel):
    account_id: str = arg(sensitive=True)
    to: str = arg(sensitive=True)


def post(path):
    ctx = current()
    headers = {"Authorization": f"Bearer {ctx.credential}"}
    if ctx.idempotency_key:
        headers["Idempotency-Key"] = ctx.idempotency_key
    response = ctx.http.post(path, headers=headers)
    response.raise_for_status()
    return response.json()


def get(path):
    response = current().http.get(path, headers={"Authorization": f"Bearer {current().credential}"})
    response.raise_for_status()
    return response.json()


def build():
    registry = Registry()

    def reg(tool_id, args, risk, func, reviewed="ben"):
        registry.tool(tool_id, args=args, description=f"Tool {tool_id.split('.')[1].replace('_', ' ')}",
                      risk=risk, stages={"EXECUTING_SOP"}, author="ana", reviewed_by=reviewed)(func)
    reg("billing.cancel_subscription", AccountArgs, "low_risk_write",
        lambda a: post(f"https://billing.test/subscriptions/{a.account_id}/cancel"))
    reg("billing.restore_subscription", AccountArgs, "low_risk_write",
        lambda a: post(f"https://billing.test/subscriptions/{a.account_id}/restore"))
    reg("billing.get_subscription", AccountArgs, "read_only",
        lambda a: get(f"https://billing.test/subscriptions/{a.account_id}"))
    reg("billing.wipe_account", AccountArgs, "destructive_irreversible",
        lambda a: post(f"https://billing.test/accounts/{a.account_id}/wipe"))
    reg("crm.deallocate_license", AccountArgs, "low_risk_write",
        lambda a: post(f"https://crm.test/licenses/{a.account_id}/deallocate"))
    reg("crm.reallocate_license", AccountArgs, "low_risk_write",
        lambda a: post(f"https://crm.test/licenses/{a.account_id}/reallocate"))
    reg("crm.reallocate_unreviewed", AccountArgs, "low_risk_write",
        lambda a: post(f"https://crm.test/licenses/{a.account_id}/reallocate"), reviewed=None)
    reg("email.send_notice", NoticeArgs, "low_risk_write",
        lambda a: post(f"https://email.test/send/{a.account_id}"))
    reg("legacy.undo", AccountArgs, "low_risk_write", lambda a: post("https://legacy.test/undo"))
    reg("legacy.do", AccountArgs, "low_risk_write", lambda a: post("https://legacy.test/do"))
    return registry.freeze()


REGISTRY = build()
SYSTEMS = {
    "billing": System("billing", frozenset({"billing.test"}), "obo", "account-tools", idempotent_writes=True),
    "crm": System("crm", frozenset({"crm.test"}), "service_account", service_secret="crm-key",
                  idempotent_writes=True),
    "email": System("email", frozenset({"email.test"}), "obo", "account-tools"),
    "legacy": System("legacy", frozenset({"legacy.test"}), "obo", "account-tools"),
}


class Fake:
    """The external systems: scripted status per path, every request in order, and an optional hook."""

    def __init__(self, script=None, on=None):
        self.script, self.on, self.requests = script or {}, on or {}, []

    def __call__(self, request):
        self.requests.append((request.method, request.url.host, request.url.path,
                              request.headers.get("Idempotency-Key"), request.headers.get("Authorization")))
        if request.url.path in self.on:
            self.on[request.url.path]()
        status = self.script.get(request.url.path, 200)
        return httpx.Response(status, json={"path": request.url.path, "state": "active"})

    def paths(self):
        return [path for method, _, path, _, _ in self.requests if method == "POST"]


class ScriptedJev:
    def evaluate(self, state, questions):
        return {"verdict": Answer("ALLOW", 0.9), "serves": Answer(True, 0.97)}


APPROVE_POLICY = """
permit (principal in Role::"specialist", action == Action::"approve_action", resource)
when { resource.tenant_id == principal.tenant_id && resource.level == "specialist"
       && resource.handler != principal && resource.customer != principal };
"""
STAFF = {"tok-sam": Approver("t_us", "sam", frozenset({"specialist"})),
         "tok-runtime": Approver("t_us", AGENT, frozenset({"specialist"}))}  # the handler itself
ROLES = {}  # the trusted role directory: (tenant, principal) -> roles


def verify(credential):
    if credential not in STAFF:
        raise UnverifiedApprover("unknown")
    return STAFF[credential]


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env.example", "up",
                    "-d", "--wait", "postgres", "openbao", "temporal"], cwd=ROOT, check=True,
                   capture_output=True)
    for name, kind in ((MAIN, "main"), (KEYS, "keys")):
        psql("postgres", f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        psql("postgres", f'CREATE DATABASE "{name}"')
        migrate(kind, name)
    sessions.apply_schema(MAIN)
    approvals.apply_schema(MAIN)
    audit_module.apply_schema(MAIN)
    psql(MAIN, "INSERT INTO tenants (id, name, region) VALUES ('t_us', 'Acme', 'US'), ('t_eu', 'G', 'EU');"
               "INSERT INTO tenant_settings (tenant_id) VALUES ('t_us'), ('t_eu')")
    bao = OpenBao("http://127.0.0.1:8200", "change-me")
    for _ in range(30):
        try:
            bao.enable_transit()
            break
        except httpx.HTTPError:
            time.sleep(1)
    policies = tmp_path_factory.mktemp("policies")
    shutil.copy(Path(POLICY_DIR) / "support.cedar", policies / "support.cedar")
    with open(policies / "support.cedar", "a", encoding="utf-8") as text:
        text.write(APPROVE_POLICY)
    schema = json.loads((Path(POLICY_DIR) / "support.cedarschema.json").read_text(encoding="utf-8"))
    schema[""]["entityTypes"]["ApprovalRequest"] = {"shape": {"type": "Record", "attributes": {
        "tenant_id": {"type": "String"}, "level": {"type": "String"},
        "handler": {"type": "Entity", "name": "User"}, "customer": {"type": "Entity", "name": "User"}}}}
    schema[""]["actions"]["approve_action"] = {"memberOf": [{"id": "write"}], "appliesTo": {
        "principalTypes": ["User"], "resourceTypes": ["ApprovalRequest"],
        "context": {"type": "Record", "attributes": {"in_blackout": {"type": "Boolean"}}}}}
    (policies / "support.cedarschema.json").write_text(json.dumps(schema), encoding="utf-8")
    return {"bao": bao, "policies": policies, "identity": Identity(connect)}


@pytest.fixture(autouse=True)
def clean_roles():
    ROLES.clear()


def connect(database=MAIN):
    return psycopg.connect(DSN.format(database), autocommit=True)


def parts(stack, fake):
    def keys():
        return KeyStore(connect(KEYS), OpenBaoTransit(stack["bao"]))
    authorizer = Authorizer(policy_dir=stack["policies"])
    executor = Executor(REGISTRY, SYSTEMS, Screener(lambda text: (0.0, []), pattern_injection),
                        identity=stack["identity"], authorizer=authorizer,
                        transport=httpx.MockTransport(fake),
                        sleep=lambda seconds: None,
                        roles_of=lambda tenant, principal: ROLES.get((tenant, principal), ()))
    gate = ApprovalGate(connect, DecisionEngine(ScriptedJev()), authorizer, verify)
    return executor, gate, AuditLog(connect, keys), keys


def new_case(tenant="t_us", principal="sarah"):
    """A live T2 session, a conversation and a case, as sign-in and the session layer create them."""
    with connect() as conn:
        session = sessions.start(conn, tenant, principal, "T2_SSO")
        conversation = f"conv-{uuid.uuid4().hex[:8]}"
        sessions.open_conversation(conn, tenant, principal, session, conversation)
        return session, conversation, sessions.link_case(conn, tenant, conversation)


def account(owner="sarah", tenant="t_us"):
    return {"action": "update_contact", "type": "Account", "id": "A-1",
            "attrs": {"tenant_id": tenant, "owner": entity("User", owner)}}


def step(step_id, tool_id, undo=None, **options):
    arguments = options.pop("arguments", {"account_id": "A-1"})
    return SagaStep(step_id, tool_id, arguments, resource=options.pop("resource", account()),
                    compensation_tool_id=undo, compensation_arguments={"account_id": "A-1"} if undo else {},
                    **options)


def saga(steps, session, conversation, case_id, tenant="t_us"):
    return SagaStart(saga_id=f"s-{uuid.uuid4().hex[:8]}", tenant_id=tenant, session_id=session,
                     case_id=case_id, conversation_id=conversation,
                     message="Please cancel my subscription and tell me by e-mail", steps=steps)


class AuditDownFor(AuditLog):
    """The audit store fails for one tool's forward call (e.g. the database is unreachable just then)."""

    def __init__(self, base, tool_id):
        super().__init__(base.connect, base.keys)
        self.tool_id = tool_id

    def record(self, **fields):
        if fields["tool_id"] == self.tool_id and fields["action"] == "forward":
            raise psycopg.OperationalError("audit store unreachable")
        return super().record(**fields)


def run(stack, fake, start, history=False, audit_down_for=None):
    executor, gate, audit, _ = parts(stack, fake)
    if audit_down_for:
        audit = AuditDownFor(audit, audit_down_for)

    async def go():
        client = await Client.connect("127.0.0.1:7233")
        queue = f"sagas-{uuid.uuid4().hex}"
        async with worker(client, SagaActivities(REGISTRY, SYSTEMS, executor, gate, audit), queue):
            handle = await start_saga(client, start, queue)
            outcome = await handle.result()
            return (outcome, (await handle.fetch_history()).to_json()) if history else outcome
    return asyncio.run(go())


def approve_last(stack, fake, start, credential="tok-sam"):
    """The agent flow opens the irreversible step's approval request for the session's customer, with the
    runtime as handler; a specialist grants it."""
    _, gate, _, _ = parts(stack, fake)
    last = start.steps[-1]
    tool = gated_tool(REGISTRY, last)
    principal, _ = stack["identity"].session_principal(start.tenant_id, start.session_id)
    ctx = CallContext(start.tenant_id, start.case_id, start.conversation_id, principal, AGENT,
                      resource=last.resource)
    args = tool.args(**last.arguments)
    decision = gate.validate(ctx, tool, args, {"message": Masked(start.message)})
    request_id = gate.request(ctx, tool, args, decision)
    gate.grant("t_us", request_id, credential)
    last.approval_request_id = request_id
    return decision


NOTICE = {"account_id": "A-1", "to": "sarah@acme.com"}


def three_steps(**cancel_options):
    return [step("cancel", "billing.cancel_subscription", "billing.restore_subscription",
                 snapshot_tool_id="billing.get_subscription", **cancel_options),
            step("deallocate", "crm.deallocate_license", "crm.reallocate_license"),
            step("notify", "email.send_notice", arguments=NOTICE, approval_request_id=str(uuid.uuid4()))]


def audited(stack, case_id):
    return [(r["step_id"], r["action"], r["outcome"], r["error_code"]) for r in
            parts(stack, Fake())[2].read("t_us", case_id)]


# The scenario: a failure midway -----------------------------------------------------------------------------

def test_a_failure_midway_compensates_the_completed_steps_once_and_never_runs_the_last(stack):
    fake = Fake({"/licenses/A-1/deallocate": 500})
    session, conversation, case_id = new_case()
    start = saga(three_steps(), session, conversation, case_id)
    outcome = run(stack, fake, start)
    assert outcome.status == "COMPENSATED" and outcome.failed_step == "deallocate"
    assert outcome.completed == ["cancel"] and outcome.compensated == ["cancel"]
    posts = fake.paths()
    assert posts.count("/subscriptions/A-1/restore") == 1 and posts[-1] == "/subscriptions/A-1/restore"
    assert not any(host == "email.test" for _, host, _, _, _ in fake.requests)
    restore_key = [key for _, _, path, key, _ in fake.requests if path.endswith("/restore")][0]
    assert restore_key == f"{start.saga_id}:{start.saga_id}:cancel:compensate"
    assert audited(stack, case_id) == [
        ("cancel", "snapshot", "ok", None), ("cancel", "snapshot", "ok", None),
        ("cancel", "forward", "ok", None),
        ("deallocate", "forward", "failed", "TRANSIENT"), ("cancel", "compensate", "ok", None)]


def test_the_irreversible_last_step_runs_only_with_a_specialists_approval(stack):
    session, conversation, case_id = new_case()
    start = saga(three_steps(), session, conversation, case_id)
    assert approve_last(stack, Fake(), start).level == "specialist"  # a low-risk tool that cannot be undone
    fake = Fake()
    outcome = run(stack, fake, start)
    assert outcome.status == "COMPLETED" and outcome.completed == ["cancel", "deallocate", "notify"]
    assert fake.paths() == ["/subscriptions/A-1/cancel", "/licenses/A-1/deallocate", "/send/A-1"]


def test_without_a_granted_approval_the_last_step_is_refused_and_everything_is_undone_in_reverse(stack):
    session, conversation, case_id = new_case()
    fake = Fake()
    outcome = run(stack, fake, saga(three_steps(), session, conversation, case_id))
    assert outcome.status == "COMPENSATED" and outcome.failed_step == "notify"
    assert outcome.error_code == "NOT_APPROVED" and outcome.compensated == ["deallocate", "cancel"]
    assert fake.paths()[-2:] == ["/licenses/A-1/reallocate", "/subscriptions/A-1/restore"]


def test_a_policy_change_after_approval_refuses_the_last_step(stack):
    """The approval binds the tenant policy version: changed after the grant, the step is refused."""
    session, conversation, case_id = new_case()
    start = saga(three_steps(), session, conversation, case_id)
    approve_last(stack, Fake(), start)
    psql(MAIN, "UPDATE tenant_settings SET approval_threshold_usd = 900, version = version + 1 "
               "WHERE tenant_id = 't_us'")
    fake = Fake()
    outcome = run(stack, fake, start)
    assert outcome.failed_step == "notify" and outcome.error_code == "NOT_APPROVED"
    assert not any(host == "email.test" for _, host, _, _, _ in fake.requests)


def test_a_failed_compensation_stops_the_rollback_for_a_human(stack):
    fake = Fake({"/licenses/A-1/reallocate": 500})
    session, conversation, case_id = new_case()
    outcome = run(stack, fake, saga(three_steps(), session, conversation, case_id))
    assert outcome.status == "COMPENSATION_FAILED" and outcome.compensated == []
    assert "/subscriptions/A-1/restore" not in fake.paths()
    reallocations = [key for _, _, path, key, _ in fake.requests if path.endswith("/reallocate")]
    assert len(reallocations) >= 3 and len(set(reallocations)) == 1  # every attempt: the same key
    failed = [r for r in audited(stack, case_id) if r[1] == "compensate"]
    assert failed and all(r[0] == "deallocate" and r[2] == "failed" for r in failed)
    assert {r[3] for r in failed} <= {"TRANSIENT", "SYSTEM_UNAVAILABLE"}  # the CRM's breaker opens meanwhile


def test_a_step_whose_audit_cannot_be_written_is_undone_around_and_flagged_for_a_human(stack):
    """The deallocation ran, but its audit write failed: the saga cannot tell, so it rolls back the earlier
    step and reports the uncertain one instead of claiming a clean rollback."""
    session, conversation, case_id = new_case()
    fake = Fake()
    outcome = run(stack, fake, saga(three_steps(), session, conversation, case_id),
                  audit_down_for="crm.deallocate_license")
    assert outcome.status == "UNCERTAIN_STEP" and outcome.failed_step == "deallocate"
    assert outcome.error_code == "ACTIVITY_FAILED" and outcome.compensated == ["cancel"]
    assert "/subscriptions/A-1/restore" in fake.paths()


def test_a_rejected_plan_runs_nothing(stack):
    session, conversation, case_id = new_case()
    fake = Fake()
    steps = [step("notify", "email.send_notice", arguments=NOTICE, approval_request_id=str(uuid.uuid4())),
             step("cancel", "billing.cancel_subscription", "billing.restore_subscription")]
    with pytest.raises(WorkflowFailureError) as failed:
        run(stack, fake, saga(steps, session, conversation, case_id))
    assert failed.value.cause.cause.type == "SAGA_REJECTED" and fake.requests == []


# 1. No credential in Temporal -------------------------------------------------------------------------------

def test_the_saga_input_and_history_carry_a_session_reference_not_a_credential(stack):
    names = {f.name for f in dataclasses.fields(SagaStart)}
    assert not names & {"access_token", "roles", "principal_id", "handler_id"}
    fake = Fake({"/licenses/A-1/deallocate": 500})
    session, conversation, case_id = new_case()
    outcome, history = run(stack, fake, saga(three_steps(), session, conversation, case_id), history=True)
    decoded = history + " ".join(base64.b64decode(chunk).decode("utf-8", "replace")
                                 for chunk in re.findall(r'"data":\s*"([A-Za-z0-9+/=]+)"', history))
    tokens = {auth.removeprefix("Bearer ") for _, _, _, _, auth in fake.requests if auth}
    assert session in decoded and tokens and outcome.status == "COMPENSATED"
    assert not any(token in decoded for token in tokens)  # neither the minted token nor the service key
    assert "access_token" not in decoded and "Bearer" not in decoded


def test_an_ended_session_stops_the_saga_before_any_call_and_is_audited(stack):
    session, conversation, case_id = new_case()
    with connect() as conn:
        sessions.end(conn, "t_us", session)
    fake = Fake()
    outcome = run(stack, fake, saga(three_steps(), session, conversation, case_id))
    assert outcome.failed_step == "cancel" and outcome.error_code == "AUTHENTICATION_EXPIRED"
    assert fake.requests == []
    (record,) = parts(stack, fake)[2].read("t_us", case_id)
    assert record["user_id"] is None and record["personal"] is None  # no user, nothing personal stored


def test_another_tenants_session_does_not_resolve(stack):
    eu_session, _, _ = new_case(tenant="t_eu")
    _, conversation, case_id = new_case()
    fake = Fake()
    outcome = run(stack, fake, saga(three_steps(), eu_session, conversation, case_id))
    assert outcome.error_code == "AUTHENTICATION_EXPIRED" and fake.requests == []


# 2. Identity and roles from trusted sources only ------------------------------------------------------------

def test_roles_cannot_be_injected_through_the_saga_input(stack):
    with pytest.raises(TypeError):
        SagaStart(saga_id="x", tenant_id="t_us", session_id="s", case_id="c", conversation_id="v",
                  message="m", steps=[], roles=["tenant_admin", "cloud_admin"])
    session, conversation, case_id = new_case()
    bobs = [step("cancel", "billing.cancel_subscription", "billing.restore_subscription",
                 resource=account(owner="bob"))]
    fake = Fake()
    outcome = run(stack, fake, saga(bobs, session, conversation, case_id))
    assert outcome.error_code == "NOT_APPROVED" and fake.requests == []  # Sarah has no role on Bob's account


def test_roles_from_the_trusted_directory_authorize_legitimate_work(stack):
    ROLES[("t_us", "sarah")] = ("tenant_admin",)
    session, conversation, case_id = new_case()
    bobs = [step("cancel", "billing.cancel_subscription", "billing.restore_subscription",
                 resource=account(owner="bob"))]
    fake = Fake()
    assert run(stack, fake, saga(bobs, session, conversation, case_id)).status == "COMPLETED"
    assert fake.paths() == ["/subscriptions/A-1/cancel"]


def test_the_handler_cannot_be_set_from_the_input_nor_approve_its_own_step(stack):
    with pytest.raises(TypeError):
        SagaStart(saga_id="x", tenant_id="t_us", session_id="s", case_id="c", conversation_id="v",
                  message="m", steps=[], handler_id="sam")
    session, conversation, case_id = new_case()
    start = saga(three_steps(), session, conversation, case_id)
    with pytest.raises(NotApproved, match="handler"):
        approve_last(stack, Fake(), start, credential="tok-runtime")


def test_an_approval_for_another_customer_does_not_carry_over(stack):
    """Bob's session and conversation, but the saga names Sarah's: the gate's binding refuses it."""
    sarah_session, conversation, case_id = new_case()
    bob_session, _, _ = new_case(principal="bob")
    start = saga(three_steps(), sarah_session, conversation, case_id)
    approve_last(stack, Fake(), start)
    start.session_id = bob_session
    fake = Fake()
    outcome = run(stack, fake, start)
    assert outcome.failed_step == "cancel" and outcome.error_code == "NOT_APPROVED" and fake.requests == []


# 3. Compensations are authorized ----------------------------------------------------------------------------

@pytest.mark.parametrize("compensation_resource", [
    account(owner="bob"),          # a resource the customer has no right to
    account(tenant="t_eu"),        # another tenant's resource
])
def test_a_compensation_the_customer_may_not_perform_is_refused_not_run(stack, compensation_resource):
    session, conversation, case_id = new_case()
    steps = three_steps(compensation_resource=compensation_resource)
    fake = Fake({"/licenses/A-1/deallocate": 500})
    outcome = run(stack, fake, saga(steps, session, conversation, case_id))
    assert outcome.status == "COMPENSATION_FAILED" and outcome.compensated == []
    assert "/subscriptions/A-1/restore" not in fake.paths()
    refused = [r for r in audited(stack, case_id) if r[1] == "compensate"]
    assert refused == [("cancel", "compensate", "failed", "NOT_APPROVED")]  # not retried: deterministic


def test_authorization_lost_between_the_step_and_its_compensation_stops_the_rollback(stack):
    ROLES[("t_us", "sarah")] = ("tenant_admin",)
    session, conversation, case_id = new_case()
    steps = [step("cancel", "billing.cancel_subscription", "billing.restore_subscription",
                  resource=account(owner="bob")),
             step("deallocate", "crm.deallocate_license", "crm.reallocate_license",
                  resource=account(owner="bob"))]
    fake = Fake({"/licenses/A-1/deallocate": 500}, on={"/licenses/A-1/deallocate": ROLES.clear})
    outcome = run(stack, fake, saga(steps, session, conversation, case_id))
    assert outcome.completed == ["cancel"] and outcome.status == "COMPENSATION_FAILED"
    assert "/subscriptions/A-1/restore" not in fake.paths()


# 4. Every tool call is audited ------------------------------------------------------------------------------

def test_invalid_arguments_and_snapshot_failures_are_audited(stack):
    session, conversation, case_id = new_case()
    bad = [step("cancel", "billing.cancel_subscription", "billing.restore_subscription",
                arguments={"account_id": None})]
    run(stack, Fake(), saga(bad, session, conversation, case_id))
    (record,) = parts(stack, Fake())[2].read("t_us", case_id)
    assert (record["outcome"], record["error_code"]) == ("failed", "INVALID_ARGUMENTS")
    assert record["personal"]["invalid_fields"] == ["account_id"] and record["amount_usd"] is None

    session, conversation, case_id = new_case()
    fake = Fake({"/subscriptions/A-1": 500})
    outcome = run(stack, fake, saga(three_steps(), session, conversation, case_id))
    assert outcome.failed_step == "cancel" and "/subscriptions/A-1/cancel" not in fake.paths()
    assert [r[1:] for r in audited(stack, case_id)] == [("snapshot", "failed", "TRANSIENT"),
                                                        ("forward", "failed", "TRANSIENT")]


def test_the_audit_covers_every_kind_of_call_and_keeps_personal_data_sealed(stack):
    session, conversation, case_id = new_case()
    run(stack, Fake({"/licenses/A-1/deallocate": 500}), saga(three_steps(), session, conversation, case_id))
    _, _, audit, keys = parts(stack, Fake())
    records = audit.read("t_us", case_id)
    assert {(r["action"], r["outcome"]) for r in records} == {
        ("snapshot", "ok"), ("forward", "ok"), ("forward", "failed"), ("compensate", "ok")}
    plain = json.dumps([{k: v for k, v in r.items() if k != "personal"} for r in records], default=str)
    assert "sarah@acme.com" not in plain and "A-1" not in plain  # arguments only in the sealed payload
    assert records[0]["personal"]["arguments"] == {"account_id": "A-1"}
    assert audit.read("t_eu", case_id) == []
    for sql in (f"UPDATE tool_audit_records SET outcome = 'ok' WHERE case_id = '{case_id}'",
                f"DELETE FROM tool_audit_records WHERE case_id = '{case_id}'"):
        with pytest.raises(PsqlError, match="append-only"):
            psql(MAIN, sql)
    keys().shred("t_us", "sarah")
    shredded = audit.read("t_us", case_id)
    assert len(shredded) == len(records) and all(r["personal"] is None for r in shredded)
    assert shredded[3]["tool"] == "crm.deallocate_license" and shredded[3]["error_code"] == "TRANSIENT"


# Plan rules -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("steps, problem", [
    ([step("w", "billing.wipe_account", approval_request_id=str(uuid.uuid4())),
      step("c", "billing.cancel_subscription", "billing.restore_subscription")], "must be the last step"),
    ([step("n", "email.send_notice", arguments=NOTICE)], "needs a human approval request"),
    ([step("n", "email.send_notice", arguments=NOTICE, approval_request_id="pending")],
     "not an approval request id"),
    ([step("a", "crm.deallocate_license"),
      step("b", "email.send_notice", arguments=NOTICE, approval_request_id=str(uuid.uuid4()))],
     "must be the last step"),
    ([step("c", "billing.cancel_subscription", "billing.nope")], "not a registered tool"),
    ([step("c", "billing.cancel_subscription", "billing.get_subscription")], "reviewed write tool"),
    ([step("c", "crm.deallocate_license", "crm.reallocate_unreviewed")], "reviewed write tool"),
    ([step("c", "billing.cancel_subscription", "crm.reallocate_license")], "another system"),
    ([step("c", "legacy.do", "legacy.undo")], "without idempotency keys"),
    ([step("c", "billing.cancel_subscription", "billing.wipe_account")], "cannot itself be irreversible"),
    ([step("c", "billing.cancel_subscription", "billing.restore_subscription",
           snapshot_tool_id="billing.restore_subscription")], "unsafe snapshot tool"),
    ([step("c", "unknown.tool")], "not a registered tool"),
])
def test_plans_that_could_not_be_rolled_back_safely_are_refused(steps, problem):
    assert any(problem in p for p in check_plan(REGISTRY, SYSTEMS, steps))


def test_a_good_plan_passes():
    assert check_plan(REGISTRY, SYSTEMS, three_steps()) == []


def test_bad_compensation_arguments_are_refused():
    bad = step("c", "billing.cancel_subscription", "billing.restore_subscription")
    bad.compensation_arguments = {"wrong": "field"}
    assert any("do not fit" in p for p in check_plan(REGISTRY, SYSTEMS, [bad]))
