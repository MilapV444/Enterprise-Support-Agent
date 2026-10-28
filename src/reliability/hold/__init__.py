"""Requests held while a system is down (NFR-17 / RP-ADP-02: RP-D7; AC-6).

When a read cannot run because its system's breaker is open (or its retries ran out on transient failures),
the turn does not serve a cached account fact (MS-D6). It starts HeldRequestWorkflow instead:

    tell the customer the request is kept -> every probe interval, try the read again -> on success, the
    answer goes to the conversation's inbox (the outbound event log, delivered when the customer is back)
    -> if the session has ended, the call is refused, or 24 hours pass, a person takes the case over

Each try runs the read through the tool executor, which resolves the principal from the live session again,
mints a fresh credential and screens the output, so authorization and account facts are re-checked at the
time of the answer. The try, the reply and its delivery happen inside one activity: Temporal's history holds
only ids, the session reference, the call and the masked question, never what the system returned. The try is
not retried by Temporal (the executor is the one retry layer, RP-D13); a failed try counts as still down.

This module imports only the stdlib and temporalio so it stays inside Temporal's workflow sandbox; the
activities are in reliability.hold.activities.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

TASK_QUEUE = "held-requests"
MAX_HOLD = timedelta(hours=24)            # RP-Q4
PROBE_EVERY = timedelta(minutes=5)
HOLDABLE = {"SYSTEM_UNAVAILABLE", "TRANSIENT"}   # breaker open, or transient failures past the retries
ONCE = RetryPolicy(maximum_attempts=1)
DURABLE = RetryPolicy(initial_interval=timedelta(seconds=1), backoff_coefficient=2.0,
                      maximum_interval=timedelta(minutes=1), maximum_attempts=10)
OPTIONS = {"start_to_close_timeout": timedelta(minutes=2)}


@dataclass
class HoldStart:
    hold_id: str
    tenant_id: str
    session_id: str                  # a reference to the customer's session, not a credential
    case_id: str
    conversation_id: str
    tool_id: str                     # a read-only tool
    arguments: dict[str, Any] = field(default_factory=dict)
    question: str = ""               # masked
    probe_seconds: float = PROBE_EVERY.total_seconds()
    max_hold_seconds: float = MAX_HOLD.total_seconds()


@dataclass
class Attempt:
    outcome: str                     # "delivered", "down" or "refused"
    code: str | None = None


def holdable(tool_risk, failure_code):
    """Whether a failed call is held: reads only, and only failures a recovering system can clear."""
    return tool_risk == "read_only" and failure_code in HOLDABLE


async def start_hold(client, start, tool_risk, failure_code, task_queue=TASK_QUEUE):
    """Hold a failed read (refuses anything else); returns the workflow handle."""
    if not holdable(tool_risk, failure_code):
        raise ValueError(f"not held: a {tool_risk} call that failed with {failure_code}")
    return await client.start_workflow(HeldRequestWorkflow.run, start, task_queue=task_queue,
                                       id=f"hold:{start.tenant_id}:{start.hold_id}")


@workflow.defn
class HeldRequestWorkflow:
    @workflow.run
    async def run(self, start: HoldStart) -> str:
        await workflow.execute_activity("hold_notify", start, retry_policy=DURABLE, **OPTIONS)
        deadline = workflow.now() + timedelta(seconds=start.max_hold_seconds)
        tries = 0
        while True:
            tries += 1
            try:
                attempt = await workflow.execute_activity("hold_attempt", args=[start, tries],
                                                          result_type=Attempt, retry_policy=ONCE, **OPTIONS)
            except ActivityError:  # the try itself failed: the system counts as still down
                attempt = Attempt("down", "ACTIVITY_FAILED")
            if attempt.outcome == "delivered":
                return "delivered"
            if attempt.outcome == "refused":
                await workflow.execute_activity("hold_hand_over", args=[start, attempt.code or "REFUSED"],
                                                retry_policy=DURABLE, **OPTIONS)
                return "handed_over"
            if workflow.now() + timedelta(seconds=start.probe_seconds) > deadline:
                await workflow.execute_activity("hold_hand_over", args=[start, "STILL_DOWN"],
                                                retry_policy=DURABLE, **OPTIONS)
                return "handed_over"
            await workflow.sleep(start.probe_seconds)
