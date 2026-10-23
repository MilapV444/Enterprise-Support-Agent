"""M2-05: approval tiers, the stricter-of Jev gate, per-call thresholds, threshold splitting, dry-run previews
and the two-person rule (FR-22, AC-10). Property runs use seeded stdlib randomness (thousands of calls
around the threshold, plus the exact boundary values); Jev is scripted. One test reads tenant_settings from
Postgres."""

import random
import subprocess
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from pydantic import BaseModel

from core.orchestrator.decisions import Answer, DecisionEngine, JevUnavailable, Masked
from data.migrate import migrate, psql
from tools.registry import Registry
from tools.schemas import arg
from tools.validation import (
    Approval,
    Limits,
    NotApproved,
    Verdict,
    call_hash,
    execute,
    limits,
    preview,
    static_gate,
    validate,
)

ROOT = Path(__file__).resolve().parents[3]
STATE = {"message": Masked("Please refund the double charge on INV-9821")}
HANDLER = "agent-session-1"  # whoever is handling the conversation (the agent's on-behalf-of identity)


class RefundArgs(BaseModel):
    invoice_id: str = arg(sensitive=True)
    amount: float = arg(sensitive=True, json_schema_extra={"financial": True})


class LookupArgs(BaseModel):
    invoice_id: str = arg(sensitive=True)


class CommentArgs(BaseModel):
    ticket_id: str = arg(sensitive=True)
    text: str = arg(sensitive=False)


def build():
    registry, ran = Registry(), []

    def runner(name):
        def run(arguments):
            ran.append((name, arguments))
            return {"ok": True}
        return run
    reg = registry.tool
    reg("billing.refund", args=RefundArgs, description="Refund an amount on an invoice",
        risk="low_risk_write",
        stages={"EXECUTING_SOP"}, author="ana", reviewed_by="ben")(runner("billing.refund"))
    reg("billing.get_invoice", args=LookupArgs, description="Read an invoice", risk="read_only",
        stages={"DELIBERATING"}, author="ana", reviewed_by="ben")(runner("billing.get_invoice"))
    reg("tickets.comment", args=CommentArgs, description="Comment on a ticket", risk="low_risk_write",
        stages={"EXECUTING_SOP"}, author="ana")(runner("tickets.comment"))  # never reviewed
    reg("status.peek", args=LookupArgs, description="Read the status page", risk="read_only",
        stages={"DELIBERATING"}, author="cy")(runner("status.peek"))  # never reviewed
    reg("cloud.delete_cluster", args=LookupArgs, description="Delete a cluster for good",
        risk="destructive_irreversible", stages={"EXECUTING_SOP"}, author="ana",
        reviewed_by="ben")(runner("cloud.delete_cluster"))
    return registry.freeze(), ran


class ScriptedJev:
    def __init__(self, verdict="ALLOW", serves=0.97, down=False):
        self.verdict, self.serves, self.down, self.seen = verdict, serves, down, []

    def evaluate(self, state, questions):
        self.seen.append(state)
        if self.down:
            raise JevUnavailable("down")
        return {"verdict": Answer(self.verdict, 0.9), "serves": Answer(self.serves >= 0.5,
                                                                        max(self.serves, 1 - self.serves))}


def engine(**options):
    return DecisionEngine(ScriptedJev(**options))


def refund(amount, invoice="INV-9821"):
    return RefundArgs(invoice_id=invoice, amount=amount)


# Gate 1: static rules in code ------------------------------------------------------------------------------

@pytest.mark.parametrize("amount, verdict", [
    (999.99, Verdict.ALLOW), (1000, Verdict.ASK_SPECIALIST), (1000.00, Verdict.ASK_SPECIALIST),
    (1000.01, Verdict.ASK_SPECIALIST), (0, Verdict.ALLOW), (-1500, Verdict.ASK_SPECIALIST),
    (float("nan"), Verdict.DENY), (float("inf"), Verdict.DENY),
])
def test_the_threshold_is_per_call_and_inclusive(amount, verdict):
    registry, _ = build()
    assert static_gate(registry.tools["billing.refund"], refund(amount), Limits())[0] is verdict


