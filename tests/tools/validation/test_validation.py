"""M2-05 (hardened, DECISION-bdad33ce): approval tiers with the stricter-of Jev gate, USD-only thresholds,
approvals bound to their full context, verified approvers checked by Cedar, expiry and single use, final
re-validation before a call runs, a server-side ledger for threshold splitting, tokenized previews and safe
dry runs (FR-22, AC-10). Runs against the compose Postgres; Cedar is real; Jev is scripted."""

import json
import random
import re
import shutil
import subprocess
import threading
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from pydantic import BaseModel

from channels import sessions
from core.orchestrator.decisions import Answer, DecisionEngine, JevUnavailable, Masked
from data.migrate import PsqlError, migrate, psql
from safety.authz.cedar import POLICY_DIR, Authorizer, entity
from safety.pii.tokens import Tokenizer
from tools.registry import Registry
from tools.schemas import arg
from tools.validation import (
    Limits,
    UnsafeDryRun,
    Verdict,
    approvals,
    decide,
    financial_amount,
    preview,
    static_gate,
)
from tools.validation.approvals import (
    ApprovalGate,
    Approver,
    CallContext,
    NotApproved,
    UnverifiedApprover,
    no_staff_identity,
)

ROOT = Path(__file__).resolve().parents[3]
DB = "test_validation"
DSN = f"postgresql://agent:change-me@127.0.0.1:5432/{DB}"  # credentials from .env.example
HANDLER = "agent:t_us"
STATE = {"message": Masked("Please refund the double charge on INV-9821")}
TOKENS = Tokenizer(b"test-validation-token-key")


class RefundArgs(BaseModel):
    invoice_id: str = arg(sensitive=True)
    amount: float = arg(sensitive=True, json_schema_extra={"financial": True})
    currency: str = arg(sensitive=True)
    notify: str = arg(sensitive=True)  # where the confirmation goes: personal data


class NoCurrencyArgs(BaseModel):
    invoice_id: str = arg(sensitive=True)
    amount: float = arg(sensitive=True, json_schema_extra={"financial": True})


class LookupArgs(BaseModel):
    invoice_id: str = arg(sensitive=True)


RAN = []


def build():
    registry = Registry()
    reg = registry.tool

    def record(name):
        def run(arguments):
            RAN.append((name, arguments))
            return {"ok": True}
        return run
    reg("billing.refund", args=RefundArgs, description="Refund an amount on an invoice",
        risk="low_risk_write", stages={"EXECUTING_SOP"}, author="ana", reviewed_by="ben")(record("refund"))
    reg("billing.refund_preview", args=RefundArgs, description="Preview a refund", risk="read_only",
        stages={"EXECUTING_SOP"}, author="ana", reviewed_by="ben")(
        lambda a: ({"balance": 2480.0, "email": "sarah@acme.com"}, {"balance": 2480.0 - a.amount}))
    reg("billing.refund_preview_unreviewed", args=RefundArgs, description="Preview a refund, unreviewed",
        risk="read_only", stages={"EXECUTING_SOP"}, author="ana")(lambda a: ({}, {}))
    reg("billing.void_invoice", args=RefundArgs, description="Void an invoice", risk="low_risk_write",
        stages={"EXECUTING_SOP"}, author="ana", reviewed_by="ben")(record("void"))
    reg("billing.get_invoice", args=LookupArgs, description="Read an invoice", risk="read_only",
        stages={"DELIBERATING"}, author="ana", reviewed_by="ben")(record("get_invoice"))
    reg("crm.refund_preview", args=RefundArgs, description="Preview elsewhere", risk="read_only",
        stages={"EXECUTING_SOP"}, author="ana", reviewed_by="ben")(lambda a: ({}, {}))
    reg("billing.legacy_refund", args=NoCurrencyArgs, description="Refund without a currency",
        risk="low_risk_write", stages={"EXECUTING_SOP"}, author="ana", reviewed_by="ben")(record("legacy"))
    reg("status.peek", args=LookupArgs, description="Read the status page", risk="read_only",
        stages={"DELIBERATING"}, author="cy")(record("peek"))
    reg("cloud.delete_cluster", args=LookupArgs, description="Delete a cluster for good",
        risk="destructive_irreversible", stages={"EXECUTING_SOP"}, author="ana", reviewed_by="ben")(
        record("delete"))
    return registry.freeze()


