"""M5-02: internal SLOs with multi-window burn-rate alerts, hand-off tripwires, token telemetry with bounded
labels and the Horvitz-Thompson estimate, and failure classification by rules then Jev (NFR-13, NFR-14,
NFR-15)."""

from decimal import Decimal

import pytest

from core.orchestrator.decisions import Answer, DecisionEngine, JevUnavailable, Masked, SecurityViolation
from observability.alerts import (
    SLOS,
    Failure,
    TokenCounter,
    Tripwires,
    Turn,
    burn_alerts,
    burn_rate,
    classify,
    estimated_cost,
)

NOW = 1_800_000_000.0


def turns(count, seconds, bad_every=None, **bad):
    """count turns spread over the last `seconds`; every bad_every-th one has the `bad` fields."""
    out = []
    for n in range(count):
        fields = {"ok": True, "first_status_ms": 100, "final_ms": 900, "escalated": False}
        if bad_every and n % bad_every == 0:
            fields.update(bad)
        out.append(Turn(at=NOW - seconds + (n + 1) * seconds / count, **fields))
    return out


# SLOs and burn rates ----------------------------------------------------------------------------------------

def test_the_four_internal_slos():
    assert {s.name: s.target for s in SLOS} == {"turn_availability": 0.999, "first_status": 0.95,
                                                "final_reply": 0.95, "escalation": 0.92}


def test_burn_rate_is_the_error_rate_over_the_budget():
    availability = SLOS[0]
    sample = turns(1000, 3600, bad_every=100, ok=False)                     # 1% errors, budget 0.1%
    from datetime import timedelta
    assert burn_rate(sample, availability, NOW, timedelta(hours=1)) == pytest.approx(10.0)
    assert burn_rate([], availability, NOW, timedelta(hours=1)) == 0.0


def test_a_fast_burn_in_both_windows_pages():
    sample = turns(2000, 3600, bad_every=50, ok=False)                      # 2%: burn 20x everywhere
    (alert,) = [a for a in burn_alerts(sample, NOW) if a.name == "slo_burn:turn_availability"]
    assert alert.severity == "P1" and alert.detail["long"] >= 14.4 and alert.detail["short"] >= 14.4


def test_an_old_spike_that_stopped_does_not_page():
    old = turns(2000, 3600, bad_every=10, ok=False)                         # bad over the hour...
    calm = [Turn(NOW - 200 + n, True, 100, 900, False) for n in range(200)]  # ...but not the last 5 minutes
    sample = [t for t in old if t.at < NOW - 300] + calm
    assert not [a for a in burn_alerts(sample, NOW) if a.severity == "P1"]


def test_a_slow_burn_over_six_hours_opens_a_ticket_not_a_page():
    sample = turns(6000, 6 * 3600, bad_every=10, final_ms=4000)             # 10% slow: burn 2x the 5% budget
    assert not burn_alerts(sample, NOW)
    sample = turns(6000, 6 * 3600, bad_every=3, final_ms=4000)              # 33%: 6.7x but under 14.4x
    assert [(a.name, a.severity) for a in burn_alerts(sample, NOW)] == [("slo_burn:final_reply", "P2")]


def test_escalations_above_eight_percent_burn_their_budget():
    sample = turns(1000, 3600, bad_every=1, escalated=True)                 # all escalated: 12.5x
    assert [(a.name, a.severity) for a in burn_alerts(sample, NOW)] == [("slo_burn:escalation", "P2")]


# Tripwires --------------------------------------------------------------------------------------------------

@pytest.fixture
def wires():
    sent = []
    return Tripwires(sent.append), sent


def test_each_hand_off_condition_alerts_once_until_it_clears(wires):
    tripwires, sent = wires
    assert tripwires.token_expiry("crm", 3 * 3600) is False
    assert tripwires.token_expiry("crm", 3600) and tripwires.token_expiry("crm", 1800)
    assert [a.name for a in sent] == ["oauth_token_expiring"]                # once while it lasts
    tripwires.token_expiry("crm", 10 * 3600)                                 # refreshed: clears
    tripwires.token_expiry("crm", 60)
    assert [a.name for a in sent] == ["oauth_token_expiring"] * 2


@pytest.mark.parametrize("exit_code, parity, alerts", [(0, 0.95, False), (1, 1.0, True), (0, 0.89, True)])
def test_a_failed_or_incomplete_nightly_batch_alerts(wires, exit_code, parity, alerts):
    tripwires, sent = wires
    assert tripwires.nightly_batch("kb-ingest", exit_code, parity) is alerts
    assert [(a.name, a.severity) for a in sent] == ([("nightly_batch_failed", "P2")] if alerts else [])


def test_an_open_breaker_pages_per_system(wires):
    tripwires, sent = wires
    tripwires.breaker("crm", "open")
    tripwires.breaker("billing", "closed")
    tripwires.breaker("crm", "open")
    assert [(a.name, a.severity, a.detail["system"]) for a in sent] == [("breaker_open", "P1", "crm")]


@pytest.mark.parametrize("fallbacks, calls, alerts", [(5, 100, False), (6, 100, True), (0, 0, False)])
def test_reranker_fallbacks_above_five_percent_alert(wires, fallbacks, calls, alerts):
    tripwires, _ = wires
    assert tripwires.reranker(fallbacks, calls) is alerts


