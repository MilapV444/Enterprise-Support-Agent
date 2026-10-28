"""Internal SLOs and alerts, token telemetry, and failure classification (NFR-13 / OB-ADP-03: OB-D7, OB-D8;
NFR-14 / OB-ADP-04: OB-D9, OB-D13; NFR-15 / OB-ADP-05: OB-D11).

- SLOS: four internal objectives (never promised to tenants): turn availability 99.9%, first status within
  300 ms for 95%, final reply within 2.5 s for 95%, escalations at most 8%. burn_alerts() applies the
  multi-window rule: page when both the 1 h and 5 min windows burn the budget at 14.4x or more, ticket when
  both the 6 h and 30 min windows do at 6x or more.
- Tripwires: the hand-off alerts (an OAuth token expiring within 2 h, a failed or incomplete nightly batch, a
  breaker opening, reranker fallbacks above 5% over 15 minutes, more than three sub-threshold financial
  writes on one case within an hour), each sent once per key until it clears.
- TokenCounter: tokens per tenant, component, model and type, the only labels (never a conversation id), with
  a cap on the number of series; Prometheus text exposition. estimated_cost(): the Horvitz-Thompson estimate
  from kept traces (deterministically kept at weight one, the 5% baseline at weight twenty).
- classify(): rules on error codes and decision records first; then a Jev choice over the failure taxonomy on
  the masked transcript, committed at confidence >= 0.85; anything else is a residual for human QA.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from enum import Enum

from core.orchestrator.decisions import JevUnavailable

# SLOs and burn rates ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Turn:
    at: float                      # epoch seconds
    ok: bool                       # the turn completed (not an error)
    first_status_ms: float
    final_ms: float
    escalated: bool


@dataclass(frozen=True)
class Slo:
    name: str
    target: float
    good: object                   # Turn -> bool

    @property
    def budget(self):
        return 1 - self.target


SLOS = (
    Slo("turn_availability", 0.999, lambda t: t.ok),
    Slo("first_status", 0.95, lambda t: t.first_status_ms <= 300),
    Slo("final_reply", 0.95, lambda t: t.final_ms <= 2500),
    Slo("escalation", 0.92, lambda t: not t.escalated),
)
PAGE = (14.4, timedelta(hours=1), timedelta(minutes=5))
TICKET = (6.0, timedelta(hours=6), timedelta(minutes=30))


@dataclass(frozen=True)
class Alert:
    name: str
    severity: str                  # P1 page, P2 ticket
    detail: dict = field(default_factory=dict)


def burn_rate(turns, slo, now, window):
    recent = [t for t in turns if now - window.total_seconds() < t.at <= now]
    if not recent:
        return 0.0
    bad = sum(1 for t in recent if not slo.good(t))
    return (bad / len(recent)) / slo.budget


def burn_alerts(turns, now, slos=SLOS):
    alerts = []
    for slo in slos:
        for severity, (threshold, long_window, short_window) in (("P1", PAGE), ("P2", TICKET)):
            long_rate = burn_rate(turns, slo, now, long_window)
            short_rate = burn_rate(turns, slo, now, short_window)
            if long_rate >= threshold and short_rate >= threshold:
                alerts.append(Alert(f"slo_burn:{slo.name}", severity,
                                    {"long": round(long_rate, 2), "short": round(short_rate, 2)}))
                break                  # a page covers the ticket
    return alerts


# Tripwires --------------------------------------------------------------------------------------------------

TOKEN_WARNING = timedelta(hours=2)
BATCH_PARITY = 0.90
RERANK_FALLBACK = 0.05
SPLIT_WRITES, SPLIT_WINDOW = 3, timedelta(hours=1)


class Tripwires:
    """Each condition alerts once (send(alert)) until it clears, then may alert again."""

    def __init__(self, send):
        self.send, self.firing = send, set()

    def _check(self, key, failing, alert):
        if failing and key not in self.firing:
            self.firing.add(key)
            self.send(alert)
        elif not failing:
            self.firing.discard(key)
        return failing

    def token_expiry(self, integration, seconds_left):
        return self._check(("token", integration), seconds_left < TOKEN_WARNING.total_seconds(),
                           Alert("oauth_token_expiring", "P2", {"integration": integration,
                                                                "seconds_left": int(seconds_left)}))

    def nightly_batch(self, batch, exit_code, parity):
        return self._check(("batch", batch), exit_code != 0 or parity < BATCH_PARITY,
                           Alert("nightly_batch_failed", "P2", {"batch": batch, "exit_code": exit_code,
                                                                "parity": parity}))

    def breaker(self, system, state):
        return self._check(("breaker", system), state == "open",
                           Alert("breaker_open", "P1", {"system": system}))

    def reranker(self, fallbacks, calls):
        rate = fallbacks / calls if calls else 0.0
        return self._check(("reranker",), rate > RERANK_FALLBACK,
                           Alert("reranker_fallback_spike", "P2", {"rate": round(rate, 4)}))

    def sub_threshold_writes(self, tenant_id, case_id, writes, threshold, now):
        """writes: [(epoch seconds, USD amount)] of the case's financial writes."""
        recent = [a for at, a in writes if now - SPLIT_WINDOW.total_seconds() < at <= now
                  and Decimal(str(a)) < Decimal(str(threshold))]
        return self._check(("split", tenant_id, case_id), len(recent) > SPLIT_WRITES,
                           Alert("repeated_sub_threshold_writes", "P1",
                                 {"tenant_id": tenant_id, "case_id": case_id, "writes": len(recent)}))


