"""The Temporal ticket workflow: the durable outer loop around a case (FR-2 / ADP-02).

Temporal holds only ids and status; the case's real state lives in the LangGraph checkpoint (MS-D8). Each turn
runs the statechart in the `run_turn` activity (see workflows.activities); between turns the workflow waits on
durable timers for a customer reply (24 h) or an approval decision (48 h), delivered as signals:

    reply(text)        a customer message while the case waits for the customer
    decide(approved)   the approval outcome while the case waits for approval
    cancel(reason)     stop the ticket at the next wait or after the running turn

This module imports only the stdlib and temporalio so it stays inside Temporal's workflow sandbox.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

TASK_QUEUE = "tickets"
TURN_RETRY = RetryPolicy(initial_interval=timedelta(seconds=1), backoff_coefficient=2.0,
                         maximum_interval=timedelta(seconds=30), maximum_attempts=3,
                         non_retryable_error_types=["IllegalTransition", "ValidationError"])


@dataclass
class TicketStart:
    tenant_id: str
    case_id: str
    session_id: str
    text: str
    reply_timeout_seconds: float = 24 * 3600
    approval_timeout_seconds: float = 48 * 3600


@dataclass
class TurnRequest:
    tenant_id: str
    case_id: str
    session_id: str
    event_id: str  # unique per turn: a retried activity never applies the same event twice
    event: dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnOutcome:
    stage: str | None
    checkpoint_id: str | None


def workflow_id(tenant_id, case_id):
    return f"ticket:{tenant_id}:{case_id}"


async def start_ticket(client, start, task_queue=TASK_QUEUE):
    """Start the ticket's workflow; a second start for the same case fails while the first is running."""
    return await client.start_workflow(TicketWorkflow.run, start, task_queue=task_queue,
                                       id=workflow_id(start.tenant_id, start.case_id))


@workflow.defn
class TicketWorkflow:
    def __init__(self):
        self.status, self.stage, self.checkpoint_id, self.turns = "ACTIVE", None, None, 0
        self.replies: list[str] = []
        self.approved: bool | None = None
        self.cancel_reason: str | None = None

    @workflow.run
    async def run(self, start: TicketStart) -> str:
        event, denied = {"type": "USER_MESSAGE", "text": start.text}, False
        while True:
            await self._turn(start, event)
            if self.cancel_reason is not None:
                self.status = "CANCELLED"
            elif self.stage == "AWAITING_CUSTOMER":
                self.status = "PENDING_CUSTOMER"
                waited = await self._wait(lambda: bool(self.replies), start.reply_timeout_seconds)
                if waited == "ok":
                    event = {"type": "USER_MESSAGE", "text": self.replies.pop(0)}
                    continue
                self.status = "CANCELLED" if waited == "cancelled" else "AUTO_CLOSED_INACTIVITY"
            elif self.stage == "AWAITING_APPROVAL":
                self.status = "AWAITING_APPROVAL"
                waited = await self._wait(lambda: self.approved is not None, start.approval_timeout_seconds)
                if waited == "ok":
                    denied, self.approved = not self.approved, None
                    event = {"type": "APPROVAL_DENIED" if denied else "APPROVAL_GRANTED"}
                    continue
                self.status = "CANCELLED" if waited == "cancelled" else "ESCALATED_HITL"
            else:
                finished = self.stage or "IGNORED"
                self.status = "APPROVAL_DENIED" if denied and finished == "RESOLVED" else finished
            return self.status

    async def _turn(self, start, event):
        self.turns += 1
        info = workflow.info()
        outcome = await workflow.execute_activity(
            "run_turn",
            TurnRequest(start.tenant_id, start.case_id, start.session_id,
                        f"{info.workflow_id}/{info.run_id}/{self.turns}", event),
            result_type=TurnOutcome, start_to_close_timeout=timedelta(minutes=2), retry_policy=TURN_RETRY)
        self.stage, self.checkpoint_id = outcome.stage, outcome.checkpoint_id

    async def _wait(self, ready, seconds):
        try:
            await workflow.wait_condition(lambda: ready() or self.cancel_reason is not None,
                                          timeout=timedelta(seconds=seconds))
        except asyncio.TimeoutError:
            return "timeout"
        return "cancelled" if self.cancel_reason is not None else "ok"

    @workflow.signal
    def reply(self, text: str) -> None:
        self.replies.append(text)

    @workflow.signal
    def decide(self, approved: bool) -> None:
        self.approved = approved

    @workflow.signal
    def cancel(self, reason: str) -> None:
        self.cancel_reason = reason

    @workflow.query
    def state(self) -> dict:
        return {"status": self.status, "stage": self.stage, "checkpoint_id": self.checkpoint_id,
                "turns": self.turns}
