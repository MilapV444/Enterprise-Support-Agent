"""Sagas: multi-system writes with idempotent compensations, the irreversible step last and approved, and an
audit record for every call (FR-24 / TA-ADP-05: TA-D8, TA-D12, TA-D17, TA-D18). The workflow is in
tools.sagas.workflow; this module checks plans and runs the steps (kept out of the package __init__ so the
workflow sandbox never imports it).

check_plan() refuses a saga before anything runs unless:
- every step's tool is registered, and so is every compensation and snapshot tool;
- each write that is not last has a compensation: a reviewed write tool on the same system, which honours
  idempotency keys there (so a retried compensation applies once), whose arguments fit its schema;
- an irreversible step (destructive, or a write without a compensation) is the last step, there is at most
  one, and it names its approval request;
- a snapshot tool (before / after state of a financial write) is a reviewed read-only tool on the same system
  with the step's argument schema (tools.validation.dry_run_tool).

Trust: the workflow input names only the tenant, the customer's session, the case and the conversation. Each
activity resolves the principal from that live session (channels.identity, through the executor's identity),
takes the principal's roles from the trusted directory (the executor's roles_of; never from the input), and
uses its own configured handler identity. A session that has ended or belongs to another tenant stops the
call before anything runs.

Authorization: every forward step and every compensation runs through the approval gate
(tools.validation.approvals: conversation and case binding, Cedar on the target resource, tenant limits,
approvals, ledger, final re-validation) with the tool's work done by the tool executor (tools.execution:
credentials minted inside the activity, egress, retries, breakers). An irreversible step is gated as at least
a high-risk write, so it always needs a specialist's approval. A compensation needs no new human approval when
the gate allows it on its own (a reviewed low-risk undo), but it is never run outside the gate: if the
current state no longer permits it, the rollback stops for a human.

Audit: every tool call, forward, compensating or snapshot, is recorded (tools.audit), whatever its outcome:
success, tool failure, refusal, invalid arguments, an ended session, or an internal error. Plain columns hold
only ids, codes and the USD amount; arguments, results, snapshots and refusal details are sealed under the
user's key, and nothing personal is stored when the user could not be established.
"""

import dataclasses
import uuid
from concurrent.futures import ThreadPoolExecutor

from pydantic import ValidationError
from temporalio import activity
from temporalio.exceptions import ApplicationError
from temporalio.worker import Worker

from channels.identity.service import AGENT
from core.orchestrator.decisions import Masked
from tools.execution import ToolFailure
from tools.execution.calls import ToolCall
from tools.registry import Risk
from tools.sagas.workflow import TASK_QUEUE, SagaStart, SagaWorkflow, StepOutcome
from tools.validation import UnsafeDryRun, Verdict, dry_run_tool, financial_amount
from tools.validation.approvals import CallContext, NotApproved


class UnverifiedSession(PermissionError):
    pass


def system_of(tool_id):
    return tool_id.split(".", 1)[0]


def is_request_id(value):
    try:
        uuid.UUID(str(value))
    except ValueError:
        return False
    return True


def irreversible(registry, step):
    tool = registry.tools[step.tool_id]
    return tool.risk is Risk.DESTRUCTIVE_IRREVERSIBLE or (tool.mutating and step.compensation_tool_id is None)


def gated_tool(registry, step):
    """The tool as the approval gate sees it: an irreversible step counts as at least a high-risk write, so it
    always needs a specialist (TA-D18). Open the step's approval request with this same tool."""
    tool = registry.tools[step.tool_id]
    if irreversible(registry, step) and tool.risk in (Risk.READ_ONLY, Risk.LOW_RISK_WRITE):
        return dataclasses.replace(tool, risk=Risk.HIGH_RISK_WRITE)
    return tool


def check_plan(registry, systems, steps):
    """Problems that keep a saga from starting; empty when it may run."""
    problems = []
    for index, step in enumerate(steps):
        where = f"step {step.step_id}"
        tool = registry.tools.get(step.tool_id)
        if tool is None:
            problems.append(f"{where}: {step.tool_id!r} is not a registered tool")
            continue
        if irreversible(registry, step):
            if index != len(steps) - 1:
                problems.append(f"{where}: {step.tool_id} cannot be undone, so it must be the last step")
            if not step.approval_request_id:
                problems.append(f"{where}: an irreversible step needs a human approval request")
        if step.approval_request_id is not None and not is_request_id(step.approval_request_id):
            problems.append(f"{where}: {step.approval_request_id!r} is not an approval request id")
        if step.compensation_tool_id is not None:
            problems += [f"{where}: {p}" for p in _compensation_problems(registry, systems, tool, step)]
        if step.snapshot_tool_id is not None:
            try:
                dry_run_tool(registry, tool, step.snapshot_tool_id)
            except UnsafeDryRun as error:
                problems.append(f"{where}: unsafe snapshot tool: {error}")
    return problems