# Token telemetry --------------------------------------------------------------------------------------------

LABELS = ("tenant_id", "component", "model", "type")
COMPONENTS = {"coordinator", "specialist", "jev", "judge", "reranker", "router", "retrieval", "other"}
MAX_SERIES = 16_000


class TokenCounter:
    """gen_ai_tokens_total with low-cardinality labels only: at most max_series regular series, then one
    overflow series per component and type (so never more than max_series + 2 x the components)."""

    def __init__(self, max_series=MAX_SERIES):
        self.max_series, self.series = max_series, Counter()

    def add(self, tenant_id, component, model, input_tokens, output_tokens):
        if component not in COMPONENTS:
            raise ValueError(f"unknown component {component!r}")
        for kind, count in (("input", input_tokens), ("output", output_tokens)):
            if type(count) is not int or count < 0:
                raise ValueError("token counts are non-negative integers")
            labels = (tenant_id, component, model, kind)
            regular = sum(1 for key in self.series if key[0] != "overflow")
            if labels not in self.series and regular >= self.max_series:
                labels = ("overflow", component, "overflow", kind)
            self.series[labels] += count

    def exposition(self):
        lines = ["# TYPE gen_ai_tokens_total counter"]
        for labels, value in sorted(self.series.items()):
            pairs = ",".join(f'{name}="{value_}"' for name, value_ in zip(LABELS, labels, strict=True))
            lines.append(f"gen_ai_tokens_total{{{pairs}}} {value}")
        return "\n".join(lines) + "\n"


def estimated_cost(traces, baseline=0.05):
    """Horvitz-Thompson: traces [(cost, sampling reason)], reason 'deterministic' or 'baseline'."""
    total = Decimal(0)
    for cost, reason in traces:
        if reason == "deterministic":
            total += Decimal(str(cost))
        elif reason == "baseline":
            total += Decimal(str(cost)) / Decimal(str(baseline))
        else:
            raise ValueError(f"unknown sampling reason {reason!r}")
    return total


# Failure classification -------------------------------------------------------------------------------------

class Failure(str, Enum):
    EXTERNAL_SYSTEM_DOWN = "infrastructure_external_system_down"
    AUTHORIZATION_DENIAL = "permission_authorization_denial"
    AGENT_LOOP_LIMIT = "orchestration_agent_loop_limit"
    TIMEOUT_ABORT = "infrastructure_timeout_abort"
    INJECTION_BLOCKED = "safety_adversarial_injection_blocked"
    INCORRECT_ROUTING = "incorrect_specialist_routing"
    KNOWLEDGE_GAP = "retrieval_knowledge_gap"
    UNBACKED_PROMISE = "unbacked_promise_attempt"
    SENTIMENT_ESCALATION = "customer_sentiment_escalation"
    OUT_OF_SCOPE = "unsupported_out_of_scope_request"
    CIRCULAR_REASONING = "repetitive_circular_reasoning"


RULES = (  # error code or decision -> category, in this order
    ({"SYSTEM_UNAVAILABLE", "BREAKER_OPEN", "STILL_DOWN"}, Failure.EXTERNAL_SYSTEM_DOWN),
    ({"FORBIDDEN", "AUTHORIZATION_DENIED", "NOT_APPROVED", "AUTHENTICATION_EXPIRED"},
     Failure.AUTHORIZATION_DENIAL),
    ({"STEP_BUDGET_USED_UP", "budget_used_up"}, Failure.AGENT_LOOP_LIMIT),
    ({"TIMEOUT", "TRANSIENT", "GATEWAY_TIMEOUT"}, Failure.TIMEOUT_ABORT),
    ({"block", "SCREENING_BLOCKED"}, Failure.INJECTION_BLOCKED),
)
CONVERSATIONAL = {
    Failure.INCORRECT_ROUTING.value: "The case was sent to the wrong specialist or domain",
    Failure.KNOWLEDGE_GAP.value: "The documentation needed to answer was missing or not found",
    Failure.UNBACKED_PROMISE.value: "The agent tried to promise something it had not done",
    Failure.SENTIMENT_ESCALATION.value: "The customer grew frustrated and asked for a person",
    Failure.OUT_OF_SCOPE.value: "The customer asked for something the agent does not support",
    Failure.CIRCULAR_REASONING.value: "The agent repeated itself or went in circles",
}
QUESTION = {"type": "choice",
            "instructions": "Which failure category best explains why this support conversation failed or "
                            "was escalated?",
            "criteria": CONVERSATIONAL}
COMMIT_AT = 0.85


@dataclass(frozen=True)
class Classification:
    category: Failure | None       # None: a residual for human QA
    source: str                    # "rule", "jev" or "residual"
    confidence: float | None = None


def classify(engine, error_codes=(), decision=None, transcript=None):
    """error_codes: codes seen in the turn; decision: the decision record's outcome; transcript: Masked."""
    seen = set(error_codes) | ({decision} if decision else set())
    for codes, category in RULES:
        if seen & codes:
            return Classification(category, "rule", 1.0)
    if transcript is None:
        return Classification(None, "residual")
    try:
        answer = engine.ask({"transcript": transcript}, {"failure": QUESTION})["failure"]
    except JevUnavailable:
        return Classification(None, "residual")
    if answer.confidence < COMMIT_AT:
        return Classification(None, "residual", answer.confidence)
    return Classification(Failure(answer.value), "jev", answer.confidence)
