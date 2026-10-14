"""M1-06: Jev decision client and question sets with masked input and a fallback LLM classifier (FR-5)."""

import json

import httpx
import pytest

from core.orchestrator.decisions import (
    QUESTIONS_VERSION,
    Answer,
    DecisionEngine,
    JevClient,
    JevUnavailable,
    Masked,
    SecurityViolation,
    mask,
)
from core.orchestrator.statechart import build
from core.orchestrator.triage import ASK_CUSTOMER, FALLBACK_MAX_CONFIDENCE, llm_fallback, triage, triage_hook

MESSAGE = {"message": Masked("My last invoice charged me twice")}


class FakeJev:
    """Answers by question id; records what it was sent; raises when told to be down."""

    def __init__(self, answers=None, down=False):
        self.answers, self.down, self.sent = answers or {}, down, []

    def evaluate(self, state, questions):
        self.sent.append((state, [q["id"] for q in questions]))
        if self.down:
            raise JevUnavailable("timeout")
        return {qid: self.answers[qid] for qid in (q["id"] for q in questions) if qid in self.answers}


def triage_answers(intent="BILLING_INQUIRY", severity=1, missing=False, confidence=0.95):
    return {"intent": Answer(intent, confidence), "severity": Answer("x", confidence, severity),
            "missing_details": Answer(missing, confidence)}


def fallback_reply(**fields):
    return llm_fallback(lambda prompt: json.dumps({"intent": "BILLING_INQUIRY", "severity": 1,
                                                   "missing_details": False, "confidence": 0.99, **fields}))


def test_triage_maps_typed_answers_onto_acuity():
    billing = triage(DecisionEngine(FakeJev(triage_answers())), MESSAGE)
    assert (billing["acuity"], billing["sop_name"], billing["confidence"]) == (2, "billing_inquiry", 0.95)
    outage = triage(DecisionEngine(FakeJev(triage_answers("TECHNICAL_OUTAGE", severity=4))), MESSAGE)
    assert (outage["acuity"], outage["sop_name"]) == (5, None)


def test_confidence_is_the_weakest_answer():
    answers = {**triage_answers(), "severity": Answer("x", 0.6, 1)}
    assert triage(DecisionEngine(FakeJev(answers)), MESSAGE)["confidence"] == 0.6


def test_jev_down_uses_the_fallback_classifier_capped_below_sop_confidence():
    result = triage(DecisionEngine(FakeJev(down=True)), MESSAGE, fallback_reply())
    assert result["intent"] == "BILLING_INQUIRY" and result["confidence"] == FALLBACK_MAX_CONFIDENCE
    assert result["rationale"].startswith("fallback")


@pytest.mark.parametrize("fallback", [None, llm_fallback(lambda prompt: "not json"),
                                      fallback_reply(intent="X"), fallback_reply(severity=9)])
def test_without_a_usable_answer_triage_asks_the_customer(fallback):
    assert triage(DecisionEngine(FakeJev(down=True)), MESSAGE, fallback) == ASK_CUSTOMER


def test_an_invalid_jev_answer_counts_as_jev_down():
    wrong = DecisionEngine(FakeJev(triage_answers(intent="REFUND_EVERYTHING")))
    assert triage(wrong, MESSAGE, fallback_reply())["rationale"].startswith("fallback")


def test_only_masked_text_without_personal_data_leaves_for_jev():
    jev = FakeJev(triage_answers())
    engine = DecisionEngine(jev)
    with pytest.raises(SecurityViolation, match="not masked"):
        triage(engine, {"message": "raw text"})
    with pytest.raises(SecurityViolation, match="personal data"):
        triage(engine, {"message": Masked("mail me at sarah@acme.com")})
    raw = "Card 4111 1111 1111 1111, SSN 123-45-6789, sarah@acme.com, +1 415 555 0100"
    triage(engine, {"message": mask(raw)})
    assert jev.sent[-1][0] == {"message": "Card <CARD>, SSN <SSN>, <EMAIL>, <PHONE>"}


def test_guards_need_a_confident_yes_and_fail_safe():
    def guard(answer=None, down=False):
        engine = DecisionEngine(FakeJev({"confirmed": answer} if answer else {}, down=down))
        return engine.guard("confirmed", "Has the customer confirmed the fix?", MESSAGE)

    assert guard(Answer(True, 0.95)) is True
    assert guard(Answer(True, 0.7)) is False
    assert guard(Answer(False, 0.99)) is False
    assert guard(down=True) is False
    assert guard() is False  # no answer at all


def test_numbers_and_money_stay_out_of_jev_questions():
    engine = DecisionEngine(FakeJev({"big": Answer(True, 1.0)}))
    with pytest.raises(ValueError, match="numbers and money"):
        engine.guard("big", "Is the refund above $1,000?", MESSAGE)


def test_tool_selection_picks_from_the_shortlist_or_nothing():
    def pick(answer=None, down=False, candidates=("status_page", "read_logs")):
        engine = DecisionEngine(FakeJev({"tool": answer} if answer else {}, down=down))
        return engine.select_tool(list(candidates), MESSAGE)

    assert pick(Answer("read_logs", 0.9)) == "read_logs"
    assert pick(Answer("read_logs", 0.5)) is None
    assert pick(Answer("NONE_REQUIRED", 0.99)) is None
    assert pick(Answer("reset_vpn", 0.99)) is None  # not on the shortlist
    assert pick(down=True) is None
    assert pick(candidates=()) is None


def test_http_client_sends_the_versioned_question_set_and_maps_failures():
    seen = []

    def handler(request):
        seen.append((request.headers["Authorization"], json.loads(request.content)))
        return httpx.Response(200, json={"answers": {"confirmed": {"value": True, "confidence": 0.97}}})

    client = JevClient("https://jev.test", "key-1", transport=httpx.MockTransport(handler))
    answers = client.evaluate({"message": "hi"}, [{"id": "confirmed", "type": "noul", "question": "Fixed?"}])
    assert answers["confirmed"] == Answer(True, 0.97, None)
    assert seen[0][0] == "Bearer key-1" and seen[0][1]["version"] == QUESTIONS_VERSION

    for broken in (lambda r: httpx.Response(503), lambda r: httpx.Response(200, json={"oops": 1}),
                   lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow"))):
        with pytest.raises(JevUnavailable):
            JevClient("https://jev.test", "k", transport=httpx.MockTransport(broken)).evaluate({}, [])


def run_case(jev, fallback=None):
    hooks = {"triage": triage_hook(DecisionEngine(jev), fallback),
             "collect": lambda s: {"parameters": {}, "missing": []},
             "execute_sop": lambda s: {"response": "ok"}}
    return build(hooks).invoke({"tenant_id": "t_us", "case_id": "c1", "session_id": "s1",
                                "event": {"type": "USER_MESSAGE", "text": "I was charged twice, a@b.com"}})


def test_typed_answers_drive_statechart_routing():
    assert run_case(FakeJev(triage_answers()))["stage"] == "RESOLVED"
    assert run_case(FakeJev(triage_answers(missing=True)))["stage"] == "AWAITING_CUSTOMER"
    assert run_case(FakeJev(triage_answers(confidence=0.3)))["stage"] == "ESCALATED_HITL"


def test_with_jev_down_a_fallback_guess_never_runs_an_sop_on_its_own():
    state = run_case(FakeJev(down=True), fallback_reply())
    assert state["stage"] == "AWAITING_CUSTOMER" and state["triage"]["confidence"] == FALLBACK_MAX_CONFIDENCE
