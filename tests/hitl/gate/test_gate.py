"""M2-08: the confidence gate routes drafts to send / co-pilot / hand-off, and any money, percentage or SLA
figure reaches a human (FR-35). Jev is scripted; property runs use seeded stdlib randomness."""

import random

import pytest

from core.orchestrator.decisions import Answer, DecisionEngine, JevUnavailable
from hitl.gate import Band, Route, route, sensitive_figures

QUESTION = "How do I rotate my API key?"
PASSAGE = "Rotate keys under Settings > API > Rotate. The old key stops working after 24 hours."
CLEAN = "Go to Settings > API and choose Rotate. Your old key keeps working for a day."


class ScriptedJev:
    def __init__(self, grounded=(True, 1.0), relevance=4.0, down=False):
        self.grounded, self.relevance, self.down, self.seen = grounded, relevance, down, []

    def evaluate(self, state, questions):
        self.seen.append(state)
        if self.down:
            raise JevUnavailable("down")
        return {"grounded": Answer(*self.grounded),
                "relevance": Answer(float(self.relevance), 0.9, round(self.relevance))}


def gate(draft=CLEAN, provenances=("human",), config=None, **jev):
    return route(DecisionEngine(ScriptedJev(**jev)), draft, QUESTION, [PASSAGE], [], provenances, config)


# Bands ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("grounded, relevance, band", [
    ((True, 1.0), 4.0, Band.SEND),           # c = 1.0
    ((True, 0.9), 4.0, Band.SEND),           # c = 0.90: the send line is inclusive
    ((True, 0.89), 4.0, Band.CO_PILOT),
    ((True, 1.0), 3.0, Band.CO_PILOT),       # c = 0.75
    ((True, 1.0), 2.0, Band.CO_PILOT),       # c = 0.50: the co-pilot line is inclusive
    ((True, 0.98), 2.0, Band.HANDOFF),       # c = 0.49
    ((False, 0.9), 4.0, Band.HANDOFF),       # probably not grounded: c = 0.10
    ((True, 1.0), 0.0, Band.HANDOFF),        # grounded but beside the point
])
def test_confidence_picks_the_band(grounded, relevance, band):
    verdict = gate(grounded=grounded, relevance=relevance)
    assert verdict.band is band


def test_an_unstaffed_route_turns_co_pilot_into_hand_off_but_still_sends():
    unstaffed = Route("night", staffed=False)
    assert gate(relevance=3.0, config=unstaffed).band is Band.HANDOFF
    assert gate(config=unstaffed).band is Band.SEND


def test_a_route_can_tune_its_thresholds():
    assert gate(relevance=3.4, config=Route("billing", send_at=0.85)).band is Band.SEND  # c = 0.85
    Route(send_at=0.85, handoff_below=0.7)


@pytest.mark.parametrize("bad", [{"send_at": 0.5}, {"send_at": 1.0}, {"handoff_below": 0.05},
                                 {"handoff_below": 0.8}, {"send_at": 0.8, "handoff_below": 0.8}])
def test_route_thresholds_stay_inside_the_calibrated_bounds(bad):
    with pytest.raises(ValueError):
        Route(**bad)


# Evidence written by the agent counts half ---------------------------------------------------------------

@pytest.mark.parametrize("provenances, band", [
    (("human",), Band.SEND), (("human", "agent"), Band.CO_PILOT),
    (("unknown",), Band.CO_PILOT),
    ((), Band.CO_PILOT),                     # the passage carries no provenance label at all
])
def test_agent_or_unlabelled_evidence_is_discounted(provenances, band):
    verdict = gate(provenances=provenances)
    assert verdict.band is band and verdict.discount == (0.5 if band is Band.CO_PILOT else 1.0)


# Money, percentages and SLAs always reach a person ------------------------------------------------------

FIGURE_DRAFTS = [
    "We have refunded the charge.", "You will receive a $20 credit.", "That is 1,240.00 USD back to you.",
    "We applied a 15% discount.", "Uptime this month was 99.95 %.", "Our SLA covers you here.",
    "A credit of twenty dollars is on its way.", "You get 10 percent off.", "€15 was returned.",
    "The response time for P1 is four hours.", "We will reimburse you.", "Your plan is prorated.",
    "￥３０００ was credited.", "＄２０ is on its way.",               # full-width signs and digits
    "We re​funded you.",                                        # a zero-width space inside the word
    "We have rеfunded you.",                                    # a Cyrillic e inside the word
]


@pytest.mark.parametrize("draft", FIGURE_DRAFTS)
def test_a_draft_with_money_percentages_or_slas_is_never_sent_automatically(draft):
    verdict = gate(draft=draft)
    assert sensitive_figures(draft), draft
    assert verdict.band is Band.CO_PILOT and verdict.figures and "checked by a person" in verdict.reasons[-1]


@pytest.mark.parametrize("draft", [CLEAN, "Restart step 3, then reinstall version 4.2.",
                                   "Ticket INV-9821 is open.", "Call us on weekdays."])
def test_plain_numbers_are_not_money(draft):
    assert sensitive_figures(draft) == [] and gate(draft=draft).band is Band.SEND


def test_a_figure_does_not_rescue_a_weak_draft_from_hand_off():
    assert gate(draft="You will get a $20 credit.", relevance=1.0).band is Band.HANDOFF


# Jev down, masking ---------------------------------------------------------------------------------------

def test_a_draft_jev_cannot_score_goes_to_a_person_never_out():
    verdict = gate(down=True)
    assert verdict.band is Band.CO_PILOT and verdict.confidence is None
    assert gate(down=True, config=Route("night", staffed=False)).band is Band.HANDOFF


def test_jev_sees_masked_text_only():
    jev = ScriptedJev()
    route(DecisionEngine(jev), "Mail sarah@acme.com the new key.", "My email is sarah@acme.com",
          [PASSAGE], ['{"owner": "sarah@acme.com"}'])
    assert "sarah@" not in str(jev.seen) and "<EMAIL>" in jev.seen[0]["draft"]


# Properties ----------------------------------------------------------------------------------------------

def test_property_no_figure_ever_reaches_the_send_band():
    rng = random.Random(20261024)
    for _ in range(3000):
        figure = rng.choice(FIGURE_DRAFTS)
        draft = " ".join(rng.sample([CLEAN, figure, "Thanks for waiting.", "Let me know if that helps."], 3)
                         + [figure])
        jev = {"grounded": (rng.random() < 0.9, rng.uniform(0.5, 1.0)), "relevance": rng.uniform(0, 4),
               "down": rng.random() < 0.05}
        provenances = rng.choice([("human",), ("agent",), ()])
        config = Route(staffed=rng.random() < 0.8)
        assert gate(draft=draft, provenances=provenances, config=config, **jev).band is not Band.SEND


def test_property_bands_follow_the_confidence():
    rng = random.Random(7)
    for _ in range(3000):
        grounded, relevance = (True, rng.uniform(0.5, 1.0)), rng.uniform(0, 4)
        verdict = gate(grounded=grounded, relevance=relevance)
        c = verdict.confidence
        expected = Band.SEND if c >= 0.90 else Band.CO_PILOT if c >= 0.50 else Band.HANDOFF
        assert verdict.band is expected and abs(c - grounded[1] * relevance / 4) < 1e-9
