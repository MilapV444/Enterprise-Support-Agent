"""M1-05: the Temporal ticket workflow around LangGraph turns, with reply / approval / cancel signals (FR-2).
Runs against the compose Temporal dev server and Postgres; timeouts are shortened through the start input."""

import asyncio
import subprocess
import uuid
from pathlib import Path

import pytest
from temporalio.client import Client, WorkflowFailureError
from temporalio.exceptions import ApplicationError, WorkflowAlreadyStartedError

from data.migrate import psql
from tests.orchestrator.test_statechart import SOP, Hooks
from workflows.activities import TurnActivities, worker
from workflows.ticket import TicketStart, TurnRequest, start_ticket

ROOT = Path(__file__).resolve().parents[2]
DB = "test_workflows"
DSN = f"postgresql://agent:change-me@127.0.0.1:5432/{DB}"  # credentials from .env.example
AMBIGUOUS = {"intent": "?", "acuity": 3, "confidence": 0.6}
REFUND = {"parameters": {"amount": 1500}, "missing": []}


@pytest.fixture(scope="module", autouse=True)
def stack():
    subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env.example",
                    "up", "-d", "--wait", "postgres", "temporal"], cwd=ROOT, check=True, capture_output=True)
    psql("postgres", f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
    psql("postgres", f'CREATE DATABASE "{DB}"')

    async def connected():
        for _ in range(60):
            try:
                return await (await Client.connect("127.0.0.1:7233")).service_client.check_health()
            except Exception:
                await asyncio.sleep(1)

    assert asyncio.run(connected())


def start(case, **timeouts):
    return TicketStart(tenant_id="t_us", case_id=f"{case}-{uuid.uuid4().hex[:6]}", session_id="s1",
                       text="My invoice is wrong", **timeouts)


def ticket(hooks, start_input, actions=None):
    """Run one ticket on a fresh task queue; `actions(handle)` drives it while it runs -> (result, state)."""
    async def go():
        client = await Client.connect("127.0.0.1:7233")
        queue = f"test-{uuid.uuid4().hex}"
        async with worker(client, TurnActivities(hooks, DSN), queue):
            handle = await start_ticket(client, start_input, queue)
            if actions:
                await actions(handle)
            result = await handle.result()
            return result, await handle.query("state")
    return asyncio.run(go())


async def until(handle, status, seconds=30):
    for _ in range(seconds * 10):
        if (await handle.query("state"))["status"] == status:
            return
        await asyncio.sleep(0.1)
    raise TimeoutError(status)


def test_a_simple_ticket_resolves_in_one_turn():
    result, state = ticket(Hooks(), start("simple"))
    assert result == "RESOLVED" and state["turns"] == 1 and state["checkpoint_id"]


def test_a_customer_reply_signal_continues_the_case():
    async def reply(handle):
        await until(handle, "PENDING_CUSTOMER")
        await handle.signal("reply", "Here is my new address")

    result, state = ticket(Hooks(triage=[AMBIGUOUS, SOP]), start("reply"), reply)
    assert (result, state["turns"]) == ("RESOLVED", 2)


@pytest.mark.parametrize("approved, outcome, executed",
                         [(True, "RESOLVED", 1), (False, "APPROVAL_DENIED", 0)])
def test_approval_signal_decides_the_change(approved, outcome, executed):
    hooks = Hooks(collect=REFUND)

    async def decide(handle):
        await until(handle, "AWAITING_APPROVAL")
        assert hooks.calls["execute_sop"] == 0
        await handle.signal("decide", approved)

    result, _ = ticket(hooks, start("approval"), decide)
    assert (result, hooks.calls["execute_sop"]) == (outcome, executed)


def test_timers_close_or_escalate_waiting_tickets():
    quiet, _ = ticket(Hooks(triage=AMBIGUOUS), start("quiet", reply_timeout_seconds=2))
    assert quiet == "AUTO_CLOSED_INACTIVITY"
    stuck, _ = ticket(Hooks(collect=REFUND), start("stuck", approval_timeout_seconds=2))
    assert stuck == "ESCALATED_HITL"


def test_cancel_signal_stops_a_waiting_ticket():
    hooks = Hooks(collect=REFUND)

    async def cancel(handle):
        await until(handle, "AWAITING_APPROVAL")
        await handle.signal("cancel", "customer withdrew")

    result, _ = ticket(hooks, start("cancel"), cancel)
    assert (result, hooks.calls["execute_sop"]) == ("CANCELLED", 0)


def test_a_crashed_turn_is_retried_from_its_checkpoint():
    crashes = [RuntimeError("worker died")]

    def flaky(state):
        if crashes:
            raise crashes.pop()
        return {"response": "Done."}

    hooks = Hooks(sop=flaky)
    result, _ = ticket(hooks, start("crash"))
    assert result == "RESOLVED"
    assert (hooks.calls["triage"], hooks.calls["collect"], hooks.calls["execute_sop"]) == (1, 1, 2)


def test_a_ticket_has_one_workflow_at_a_time():
    async def twice():
        client = await Client.connect("127.0.0.1:7233")
        queue, first = f"test-{uuid.uuid4().hex}", start("dup", reply_timeout_seconds=30)
        async with worker(client, TurnActivities(Hooks(triage=AMBIGUOUS), DSN), queue):
            handle = await start_ticket(client, first, queue)
            with pytest.raises(WorkflowAlreadyStartedError):
                await start_ticket(client, first, queue)
            await handle.signal("cancel", "test done")
            return await handle.result()
    assert asyncio.run(twice()) == "CANCELLED"


def test_a_repeated_turn_applies_its_event_once():
    hooks = Hooks()
    activities = TurnActivities(hooks, DSN)
    request = TurnRequest("t_us", f"repeat-{uuid.uuid4().hex[:6]}", "s1", "wf/run/1",
                          {"type": "USER_MESSAGE", "text": "hi"})
    first, again = activities.run_turn(request), activities.run_turn(request)
    assert first == again and first.stage == "RESOLVED"
    assert hooks.calls["triage"] == 1


def test_an_unfinished_turn_from_another_run_is_not_mixed_with_a_new_one():
    def crash(state):
        raise RuntimeError("worker died")

    activities = TurnActivities(Hooks(sop=crash), DSN)
    case = f"orphan-{uuid.uuid4().hex[:6]}"
    with pytest.raises(RuntimeError):
        activities.run_turn(TurnRequest("t_us", case, "s1", "old/run/1", {"type": "USER_MESSAGE"}))
    with pytest.raises(ApplicationError, match="unfinished turn"):
        activities.run_turn(TurnRequest("t_us", case, "s1", "new/run/1", {"type": "USER_MESSAGE"}))


def test_workflow_failure_surfaces_when_retries_run_out():
    def always(state):
        raise RuntimeError("SOP backend down")

    with pytest.raises(WorkflowFailureError):
        ticket(Hooks(sop=always), start("down"))