def test_reads_and_reviewed_low_risk_writes_run_automatically_others_ask_a_specialist():
    registry, _ = build()
    tools = registry.tools
    invoice = LookupArgs(invoice_id="INV-1")
    assert static_gate(tools["billing.get_invoice"], invoice, Limits())[0] is Verdict.ALLOW
    assert static_gate(tools["cloud.delete_cluster"], LookupArgs(invoice_id="c"), Limits())[0] is \
        Verdict.ASK_SPECIALIST
    unreviewed = static_gate(tools["tickets.comment"], CommentArgs(ticket_id="T-1", text="hi"), Limits())
    assert unreviewed[0] is Verdict.ASK_SPECIALIST and "unreviewed tool" in unreviewed[1]
    unreviewed_read = static_gate(tools["status.peek"], LookupArgs(invoice_id="x"), Limits())
    assert unreviewed_read[0] is Verdict.ASK_SPECIALIST  # TA-D16: any unreviewed tool, reads included


def test_a_tenant_threshold_moves_the_line():
    registry, _ = build()
    tool = registry.tools["billing.refund"]
    low = Limits(Decimal("250"), Decimal("1000"))
    assert static_gate(tool, refund(400), low)[0] is Verdict.ASK_SPECIALIST
    assert static_gate(tool, refund(4000), Limits(Decimal("5000"), Decimal("9000")))[0] is Verdict.ALLOW


def test_splitting_a_payment_below_the_threshold_still_reaches_a_specialist():
    registry, _ = build()
    tool = registry.tools["billing.refund"]
    assert static_gate(tool, refund(400), Limits(), recent=[400, 400])[0] is Verdict.ALLOW  # 3 payments
    verdict, reasons, _ = static_gate(tool, refund(400), Limits(), recent=[400, 400, 400])  # the 4th, $1,600
    assert verdict is Verdict.ASK_SPECIALIST and "threshold splitting" in reasons[0]
    assert static_gate(tool, refund(10), Limits(), recent=[10, 10, 10])[0] is Verdict.ALLOW  # small total


# Gate 2: Jev, stricter-of ----------------------------------------------------------------------------------

@pytest.mark.parametrize("jev, tool, expected", [
    ({"verdict": "ASK"}, "billing.get_invoice", Verdict.ASK_USER),
    ({"verdict": "DENY"}, "billing.get_invoice", Verdict.DENY),
    ({"verdict": "ALLOW", "serves": 0.6}, "billing.refund", Verdict.ASK_USER),  # off-purpose
    ({"down": True}, "billing.refund", Verdict.ASK_USER),
    ({"down": True}, "billing.get_invoice", Verdict.ALLOW),
    ({"verdict": "ALLOW"}, "cloud.delete_cluster", Verdict.ASK_SPECIALIST),  # Jev cannot loosen
])
def test_jev_can_only_tighten(jev, tool, expected):
    registry, _ = build()
    args = refund(100) if tool == "billing.refund" else LookupArgs(invoice_id="INV-9821")
    assert validate(registry.tools[tool], args, Limits(), engine(**jev), STATE).verdict is expected


def test_jev_sees_the_proposed_call_masked():
    registry, _ = build()
    jev = ScriptedJev()
    validate(registry.tools["billing.refund"], RefundArgs(invoice_id="sarah@acme.com", amount=5),
             Limits(), DecisionEngine(jev), STATE)
    assert "Refund an amount on an invoice" in jev.seen[0]["proposed_action"]
    assert "<EMAIL>" in jev.seen[0]["proposed_action"] and "sarah@" not in str(jev.seen)


# The two-person rule ---------------------------------------------------------------------------------------

