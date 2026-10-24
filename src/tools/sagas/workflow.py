"""The saga workflow (FR-24 / TA-ADP-05: TA-D8, TA-D17, TA-D18). Imports only the stdlib and temporalio so it
stays inside Temporal's workflow sandbox; the activities are in tools.sagas.activities.

    check the plan -> run the steps in order -> on the first failure, compensate the completed steps in
    reverse, each once -> a compensation that still fails stops the rollback for a human

Everything here is workflow data and so lives in Temporal's history. The input therefore only identifies the
request: tenant, the customer's session (a reference, not a credential), case and conversation. Who the
principal is, their roles, the handler and every credential are resolved inside the activities from trusted
sources; nothing in the input grants a privilege.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

TASK_QUEUE = "sagas"
COMPENSATION_ATTEMPTS = 3
ONCE = RetryPolicy(maximum_attempts=1)
COMPENSATE = RetryPolicy(initial_interval=timedelta(seconds=1), backoff_coefficient=2.0,
                         maximum_interval=timedelta(seconds=30), maximum_attempts=COMPENSATION_ATTEMPTS,
                         non_retryable_error_types=["FORBIDDEN", "NOT_APPROVED", "INVALID_ARGUMENTS",
                                                    "AUTHENTICATION_EXPIRED", "STEP_UP_REQUIRED"])


@dataclass
class SagaStep:
    step_id: str
    tool_id: str
    arguments: dict[str, Any]
    resource: dict[str, Any] = field(default_factory=dict)     # Cedar target, as tools.validation needs
    compensation_tool_id: str | None = None
    compensation_arguments: dict[str, Any] = field(default_factory=dict)
    compensation_resource: dict[str, Any] = field(default_factory=dict)  # empty: the step's own resource
    snapshot_tool_id: str | None = None      # reviewed read-only tool for before / after state
    approval_request_id: str | None = None   # required for the irreversible last step


@dataclass
class SagaStart:
    saga_id: str
    tenant_id: str
    session_id: str                          # the customer's live session: a reference, not a credential
    case_id: str
    conversation_id: str
    message: str                             # the masked customer turn the gate shows Jev
    steps: list[SagaStep]


@dataclass
class StepOutcome:
    ok: bool
    error_code: str | None = None


@dataclass
class SagaOutcome:
    status: str  # COMPLETED, COMPENSATED; COMPENSATION_FAILED or UNCERTAIN_STEP go to a human
    completed: list[str] = field(default_factory=list)
    compensated: list[str] = field(default_factory=list)
    failed_step: str | None = None
    error_code: str | None = None


async def start_saga(client, start, task_queue=TASK_QUEUE):
    return await client.start_workflow(SagaWorkflow.run, start, task_queue=task_queue,
                                       id=f"saga:{start.tenant_id}:{start.saga_id}")


@workflow.defn
class SagaWorkflow:
    @workflow.run
    async def run(self, start: SagaStart) -> SagaOutcome:
        options = {"start_to_close_timeout": timedelta(minutes=5)}
        await workflow.execute_activity("saga_plan", start, retry_policy=ONCE, **options)
        outcome = SagaOutcome("COMPLETED")
        done = []
        for index, step in enumerate(start.steps):
            try:
                result = await workflow.execute_activity("saga_step", args=[start, index],
                                                         result_type=StepOutcome, retry_policy=ONCE,
                                                         **options)
            except ActivityError:  # the activity itself failed (e.g. its audit write): treat as a failed step
                result = StepOutcome(False, "ACTIVITY_FAILED")
            if not result.ok:
                outcome.failed_step, outcome.error_code = step.step_id, result.error_code
                break
            done.append(index)
            outcome.completed.append(step.step_id)
        if outcome.failed_step is None:
            return outcome
        for index in reversed(done):
            step = start.steps[index]
            if step.compensation_tool_id is None:
                continue  # a read: nothing to undo
            try:
                await workflow.execute_activity("saga_compensate", args=[start, index],
                                                retry_policy=COMPENSATE, **options)
            except ActivityError:
                outcome.status = "COMPENSATION_FAILED"
                return outcome  # never loop or guess on a failed rollback: a specialist takes it from here
            outcome.compensated.append(step.step_id)
        # A step whose activity failed may or may not have taken effect: rolled back around it, but a human
        # has to check that step itself.
        outcome.status = "UNCERTAIN_STEP" if outcome.error_code == "ACTIVITY_FAILED" else "COMPENSATED"
        return outcome
