"""M4-04: framework scenario 6, tool degradation and a breaker trip, end to end (NFR-17, AC-6).

"What is the current subscription tier and renewal date for tenant Globex Corp?" while the CRM is failing: the
read's retries run out (or its breaker is open), so the turn serves no cached account fact and holds the
request in a Temporal workflow. When the CRM is back, the read runs again through the executor (session,
credential and screening checked again) and the answer goes to the conversation's inbox; if the CRM stays down
past the hold (24 h, simulated here in seconds), or the session has ended, a person takes the case over.

Real: Temporal, Postgres, the tool executor with its retries and breaker. Fake: the CRM's HTTP API, the
identity service's sessions, Jev and the drafting model.
"""

import asyncio
import json
import subprocess
import uuid
from pathlib import Path

import httpx
import psycopg
import pytest
from pydantic import BaseModel
from temporalio.client import Client

from channels import sessions
from core.orchestrator.decisions import Answer, DecisionEngine
from data import events
from data.migrate import migrate, psql
from hitl import queues
from hitl.queues import Queues
from reliability.hold import HoldStart, holdable, start_hold
from reliability.hold.activities import HANDED_OVER, HELD, HoldActivities, worker
from safety.authz.cedar import Authorizer
from safety.pii.tokens import Tokenizer
from safety.screening.pipeline import Screener
from safety.screening.scorers import pattern_injection
from tests.tools.execution.test_execution import FakeIdentity, http_json
from tools.execution import Executor, System, ToolFailure
from tools.execution.calls import ToolCall
from tools.registry import Registry
from tools.schemas import arg
from tools.validation import approvals

ROOT = Path(__file__).resolve().parents[2]
DB = "test_e2e_degradation"
DSN = f"postgresql://agent:change-me@127.0.0.1:5432/{DB}"  # credentials from .env.example
QUESTION = "What is the current subscription tier and renewal date for tenant Globex Corp?"
FRESH = {"account": "globex", "tier": "Enterprise", "renewal": "2026-12-01"}


class AccountArgs(BaseModel):
    account_id: str = arg(sensitive=True)


def registry():
    reg = Registry()
    reg.tool("crm.get_subscription", args=AccountArgs, description="Read an account's subscription",
             risk="read_only", stages={"DELIBERATING"}, author="ana", reviewed_by="ben")(
        lambda a: http_json("GET", f"https://crm.test/accounts/{a.account_id}/subscription"))
    reg.tool("crm.cancel_subscription", args=AccountArgs, description="Cancel a subscription",
             risk="high_risk_write", stages={"DELIBERATING"}, author="ana", reviewed_by="ben")(lambda a: {})
    return reg.freeze()


class Crm:
    """The CRM's API: 503 while down, the live subscription once it is back; every request is kept."""

    def __init__(self):
        self.down, self.requests, self.served = True, [], 0

    def __call__(self, request):
        self.requests.append(request)
        if self.down:
            return httpx.Response(503, json={"error": "maintenance"})
        self.served += 1
        return httpx.Response(200, json=FRESH)


class Jev:
    def evaluate(self, state, questions):
        return {"acuity": Answer(2.0, 0.9, 2)}


def connect():
    return psycopg.connect(DSN, autocommit=True)


