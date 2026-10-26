"""M3-03: numeric disagreements go to a person in code, other conflicts are scored by Jev against the
evidence, and the coordinator sends one reply that does not redirect and claims nothing unverified (FR-29 /
MA-ADP-05)."""

import json
from decimal import Decimal

import pytest

from agents.contracts import ExecutedAction
from agents.merge import Claim, claims_from, merge
from core.orchestrator.decisions import Answer, DecisionEngine, JevUnavailable, SecurityViolation

EVIDENCE = {"ops.uptime": "EU primary cluster uptime for the quarter: 99.98 percent",
            "billing.credit_memos": "Credit memo CM-7 applied for the March incident",
            "kb.sla": "Contracted uptime is 99.9 percent per quarter"}


class Jev:
    """support: {claim text: level 1..5}; redirect: P(redirect)."""

    def __init__(self, support=None, redirect=0.05, down=False):
        self.support, self.redirect, self.down, self.seen = support or {}, redirect, down, []

    def evaluate(self, state, questions):
        self.seen.append((state, questions))
        if self.down:
            raise JevUnavailable("down")
        answers = {}
        for qid in questions:
            if qid.startswith("support_"):
                level = self.support[state[f"claim_{qid.removeprefix('support_')}"]]
                answers[qid] = Answer(float(level - 1), 0.9, level - 1)
            elif qid == "redirect":
                answers[qid] = Answer(self.redirect >= 0.5, max(self.redirect, 1 - self.redirect))
        return answers


def result(role, *claims, status="completed"):
    return {"role": role, "status": status, "findings": json.dumps(list(claims)), "evidence": [], "steps": 2}


def claim(topic, text, evidence, value=None, unit=None):
    return {"topic": topic, "text": text, "evidence": [evidence], **({"value": str(value), "unit": unit}
                                                                     if value is not None else {})}


UPTIME = claim("eu_uptime_q2", "EU database uptime was 99.98 percent", "ops.uptime", "99.98", "percent")
CREDITS = claim("credits_q2", "One credit memo, CM-7, was applied", "billing.credit_memos")


class Drafts:
    def __init__(self, text="Our technical review found EU uptime of 99.98 percent; billing applied CM-7."):
        self.text, self.calls = text, []

    def __call__(self, claims):
        self.calls.append(claims)
        return self.text


def run(results, jev=None, draft=None, verified=()):
    jev, draft = jev or Jev(), draft or Drafts()
    return merge(DecisionEngine(jev), results, EVIDENCE, draft, verified), jev, draft


# Claims -----------------------------------------------------------------------------------------------------

def test_claims_are_typed_and_labelled_with_the_role_that_returned_them():
    (got,) = claims_from(result("technical", {**UPTIME, "role": "billing"}))
    assert got.role == "technical" and got.value == Decimal("99.98") and got.unit == "percent"


@pytest.mark.parametrize("bad", [
    {"status": "blocked", "findings": json.dumps([UPTIME])},
    {"findings": "uptime looked fine"},                                    # not typed
    {"findings": json.dumps([{**UPTIME, "evidence": []}])},               # ungrounded
    {"findings": json.dumps([{**UPTIME, "value": "NaN"}])},
    {"findings": json.dumps([{**UPTIME, "customer_reply": "All good!"}])},
    {"findings": json.dumps({"topic": "x"})},
])
def test_untyped_ungrounded_or_blocked_findings_are_not_used(bad):
    assert claims_from({"role": "technical", "status": "completed", **bad}) == []


def test_nothing_usable_goes_to_a_person():
    outcome, jev, draft = run([result("technical", status="blocked")])
    assert (outcome.kind, outcome.reason) == ("human", "NOTHING_TO_SAY")
    assert draft.calls == [] and jev.seen == []


# Numbers: code only -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("other, conflict", [
    ("99.98", False), ("99.984", False),               # within the percent tolerance
    ("99.90", True), ("99.986", True),
])
def test_numbers_that_disagree_go_to_a_person_with_both_values_and_jev_never_judges_them(other, conflict):
    billing = claim("eu_uptime_q2", f"Credits assume {other} percent uptime", "billing.credit_memos", other,
                    "percent")
    outcome, jev, draft = run([result("technical", UPTIME), result("billing", billing)])
    if conflict:
        assert (outcome.kind, outcome.reason) == ("human", "NUMERIC_DISCREPANCY")
        assert outcome.detail["values"] == {"eu_uptime_q2": {"technical": "99.98 percent",
                                                             "billing": f"{other} percent"}}
        assert jev.seen == [] and draft.calls == []
    else:
        assert outcome.kind == "reply"
        assert not any("claim_a" in str(state) for state, _ in jev.seen)  # agreeing numbers are not scored


