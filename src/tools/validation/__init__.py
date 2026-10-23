"""Action validation and approval tiers (FR-22 / TA-ADP-03: TA-D5, TA-D6, TA-D7, TA-D14; AC-10).

Every proposed tool call gets a verdict, ALLOW < ASK_USER < ASK_SPECIALIST < DENY, as the stricter of two
gates:

1. static, in code: reads and low-risk writes ALLOW; a financial amount at or above the tenant's threshold
   (default USD 1,000), a high-risk or destructive tool, or any unreviewed tool ASK_SPECIALIST; at or above
   the tenant's senior amount the approver must be a senior specialist. Amounts are the call's financial
   fields (args declared with financial=True), compared as decimals, per call. A case that already had 3
   sub-threshold financial writes in 24 hours and would reach USD 1,500 with this one asks a specialist too
   (threshold splitting).
2. Jev, on the masked turn: allow / ask / deny, plus "does this serve the customer's request?"; below 0.85 it
   counts as ask. Jev can only tighten: its verdict is combined with max(), never min(). Jev down: a write
   asks, a read stays as the static gate says.

execute() runs a call only when the verdict allows it: ALLOW runs; ASK_* needs an Approval for exactly this
call (bound by a hash of tool and arguments) from someone who is not the conversation's handler, a
specialist (senior when required) for ASK_SPECIALIST, the customer for ASK_USER; DENY never runs.
preview() builds the approval card: a dry-run diff when the tool offers one, else the arguments with a fresh
read of the current state.
"""

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import IntEnum

from core.orchestrator.decisions import JevUnavailable, mask
from tools.registry import Risk

DEFAULT_THRESHOLD, DEFAULT_SENIOR = Decimal("1000"), Decimal("5000")
SPLIT_COUNT, SPLIT_TOTAL = 3, Decimal("1500")
SERVES_AT = 0.85
GATE = {
    "verdict": {"type": "choice", "instructions": "Should this proposed tool call go ahead?",
                "criteria": {"ALLOW": "Appropriate as proposed", "ASK": "Needs a confirmation first",
                             "DENY": "Forbidden or clearly wrong here"}},
    "serves": {"type": "noul",
               "instructions": "Does this action directly serve the customer's stated request?"},
}


class Verdict(IntEnum):
    ALLOW = 0
    ASK_USER = 1
    ASK_SPECIALIST = 2
    DENY = 3


class NotApproved(PermissionError):
    pass


@dataclass(frozen=True)
class Limits:
    threshold: Decimal = DEFAULT_THRESHOLD
    senior: Decimal = DEFAULT_SENIOR


@dataclass(frozen=True)
class Approval:
    call_hash: str
    approver_id: str
    role: str  # "customer", "specialist" or "senior_specialist"


@dataclass
class Decision:
    tool_id: str
    verdict: Verdict
    static: Verdict
    jev: Verdict
    reasons: list[str] = field(default_factory=list)
    amount: Decimal = Decimal("0")
    senior: bool = False
    call_hash: str = ""


def limits(conn, tenant_id):
    """The tenant's thresholds from tenant_settings (runtime role, tenant context), else the defaults."""
    with conn.transaction():
        conn.execute("SET LOCAL ROLE app_runtime")
        conn.execute("SELECT set_config('app.current_tenant_id', %s, true)", (tenant_id,))
        row = conn.execute("SELECT approval_threshold_usd, senior_amount_usd FROM tenant_settings").fetchone()
    return Limits(Decimal(row[0]), Decimal(row[1])) if row else Limits()


