"""Dual-process circuit breaker around one step (FR-4 / ADP-04).

The step runs; Jev (not the model that ran it) decides whether it worked, and anything short of a
confident yes is a failure. A failed step gets at most 2 Reflexion retries, each with one fresh verbal
critique (only the latest critique is passed on). The whole trajectory may use at most 4 execution steps.
Past either limit, or on a failure no retry can fix (NonRetryable), the breaker trips and returns an
incident packet for a human.

    outcome = recover(step, verify, critique, tenant_id=..., case_id=...)
    step(critique: str | None) -> result      verify(result) -> bool      critique(trajectory, error) -> str
"""

from dataclasses import dataclass, field
from typing import Any

from core.orchestrator.decisions import mask
from schemas.diagnostic import IncidentDiagnosticPacket

MAX_TRIALS = 2
MAX_STEPS = 4
STEP_CHECK_CONFIDENCE = 0.85
STEP_CHECK_QUESTION = "Did this step achieve its intended outcome without unhandled errors?"
CRITIQUE_LIMIT = 1_200  # characters; one short critique, never a growing log


class NonRetryable(Exception):
    """A failure that retrying cannot fix (e.g. permission denied): trip at once."""


@dataclass
class Outcome:
    ok: bool
    result: Any = None
    packet: IncidentDiagnosticPacket | None = None
    trajectory: list[dict[str, Any]] = field(default_factory=list)
    steps: int = 0


def recover(step, verify, critique, *, tenant_id, case_id, steps_used=0, max_trials=MAX_TRIALS,
            max_steps=MAX_STEPS):
    trajectory, latest, trials = [], None, 0

    def trip(reason, error):
        packet = IncidentDiagnosticPacket(tenant_id=tenant_id, case_id=case_id, failure_reason=reason,
                                          steps=steps_used, reflexion_trials=trials, trajectory=trajectory,
                                          last_error=error)
        return Outcome(False, None, packet, trajectory, steps_used)

    while True:
        if steps_used >= max_steps:
            return trip("step ceiling reached", trajectory[-1]["error"] if trajectory else None)
        steps_used += 1
        retryable, result = True, None
        try:
            result = step(latest)
            error = None if verify(result) else "the step check did not confirm success"
        except NonRetryable as failure:
            error, retryable = f"{type(failure).__name__}: {failure}", False
        except Exception as failure:  # any step failure is input to the critique, never a crash of the turn
            error = f"{type(failure).__name__}: {failure}"
        error = mask(error).text if error else None
        trajectory.append({"attempt": len(trajectory) + 1, "critique": latest, "error": error,
                           "ok": error is None})
        if error is None:
            return Outcome(True, result, None, trajectory, steps_used)
        if not retryable:
            return trip("not retryable", error)
        if trials >= max_trials:
            return trip("reflexion trials exhausted", error)
        trials += 1
        latest = critique(trajectory, error)[:CRITIQUE_LIMIT]


def jev_step_check(engine, describe=str, confidence=STEP_CHECK_CONFIDENCE):
    """verify(result) backed by a Jev guard: masked step summary in, confident yes or failure out."""
    def verify(result):
        state = {"step_result": mask(describe(result)[:4_000])}
        return engine.guard("step_success", STEP_CHECK_QUESTION, state, min_confidence=confidence)
    return verify


CRITIQUE_PROMPT = """You review a failed step of a support agent. No apologies, no pleasantries.

Attempts so far:
{trajectory}

Last error:
{error}

In at most three sentences: name the exact input, assumption or condition that caused the failure, and the
different approach the next attempt should take. Do not invent parameters or tools."""


def llm_critique(complete):
    """critique(trajectory, error) over `complete(prompt) -> str`, any chat model."""
    def critique(trajectory, error):
        lines = "\n".join(f"{a['attempt']}. {'ok' if a['ok'] else a['error']}" for a in trajectory)
        return complete(CRITIQUE_PROMPT.format(trajectory=lines, error=error)).strip()
    return critique
