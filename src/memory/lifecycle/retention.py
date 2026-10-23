"""Fixed retention per memory type (FR-19 / MS-D10, MS-Q3), swept per tenant by sweep():

    facts                      12 months since last confirmed: a lineage (a fact and the versions it replaced)
                               goes when its newest version is older than that, or was closed that long ago
    conversations              24 months since they began, with their turns, summary and pins (dialogue memory
                               lives as long as its conversation)
    checkpoints                30 days after the case was resolved or closed

Cases get a closed_at stamp from a trigger, so "30 days after closing" is measurable. Runs as
lifecycle_service.

ponytail: facts have no separate last-confirmed stamp yet, so the newest version's valid_from stands in for
it; a reconcile NOOP does not refresh it. Older versions of a live fact stay until the whole lineage expires
(user_facts.replaces is a plain foreign key). Ticket workflow histories expire with the Temporal namespace
retention, not here.
"""

from data.migrate import psql
from memory.lifecycle.inventory import CHECKPOINT_TABLES, context

FACTS_TTL, CONVERSATION_TTL, CHECKPOINT_TTL = "12 months", "24 months", "30 days"

SCHEMA_NAME = "lifecycle_0002_retention.sql"
SCHEMA = """
ALTER TABLE cases ADD COLUMN closed_at timestamptz;
CREATE FUNCTION stamp_case_closed() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status IN ('resolved', 'closed') AND OLD.status NOT IN ('resolved', 'closed') THEN
    NEW.closed_at := now();
  ELSIF NEW.status NOT IN ('resolved', 'closed') THEN
    NEW.closed_at := NULL;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER cases_closed_at BEFORE UPDATE OF status ON cases
  FOR EACH ROW EXECUTE FUNCTION stamp_case_closed();

-- The sweeper works across a tenant's users; user_facts otherwise shows a session only its own principal.
CREATE POLICY lifecycle ON user_facts TO lifecycle_service USING (tenant_id = current_tenant());
"""

LINEAGE = """
WITH RECURSIVE doomed(id, replaces) AS (
  SELECT id, replaces FROM user_facts WHERE {start}
  UNION
  SELECT f.id, f.replaces FROM user_facts f JOIN doomed d ON f.id = d.replaces
)
DELETE FROM user_facts WHERE id IN (SELECT id FROM doomed)
"""
EXPIRED_FACTS = ("tenant_id = %(t)s "
                 "AND NOT EXISTS (SELECT 1 FROM user_facts n WHERE n.replaces = user_facts.id) "
                 f"AND coalesce(valid_to, valid_from) < %(now)s - interval '{FACTS_TTL}'")
OLD_CONVERSATIONS = ("SELECT id FROM conversations WHERE tenant_id = %(t)s "
                     f"AND created_at < %(now)s - interval '{CONVERSATION_TTL}'")


def apply_schema(database):
    if not psql(database, f"SELECT 1 FROM schema_migrations WHERE name = '{SCHEMA_NAME}'"):
        psql(database, f"BEGIN;\n{SCHEMA}\nINSERT INTO schema_migrations (name) VALUES ('{SCHEMA_NAME}');\n"
                       "COMMIT;\n")


def delete_lineage(conn, start, args):
    """Delete the facts matching `start` and every version they replaced; returns how many rows went."""
    return conn.execute(LINEAGE.format(start=start), args).rowcount


def sweep(conn, tenant_id, now=None):
    """Apply every TTL to one tenant; returns {store: rows deleted}. conn: autocommit, main database."""
    args = {"t": tenant_id, "now": now}
    if now is None:
        args["now"] = conn.execute("SELECT now()").fetchone()[0]
    with conn.transaction():
        context(conn, tenant_id, "")
        threads = [f"{tenant_id}:{case}" for (case,) in conn.execute(
            "SELECT id FROM cases WHERE tenant_id = %(t)s AND status IN ('resolved', 'closed') "
            f"AND closed_at < %(now)s - interval '{CHECKPOINT_TTL}'", args)]
        deleted = {"facts": delete_lineage(conn, EXPIRED_FACTS, args)}
        deleted["conversations"] = sum(
            conn.execute(f"DELETE FROM {table} WHERE tenant_id = %(t)s AND {column} IN ({OLD_CONVERSATIONS})",
                         args).rowcount
            for table, column in (("dialogue_pins", "conversation_id"),
                                  ("dialogue_summaries", "conversation_id"),
                                  ("dialogue_turns", "conversation_id"), ("conversations", "id")))
    with conn.transaction():
        present = [t for t in CHECKPOINT_TABLES if conn.execute("SELECT to_regclass(%s)", (t,)).fetchone()[0]]
        deleted["checkpoints"] = sum(conn.execute(f"DELETE FROM {table} WHERE thread_id = ANY(%s)",
                                                  (threads,)).rowcount for table in present)
    return deleted