def test_an_approved_large_refund_runs_and_an_unapproved_one_does_not():
    registry, ran = build()
    tool, args = registry.tools["billing.refund"], refund(1240)
    decision = validate(tool, args, Limits(), engine(), STATE)
    with pytest.raises(NotApproved, match="needs approval"):
        execute(tool, args, decision, None, HANDLER)
    with pytest.raises(NotApproved, match="handler"):
        execute(tool, args, decision, Approval(decision.call_hash, HANDLER, "specialist"), HANDLER)
    with pytest.raises(NotApproved, match="customer cannot approve"):
        execute(tool, args, decision, Approval(decision.call_hash, "sarah", "customer"), HANDLER)
    with pytest.raises(NotApproved, match="different call"):
        other = Approval(call_hash(tool.tool_id, refund(10)), "sam", "specialist")
        execute(tool, args, decision, other, HANDLER)
    assert ran == []
    execute(tool, args, decision, Approval(decision.call_hash, "sam", "specialist"), HANDLER)
    assert ran == [("billing.refund", args)]


def test_changing_the_arguments_after_approval_is_refused():
    registry, ran = build()
    tool = registry.tools["billing.refund"]
    decision = validate(tool, refund(1240), Limits(), engine(), STATE)
    approval = Approval(decision.call_hash, "sam", "specialist")
    with pytest.raises(NotApproved, match="changed"):
        execute(tool, refund(12400), decision, approval, HANDLER)
    assert ran == []


def test_amounts_at_the_senior_line_need_a_senior_specialist():
    registry, ran = build()
    tool, args = registry.tools["billing.refund"], refund(5000)
    decision = validate(tool, args, Limits(), engine(), STATE)
    assert decision.senior
    with pytest.raises(NotApproved, match="senior_specialist"):
        execute(tool, args, decision, Approval(decision.call_hash, "sam", "specialist"), HANDLER)
    execute(tool, args, decision, Approval(decision.call_hash, "sue", "senior_specialist"), HANDLER)
    assert len(ran) == 1


def test_a_user_confirmation_is_enough_for_an_ask_user_verdict_and_nothing_runs_on_deny():
    registry, ran = build()
    tool, args = registry.tools["billing.refund"], refund(20)
    asked = validate(tool, args, Limits(), engine(verdict="ASK"), STATE)
    assert asked.verdict is Verdict.ASK_USER
    execute(tool, args, asked, Approval(asked.call_hash, "sarah", "customer"), HANDLER)
    denied = validate(tool, args, Limits(), engine(verdict="DENY"), STATE)
    with pytest.raises(NotApproved, match="denied"):
        execute(tool, args, denied, Approval(denied.call_hash, "sue", "senior_specialist"), HANDLER)
    assert len(ran) == 1


ROLES = ["customer", "specialist", "senior_specialist"]
PEOPLE = [HANDLER, "sam", "sue", "sarah"]
JEVS = [{"verdict": "ALLOW"}, {"verdict": "ASK"}, {"verdict": "DENY"}, {"verdict": "ALLOW", "serves": 0.5},
        {"down": True}]


def random_amount(rng, threshold):
    cents = int(threshold * 100)
    return rng.choice([
        (cents + rng.randint(-300, 300)) / 100,          # within three dollars of the line
        rng.randint(0, 10 * max(cents, 100)) / 100,      # anywhere up to ten times it
        threshold, threshold - 0.01, threshold + 0.01,   # the exact boundary
        -rng.randint(0, 2 * max(cents, 100)) / 100,      # negative: a charge back is still money
    ])