def call_hash(tool_id, arguments):
    payload = json.dumps({"tool": tool_id, "args": arguments.model_dump(mode="json")}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def financial_amount(arguments):
    """Sum of the absolute values of the call's financial fields; None when one is not a finite number."""
    total = Decimal("0")
    for name, info in type(arguments).model_fields.items():
        if (info.json_schema_extra or {}).get("financial") is True:
            try:
                value = Decimal(str(getattr(arguments, name)))
            except (InvalidOperation, ValueError):
                return None
            if not value.is_finite():
                return None
            total += abs(value)
    return total


def static_gate(tool, arguments, limits, recent=()):
    """Gate 1, code only. recent: amounts of this case's financial writes in the last 24 hours."""
    amount = financial_amount(arguments)
    if amount is None:
        return Verdict.DENY, ["financial amount is not a number"], Decimal("0")
    reasons = []
    if amount >= limits.threshold:
        reasons.append("amount at or above the tenant threshold")
    if tool.risk in (Risk.HIGH_RISK_WRITE, Risk.DESTRUCTIVE_IRREVERSIBLE):
        reasons.append(f"{tool.risk.value} tool")
    if not tool.reviewed_by:
        reasons.append("unreviewed tool")
    sub_threshold = [Decimal(str(a)) for a in recent if Decimal(str(a)) < limits.threshold]
    if amount and len(sub_threshold) >= SPLIT_COUNT and sum(sub_threshold) + amount >= SPLIT_TOTAL:
        reasons.append("many sub-threshold payments on this case (threshold splitting)")
    return (Verdict.ASK_SPECIALIST if reasons else Verdict.ALLOW), reasons, amount


def jev_gate(engine, tool, arguments, masked_state):
    """Gate 2: Jev on the masked turn and the masked proposed call. Its 'ask' goes to the customer for reads
    and low-risk writes, to a specialist otherwise."""
    ask = Verdict.ASK_USER if tool.risk in (Risk.READ_ONLY, Risk.LOW_RISK_WRITE) else Verdict.ASK_SPECIALIST
    proposed = mask(f"{tool.description} with {json.dumps(arguments.model_dump(mode='json'))}")
    try:
        answers = engine.ask({**masked_state, "proposed_action": proposed}, GATE)
    except JevUnavailable:
        return (ask if tool.mutating else Verdict.ALLOW), ["Jev unavailable"]
    verdict = {"ALLOW": Verdict.ALLOW, "ASK": ask, "DENY": Verdict.DENY}[answers["verdict"].value]
    serves = answers["serves"]
    p_serves = serves.confidence if serves.value else 1 - serves.confidence
    reasons = [f"Jev: {answers['verdict'].value.lower()}"]
    if p_serves < SERVES_AT:
        verdict = max(verdict, ask)
        reasons.append("Jev: may not serve the customer's request")
    return verdict, reasons


def validate(tool, arguments, limits, engine, masked_state, recent=()):
    static, static_reasons, amount = static_gate(tool, arguments, limits, recent)
    jev, jev_reasons = jev_gate(engine, tool, arguments, masked_state)
    return Decision(tool.tool_id, max(static, jev), static, jev, static_reasons + jev_reasons, amount,
                    senior=amount >= limits.senior, call_hash=call_hash(tool.tool_id, arguments))


def authorize(decision, approval, handler_id):
    """Raise NotApproved unless this decision may run with this approval (None for no approval)."""
    if decision.verdict is Verdict.ALLOW:
        return
    if decision.verdict is Verdict.DENY:
        raise NotApproved(f"{decision.tool_id}: denied ({'; '.join(decision.reasons)})")
    if approval is None:
        raise NotApproved(f"{decision.tool_id}: needs approval ({'; '.join(decision.reasons)})")
    if approval.call_hash != decision.call_hash:
        raise NotApproved("the approval is for a different call")
    if approval.approver_id == handler_id:
        raise NotApproved("the conversation's handler cannot approve their own action")
    if decision.verdict is Verdict.ASK_SPECIALIST:
        allowed = {"senior_specialist"} if decision.senior else {"specialist", "senior_specialist"}
    else:
        allowed = {"customer", "specialist", "senior_specialist"}
    if approval.role not in allowed:
        raise NotApproved(f"a {approval.role} cannot approve this; it needs one of {sorted(allowed)}")


def execute(tool, arguments, decision, approval, handler_id):
    """Run the tool if the decision and approval allow it; returns its result."""
    if decision.call_hash != call_hash(tool.tool_id, arguments):
        raise NotApproved("the arguments changed after validation")
    authorize(decision, approval, handler_id)
    return tool.func(arguments)


def preview(tool, arguments, decision, dry_run=None, read_current=None):
    """The approval card: before / after from a dry run when the tool has one, else the arguments with a
    fresh read of the current state."""
    card = {"tool_id": tool.tool_id, "call_hash": decision.call_hash, "verdict": decision.verdict.name,
            "reasons": decision.reasons, "arguments": arguments.model_dump(mode="json"),
            "amount": str(decision.amount), "senior_approval": decision.senior}
    if dry_run is not None:
        before, after = dry_run(arguments)
        return {**card, "mode": "dry_run", "before": before, "after": after}
    return {**card, "mode": "current_state", "current": read_current(arguments) if read_current else None}
