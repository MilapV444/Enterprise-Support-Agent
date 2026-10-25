"""Action validation and approval tiers (FR-22 / TA-ADP-03: TA-D5, TA-D6, TA-D7, TA-D14; AC-10).

Every proposed tool call gets a verdict, ALLOW < ASK_USER < ASK_SPECIALIST < DENY, as the stricter of two
gates:

1. static, in code: reads and low-risk writes ALLOW; a financial amount at or above the tenant's threshold
   (default USD 1,000), a high-risk or destructive tool, or any unreviewed tool ASK_SPECIALIST; at or above
   the tenant's senior amount the approver must be a senior specialist. Amounts are the call's financial
   fields (args declared with financial=True), compared as decimals, per call, and only in USD: a financial
   call must carry currency="USD"; missing, unknown or other currencies are DENY (DECISION-bdad33ce: no
   trusted FX source exists, so no conversion is attempted). A case that already had 3 sub-threshold
   financial writes in 24 hours and would reach USD 1,500 with this one asks a specialist too (threshold
   splitting); that history comes only from the server-side ledger (tools.validation.approvals).
2. Jev, on the masked turn and the masked proposed call: allow / ask / deny, plus "does this serve the
   customer's request?"; below 0.85 it counts as ask. Jev can only tighten: verdicts combine with max().
   Jev down: a write asks, a read stays as the static gate says.

Approvals, their lifecycle and the final re-validation before a call runs are in tools.validation.approvals;
nothing here runs a tool. preview() builds the approval card with every string value tokenized by the PII
tokenizer, and a dry run only through a reviewed read-only registry tool with the same argument schema.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import IntEnum

from core.orchestrator.decisions import JevUnavailable, mask
from tools.registry import Risk

DEFAULT_THRESHOLD, DEFAULT_SENIOR = Decimal("1000"), Decimal("5000")
SPLIT_COUNT, SPLIT_TOTAL = 3, Decimal("1500")
SERVES_AT = 0.85
CURRENCY = "USD"  # the only currency thresholds are defined in (approval_threshold_usd, senior_amount_usd)
LEVELS = ("customer", "specialist", "senior_specialist")
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


class UnsafeDryRun(ValueError):
    pass


@dataclass(frozen=True)
class Limits:
    threshold: Decimal = DEFAULT_THRESHOLD
    senior: Decimal = DEFAULT_SENIOR
    version: int = 0  # tenant_settings.version; 0 = platform defaults (no settings row)


@dataclass
class Decision:
    decision_id: str
    tool_id: str
    verdict: Verdict
    static: Verdict
    jev: Verdict
    reasons: list[str] = field(default_factory=list)
    amount: Decimal = Decimal("0")
    level: str | None = None          # who must approve: "customer", "specialist" or "senior_specialist"
    policy_version: int = 0


def canonical(arguments):
    """The validated arguments as canonical JSON, the form approvals are bound to."""
    return json.dumps(arguments.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def arguments_hash(arguments):
    return hashlib.sha256(canonical(arguments).encode()).hexdigest()


def financial_fields(arguments):
    return [name for name, info in type(arguments).model_fields.items()
            if (info.json_schema_extra or {}).get("financial") is True]


def financial_amount(arguments):
    """(USD amount, problem). The amount is the sum of |financial fields|; problem is set (and the call must
    be denied) when an amount is not a finite number or the call is not in USD."""
    names = financial_fields(arguments)
    if not names:
        return Decimal("0"), None
    currency = getattr(arguments, "currency", None)
    if currency != CURRENCY:
        return Decimal("0"), f"financial call must be in {CURRENCY}, got {currency!r}"
    total = Decimal("0")
    for name in names:
        try:
            value = Decimal(str(getattr(arguments, name)))
        except (InvalidOperation, ValueError):
            return Decimal("0"), "financial amount is not a number"
        if not value.is_finite():
            return Decimal("0"), "financial amount is not a number"
        total += abs(value)
    return total, None


def static_gate(tool, arguments, limits, recent=()):
    """Gate 1, code only. recent: USD amounts of this case's financial writes in the last 24 hours, read from
    the ledger by tools.validation.approvals (never taken from a caller)."""
    amount, problem = financial_amount(arguments)
    if problem:
        return Verdict.DENY, [problem], Decimal("0")
    reasons = []
    if amount >= limits.threshold:
        reasons.append("amount at or above the tenant threshold")
    if tool.risk in (Risk.HIGH_RISK_WRITE, Risk.DESTRUCTIVE_IRREVERSIBLE):
        reasons.append(f"{tool.risk.value} tool")
    if not tool.reviewed_by:
        reasons.append("unreviewed tool")
    sub_threshold = [Decimal(a) for a in recent if Decimal(a) < limits.threshold]
    if amount and len(sub_threshold) >= SPLIT_COUNT and sum(sub_threshold) + amount >= SPLIT_TOTAL:
        reasons.append("many sub-threshold payments on this case (threshold splitting)")
    return (Verdict.ASK_SPECIALIST if reasons else Verdict.ALLOW), reasons, amount


def jev_gate(engine, tool, arguments, masked_state):
    """Gate 2: Jev on the masked turn and the masked proposed call. Its 'ask' goes to the customer for reads
    and low-risk writes, to a specialist otherwise."""
    ask = Verdict.ASK_USER if tool.risk in (Risk.READ_ONLY, Risk.LOW_RISK_WRITE) else Verdict.ASK_SPECIALIST
    proposed = mask(f"{tool.description} with {canonical(arguments)}")
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


def required_level(verdict, amount, limits):
    if verdict is Verdict.ASK_USER:
        return "customer"
    if verdict is Verdict.ASK_SPECIALIST:
        return "senior_specialist" if amount >= limits.senior else "specialist"
    return None


def decide(tool, arguments, limits, engine, masked_state, recent=(), floor=Verdict.ALLOW, extra_reasons=()):
    """Both gates, combined stricter-of. floor: a verdict the caller's own checks require (e.g. Cedar)."""
    static, static_reasons, amount = static_gate(tool, arguments, limits, recent)
    jev, jev_reasons = jev_gate(engine, tool, arguments, masked_state)
    verdict = max(static, jev, floor)
    return Decision(str(uuid.uuid4()), tool.tool_id, verdict, static, jev,
                    static_reasons + jev_reasons + list(extra_reasons), amount,
                    required_level(verdict, amount, limits), limits.version)