@pytest.fixture(scope="module")
def database():
    subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env.example",
                    "up", "-d", "--wait", "postgres", "temporal"], cwd=ROOT, check=True, capture_output=True)
    psql("postgres", f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
    psql("postgres", f'CREATE DATABASE "{DB}"')
    migrate("main", DB)
    for module in (sessions, events, approvals, queues):
        module.apply_schema(DB)
    psql(DB, "INSERT INTO tenants (id, name, region) VALUES ('t_us', 'Acme', 'US')")


class World:
    def __init__(self):
        self.crm, self.clock, self.recover_at, self.session_ends = Crm(), [0.0], None, False
        systems = {"crm": System("crm", frozenset({"crm.test"}), "obo", "account-tools")}
        self.executor = Executor(registry(), systems,
                                 Screener(lambda text: (0.0, []), pattern_injection), identity=FakeIdentity(),
                                 authorizer=Authorizer(), transport=httpx.MockTransport(self.crm),
                                 sleep=lambda seconds: None, clock=lambda: self.clock[0])
        self.queues = Queues(connect, DecisionEngine(Jev()), Tokenizer(b"e2e-hold"), lambda c: None,
                             alert=lambda *a: None, notify=lambda *a: None)
        with connect() as conn:
            session = sessions.start(conn, "t_us", "sarah", "T2_SSO")
            self.conversation = f"conv-{uuid.uuid4().hex[:8]}"
            sessions.open_conversation(conn, "t_us", "sarah", session, self.conversation)
            self.case_id = sessions.link_case(conn, "t_us", self.conversation)

    def answer(self, question, screened):
        """The drafting model, from the fresh read only."""
        data = json.loads(screened[screened.index("{"):screened.rindex("}") + 1])
        return f"Globex Corp is on the {data['tier']} tier, renewing on {data['renewal']}."

    def events(self):
        return [(kind, json.loads(data)) for kind, data in psql(
            DB, f"SELECT event_type, data::text FROM outbound_event_log WHERE conversation_id = "
                f"'{self.conversation}' ORDER BY id")]

    def start(self, session_id="s-sarah", max_hold=4.0):
        return HoldStart(hold_id=uuid.uuid4().hex[:12], tenant_id="t_us", session_id=session_id,
                         case_id=self.case_id, conversation_id=self.conversation,
                         tool_id="crm.get_subscription", arguments={"account_id": "globex"},
                         question=QUESTION, probe_seconds=0.5, max_hold_seconds=max_hold)


@pytest.fixture
def world(database):
    return World()


def turn(world, start):
    """The live read fails; nothing cached is served; the request is held. Returns (failure code, outcome)."""
    async def go():
        client = await Client.connect("127.0.0.1:7233")
        queue = f"hold-{uuid.uuid4().hex}"
        try:
            world.executor.run(world_call(start))
        except ToolFailure as failure:
            code = failure.code
        else:
            pytest.fail("the CRM was supposed to be down")
        async with worker(client, HoldActivities(world.executor, connect, world.queues, world.answer), queue):
            handle = await start_hold(client, start, "read_only", code, task_queue=queue)
            await asyncio.sleep(1.2)
            first = world.events()
            if world.recover_at is not None:
                await asyncio.sleep(world.recover_at)
                world.clock[0] += 31          # past the breaker's cool-down
                world.crm.down = False
                if world.session_ends:
                    world.executor.identity.SESSIONS = {}  # the customer's session ended during the hold
            outcome = await handle.result()
            history = await handle.fetch_history()
        return code, outcome, first, history
    return asyncio.run(go())


def world_call(start):
    return ToolCall(tool_call_id="turn-1", tool_id=start.tool_id, arguments=start.arguments, tenant_id="t_us",
                    principal_id="sarah", case_id=start.case_id, checkpoint_id="turn",
                    session_id=start.session_id)


def test_scenario_6_the_request_is_held_and_the_fresh_answer_reaches_the_inbox_when_the_crm_is_back(world):
    world.recover_at = 0.5
    code, outcome, first, history = turn(world, world.start(max_hold=30))
    assert code == "TRANSIENT" and outcome == "delivered"
    assert first == [("status", {"state": "held", "hold_id": first[0][1]["hold_id"], "text": HELD})]
    assert "Enterprise" not in json.dumps(first)                          # no cached account fact served
    final = [data for kind, data in world.events() if kind == "final"]
    assert final == [{"text": "Globex Corp is on the Enterprise tier, renewing on 2026-12-01.",
                      "hold_id": first[0][1]["hold_id"], "deferred": True}]
    escalated = psql(DB, f"SELECT count(*) FROM escalations WHERE conversation_id = '{world.conversation}'")
    assert escalated == [["0"]]
    raw = history.to_json()
    assert "Enterprise" not in raw and "2026-12-01" not in raw            # history holds no account data


def test_scenario_6_a_crm_down_past_the_hold_goes_to_a_person(world):
    world.recover_at = None
    _, outcome, _, _ = turn(world, world.start(max_hold=3))
    assert outcome == "handed_over"
    kinds = [kind for kind, _ in world.events()]
    assert kinds[0] == "status" and kinds[-1] == "handoff" and "final" not in kinds
    assert world.events()[-1][1] == {"state": "queued", "hold_id": world.events()[0][1]["hold_id"],
                                     "text": HANDED_OVER, "reason": "STILL_DOWN"}
    escalated = psql(DB, "SELECT reason, queue, status FROM escalations "
                         f"WHERE conversation_id = '{world.conversation}'")
    assert escalated == [["system_dependency_held", "queue_technical", "waiting"]]


def test_scenario_6_the_breaker_opens_while_the_crm_stays_down(world):
    world.recover_at = None
    turn(world, world.start(max_hold=3))
    # the turn's call and its three retries, then the first held try, whose failure opens the breaker: every
    # later try fails fast without reaching the CRM
    assert len(world.crm.requests) == 5


def test_scenario_6_a_session_that_ends_during_the_hold_is_never_answered_on_its_behalf(world):
    world.recover_at, world.session_ends = 0.5, True
    _, outcome, _, _ = turn(world, world.start(max_hold=30))
    assert outcome == "handed_over"
    assert world.events()[-1][1]["reason"] == "AUTHENTICATION_EXPIRED"
    assert "final" not in [kind for kind, _ in world.events()]
    assert world.crm.served == 0               # the recovered CRM is never read without a live session


def test_scenario_6_a_reply_that_fails_the_output_checks_is_not_delivered(world):
    world.recover_at = 0.5
    world.answer = lambda question, screened: "Use the key sk_live_4eC39HqLyjWDarjtT1zdp7dc to log in."
    _, outcome, _, _ = turn(world, world.start(max_hold=30))
    assert outcome == "handed_over" and world.events()[-1][1]["reason"] == "REPLY_HELD"
    assert "final" not in [kind for kind, _ in world.events()] and "sk_live" not in json.dumps(world.events())


@pytest.mark.parametrize("risk, code", [("high_risk_write", "TRANSIENT"), ("read_only", "FORBIDDEN"),
                                        ("read_only", "AUTHENTICATION_EXPIRED"), ("read_only", "REJECTED")])
def test_only_reads_that_a_recovery_can_clear_are_held(risk, code):
    assert not holdable(risk, code)
    with pytest.raises(ValueError, match="not held"):
        asyncio.run(start_hold(None, HoldStart("h", "t", "s", "c", "v", "crm.x"), risk, code))
    assert holdable("read_only", "SYSTEM_UNAVAILABLE") and holdable("read_only", "TRANSIENT")
