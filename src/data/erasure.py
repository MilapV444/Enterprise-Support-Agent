"""The erasure workflow: one user's data out of every store, durably (NFR-5 / DP-ADP-05: DP-D9, DP-D13,
DP-D14; FR-19 / MS-D14).

    collect -> purge each store in the inventory -> verify every store -> signed receipt

Each step is a Temporal activity with retries, so a store that is down is retried, not skipped. The plan
(the user's cases and the PII tokens their data used) is collected before anything is deleted, because the
links are gone afterwards. Verification asks every store again; a residue sends the workflow through the purge
once more, and if it is still there the job ends FAILED for a human (and is never reported complete). The
stores and activities live in memory.lifecycle.inventory.

Backups are not rewritten (DP-D9): they expire after BACKUP_RETENTION_DAYS, and because the user's data keys
are shredded, encrypted fields restored from a backup stay unreadable (DP-D14). The receipt says by when.

This module imports only the stdlib and temporalio so it stays inside Temporal's workflow sandbox.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

TASK_QUEUE = "erasure"
BACKUP_RETENTION_DAYS = 35
ROUNDS = 2
STEP = {"start_to_close_timeout": timedelta(minutes=5),
        "retry_policy": RetryPolicy(initial_interval=timedelta(seconds=1), backoff_coefficient=2.0,
                                    maximum_interval=timedelta(minutes=5), maximum_attempts=50)}


@dataclass
class ErasureRequest:
    tenant_id: str
    principal_id: str  # from the verified identity of the request, never from conversation text
    requested_by: str  # back-office admin, or "SCIM_OFFBOARDING"
    reason: str = "GDPR_ARTICLE_17"


@dataclass
class Plan:
    case_ids: list[str] = field(default_factory=list)          # cases only this user took part in
    conversation_ids: list[str] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)            # PII tokens found in the user's data


@dataclass
class Outcome:
    job_id: str
    status: str                                                # "COMPLETED" or "FAILED"
    purged: dict[str, int] = field(default_factory=dict)       # store -> records removed
    residual: dict[str, int] = field(default_factory=dict)     # store -> records still readable


def subject_hash(tenant_id, principal_id):
    """The ledger and workflow id carry this instead of the user's id."""
    return hashlib.sha256(f"{tenant_id}\x1f{principal_id}".encode()).hexdigest()


def workflow_id(tenant_id, principal_id):
    return f"erasure:{tenant_id}:{subject_hash(tenant_id, principal_id)[:32]}"


async def start_erasure(client, request, task_queue=TASK_QUEUE):
    """Start the user's erasure; a second request while one runs joins nothing and fails to start."""
    return await client.start_workflow(ErasureWorkflow.run, request, task_queue=task_queue,
                                       id=workflow_id(request.tenant_id, request.principal_id))


@workflow.defn
class ErasureWorkflow:
    @workflow.run
    async def run(self, request: ErasureRequest) -> Outcome:
        job_id = workflow.info().workflow_id
        stores = await workflow.execute_activity("erasure_stores", result_type=list[str], **STEP)
        await workflow.execute_activity("erasure_open", args=[job_id, request], **STEP)
        plan = await workflow.execute_activity("erasure_collect", request, result_type=Plan, **STEP)
        purged, residual = {}, {}
        for _ in range(ROUNDS):
            for store in stores:
                count = await workflow.execute_activity("erasure_purge", args=[store, request, plan],
                                                        result_type=int, **STEP)
                purged[store] = purged.get(store, 0) + count
            residual = await workflow.execute_activity("erasure_verify", args=[request, plan],
                                                       result_type=dict[str, int], **STEP)
            if not any(residual.values()):
                break
        status = "FAILED" if any(residual.values()) else "COMPLETED"
        outcome = Outcome(job_id, status, purged, residual)
        await workflow.execute_activity("erasure_close", args=[outcome, request], **STEP)
        return outcome
