"""TK-02: support_desk.raise_ticket through the real executor, identity and audit log (FR-45, FR-20 .. FR-24;
DECISION-368069f5): it opens only the signed-in customer's own proposal, from tier T1, once, audited, and no
model or specialist is ever offered it."""

import subprocess
from pathlib import Path

import psycopg
import pytest
from pydantic import ValidationError

from channels import sessions
from channels.identity.service import Identity
from data.migrate import migrate, psql
from hitl import tickets
from hitl.tickets import Tickets
from safety.screening.pipeline import Screener
from safety.screening.scorers import pattern_injection
from tools import audit as audit_module
from tools import desk
from tools.audit import AuditLog
from tools.execution import Executor, ToolFailure
from tools.execution.calls import ToolCall
from tools.registry import Registry, Risk
from tools.schemas import personal_arguments

ROOT = Path(__file__).resolve().parents[3]
DB = "test_desk"
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
    for module in (sessions, audit_module, tickets):
        module.apply_schema(DB)
    psql(DB, "INSERT INTO tenants (id, name, region) VALUES ('t_us', 'Acme', 'US'), ('t_eu', 'G', 'EU');")
    identity = Identity(connect)
    return identity, desk.register(Registry(), connect, identity).freeze()


def propose(principal="sarah", tenant="t_us", key="k"):
    return Tickets(connect).propose(tenant, principal, f"c-{principal}-{key}", key, category="refund",
                                    subject="Duplicate charge on INV-1001", queue="queue_billing",
                                    reason="refund request", invoice_id="INV-1001", amount_cents=50000,
                                    currency="USD")


def raise_ticket(stack, proposal, principal="sarah", tier="T1_VERIFIED", tenant="t_us", call_id="call-1"):
    """One call through the executor on a fresh live session -> (result or ToolFailure, the call's audit)."""
    identity, registry = stack
    audit_log = AuditLog(connect, lambda: None)
    executor = Executor(registry, desk.SYSTEMS, Screener(lambda text: (0.0, []), pattern_injection),
                        identity=identity, audit=audit_log)
    with connect() as conn:
        session = sessions.start(conn, tenant, principal, tier)
    case_id = f"case-{session}"
    try:
        outcome = executor.run(ToolCall(tool_call_id=call_id, tool_id=desk.RAISE,
                                        arguments={"proposal": proposal}, tenant_id=tenant,
                                        principal_id=principal, case_id=case_id, checkpoint_id="cp-1",
                                        session_id=session))
    except ToolFailure as failure:
        outcome = failure
    return outcome, audit_log.read(tenant, case_id)


def test_the_tool_is_a_low_risk_write_from_tier_one_that_nothing_offers(stack):
    tool = stack[1].tools[desk.RAISE]
    assert (tool.risk, tool.min_tier.name, tool.stages) == (Risk.LOW_RISK_WRITE, "T1_VERIFIED",
                                                           frozenset({desk.CUSTOMER_ACTION}))
    for stage in ("TRIAGED", "DELIBERATING", "EXECUTING_SOP", "ESCALATED_HITL"):
        assert stack[1].permitted("T2_SSO", (), stage) == []


def test_a_signed_in_customer_raises_their_proposal_once_and_it_is_audited(stack):
    proposal = propose(key="once")
    result, audit = raise_ticket(stack, proposal.number)
    assert result.data["ticket"]["ticket_id"] == proposal.number and result.data["ticket"]["status"] == "open"
    again, _ = raise_ticket(stack, proposal.number, call_id="call-2")           # a retry or a second click
    assert again.data == result.data
    assert [(a["tool"], a["outcome"], a["risk_class"]) for a in audit] == [
        (desk.RAISE, "ok", "low_risk_write")]
    assert [t.number for t in Tickets(connect).list_for("t_us", "sarah")].count(proposal.number) == 1


@pytest.mark.parametrize("who, code", [({"principal": "bob"}, "REJECTED"),
                                       ({"tenant": "t_eu"}, "REJECTED"),
                                       ({"tier": "T0_ANON"}, "STEP_UP_REQUIRED")])
def test_only_the_customer_who_owns_the_proposal_can_raise_it_and_not_as_a_guest(stack, who, code):
    proposal = propose(key=f"other-{code}-{len(who)}-{next(iter(who.values()))}")
    result, audit = raise_ticket(stack, proposal.number, **who)
    assert isinstance(result, ToolFailure) and result.code == code
    assert Tickets(connect).get("t_us", "sarah", proposal.id).status == "proposed"
    assert [a["outcome"] for a in audit] == ["failed"]


def test_an_argument_that_is_not_a_ticket_number_is_refused_before_anything_runs(stack):
    before = psql(DB, "SELECT count(*) FROM support_tickets WHERE status = 'open'")
    with pytest.raises(ValidationError):
        raise_ticket(stack, "INV-1001; DROP TABLE support_tickets")
    assert psql(DB, "SELECT count(*) FROM support_tickets WHERE status = 'open'") == before


def test_the_audit_record_seals_personal_arguments_but_not_an_issued_ticket_number(stack):
    assert personal_arguments(desk.RaiseTicket, {"proposal": "TKT-00001"}) is None
    proposal = propose(key="audit")
    _, audit = raise_ticket(stack, proposal.number)
    assert audit[0]["outcome"] == "ok" and audit[0]["personal"] is None   # nothing personal to seal