def test_more_than_three_sub_threshold_writes_on_a_case_within_an_hour_is_a_security_page(wires):
    tripwires, sent = wires
    writes = [(NOW - 3000, 900), (NOW - 2000, 950), (NOW - 1000, 990)]
    assert not tripwires.sub_threshold_writes("t_us", "case-1", writes, 1000, NOW)
    writes.append((NOW - 10, 999.99))
    assert tripwires.sub_threshold_writes("t_us", "case-1", writes, 1000, NOW)
    assert [(a.name, a.severity) for a in sent] == [("repeated_sub_threshold_writes", "P1")]
    spread = [(NOW - 4000, 900)] + writes[1:]                                # one write left the hour
    assert not Tripwires(sent.append).sub_threshold_writes("t_us", "case-2", spread, 1000, NOW)
    approved = writes[:3] + [(NOW - 5, 1000)]                 # at the threshold: approved, not split
    assert not Tripwires(lambda a: None).sub_threshold_writes("t_us", "case-3", approved, 1000, NOW)


# Token telemetry --------------------------------------------------------------------------------------------

def test_tokens_are_counted_by_tenant_component_model_and_type_only():
    counter = TokenCounter()
    counter.add("t_us", "specialist", "claude-sonnet", 1200, 300)
    counter.add("t_us", "specialist", "claude-sonnet", 800, 200)
    counter.add("t_eu", "jev", "jev-latest", 50, 5)
    text = counter.exposition()
    series = 'gen_ai_tokens_total{tenant_id="t_us",component="specialist",model="claude-sonnet",type="input"}'
    assert f"{series} 2000" in text
    assert 'type="output"} 500' in text and "conversation" not in text
    with pytest.raises(ValueError, match="unknown component"):
        counter.add("t_us", "conv-123", "m", 1, 1)                           # no high-cardinality labels
    with pytest.raises(ValueError):
        counter.add("t_us", "jev", "m", -1, 1)


def test_the_series_count_is_capped():
    counter = TokenCounter(max_series=4)
    for tenant in ("a", "b", "c"):
        counter.add(tenant, "router", "m", 1, 1)
    regular = [key for key in counter.series if key[0] != "overflow"]
    assert len(regular) == 4 and counter.series[("overflow", "router", "overflow", "input")] == 1
    for tenant in ("d", "e", "f"):
        counter.add(tenant, "router", "m", 1, 1)
    assert len(counter.series) == 6 and counter.series[("overflow", "router", "overflow", "input")] == 4


def test_the_horvitz_thompson_estimate_weights_only_the_baseline():
    kept = [(Decimal("0.40"), "deterministic"), (Decimal("0.02"), "baseline"), (Decimal("0.03"), "baseline")]
    assert estimated_cost(kept) == Decimal("0.40") + Decimal("0.05") * 20
    with pytest.raises(ValueError):
        estimated_cost([(1, "guess")])


# Failure classification -------------------------------------------------------------------------------------

class Jev:
    def __init__(self, category="retrieval_knowledge_gap", confidence=0.9, down=False):
        self.category, self.confidence, self.down, self.seen = category, confidence, down, []

    def evaluate(self, state, questions):
        self.seen.append(state)
        if self.down:
            raise JevUnavailable("down")
        return {"failure": Answer(self.category, self.confidence)}


TRANSCRIPT = Masked("customer: how do I export audit logs?\n"
                    "agent: I could not find that in our documentation.")


@pytest.mark.parametrize("codes, decision, category", [
    (["SYSTEM_UNAVAILABLE"], None, Failure.EXTERNAL_SYSTEM_DOWN),
    (["FORBIDDEN"], None, Failure.AUTHORIZATION_DENIAL),
    ([], "budget_used_up", Failure.AGENT_LOOP_LIMIT),
    (["TRANSIENT"], None, Failure.TIMEOUT_ABORT),
    ([], "block", Failure.INJECTION_BLOCKED),
])
def test_hard_faults_are_classified_by_rules_without_jev(codes, decision, category):
    jev = Jev()
    result = classify(DecisionEngine(jev), codes, decision, TRANSCRIPT)
    assert (result.category, result.source) == (category, "rule") and jev.seen == []


def test_conversational_failures_are_classified_by_jev_on_the_masked_transcript():
    jev = Jev()
    result = classify(DecisionEngine(jev), [], "escalate", TRANSCRIPT)
    assert (result.category, result.source, result.confidence) == (Failure.KNOWLEDGE_GAP, "jev", 0.9)
    assert jev.seen == [{"transcript": TRANSCRIPT.text}]


@pytest.mark.parametrize("jev", [Jev(confidence=0.84), Jev(down=True), Jev(category="blame_the_user")])
def test_unsure_unavailable_or_invalid_answers_go_to_human_qa(jev):
    result = classify(DecisionEngine(jev), [], "escalate", TRANSCRIPT)
    assert (result.category, result.source) == (None, "residual")


def test_no_transcript_no_guess_and_raw_personal_data_never_reaches_jev():
    assert classify(DecisionEngine(Jev()), [], "escalate").source == "residual"
    with pytest.raises(SecurityViolation):
        classify(DecisionEngine(Jev()), [], "escalate", Masked("customer sarah@acme.com is angry"))
