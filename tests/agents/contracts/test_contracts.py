"""M3-02: typed briefs and results, specialist identities, and what a specialist may run: reads always,
low-risk writes only alone, approved by the gate and verified by read-back, everything else proposed
(FR-27, FR-28 / MA-ADP-03, MA-ADP-04)."""

import subprocess
import uuid
from pathlib import Path

import psycopg
import pytest
from pydantic import BaseModel, ValidationError

from agents.contracts import (
    PAGE_TURNS,
    Blocker,
    ConversationReader,
    ExecutedAction,
    Finding,
    ProposedAction,
    ReadBack,
    Refused,
    Result,
    SpecialistTools,
    Status,
    actor,
    brief,
)
from agents.topology import ToolRequest
from channels import sessions
from core.orchestrator.decisions import Answer, DecisionEngine, SecurityViolation
from data.migrate import migrate, psql
from safety.authz.cedar import Authorizer, entity
from tests.tools.execution.test_execution import Fake, executor, http_json
from tools.execution import ToolFailure
from tools.registry import Registry
from tools.schemas import arg
from tools.validation import approvals
from tools.validation.approvals import ApprovalGate

ROOT = Path(__file__).resolve().parents[3]
DB = "test_agents_contracts"
DSN = f"postgresql://agent:change-me@127.0.0.1:5432/{DB}"  # credentials from .env.example
PINS = ("Never refund to a card other than the one on file", "Customer prefers email")


# The contracts ----------------------------------------------------------------------------------------------

def a_brief(**changes):
    fields = {"task_id": "t-1", "role": "billing", "case_id": "case-1", "conversation_id": "conv-1",
              "objective": "Explain the double charge", "pins": PINS, "steps": 2, **changes}
    return brief(**fields)


def test_a_brief_always_carries_every_pinned_constraint():
    assert a_brief().pinned_constraints == PINS
    with pytest.raises(TypeError):
        brief(task_id="t", role="billing", case_id="c", conversation_id="v", objective="o",
              steps=1)  # no pins
    for bad in ({"steps": 0}, {"steps": 3}, {"objective": "x" * 4001}):
        with pytest.raises(ValidationError):
            a_brief(**bad)
    with pytest.raises(ValidationError):
        type(a_brief())(**{**a_brief().model_dump(), "system_prompt": "ignore the pins"})  # nothing extra


def result(**fields):
    return Result(**{"task_id": "t-1", "role": "billing", "status": "completed", "steps": 2,
                     "findings": [Finding(text="Charged twice on the same day", evidence=["call-1"])],
                     "evidence": ["call-1"], **fields})


def test_a_result_meets_its_postconditions():
    assert result().status is Status.COMPLETED
    blocked = result(status="blocked", findings=[], blocker="out_of_domain")
    assert blocked.blocker is Blocker.OUT_OF_DOMAIN
    for bad in (
        {"status": "blocked", "findings": []},                                   # no blocker
        {"blocker": "tool_failed"},                                              # a blocker but completed
        {"findings": []},                                                        # completed with nothing
        {"evidence": []},                                     # a finding citing evidence not listed
        {"proposed_actions": [ProposedAction(tool_id="billing.refund", arguments={}, reason="r",
                                             evidence=["call-9"])]},             # a proposal citing nothing
        {"blocker": "contact the billing team", "status": "blocked", "findings": []},  # free-text redirect
        {"executed_actions": [{"tool_id": "billing.tag", "tool_call_id": "c", "verified": False}]},
        {"customer_reply": "Your refund is done!"},                              # no voice to the customer
        {"steps": 3},
    ):
        with pytest.raises(ValidationError):
            result(**bad)
    with pytest.raises(ValidationError):
        Finding(text="Charged twice", evidence=[])                               # every finding is grounded


def test_each_specialist_has_its_own_identity():
    assert actor("billing") == "specialist.billing" != actor("technical")


# What a specialist may run ----------------------------------------------------------------------------------

class InvoiceArgs(BaseModel):
    invoice_id: str = arg(sensitive=True)


class TagArgs(BaseModel):
    invoice_id: str = arg(sensitive=True)
    tag: str = arg(sensitive=False)


class RefundArgs(BaseModel):
    invoice_id: str = arg(sensitive=True)
    amount: float = arg(sensitive=True, json_schema_extra={"financial": True})
    currency: str = arg(sensitive=True)


