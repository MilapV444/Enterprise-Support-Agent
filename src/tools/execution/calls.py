"""The shape of a tool call sent to a system's worker pool, and the workflow-side dispatch (FR-23 / TA-D11).

Each external system has its own Temporal task queue ("tools-<system>") and worker pool, so a slow CRM cannot
starve billing. Temporal does not retry tool activities itself: the worker's executor decides what is safe to
retry (tools.execution). This module imports only the stdlib and temporalio so workflows can use it.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

NO_TEMPORAL_RETRY = RetryPolicy(maximum_attempts=1)


@dataclass
class ToolCall:
    tool_call_id: str
    tool_id: str                      # "<system>.<name>": the prefix picks the system and its queue
    arguments: dict[str, Any]
    tenant_id: str
    principal_id: str
    case_id: str
    checkpoint_id: str
    roles: list[str] = field(default_factory=list)
    access_token: str | None = None   # the customer's session token, exchanged for an on-behalf-of token
    resource: dict[str, Any] = field(default_factory=dict)  # {"action", "type", "id", "attrs"} for Cedar


@dataclass
class ToolResult:
    tool_call_id: str
    tool_id: str
    data: dict[str, Any]              # structured output, {} when screening withheld it
    content: str                      # screened, spotlighted text for a model
    band: str                         # screening band: pass / review / block
    attempts: int
    blob_ref: str | None = None       # set when the output was too large and stored by reference


def task_queue(tool_id):
    return f"tools-{tool_id.split('.', 1)[0]}"


async def call_tool(call, timeout_seconds=30):
    """From a workflow: run the call on its system's queue; tool failures surface as ApplicationError."""
    return await workflow.execute_activity("run_tool", call, result_type=ToolResult,
                                           task_queue=task_queue(call.tool_id),
                                           start_to_close_timeout=timedelta(seconds=timeout_seconds),
                                           retry_policy=NO_TEMPORAL_RETRY)