def _compensation_problems(registry, systems, tool, step):
    undo = registry.tools.get(step.compensation_tool_id)
    if undo is None:
        return [f"compensation {step.compensation_tool_id!r} is not a registered tool"]
    problems = []
    if not tool.mutating:
        problems.append("a read has nothing to compensate")
    if not undo.mutating or not undo.reviewed_by:
        problems.append(f"compensation {undo.tool_id} must be a reviewed write tool")
    if undo.risk is Risk.DESTRUCTIVE_IRREVERSIBLE:
        problems.append(f"compensation {undo.tool_id} cannot itself be irreversible")
    if system_of(undo.tool_id) != system_of(tool.tool_id):
        problems.append(f"compensation {undo.tool_id} is on another system than {tool.tool_id}")
    system = systems.get(system_of(undo.tool_id))
    if system is None or not system.idempotent_writes:
        problems.append(f"compensation {undo.tool_id} runs on a system without idempotency keys")
    try:
        undo.args(**step.compensation_arguments)
    except ValidationError:
        problems.append(f"compensation arguments do not fit {undo.tool_id}")
    return problems


def failure_code(error):
    """A stable, non-sensitive code for the audit's plain columns (details go to the sealed payload)."""
    if isinstance(error, ToolFailure):
        return error.code
    if isinstance(error, NotApproved):
        return "NOT_APPROVED"
    if isinstance(error, ValidationError):
        return "INVALID_ARGUMENTS"
    if isinstance(error, UnverifiedSession):
        return "AUTHENTICATION_EXPIRED"
    return "INTERNAL_ERROR"