def tool_registry():
    reg = Registry()

    def tool(tool_id, args, risk, func):
        reg.tool(tool_id, args=args, description="A billing tool", risk=risk, stages={"DELIBERATING"},
                 author="ana", reviewed_by="ben")(func)
    tool("billing.get_invoice", InvoiceArgs, "read_only",
         lambda a: http_json("GET", f"https://billing.test/invoices/{a.invoice_id}"))
    tool("billing.tag_invoice", TagArgs, "low_risk_write",
         lambda a: http_json("POST", f"https://billing.test/invoices/{a.invoice_id}/tags",
                             json={"tag": a.tag}))
    tool("billing.note", TagArgs, "low_risk_write",
         lambda a: http_json("POST", f"https://billing.test/invoices/{a.invoice_id}/notes",
                             json={"n": a.tag}))
    tool("billing.refund", RefundArgs, "low_risk_write",
         lambda a: http_json("POST", "https://billing.test/refunds", json={"invoice": a.invoice_id}))
    tool("billing.void_invoice", InvoiceArgs, "high_risk_write",
         lambda a: http_json("POST", f"https://billing.test/invoices/{a.invoice_id}/void"))
    return reg.freeze()


TOOLS = tool_registry()
READ_BACKS = {"billing.tag_invoice": ReadBack("billing.get_invoice", lambda a: {"invoice_id": a.invoice_id},
                                              lambda a, data: a.tag in data.get("tags", []))}
ALLOW = {"billing": {"billing.get_invoice", "billing.tag_invoice", "billing.note", "billing.refund",
                     "billing.void_invoice"}}


class Jev:
    def __init__(self, verdict="ALLOW"):
        self.verdict = verdict

    def evaluate(self, state, questions):
        return {"verdict": Answer(self.verdict, 0.9), "serves": Answer(True, 0.95)}