REGISTRY = build()
REFUND = REGISTRY.tools["billing.refund"]


def refund(amount, currency="USD", invoice="INV-9821", notify="sarah@acme.com"):
    return RefundArgs(invoice_id=invoice, amount=amount, currency=currency, notify=notify)


class ScriptedJev:
    def __init__(self, verdict="ALLOW", serves=0.97, down=False):
        self.verdict, self.serves, self.down, self.seen = verdict, serves, down, []

    def evaluate(self, state, questions):
        self.seen.append(state)
        if self.down:
            raise JevUnavailable("down")
        return {"verdict": Answer(self.verdict, 0.9),
                "serves": Answer(self.serves >= 0.5, max(self.serves, 1 - self.serves))}


def engine(**options):
    return DecisionEngine(ScriptedJev(**options))


# Postgres, the production Cedar policies, and a stand-in staff identity -----------------------------------

APPROVE_RULE = re.compile(r'permit \(principal in Role::"(?:senior_)?specialist", action == '
                          r'Action::"approve_action".*?\};', re.DOTALL)


@pytest.fixture(scope="module")
def policy_dir():
    """The production policies (policies/), approve_action included since M2-09a."""
    return Path(POLICY_DIR)


@pytest.fixture(scope="module")
def no_approve_rule(tmp_path_factory):
    """The production policies with the approve_action permits taken out."""
    folder = tmp_path_factory.mktemp("policies")
    text = (Path(POLICY_DIR) / "support.cedar").read_text(encoding="utf-8")
    stripped, removed = APPROVE_RULE.subn("", text)
    assert removed == 2
    (folder / "support.cedar").write_text(stripped, encoding="utf-8")
    shutil.copy(Path(POLICY_DIR) / "support.cedarschema.json", folder / "support.cedarschema.json")
    return folder


# credential -> who it verifiably is: stands in for the staff identity provider M2-09 adds
DIRECTORY = {
    "tok-sam": Approver("t_us", "sam", frozenset({"specialist"})),
    "tok-sue": Approver("t_us", "sue", frozenset({"senior_specialist"})),
    "tok-eve": Approver("t_eu", "eve", frozenset({"senior_specialist"})),
    "tok-handler": Approver("t_us", HANDLER, frozenset({"specialist"})),
    "tok-sarah": Approver("t_us", "sarah", frozenset({"customer"})),
    "tok-bob": Approver("t_us", "bob", frozenset({"customer"})),
    "tok-sarah-as-specialist": Approver("t_us", "sarah", frozenset({"specialist"})),
}


def verify(credential):
    if credential not in DIRECTORY:
        raise UnverifiedApprover("unknown credential")
    return DIRECTORY[credential]