def test_property_no_financial_write_at_or_above_the_threshold_runs_without_a_second_person():
    """AC-10: across thousands of calls around random tenant thresholds, with random Jev answers and random
    approvals, every executed refund at or above the threshold had an approval for exactly that call from a
    specialist who is not the conversation's handler."""
    rng = random.Random(20261023)
    registry, ran = build()
    tool = registry.tools["billing.refund"]
    executed_large = 0
    for _ in range(5000):
        threshold = rng.choice([0, 1, 250, 999.99, 1000, 2500.5, 10000])
        lim = Limits(Decimal(str(threshold)), Decimal(str(threshold)) * 5)
        args = refund(random_amount(rng, threshold))
        decision = validate(tool, args, lim, engine(**rng.choice(JEVS)), STATE,
                            recent=[rng.randint(1, 600) for _ in range(rng.randint(0, 5))])
        approval = None
        if rng.random() < 0.8:
            target = decision.call_hash if rng.random() < 0.9 else call_hash(tool.tool_id, refund(1))
            approval = Approval(target, rng.choice(PEOPLE), rng.choice(ROLES))
        before = len(ran)
        try:
            execute(tool, args, decision, approval, HANDLER)
        except NotApproved:
            assert len(ran) == before
            continue
        if Decimal(str(abs(args.amount))) >= lim.threshold:
            executed_large += 1
            assert decision.verdict is Verdict.ASK_SPECIALIST
            assert approval is not None and approval.call_hash == decision.call_hash
            assert approval.approver_id != HANDLER and approval.role in ("specialist", "senior_specialist")
    assert executed_large > 100  # the property was exercised, not vacuous


def test_property_jev_never_loosens_the_static_verdict():
    rng = random.Random(7)
    registry, _ = build()
    for _ in range(3000):
        tool = rng.choice(list(registry.tools.values()))
        args = {"billing.refund": refund(random_amount(rng, 1000)),
                "tickets.comment": CommentArgs(ticket_id="T-1", text="x")}.get(tool.tool_id,
                                                                               LookupArgs(invoice_id="I"))
        decision = validate(tool, args, Limits(), engine(**rng.choice(JEVS)), STATE)
        assert decision.verdict == max(decision.static, decision.jev) >= decision.static


# Approval cards --------------------------------------------------------------------------------------------

def test_the_card_shows_a_dry_run_diff_or_the_current_state():
    registry, _ = build()
    tool, args = registry.tools["billing.refund"], refund(1240)
    decision = validate(tool, args, Limits(), engine(), STATE)
    card = preview(tool, args, decision, dry_run=lambda a: ({"balance": 2480.0}, {"balance": 1240.0}))
    assert card["mode"] == "dry_run" and card["before"] == {"balance": 2480.0} and card["after"] == {
        "balance": 1240.0}
    assert card["verdict"] == "ASK_SPECIALIST" and card["amount"] == "1240.0"
    assert card["call_hash"] == decision.call_hash
    fresh = preview(tool, args, decision, read_current=lambda a: {"invoice": a.invoice_id, "balance": 2480.0})
    assert fresh["mode"] == "current_state" and fresh["current"]["balance"] == 2480.0


# Tenant thresholds from Postgres ---------------------------------------------------------------------------

def test_thresholds_come_from_the_tenants_settings():
    subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env.example",
                    "up", "-d", "--wait", "postgres"], cwd=ROOT, check=True, capture_output=True)
    database = "test_validation"
    psql("postgres", f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
    psql("postgres", f'CREATE DATABASE "{database}"')
    migrate("main", database)
    psql(database, "INSERT INTO tenants (id, name, region) "
                   "VALUES ('t_us', 'Acme', 'US'), ('t_eu', 'G', 'EU');"
                   "INSERT INTO tenant_settings (tenant_id, approval_threshold_usd, senior_amount_usd) "
                   "VALUES ('t_us', 250, 2000)")
    with psycopg.connect(f"postgresql://agent:change-me@127.0.0.1:5432/{database}", autocommit=True) as conn:
        assert limits(conn, "t_us") == Limits(Decimal("250"), Decimal("2000"))
        assert limits(conn, "t_eu") == Limits()  # no settings row: the platform default