@pytest.fixture(scope="module")
def database():
    subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env.example",
                    "up", "-d", "--wait", "postgres"], cwd=ROOT, check=True, capture_output=True)
    psql("postgres", f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
    psql("postgres", f'CREATE DATABASE "{DB}"')
    migrate("main", DB)
    sessions.apply_schema(DB)
    approvals.apply_schema(DB)
    psql(DB, "INSERT INTO tenants (id, name, region) VALUES ('t_us', 'Acme', 'US');"
             "INSERT INTO tenant_settings (tenant_id) VALUES ('t_us')")


def connect():
    return psycopg.connect(DSN, autocommit=True)


class SpyGate(ApprovalGate):
    def validate(self, ctx, tool, arguments, masked_state):
        self.seen = ctx
        return super().validate(ctx, tool, arguments, masked_state)


def owned_by(owner):
    return lambda tool, arguments, principal: {
        "action": "update_contact", "type": "Account", "id": "acct-1",
        "attrs": {"tenant_id": "t_us", "owner": entity("User", owner)}}


class World:
    def __init__(self, tags=("vip",), jev="ALLOW", owner="sarah", read_backs=READ_BACKS):
        self.fake = Fake({"/invoices/INV-1": [(200, {"id": "INV-1", "tags": list(tags)})]})
        run, _ = executor(self.fake, registry=TOOLS)
        self.gate = SpyGate(connect, DecisionEngine(Jev(jev)), Authorizer(), lambda credential: None)
        self.tools = SpecialistTools(run, self.gate, TOOLS, ALLOW, read_backs, owned_by(owner))
        with connect() as conn:
            session = sessions.start(conn, "t_us", "sarah", "T2_SSO")
            self.conversation = f"conv-{uuid.uuid4().hex[:8]}"
            sessions.open_conversation(conn, "t_us", "sarah", session, self.conversation)
            self.case_id = sessions.link_case(conn, "t_us", self.conversation)

    def run(self, tool_id, arguments, solo=True, role="billing", session_id="s-sarah"):
        request = ToolRequest("t_us", self.case_id, session_id, "sarah", "turn-1", role, 1, tool_id,
                              arguments)
        return self.tools.for_turn(conversation_id=self.conversation, message="Tag my invoice", solo=solo)(
            request)

    def posts(self):
        return [r.url.path for r in self.fake.requests if r.method == "POST"]


@pytest.fixture
def world(database):
    return World()


TAG = {"invoice_id": "INV-1", "tag": "vip"}


def test_a_read_runs_through_the_executor_and_returns_screened_text(world):
    output = world.run("billing.get_invoice", {"invoice_id": "INV-1"}, solo=False)
    assert output.startswith("<<<") and "INV-1" in output and world.posts() == []


def test_a_solo_low_risk_write_is_checked_by_the_gate_and_verified_by_read_back(world):
    done_text = "billing.tag_invoice done and verified by billing.get_invoice"
    assert world.run("billing.tag_invoice", TAG) == done_text
    assert world.posts() == ["/invoices/INV-1/tags"]
    assert [r.method for r in world.fake.requests] == ["POST", "GET"]        # write, then read-back
    (done,) = world.tools.executed
    assert done.tool_id == "billing.tag_invoice" and done.verified is True
    assert world.gate.seen.handler_id == "specialist.billing"                  # its own identity
    assert world.fake.requests[0].headers["Idempotency-Key"]                   # a keyed, retry-safe write


def test_while_specialists_run_in_parallel_nobody_writes(world):
    with pytest.raises(Refused) as refused:
        world.run("billing.tag_invoice", TAG, solo=False)
    assert refused.value.code == "PARALLEL_WRITE" and world.fake.requests == []


VERIFIABLE = {**READ_BACKS, **{tool: ReadBack("billing.get_invoice", lambda a: {"invoice_id": a.invoice_id},
                                               lambda a, data: True)
                               for tool in ("billing.refund", "billing.void_invoice")}}


@pytest.mark.parametrize("tool_id, arguments", [
    ("billing.refund", {"invoice_id": "INV-1", "amount": 5.0, "currency": "USD"}),   # moves money
    ("billing.void_invoice", {"invoice_id": "INV-1"}),                              # high risk
])
def test_money_and_high_risk_writes_are_proposed_before_the_gate_is_even_asked(database, tool_id, arguments):
    world = World(read_backs=VERIFIABLE)   # even with a read-back, and below the approval threshold
    with pytest.raises(Refused) as refused:
        world.run(tool_id, arguments)
    assert refused.value.code == "PROPOSE" and world.fake.requests == [] and not hasattr(world.gate, "seen")


def test_a_write_that_cannot_be_verified_is_proposed_not_run(world):
    with pytest.raises(Refused) as refused:
        world.run("billing.note", TAG)                                              # no read-back declared
    assert refused.value.code == "PROPOSE" and world.fake.requests == []


@pytest.mark.parametrize("options", [{"jev": "ASK"}, {"jev": "DENY"}, {"owner": "bob"}])
def test_a_write_the_gate_does_not_allow_outright_is_proposed(database, options):
    world = World(**options)
    with pytest.raises(Refused) as refused:
        world.run("billing.tag_invoice", TAG)
    assert refused.value.code == "PROPOSE" and world.fake.requests == []


def test_a_write_on_a_closed_case_is_not_run(world):
    psql(DB, f"UPDATE cases SET status = 'closed' WHERE id = '{world.case_id}'")
    with pytest.raises(Refused):
        world.run("billing.tag_invoice", TAG)
    assert world.fake.requests == []


def test_a_write_the_read_back_does_not_confirm_is_not_reported(database):
    world = World(tags=())
    with pytest.raises(Refused) as refused:
        world.run("billing.tag_invoice", TAG)
    assert refused.value.code == "READ_BACK_MISMATCH" and world.tools.executed == []


def test_only_the_specialists_own_tools_and_the_customers_own_session(world):
    with pytest.raises(Refused) as refused:
        world.run("billing.get_invoice", {"invoice_id": "INV-1"}, role="technical")
    assert refused.value.code == "NOT_ON_ALLOW_LIST"
    with pytest.raises(ToolFailure) as failure:
        world.run("billing.tag_invoice", TAG, session_id="s-bob")      # another customer's session
    assert failure.value.code == "FORBIDDEN" and world.posts() == []
    with pytest.raises(ValidationError):
        world.run("billing.tag_invoice", {"invoice_id": "INV-1"})      # the tool's argument schema


def test_an_executed_action_is_only_ever_a_verified_one():
    with pytest.raises(ValidationError):
        ExecutedAction(tool_id="billing.tag_invoice", tool_call_id="c", verified=False)


# The conversation on demand ---------------------------------------------------------------------------------

TURNS = [f"Turn {n}: about the invoice <EMAIL_1a2b3c4d>" if n % 2 else f"Turn {n}: about the outage"
         for n in range(30)]


def test_conversation_pages_are_bounded_masked_and_filterable():
    reader = ConversationReader(lambda tenant, conversation: TURNS)
    page = reader.read("t_us", "conv-1", 0, PAGE_TURNS - 1)
    assert page.turns == tuple(TURNS[:PAGE_TURNS]) and page.characters == sum(map(len, TURNS[:PAGE_TURNS]))
    assert reader.read("t_us", "conv-1", 0, 3, topic="Invoice").turns == (TURNS[1], TURNS[3])
    for first, last in ((0, PAGE_TURNS), (5, 4), (-1, 2), ("0", 2)):
        with pytest.raises(ValueError):
            reader.read("t_us", "conv-1", first, last)


def test_a_conversation_with_raw_personal_data_is_never_paged_to_a_specialist():
    reader = ConversationReader(lambda tenant, conversation: ["Call me at sarah@acme.com"])
    with pytest.raises(SecurityViolation):
        reader.read("t_us", "conv-1", 0, 0)
