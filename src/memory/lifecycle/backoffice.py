"""Back-office erasure and correction (FR-19 / MS-D11: v1 is administrative, SLA <= 30 days).

A support administrator, already authorized by the caller (Cedar, tenant_admin), can:
- see what the agent remembers about a user (remembered),
- correct a fact (correct: the old version is closed, the corrected one added, history kept),
- forget a fact outright (forget: the fact and every earlier version deleted),
- erase the user entirely (request_erasure: starts the erasure workflow across every store).
The user is always named by the verified (tenant_id, principal_id), never by text from a conversation.
"""

from data.erasure import ErasureRequest, start_erasure
from memory.lifecycle.inventory import context
from memory.lifecycle.retention import delete_lineage


def remembered(facts, tenant_id, principal_id):
    """[{"id", "statement", "category", "since"}] the agent holds as true now."""
    return [{"id": f.id, "statement": f.statement, "category": f.category, "since": f.valid_from}
            for f in facts.as_of(tenant_id, principal_id)]


def correct(facts, embed, tenant_id, principal_id, fact_id, statement):
    """Replace a current fact with the corrected statement; returns the new fact id."""
    current = {f.id: f for f in facts.as_of(tenant_id, principal_id)}
    if fact_id not in current:
        raise LookupError(f"{fact_id} is not a current fact of this user")
    old = current[fact_id]
    vector = embed([statement])[0]
    new_id = facts.add(tenant_id, principal_id, statement, old.category, old.importance, vector,
                       replaces=fact_id)
    if new_id is None:
        raise LookupError(f"{fact_id} was changed meanwhile")
    return new_id


def forget(conn, tenant_id, principal_id, fact_id):
    """Delete a fact and every version it replaced; returns how many rows went (0: not this user's)."""
    with conn.transaction():
        context(conn, tenant_id, principal_id)
        return delete_lineage(conn, "tenant_id = %(t)s AND principal_id = %(p)s AND id = %(id)s",
                              {"t": tenant_id, "p": principal_id, "id": fact_id})


async def request_erasure(client, tenant_id, principal_id, requested_by, reason="GDPR_ARTICLE_17",
                          task_queue=None):
    """Start the user's erasure; returns the workflow handle (its result is the outcome)."""
    request = ErasureRequest(tenant_id, principal_id, requested_by, reason)
    if task_queue:
        return await start_erasure(client, request, task_queue)
    return await start_erasure(client, request)