class SagaActivities:
    def __init__(self, registry, systems, executor, gate, audit, handler_id=AGENT):
        """executor: tools.execution.Executor (its identity resolves sessions, its roles_of is the trusted
        role directory); gate: tools.validation.approvals.ApprovalGate; audit: tools.audit.AuditLog;
        handler_id: the identity this runtime acts as (never taken from a saga's input)."""
        self.registry, self.systems, self.executor = registry, systems, executor
        self.gate, self.audit, self.handler_id = gate, audit, handler_id

    # trusted identity -------------------------------------------------------------------------------------

    def _principal(self, start):
        try:
            principal_id, _ = self.executor.identity.session_principal(start.tenant_id, start.session_id)
        except Exception as error:  # ended, expired, unknown or another tenant's session
            raise UnverifiedSession("the saga's session is not live in this tenant") from error
        return principal_id

    def _ctx(self, start, principal_id, resource):
        roles = tuple(self.executor.roles_of(start.tenant_id, principal_id))
        return CallContext(start.tenant_id, start.case_id, start.conversation_id, principal_id,
                           self.handler_id, roles, resource)

    def _call(self, start, principal_id, step, tool_id, arguments, suffix, resource):
        return ToolCall(tool_call_id=f"{start.saga_id}:{step.step_id}{suffix}", tool_id=tool_id,
                        arguments=arguments, tenant_id=start.tenant_id, principal_id=principal_id,
                        case_id=start.case_id, checkpoint_id=start.saga_id, session_id=start.session_id,
                        resource=resource)

    # audit ------------------------------------------------------------------------------------------------

    def _key(self, tool, call_id, checkpoint_id):
        keyed = tool.mutating and self.systems[system_of(tool.tool_id)].idempotent_writes
        return f"{checkpoint_id}:{call_id}" if keyed else None

    def _audit(self, start, principal_id, step, tool, call_id, arguments, action, error_code, personal,
               **fields):
        try:
            amount, problem = financial_amount(tool.args(**arguments))
        except ValidationError:
            amount, problem = None, "invalid arguments"
        self.audit.record(tenant_id=start.tenant_id, conversation_id=start.conversation_id,
                          user_id=principal_id, tool_id=tool.tool_id, action=action,
                          outcome="failed" if error_code else "ok", case_id=start.case_id, call_id=call_id,
                          saga_id=start.saga_id, step_id=step.step_id,
                          idempotency_key=self._key(tool, call_id, start.saga_id),
                          credential_basis=self.systems[system_of(tool.tool_id)].credential,
                          risk_class=tool.risk.value, amount_usd=None if problem else amount,
                          error_code=error_code, personal=personal if principal_id else None, **fields)

    @staticmethod
    def _sealed_details(error, personal):
        if isinstance(error, ValidationError):  # field names only, not the pydantic message with values
            personal["invalid_fields"] = [".".join(map(str, e["loc"])) for e in error.errors()]
        elif isinstance(error, NotApproved):
            personal["refusal"] = str(error)

    def _snapshot(self, start, principal_id, step, moment):
        """Read the before / after state through the executor, audited as a tool call of its own."""
        tool = self.registry.tools[step.snapshot_tool_id]
        call = self._call(start, principal_id, step, tool.tool_id, step.arguments, f":snapshot-{moment}",
                          step.resource)
        personal = {"arguments": step.arguments}
        try:
            data = self.executor.run(call).data
            personal["result"] = data
        except Exception as error:
            self._audit(start, principal_id, step, tool, call.tool_call_id, step.arguments, "snapshot",
                        failure_code(error), personal)
            raise
        self._audit(start, principal_id, step, tool, call.tool_call_id, step.arguments, "snapshot", None,
                    personal)
        return data

    # activities -------------------------------------------------------------------------------------------

    @activity.defn(name="saga_plan")
    def plan(self, start: SagaStart) -> None:
        problems = check_plan(self.registry, self.systems, start.steps)
        if problems:
            raise ApplicationError("; ".join(problems), type="SAGA_REJECTED", non_retryable=True)

    @activity.defn(name="saga_step")
    def step(self, start: SagaStart, index: int) -> StepOutcome:
        step = start.steps[index]
        tool = self.registry.tools[step.tool_id]
        call_id = f"{start.saga_id}:{step.step_id}"
        principal_id, personal, error_code = None, {"arguments": step.arguments}, None
        try:
            principal_id = self._principal(start)
            arguments = tool.args(**step.arguments)
            ctx, state = self._ctx(start, principal_id, step.resource), {"message": Masked(start.message)}
            gated = gated_tool(self.registry, step)
            first = self.gate.validate(ctx, gated, arguments, state)  # authorize before any call, reads too
            if first.verdict is Verdict.DENY:
                raise NotApproved(f"{tool.tool_id}: denied ({'; '.join(first.reasons)})")
            if step.snapshot_tool_id:
                personal["before"] = self._snapshot(start, principal_id, step, "before")
            call = self._call(start, principal_id, step, step.tool_id, step.arguments, "", step.resource)
            gated = dataclasses.replace(gated, func=lambda arguments: self.executor.run(call))
            result = self.gate.execute(ctx, gated, arguments, state, step.approval_request_id)  # checks again
            personal["result"] = result.data
        except Exception as error:  # noqa: BLE001 - every failure is audited, then reported as a failed step
            error_code = failure_code(error)
            self._sealed_details(error, personal)
        if error_code is None and step.snapshot_tool_id:
            try:  # the write happened: a failed after-read is recorded, it does not undo the step
                personal["after"] = self._snapshot(start, principal_id, step, "after")
            except Exception as error:  # noqa: BLE001
                personal["after_error"] = failure_code(error)
        self._audit(start, principal_id, step, tool, call_id, step.arguments, "forward", error_code, personal,
                    approval_request_id=step.approval_request_id)
        return StepOutcome(error_code is None, error_code)

    @activity.defn(name="saga_compensate")
    def compensate(self, start: SagaStart, index: int) -> None:
        step = start.steps[index]
        undo = self.registry.tools[step.compensation_tool_id]
        call_id = f"{start.saga_id}:{step.step_id}:compensate"
        resource = step.compensation_resource or step.resource
        principal_id, personal, error_code = None, {"arguments": step.compensation_arguments}, None
        try:
            principal_id = self._principal(start)
            arguments = undo.args(**step.compensation_arguments)
            call = self._call(start, principal_id, step, undo.tool_id, step.compensation_arguments,
                              ":compensate", resource)
            gated = dataclasses.replace(undo, func=lambda arguments: self.executor.run(call))
            result = self.gate.execute(self._ctx(start, principal_id, resource), gated, arguments,
                                       {"message": Masked(start.message)})
            personal["result"] = result.data
        except Exception as error:  # noqa: BLE001 - audited, then retried or handed to a human by the workflow
            error_code = failure_code(error)
            self._sealed_details(error, personal)
        self._audit(start, principal_id, step, undo, call_id, step.compensation_arguments, "compensate",
                    error_code, personal)
        if error_code:
            raise ApplicationError(f"compensation of {step.step_id} failed: {error_code}", type=error_code)


def worker(client, activities, task_queue=TASK_QUEUE):
    return Worker(client, task_queue=task_queue, workflows=[SagaWorkflow],
                  activities=[activities.plan, activities.step, activities.compensate],
                  activity_executor=ThreadPoolExecutor(max_workers=8))