@pytest.mark.parametrize("value, unit", [("26", "minutes"), ("99.98", "permille"), ("99.98", None)])
def test_the_same_figure_in_different_units_is_a_discrepancy(value, unit):
    other = claim("eu_uptime_q2", "Uptime as billing measured it", "ops.uptime", value, unit)
    outcome, _, _ = run([result("technical", UPTIME), result("billing", other)])
    assert outcome.reason == "NUMERIC_DISCREPANCY"


# Other disagreements: Jev against the evidence --------------------------------------------------------------

A = claim("root_cause", "A database failover caused the outage", "ops.uptime")
B = claim("root_cause", "A billing job caused the outage", "billing.credit_memos")


@pytest.mark.parametrize("a, b, outcome_kind, winner", [
    (5, 1, "reply", "A database failover caused the outage"),
    (2, 4, "reply", "A billing job caused the outage"),
    (4, 3, "human", None), (3, 3, "human", None), (5, 5, "human", None), (2, 2, "human", None),
])
def test_a_conflict_is_settled_only_by_a_clear_evidence_margin(a, b, outcome_kind, winner):
    jev = Jev(support={A["text"]: a, B["text"]: b})
    outcome, _, draft = run([result("technical", A), result("billing", B)], jev)
    assert outcome.kind == outcome_kind
    if winner:
        assert [c.text for c in draft.calls[0]] == [winner]
    else:
        assert outcome.reason == "EVIDENCE_AMBIGUITY" and draft.calls == []
        assert outcome.detail["claims"] == {"technical": (A["text"], a), "billing": (B["text"], b)}
    state, questions = jev.seen[0]
    assert state["evidence_a"] == EVIDENCE["ops.uptime"]                 # each claim with its own evidence
    assert state["evidence_b"] == EVIDENCE["billing.credit_memos"]


def test_three_way_conflicts_need_one_clear_winner():
    c = claim("root_cause", "A network change caused the outage", "kb.sla")
    jev = Jev(support={A["text"]: 5, B["text"]: 1, c["text"]: 3})
    outcome, _, _ = run([result("technical", A), result("billing", B), result("generalist", c)], jev)
    assert outcome.reason == "EVIDENCE_AMBIGUITY"


@pytest.mark.parametrize("jev", [Jev(down=True), Jev(support={A["text"]: 9, B["text"]: 1})])
def test_jev_down_or_malformed_goes_to_a_person(jev):
    outcome, _, draft = run([result("technical", A), result("billing", B)], jev)
    assert outcome.reason == "JEV_UNAVAILABLE" and draft.calls == []


def test_personal_data_never_goes_to_jev():
    leaky = claim("root_cause", "sarah@acme.com changed the config", "ops.uptime")
    with pytest.raises(SecurityViolation):
        run([result("technical", leaky), result("billing", B)], Jev(support={B["text"]: 1}))


# One reply, one voice ---------------------------------------------------------------------------------------

def test_one_reply_from_the_coordinator_built_from_the_accepted_claims():
    outcome, _, draft = run([result("technical", UPTIME), result("billing", CREDITS)])
    assert outcome.kind == "reply" and outcome.text == draft.text and len(draft.calls) == 1
    assert {c.topic for c in draft.calls[0]} == {"eu_uptime_q2", "credits_q2"}


@pytest.mark.parametrize("p, kind", [(0.19, "reply"), (0.20, "human"), (0.9, "human")])
def test_a_reply_that_sends_the_customer_elsewhere_is_held(p, kind):
    outcome, _, _ = run([result("billing", CREDITS)], Jev(redirect=p),
                        Drafts("Please contact the billing department about CM-7."))
    assert outcome.kind == kind
    if kind == "human":
        assert outcome.reason == "REDIRECT" and "billing department" in outcome.detail["draft"]


def test_jev_down_at_the_redirect_check_holds_the_reply():
    class DownLater(Jev):
        def evaluate(self, state, questions):
            if "redirect" in questions:
                raise JevUnavailable("down")
            return super().evaluate(state, questions)
    outcome, _, _ = run([result("billing", CREDITS)], DownLater())
    assert outcome.reason == "JEV_UNAVAILABLE"


DONE = ExecutedAction(tool_id="billing.tag_invoice", tool_call_id="c-1", verified=True)


@pytest.mark.parametrize("text, verified, kind", [
    ("I have processed your refund.", (), "human"),
    ("Your credit has been applied.", (), "human"),
    ("The account is now reset.", (), "human"),
    ("I have prepared a credit memo for your review.", (), "reply"),       # prospective wording
    ("I have processed the tag on your invoice.", (DONE,), "reply"),       # a verified write
])
def test_completed_actions_are_claimed_only_when_a_verified_write_backs_them(text, verified, kind):
    outcome, _, _ = run([result("billing", CREDITS)], draft=Drafts(text), verified=verified)
    assert outcome.kind == kind
    if kind == "human":
        assert outcome.reason == "UNVERIFIED_COMPLETION"


def test_a_claim_model_refuses_unknown_fields():
    with pytest.raises(ValueError):
        Claim(topic="t", text="x", evidence=("e",), voice="customer")
