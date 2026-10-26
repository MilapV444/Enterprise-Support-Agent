"""What the coordinator and its specialists exchange, and what a specialist may do (FR-27 / MA-ADP-03: MA-D4,
MA-D5; FR-28 / MA-ADP-04: MA-D9, MA-D14, MA-D18).

- Brief: the task a specialist gets. brief() always copies every pinned constraint of the conversation, so a
  brief cannot leave one out. Result: status completed / blocked / needs_user; a blocked result has a
  structured blocker (no "contact another team"); every finding and proposal cites evidence the result
  lists; an executed write is reported only after its read-back verified it; there is no field for text to
  the customer.
- actor(role): each specialist's own identity, "specialist.<role>", recorded as the handler of anything it
  asks the approval gate for.
- SpecialistTools.for_turn(...) -> run_tool for agents.topology. A read runs through the executor. A low-risk
  write that moves no money runs only when the specialist is the only one in the turn, only when the approval
  gate allows it without approval (decided again on current state), and only when it has a declared
  read-back: after the write the read-back tool runs and must confirm the change, or the write is reported
  as unverified. Everything else (high-risk, destructive, financial, needing approval, or any write while
  specialists run in parallel) is refused with a code, for the specialist to propose instead.
- ConversationReader: the brief plus on-demand reads of the conversation, a bounded page of masked turns.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.orchestrator.decisions import Masked, SecurityViolation
from safety.pii.tokens import find as find_pii
from tools.execution.calls import ToolCall
from tools.registry import Risk
from tools.validation import Verdict, financial_fields
from tools.validation.approvals import CallContext

MAX_TEXT = 4000
PAGE_TURNS = 10


def actor(role):
    return f"specialist.{role}"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Brief(Contract):
    task_id: str
    role: str
    case_id: str
    conversation_id: str
    objective: str = Field(max_length=MAX_TEXT)              # masked
    entity_ids: dict[str, str] = {}
    pinned_constraints: tuple[str, ...]
    evidence_refs: tuple[str, ...] = ()
    steps: int = Field(ge=1, le=2)
    upstream: "Result | None" = None


def brief(*, task_id, role, case_id, conversation_id, objective, pins, steps, entity_ids=None,
          evidence_refs=(), upstream=None):
    """A brief that carries every pinned constraint of the conversation (MS-ADP-01 pins: an iterable)."""
    return Brief(task_id=task_id, role=role, case_id=case_id, conversation_id=conversation_id,
                 objective=objective, entity_ids=entity_ids or {}, pinned_constraints=tuple(pins),
                 steps=steps, evidence_refs=tuple(evidence_refs), upstream=upstream)


class Status(str, Enum):
    COMPLETED = "completed"
    BLOCKED = "blocked"
    NEEDS_USER = "needs_user"


class Blocker(str, Enum):
    MISSING_INFORMATION = "missing_information"
    TOOL_FAILED = "tool_failed"
    OUT_OF_DOMAIN = "out_of_domain"
    NEEDS_APPROVAL = "needs_approval"
    BUDGET_USED_UP = "budget_used_up"
    READ_BACK_MISMATCH = "read_back_mismatch"


class Finding(Contract):
    text: str = Field(min_length=1, max_length=MAX_TEXT)
    evidence: tuple[str, ...] = Field(min_length=1)


class ProposedAction(Contract):
    tool_id: str
    arguments: dict[str, Any]
    reason: str = Field(min_length=1, max_length=MAX_TEXT)
    evidence: tuple[str, ...] = Field(min_length=1)


class ExecutedAction(Contract):
    tool_id: str
    tool_call_id: str
    verified: Literal[True]     # only a write its read-back confirmed may be reported


class Result(Contract):
    task_id: str
    role: str
    status: Status
    findings: tuple[Finding, ...] = ()
    evidence: tuple[str, ...] = ()       # tool call ids and knowledge passage ids
    proposed_actions: tuple[ProposedAction, ...] = ()
    executed_actions: tuple[ExecutedAction, ...] = ()
    blocker: Blocker | None = None
    steps: int = Field(ge=0, le=2)

    @model_validator(mode="after")
    def _postconditions(self):
        if (self.status is Status.BLOCKED) != (self.blocker is not None):
            raise ValueError("a blocked result names its blocker, and only a blocked result has one")
        if self.status is Status.COMPLETED and not self.findings:
            raise ValueError("a completed result has findings")
        cited = {e for item in (*self.findings, *self.proposed_actions) for e in item.evidence}
        if not cited <= set(self.evidence):
            raise ValueError("every finding and proposal cites evidence the result lists")
        return self


Brief.model_rebuild()


# What a specialist may run ----------------------------------------------------------------------------------

class Refused(PermissionError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ReadBack:
    """How a write is verified: run `tool_id` with read_arguments(write arguments), then confirm(write
    arguments, the read's structured output) must be true."""

    tool_id: str
    read_arguments: Callable[[Any], dict]
    confirm: Callable[[Any, dict], bool]


class SpecialistTools:
    def __init__(self, executor, gate, tool_registry, allow_lists, read_backs, resource_of):
        """executor: tools.execution.Executor; gate: tools.validation.approvals.ApprovalGate; allow_lists:
        {role: tool ids}; read_backs: {write tool id: ReadBack}; resource_of(tool, arguments, principal) ->
        the Cedar resource of a write."""
        self.executor, self.gate, self.tools = executor, gate, tool_registry.tools
        self.allow_lists, self.read_backs, self.resource_of = allow_lists, read_backs, resource_of
        self.executed = []   # ExecutedAction, verified writes only

    def _call(self, request, tool_id, arguments, suffix=""):
        return self.executor.run(ToolCall(
            tool_call_id=request.tool_call_id + suffix, tool_id=tool_id, arguments=arguments,
            tenant_id=request.tenant_id, principal_id=request.principal_id, case_id=request.case_id,
            checkpoint_id=request.turn_id, session_id=request.session_id))

    def for_turn(self, *, conversation_id, message, solo):
        """run_tool for one turn. solo: this specialist is the only one dispatched in the turn."""
        def run(request):
            if request.tool_id not in self.allow_lists.get(request.role, ()):
                raise Refused("NOT_ON_ALLOW_LIST")
            tool = self.tools[request.tool_id]
            if tool.risk is Risk.READ_ONLY:
                return self._call(request, request.tool_id, request.arguments).content
            arguments = tool.args(**request.arguments)
            if tool.risk is not Risk.LOW_RISK_WRITE or financial_fields(arguments):
                raise Refused("PROPOSE")             # high-risk, destructive or money: a proposal
            if not solo:
                raise Refused("PARALLEL_WRITE")      # parallel branches are read-only
            read_back = self.read_backs.get(request.tool_id)
            if read_back is None:
                raise Refused("PROPOSE")             # a write that cannot be verified is not run
            ctx = CallContext(request.tenant_id, request.case_id, conversation_id, request.principal_id,
                              actor(request.role),
                              resource=self.resource_of(tool, arguments, request.principal_id))
            decision = self.gate.validate(ctx, tool, arguments, {"message": Masked(message)})
            if decision.verdict is not Verdict.ALLOW:
                raise Refused("PROPOSE")             # needs a person or the customer: a proposal
            written = self._call(request, request.tool_id, request.arguments)
            check = self._call(request, read_back.tool_id, read_back.read_arguments(arguments), ":read-back")
            if check.band != "pass" or not read_back.confirm(arguments, check.data):
                raise Refused("READ_BACK_MISMATCH")
            self.executed.append(ExecutedAction(tool_id=request.tool_id, tool_call_id=written.tool_call_id,
                                                verified=True))
            return f"{request.tool_id} done and verified by {read_back.tool_id}"
        return run


# The conversation, on demand --------------------------------------------------------------------------------

@dataclass(frozen=True)
class Page:
    turns: tuple[str, ...]
    characters: int      # charged to the turn's budget by the caller


class ConversationReader:
    def __init__(self, load):
        """load(tenant_id, conversation_id) -> the conversation's turns as masked text, oldest first."""
        self.load = load

    def read(self, tenant_id, conversation_id, first, last, topic=None):
        """Turns first..last (inclusive, at most PAGE_TURNS), optionally only those mentioning topic."""
        if type(first) is not int or type(last) is not int or not 0 <= first <= last < first + PAGE_TURNS:
            raise ValueError(f"a page is one to {PAGE_TURNS} turns")
        turns = self.load(tenant_id, conversation_id)[first:last + 1]
        if any(find_pii(turn) for turn in turns):
            raise SecurityViolation("the stored conversation holds unmasked personal data")
        if topic is not None:
            turns = [turn for turn in turns if topic.lower() in turn.lower()]
        return Page(tuple(turns), sum(len(turn) for turn in turns))