@pytest.fixture(scope="module")
def database():
    subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env.example",
                    "up", "-d", "--wait", "postgres"], cwd=ROOT, check=True, capture_output=True)
    psql("postgres", f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
    psql("postgres", f'CREATE DATABASE "{DB}"')
    migrate("main", DB)
    sessions.apply_schema(DB)
    approvals.apply_schema(DB)
    psql(DB, "INSERT INTO tenants (id, name, region) VALUES ('t_us', 'Acme', 'US'), ('t_eu', 'Globex', 'EU');"
             "INSERT INTO tenant_settings (tenant_id) VALUES ('t_us'), ('t_eu')")


def connect():
    return psycopg.connect(DSN, autocommit=True)


@pytest.fixture
def gate(database, policy_dir):
    return ApprovalGate(connect, engine(), Authorizer(policy_dir=policy_dir), verify)


def account(tenant="t_us", owner="sarah"):
    return {"action": "update_contact", "type": "Account", "id": "A-1",
            "attrs": {"tenant_id": tenant, "owner": entity("User", owner)}}


def case(principal="sarah", tenant="t_us"):
    """A live conversation on its own open case, as the session layer creates them."""
    with connect() as conn:
        session = sessions.start(conn, tenant, principal, "T2_SSO")
        conversation = f"conv-{uuid.uuid4().hex[:8]}"
        sessions.open_conversation(conn, tenant, principal, session, conversation)
        case_id = sessions.link_case(conn, tenant, conversation)
    return CallContext(tenant, case_id, conversation, principal, f"agent:{tenant}", resource=account(tenant,
                                                                                                    principal))


def approved(gate, ctx, args, credential="tok-sam", tool=REFUND):
    decision = gate.validate(ctx, tool, args, STATE)
    request_id = gate.request(ctx, tool, args, decision)
    gate.grant(ctx.tenant_id, request_id, credential)
    return decision, request_id


# Gate 1 and Jev (pure) -------------------------------------------------------------------------------------

@pytest.mark.parametrize("amount, verdict", [
    (999.99, Verdict.ALLOW), (1000, Verdict.ASK_SPECIALIST), (1000.00, Verdict.ASK_SPECIALIST),
    (1000.01, Verdict.ASK_SPECIALIST), (0, Verdict.ALLOW), (-1500, Verdict.ASK_SPECIALIST),
    (float("nan"), Verdict.DENY), (float("inf"), Verdict.DENY),
])
def test_the_threshold_is_per_call_and_inclusive(amount, verdict):
    assert static_gate(REFUND, refund(amount), Limits())[0] is verdict


@pytest.mark.parametrize("currency", ["EUR", "INR", "JPY", "usd", "US$", "", "XXX"])
def test_anything_but_usd_is_denied_because_thresholds_are_in_usd(currency):
    verdict, reasons, _ = static_gate(REFUND, refund(10, currency=currency), Limits())
    assert verdict is Verdict.DENY and "USD" in reasons[0]


def test_a_financial_tool_without_a_currency_field_is_denied():
    args = NoCurrencyArgs(invoice_id="INV-1", amount=5)
    assert financial_amount(args)[1] and static_gate(REGISTRY.tools["billing.legacy_refund"], args,
                                                     Limits())[0] is Verdict.DENY


def test_reads_reviewed_writes_and_unreviewed_or_destructive_tools():
    tools = REGISTRY.tools
    assert static_gate(tools["billing.get_invoice"], LookupArgs(invoice_id="I"), Limits())[0] is Verdict.ALLOW
    unreviewed = static_gate(tools["status.peek"], LookupArgs(invoice_id="I"), Limits())
    assert unreviewed[0] is Verdict.ASK_SPECIALIST
    assert static_gate(tools["cloud.delete_cluster"], LookupArgs(invoice_id="c"), Limits())[0] is \
        Verdict.ASK_SPECIALIST


@pytest.mark.parametrize("jev, tool, expected", [
    ({"verdict": "ASK"}, "billing.get_invoice", Verdict.ASK_USER),
    ({"verdict": "DENY"}, "billing.get_invoice", Verdict.DENY),
    ({"verdict": "ALLOW", "serves": 0.6}, "billing.refund", Verdict.ASK_USER),
    ({"down": True}, "billing.refund", Verdict.ASK_USER),
    ({"down": True}, "billing.get_invoice", Verdict.ALLOW),
    ({"verdict": "ALLOW"}, "cloud.delete_cluster", Verdict.ASK_SPECIALIST),
])
def test_jev_can_only_tighten(jev, tool, expected):
    args = refund(100) if tool == "billing.refund" else LookupArgs(invoice_id="INV-9821")
    assert decide(REGISTRY.tools[tool], args, Limits(), engine(**jev), STATE).verdict is expected


def test_property_jev_never_loosens_the_static_verdict():
    rng = random.Random(7)
    jevs = [{"verdict": "ALLOW"}, {"verdict": "ASK"}, {"verdict": "DENY"}, {"serves": 0.5}, {"down": True}]
    tools = [REGISTRY.tools[t] for t in ("billing.refund", "billing.get_invoice", "status.peek",
                                         "cloud.delete_cluster")]
    for _ in range(2000):
        tool = rng.choice(tools)
        args = refund(rng.uniform(-3000, 3000)) if tool is REFUND else LookupArgs(invoice_id="I")
        decision = decide(tool, args, Limits(), engine(**rng.choice(jevs)), STATE)
        assert decision.verdict == max(decision.static, decision.jev) >= decision.static


# 1. Approvals bound to their full context ------------------------------------------------------------------

def test_an_approved_large_refund_runs_once_and_is_recorded(gate):
    ctx = case()
    RAN.clear()
    decision, request_id = approved(gate, ctx, refund(1240))
    assert decision.level == "specialist"
    gate.execute(ctx, REFUND, refund(1240), STATE, request_id)
    assert len(RAN) == 1
    assert psql(DB, f"SELECT status, approver_id FROM approval_requests WHERE id = '{request_id}'") == [
        ["consumed", "sam"]]
    ledger = psql(DB, f"SELECT amount_usd FROM financial_writes WHERE case_id = '{ctx.case_id}'")
    assert ledger == [["1240.00"]]


def test_an_approval_cannot_be_replayed_in_another_tenant(gate):
    us, eu = case(), case(tenant="t_eu")
    _, request_id = approved(gate, us, refund(1240))
    with pytest.raises(NotApproved, match="no such approval request in this tenant"):
        gate.execute(eu, REFUND, refund(1240), STATE, request_id)


def test_an_approval_cannot_be_replayed_in_another_case_or_conversation(gate):
    first, second = case(), case()
    _, request_id = approved(gate, first, refund(1240))
    with pytest.raises(NotApproved, match="different call, context"):
        gate.execute(second, REFUND, refund(1240), STATE, request_id)
    moved = CallContext(first.tenant_id, first.case_id, second.conversation_id, "sarah", first.handler_id,
                        resource=first.resource)
    with pytest.raises(NotApproved):
        gate.execute(moved, REFUND, refund(1240), STATE, request_id)


def test_an_approval_does_not_cover_other_arguments_or_another_tool(gate):
    ctx = case()
    _, request_id = approved(gate, ctx, refund(1240))
    with pytest.raises(NotApproved, match="different call"):
        gate.execute(ctx, REFUND, refund(1240, notify="mallory@evil.test"), STATE, request_id)
    with pytest.raises(NotApproved, match="different call"):
        gate.execute(ctx, REGISTRY.tools["billing.void_invoice"], refund(1240), STATE, request_id)


# 2. Verified approvers only --------------------------------------------------------------------------------

@pytest.mark.parametrize("credential, error, match", [
    ("forged-token", UnverifiedApprover, "unknown"),
    ("tok-eve", NotApproved, "another tenant"),
    ("tok-handler", NotApproved, "handler"),
    ("tok-sarah", NotApproved, "needs one of"),             # the customer cannot approve their own refund
    ("tok-sarah-as-specialist", NotApproved, "needs one of"),  # nor as a "specialist" on their own case
])
def test_forged_foreign_or_conflicted_approvers_are_refused(gate, credential, error, match):
    ctx = case()
    decision = gate.validate(ctx, REFUND, refund(1240), STATE)
    request_id = gate.request(ctx, REFUND, refund(1240), decision)
    with pytest.raises(error, match=match):
        gate.grant("t_us", request_id, credential)
    with pytest.raises(NotApproved, match="pending"):
        gate.execute(ctx, REFUND, refund(1240), STATE, request_id)


def test_a_senior_amount_needs_a_senior_specialist(gate):
    ctx = case()
    decision = gate.validate(ctx, REFUND, refund(5000), STATE)
    request_id = gate.request(ctx, REFUND, refund(5000), decision)
    assert decision.level == "senior_specialist"
    with pytest.raises(NotApproved, match="senior_specialist"):
        gate.grant("t_us", request_id, "tok-sam")
    gate.grant("t_us", request_id, "tok-sue")
    gate.execute(ctx, REFUND, refund(5000), STATE, request_id)


def test_without_an_approve_rule_in_cedar_nobody_can_approve(database, no_approve_rule):
    """Fail closed: take the approve_action permits out of the policies and every specialist grant fails."""
    strict = ApprovalGate(connect, engine(), Authorizer(policy_dir=no_approve_rule), verify)
    ctx = case()
    decision = strict.validate(ctx, REFUND, refund(1240), STATE)
    request_id = strict.request(ctx, REFUND, refund(1240), decision)
    with pytest.raises(NotApproved, match="authorization policy"):
        strict.grant("t_us", request_id, "tok-sue")


def test_the_production_policies_let_a_senior_specialist_approve_a_specialist_level_request(gate):
    ctx = case()
    decision = gate.validate(ctx, REFUND, refund(1240), STATE)
    assert decision.level == "specialist"
    request_id = gate.request(ctx, REFUND, refund(1240), decision)
    gate.grant("t_us", request_id, "tok-sue")
    gate.execute(ctx, REFUND, refund(1240), STATE, request_id)


# Approval lifetimes (M2-09a) -------------------------------------------------------------------------------

def expires_in(request_id):
    (seconds,) = psql(DB, "SELECT extract(epoch FROM expires_at - created_at)::int FROM approval_requests "
                          f"WHERE id = '{request_id}'")[0]
    return int(seconds)


def test_a_request_lives_for_the_gates_lifetime_or_the_one_it_asks_for(database, policy_dir):
    ctx = case()
    short = ApprovalGate(connect, engine(), Authorizer(policy_dir=policy_dir), verify)
    decision = short.validate(ctx, REFUND, refund(1240), STATE)
    assert expires_in(short.request(ctx, REFUND, refund(1240), decision)) == 30 * 60
    long = short.request(ctx, REFUND, refund(1240), decision, ttl=timedelta(hours=72))
    assert expires_in(long) == 72 * 3600
    queue = ApprovalGate(connect, engine(), Authorizer(policy_dir=policy_dir), verify, ttl=timedelta(hours=1))
    assert expires_in(queue.request(ctx, REFUND, refund(1240), decision)) == 3600


@pytest.mark.parametrize("ttl", [timedelta(hours=72, seconds=1), timedelta(0), timedelta(seconds=-5),
                                 "1 hour", 3600])
def test_a_lifetime_is_positive_and_at_most_three_days(database, policy_dir, ttl):
    with pytest.raises(ValueError):
        ApprovalGate(connect, engine(), Authorizer(policy_dir=policy_dir), verify, ttl=ttl)
    gate = ApprovalGate(connect, engine(), Authorizer(policy_dir=policy_dir), verify)
    ctx = case()
    decision = gate.validate(ctx, REFUND, refund(1240), STATE)
    with pytest.raises(ValueError):
        gate.request(ctx, REFUND, refund(1240), decision, ttl=ttl)


@pytest.mark.parametrize("request_id", ["pending", "", "1; DROP TABLE approval_requests", "12345"])
def test_a_malformed_request_id_is_refused_cleanly(gate, request_id):
    ctx = case()
    with pytest.raises(NotApproved, match="not an approval request id"):
        gate.grant("t_us", request_id, "tok-sam")
    with pytest.raises(NotApproved, match="not an approval request id"):
        gate.revoke("t_us", request_id)
    with pytest.raises(NotApproved, match="not an approval request id"):
        gate.execute(ctx, REFUND, refund(1240), STATE, request_id)


def test_without_a_staff_identity_provider_nothing_verifies(database, policy_dir):
    default = ApprovalGate(connect, engine(), Authorizer(policy_dir=policy_dir))
    assert default.verify_approver is no_staff_identity
    ctx = case()
    decision = default.validate(ctx, REFUND, refund(1240), STATE)
    request_id = default.request(ctx, REFUND, refund(1240), decision)
    with pytest.raises(UnverifiedApprover):
        default.grant("t_us", request_id, "tok-sue")


def test_a_customer_confirmation_comes_from_that_customer_only(database, policy_dir):
    asking = ApprovalGate(connect, engine(verdict="ASK"), Authorizer(policy_dir=policy_dir), verify)
    ctx = case()
    decision = asking.validate(ctx, REFUND, refund(20), STATE)
    request_id = asking.request(ctx, REFUND, refund(20), decision)
    assert decision.level == "customer"
    with pytest.raises(NotApproved, match="only the customer"):
        asking.grant("t_us", request_id, "tok-bob")
    asking.grant("t_us", request_id, "tok-sarah")
    asking.execute(ctx, REFUND, refund(20), STATE, request_id)


def test_execute_takes_no_approval_object_only_a_stored_request(gate):
    ctx = case()
    with pytest.raises(NotApproved, match="needs specialist approval"):
        gate.execute(ctx, REFUND, refund(1240), STATE)
    with pytest.raises(NotApproved, match="no such approval request"):
        gate.execute(ctx, REFUND, refund(1240), STATE, str(uuid.uuid4()))


# 3. Expiry and single use ----------------------------------------------------------------------------------

def test_an_expired_request_can_be_neither_granted_nor_used(gate):
    ctx = case()
    decision = gate.validate(ctx, REFUND, refund(1240), STATE)
    stale = gate.request(ctx, REFUND, refund(1240), decision)
    psql(DB, f"UPDATE approval_requests SET expires_at = now() - interval '1 second' WHERE id = '{stale}'")
    with pytest.raises(NotApproved, match="expired"):
        gate.grant("t_us", stale, "tok-sam")
    _, granted = approved(gate, ctx, refund(1240))
    psql(DB, f"UPDATE approval_requests SET expires_at = now() - interval '1 second' WHERE id = '{granted}'")
    with pytest.raises(NotApproved, match="expired"):
        gate.execute(ctx, REFUND, refund(1240), STATE, granted)


def test_a_used_or_revoked_approval_does_not_work_again(gate):
    ctx = case()
    _, request_id = approved(gate, ctx, refund(1240))
    gate.execute(ctx, REFUND, refund(1240), STATE, request_id)
    with pytest.raises(NotApproved, match="consumed"):
        gate.execute(ctx, REFUND, refund(1240), STATE, request_id)
    _, revoked = approved(gate, ctx, refund(1240))
    assert gate.revoke("t_us", revoked)
    with pytest.raises(NotApproved, match="revoked"):
        gate.execute(ctx, REFUND, refund(1240), STATE, revoked)
    with pytest.raises(NotApproved, match="pending|revoked"):
        gate.grant("t_us", revoked, "tok-sue")


def test_two_concurrent_uses_of_one_approval_run_once(gate):
    ctx = case()
    _, request_id = approved(gate, ctx, refund(1240))
    RAN.clear()
    outcomes, start = [], threading.Barrier(4)

    def attempt():
        start.wait()
        try:
            gate.execute(ctx, REFUND, refund(1240), STATE, request_id)
            outcomes.append("ran")
        except NotApproved:
            outcomes.append("refused")
    threads = [threading.Thread(target=attempt) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["ran", "refused", "refused", "refused"] and len(RAN) == 1


# 4. Final re-validation before execution -------------------------------------------------------------------

def test_a_policy_change_after_approval_voids_it(gate):
    ctx = case()
    _, request_id = approved(gate, ctx, refund(1240))
    psql(DB, "UPDATE tenant_settings SET approval_threshold_usd = 1200, version = version + 1 "
             "WHERE tenant_id = 't_us'")
    try:
        with pytest.raises(NotApproved, match="policy"):
            gate.execute(ctx, REFUND, refund(1240), STATE, request_id)
    finally:
        psql(DB, "UPDATE tenant_settings SET approval_threshold_usd = 1000, version = version + 1 "
                 "WHERE tenant_id = 't_us'")


def test_a_lost_permission_closed_case_or_reassigned_conversation_stops_the_call(gate, policy_dir):
    ctx = case()
    _, request_id = approved(gate, ctx, refund(1240))
    foreign = CallContext(ctx.tenant_id, ctx.case_id, ctx.conversation_id, ctx.principal_id, ctx.handler_id,
                          resource=account(owner="bob"))  # the target account is no longer the customer's
    with pytest.raises(NotApproved, match="authorization policy refuses"):
        gate.execute(foreign, REFUND, refund(1240), STATE, request_id)
    no_target = CallContext(ctx.tenant_id, ctx.case_id, ctx.conversation_id, ctx.principal_id, ctx.handler_id)
    with pytest.raises(NotApproved, match="target resource"):
        gate.execute(no_target, REFUND, refund(1240), STATE, request_id)
    psql(DB, f"UPDATE conversations SET principal_id = 'bob' WHERE id = '{ctx.conversation_id}'")
    with pytest.raises(NotApproved, match="does not belong"):
        gate.execute(ctx, REFUND, refund(1240), STATE, request_id)
    psql(DB, f"UPDATE conversations SET principal_id = 'sarah' WHERE id = '{ctx.conversation_id}'")
    psql(DB, f"UPDATE cases SET status = 'resolved' WHERE id = '{ctx.case_id}'")
    with pytest.raises(NotApproved, match="not open"):
        gate.execute(ctx, REFUND, refund(1240), STATE, request_id)
    assert psql(DB, f"SELECT status FROM approval_requests WHERE id = '{request_id}'") == [["approved"]]


def test_a_stricter_verdict_at_execution_needs_the_stricter_approval(gate):
    """Small refund approved under no history; by execution time the case has three others: it now needs a
    specialist, and a customer confirmation granted earlier no longer covers it."""
    asking = ApprovalGate(connect, engine(verdict="ASK"), gate.authorizer, verify)
    ctx = case()
    decision = asking.validate(ctx, REFUND, refund(400), STATE)
    request_id = asking.request(ctx, REFUND, refund(400), decision)
    asking.grant("t_us", request_id, "tok-sarah")
    for _ in range(3):
        gate.execute(ctx, REFUND, refund(400, invoice=f"INV-{uuid.uuid4().hex[:4]}"), STATE)
    with pytest.raises(NotApproved, match="different call, context, policy or level"):
        asking.execute(ctx, REFUND, refund(400), STATE, request_id)


# 5. Threshold splitting from the server-side ledger --------------------------------------------------------

def test_splitting_is_detected_from_the_ledger_not_from_the_caller(gate):
    ctx = case()
    for _ in range(3):
        gate.execute(ctx, REFUND, refund(400), STATE)
    decision = gate.validate(ctx, REFUND, refund(400), STATE)
    assert decision.verdict is Verdict.ASK_SPECIALIST and "threshold splitting" in " ".join(decision.reasons)
    other = case()
    assert gate.validate(other, REFUND, refund(400), STATE).verdict is Verdict.ALLOW  # another case


def test_old_foreign_and_unrelated_ledger_rows_do_not_count(gate):
    ctx = case()
    psql(DB, "INSERT INTO financial_writes (tenant_id, case_id, tool_id, decision_id, amount_usd, "
             f"executed_at) SELECT 't_us', '{ctx.case_id}', 'billing.refund', gen_random_uuid(), 500, "
             "now() - interval '25 hours' FROM generate_series(1, 3)")
    eu = case(tenant="t_eu")
    psql(DB, "INSERT INTO financial_writes (tenant_id, case_id, tool_id, decision_id, amount_usd) "
             f"SELECT 't_eu', '{eu.case_id}', 'billing.refund', gen_random_uuid(), 500 "
             "FROM generate_series(1, 3)")
    assert gate.validate(ctx, REFUND, refund(400), STATE).verdict is Verdict.ALLOW
    assert gate.validate(eu, REFUND, refund(400), STATE).verdict is Verdict.ASK_SPECIALIST


def test_the_ledger_cannot_be_forged_rewritten_or_emptied(gate):
    ctx = case()
    gate.execute(ctx, REFUND, refund(400), STATE)
    with connect() as conn, pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
        conn.execute("SET LOCAL ROLE app_runtime")
        conn.execute("SELECT set_config('app.current_tenant_id', 't_us', true)")
        conn.execute("INSERT INTO financial_writes (tenant_id, case_id, tool_id, decision_id, amount_usd) "
                     "VALUES ('t_eu', 'x', 'billing.refund', gen_random_uuid(), 1)")
    for sql in ("UPDATE financial_writes SET amount_usd = 0", "DELETE FROM financial_writes",
                "TRUNCATE financial_writes"):
        with pytest.raises(PsqlError, match="append-only"):
            psql(DB, sql)


# 6, 7, 8. Currency at execution, previews and dry runs -----------------------------------------------------

def test_a_non_usd_call_never_runs(gate):
    RAN.clear()
    with pytest.raises(NotApproved, match="USD"):
        gate.execute(case(), REFUND, refund(10, currency="EUR"), STATE)
    assert RAN == []


def test_previews_tokenize_personal_data_and_show_the_usd_amount(gate):
    ctx = case()
    decision = gate.validate(ctx, REFUND, refund(1240), STATE)
    card = preview(REGISTRY, REFUND, refund(1240), decision, TOKENS,
                   read_current=lambda a: {"invoice": a.invoice_id, "owner": "Sarah Lee <sarah@acme.com>"})
    text = json.dumps(card)
    assert "sarah@acme.com" not in text and "<EMAIL_" in text
    assert card["amount_usd"] == "1240.0" and card["arguments"]["invoice_id"] == "INV-9821"
    assert card["approval_level"] == "specialist" and card["current"]["invoice"] == "INV-9821"


def test_a_dry_run_is_a_reviewed_read_only_tool_and_its_output_is_tokenized(gate):
    decision = gate.validate(case(), REFUND, refund(1240), STATE)
    card = preview(REGISTRY, REFUND, refund(1240), decision, TOKENS, dry_run_id="billing.refund_preview")
    assert card["mode"] == "dry_run" and card["after"] == {"balance": 1240.0}
    assert "sarah@acme.com" not in json.dumps(card)


@pytest.mark.parametrize("dry_run_id, match", [
    ("billing.nonexistent", "not a registered tool"),
    ("billing.void_invoice", "must be read_only"),
    ("billing.refund", "must be read_only"),               # the action itself as its own "dry run"
    ("billing.refund_preview_unreviewed", "not been reviewed"),
    ("billing.get_invoice", "does not take"),
    ("crm.refund_preview", "another system"),
])
def test_unsafe_dry_runs_are_refused_before_anything_runs(gate, dry_run_id, match):
    RAN.clear()
    decision = gate.validate(case(), REFUND, refund(1240), STATE)
    with pytest.raises(UnsafeDryRun, match=match):
        preview(REGISTRY, REFUND, refund(1240), decision, TOKENS, dry_run_id=dry_run_id)
    assert RAN == []


# AC-10 as a property ---------------------------------------------------------------------------------------

def test_property_no_financial_write_at_or_above_the_threshold_runs_without_a_second_person(gate):
    """Random amounts around the threshold, random (including forged, foreign and conflicted) approvers and
    random replays into other cases: every refund at or above USD 1,000 that ran had its own approval,
    consumed once, from a verified specialist of the tenant who is neither the handler nor the customer."""
    rng = random.Random(20261024)
    contexts = [case() for _ in range(6)]
    credentials = [*DIRECTORY, "forged-token"]
    executed_large = 0
    for _ in range(250):
        ctx = rng.choice(contexts)
        amount = rng.choice([999.99, 1000, 1000.01, rng.uniform(900, 1100), rng.uniform(0, 6000),
                             -rng.uniform(0, 3000)])
        args = refund(round(amount, 2))
        decision = gate.validate(ctx, REFUND, args, STATE)
        request_id = None
        if decision.level is not None and rng.random() < 0.85:
            request_id = gate.request(ctx, REFUND, args, decision)
            try:
                gate.grant(ctx.tenant_id, request_id, rng.choice(credentials))
            except (NotApproved, UnverifiedApprover):
                pass
        run_ctx = rng.choice(contexts) if rng.random() < 0.15 else ctx  # replay into another case
        try:
            gate.execute(run_ctx, REFUND, args, STATE, request_id)
        except NotApproved:
            continue
        if Decimal(str(abs(args.amount))) >= Decimal("1000"):
            executed_large += 1
            status, approver, roles = psql(DB, "SELECT status, approver_id, "
                                               "array_to_string(approver_roles, ',') FROM approval_requests "
                                               f"WHERE id = '{request_id}'")[0]
            assert status == "consumed" and run_ctx == ctx
            assert approver not in (HANDLER, ctx.principal_id)
            assert DIRECTORY[{"sam": "tok-sam", "sue": "tok-sue"}[approver]].tenant_id == ctx.tenant_id
            assert set(roles.split(",")) & {"specialist", "senior_specialist"}
    assert executed_large > 10  # the property was exercised, not vacuous
