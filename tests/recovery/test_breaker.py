"""M1-08: circuit breaker, Reflexion retries, step caps and the incident diagnostic packet (FR-4)."""

import pytest

from core.orchestrator.decisions import Answer, DecisionEngine, JevUnavailable
from core.recovery.breaker import (
    CRITIQUE_LIMIT,
    MAX_STEPS,
    NonRetryable,
    jev_step_check,
    llm_critique,
    recover,
)

CASE = {"tenant_id": "t_us", "case_id": "c1"}


class Step:
    """Fails with the given errors in turn, then returns 'done'; records the critique each attempt saw."""

    def __init__(self, *failures):
        self.failures, self.seen = list(failures), []

    def __call__(self, critique):
        self.seen.append(critique)
        if self.failures:
            raise self.failures.pop(0)
        return "done"


def numbered_critiques():
    calls = []

    def critique(trajectory, error):
        calls.append(error)
        return f"critique {len(calls)}"
    return critique, calls


def test_a_step_that_works_needs_no_critique():
    critique, calls = numbered_critiques()
    outcome = recover(Step(), lambda r: True, critique, **CASE)
    assert (outcome.ok, outcome.result, outcome.steps, calls) == (True, "done", 1, [])


def test_a_failed_step_retries_with_only_the_latest_critique():
    step, (critique, calls) = Step(ValueError("bad date"), ValueError("still bad")), numbered_critiques()
    outcome = recover(step, lambda r: True, critique, **CASE)
    assert outcome.ok and outcome.steps == 3
    assert step.seen == [None, "critique 1", "critique 2"]  # each retry gets one critique, not a growing log
    assert calls == ["ValueError: bad date", "ValueError: still bad"]


def test_after_two_reflexion_trials_the_breaker_trips_with_a_packet():
    step = Step(*[RuntimeError("timeout")] * 5)
    outcome = recover(step, lambda r: True, numbered_critiques()[0], **CASE)
    packet = outcome.packet
    assert not outcome.ok and len(step.seen) == 3
    got = (packet.failure_reason, packet.reflexion_trials, packet.steps)
    assert got == ("reflexion trials exhausted", 2, 3)
    assert [a["ok"] for a in packet.trajectory] == [False, False, False]


def test_the_step_ceiling_trips_before_a_fifth_step():
    step = Step(*[RuntimeError("timeout")] * 5)
    outcome = recover(step, lambda r: True, numbered_critiques()[0], steps_used=MAX_STEPS - 1, **CASE)
    assert len(step.seen) == 1 and outcome.packet.failure_reason == "step ceiling reached"
    assert outcome.packet.steps == MAX_STEPS
    nothing = recover(Step(), lambda r: True, numbered_critiques()[0], steps_used=MAX_STEPS, **CASE)
    assert nothing.packet.failure_reason == "step ceiling reached" and nothing.trajectory == []


def test_a_step_the_check_does_not_confirm_is_a_failure():
    verdicts = [False, True]
    outcome = recover(Step(), lambda r: verdicts.pop(0), numbered_critiques()[0], **CASE)
    assert outcome.ok and outcome.trajectory[0]["error"] == "the step check did not confirm success"


def test_a_non_retryable_failure_trips_at_once():
    critique, calls = numbered_critiques()
    outcome = recover(Step(NonRetryable("permission denied")), lambda r: True, critique, **CASE)
    assert outcome.packet.failure_reason == "not retryable" and calls == []


class FakeJev:
    def __init__(self, answer=None, down=False):
        self.answer, self.down, self.sent = answer, down, []

    def evaluate(self, state, questions):
        self.sent.append(state)
        if self.down:
            raise JevUnavailable("timeout")
        return {"step_success": self.answer}


@pytest.mark.parametrize("answer, down, passed", [
    (Answer(True, 0.9), False, True),
    (Answer(True, 0.8), False, False),  # below 0.85 is a failure, never fail open
    (Answer(False, 0.99), False, False),
    (None, True, False),               # Jev down: not confirmed
])
def test_jev_decides_step_success(answer, down, passed):
    jev = FakeJev(answer, down)
    assert jev_step_check(DecisionEngine(jev))("refund created for sarah@acme.com") is passed
    assert jev.sent[0] == {"step_result": "refund created for <EMAIL>"}


def test_errors_are_masked_in_the_packet_and_safe_to_render():
    failure = RuntimeError('<script>alert(1)</script> card 4111 1111 1111 1111 rejected')
    outcome = recover(Step(*[failure] * 3), lambda r: True, lambda t, e: "<b>retry</b>", **CASE)
    assert "4111" not in outcome.packet.last_error and "<CARD>" in outcome.packet.last_error
    text = outcome.packet.safe_text()
    assert "<script>" not in text and "&lt;script&gt;" in text and "<b>" not in text


def test_the_critique_prompt_is_clinical_and_capped():
    prompts = []
    critique = llm_critique(lambda prompt: prompts.append(prompt) or "x" * 5000)
    outcome = recover(Step(ValueError("bad")), lambda r: True, critique, **CASE)
    assert outcome.ok and "No apologies" in prompts[0] and "ValueError: bad" in prompts[0]
    assert outcome.trajectory[1]["critique"] == "x" * CRITIQUE_LIMIT