def masked(value, tokenizer):
    """Every string inside `value` tokenized by the PII tokenizer (the same tokens the vault resolves for an
    authorized viewer); numbers, booleans and structure kept."""
    if isinstance(value, str):
        return tokenizer.mask(value)[0]
    if isinstance(value, dict):
        return {key: masked(item, tokenizer) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [masked(item, tokenizer) for item in value]
    return value


def dry_run_tool(registry, tool, dry_run_id):
    """The registered tool that may preview `tool`: reviewed, read-only, same system, same argument schema.
    Anything else is refused, so a preview can never be a side-effect path."""
    preview_tool = registry.tools.get(dry_run_id)
    if preview_tool is None:
        raise UnsafeDryRun(f"{dry_run_id!r} is not a registered tool")
    if preview_tool.risk is not Risk.READ_ONLY:
        raise UnsafeDryRun(f"{dry_run_id} is {preview_tool.risk.value}, a dry run must be read_only")
    if not preview_tool.reviewed_by:
        raise UnsafeDryRun(f"{dry_run_id} has not been reviewed")
    if preview_tool.args is not tool.args:
        raise UnsafeDryRun(f"{dry_run_id} does not take {tool.tool_id}'s arguments")
    if dry_run_id.split(".", 1)[0] != tool.tool_id.split(".", 1)[0]:
        raise UnsafeDryRun(f"{dry_run_id} is on another system than {tool.tool_id}")
    return preview_tool


def preview(registry, tool, arguments, decision, tokenizer, dry_run_id=None, read_current=None,
            run=lambda preview_tool, arguments: preview_tool.func(arguments)):
    """The approval card. Values are tokenized; the USD amount is shown as is (the approver needs it).
    run(tool, arguments) is how a read-only tool is called (the tool executor in production)."""
    card = {"tool_id": tool.tool_id, "decision_id": decision.decision_id, "verdict": decision.verdict.name,
            "reasons": decision.reasons, "arguments": masked(arguments.model_dump(mode="json"), tokenizer),
            "amount_usd": str(decision.amount), "approval_level": decision.level}
    if dry_run_id is not None:
        before, after = run(dry_run_tool(registry, tool, dry_run_id), arguments)
        return {**card, "mode": "dry_run", "before": masked(before, tokenizer),
                "after": masked(after, tokenizer)}
    current = read_current(arguments) if read_current else None
    return {**card, "mode": "current_state", "current": masked(current, tokenizer)}
