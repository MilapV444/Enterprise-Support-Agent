"""Outbound event log for SSE streaming with a 7-day replay window (NFR-4, DP-ADP-04: DP-D6, DP-D7).

Events are written directly (no event bus). A client reconnecting with Last-Event-ID gets every later
event of the conversation while that event is inside the window; otherwise replay() returns None and the
caller rebuilds the conversation from its transcript with rebuild_from_transcript().

The table's SQL lives here (module-owned schema, DECISION-d4b79fe1) and is applied with apply_schema().
"""

import json

from data.migrate import psql

SCHEMA_NAME = "events_0001_outbound_event_log.sql"
SCHEMA = """
CREATE TABLE outbound_event_log (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id       text NOT NULL REFERENCES tenants (id),
  conversation_id text NOT NULL,
  event_type      text NOT NULL,
  data            jsonb NOT NULL DEFAULT '{}',
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX outbound_event_log_conversation ON outbound_event_log (conversation_id, id);
CREATE INDEX outbound_event_log_created ON outbound_event_log (created_at);

ALTER TABLE outbound_event_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE outbound_event_log FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_read ON outbound_event_log FOR SELECT USING (tenant_id = current_tenant());
CREATE POLICY tenant_write ON outbound_event_log FOR INSERT WITH CHECK (tenant_id = current_tenant());
-- Deletes only ever remove events past the window. A DELETE without WHERE reads no rows, so only this policy
-- applies and the purge covers every tenant; any WHERE clause adds the tenant_read policy on top.
CREATE POLICY expired_only ON outbound_event_log FOR DELETE USING (created_at < now() - interval '7 days');

ALTER TABLE outbound_event_log OWNER TO app_owner;
GRANT SELECT, INSERT, DELETE ON outbound_event_log TO app_runtime;
"""


def apply_schema(database):
    """Create the table once, recorded in the schema_migrations ledger like the files in migrations/."""
    if not psql(database, f"SELECT 1 FROM schema_migrations WHERE name = '{SCHEMA_NAME}'"):
        psql(database, f"BEGIN;\n{SCHEMA}\nINSERT INTO schema_migrations (name) VALUES ('{SCHEMA_NAME}');\n"
                       "COMMIT;\n")


class EventLog:
    """Reads and writes as app_runtime under the tenant's context; needs an autocommit connection."""

    def __init__(self, conn):
        if not conn.autocommit:
            raise ValueError("EventLog needs an autocommit connection")
        self.conn = conn

    def append(self, tenant_id, conversation_id, event_type, data):
        """Store one event and return its id, which the SSE stream sends as the event id."""
        with self.conn.transaction():
            self._context(tenant_id)
            (event_id,) = self.conn.execute(
                "INSERT INTO outbound_event_log (tenant_id, conversation_id, event_type, data) "
                "VALUES (%s, %s, %s, %s::jsonb) RETURNING id",
                (tenant_id, conversation_id, event_type, json.dumps(data))).fetchone()
        return str(event_id)

    def replay(self, tenant_id, conversation_id, last_event_id):
        """Events after last_event_id as (id, type, data), or None if that event is unknown or expired."""
        try:
            last = int(last_event_id)
        except (TypeError, ValueError):
            return None
        with self.conn.transaction():
            self._context(tenant_id)
            known = self.conn.execute(
                "SELECT 1 FROM outbound_event_log WHERE id = %s AND conversation_id = %s "
                "AND created_at > now() - interval '7 days'", (last, conversation_id)).fetchone()
            if known is None:
                return None
            rows = self.conn.execute(
                "SELECT id, event_type, data FROM outbound_event_log WHERE conversation_id = %s AND id > %s "
                "ORDER BY id", (conversation_id, last)).fetchall()
        return [(str(event_id), event_type, data) for event_id, event_type, data in rows]

    def purge_expired(self):
        """Delete every tenant's events older than 7 days (run daily); returns how many were deleted."""
        with self.conn.transaction():
            self.conn.execute("SET LOCAL ROLE app_runtime")
            return self.conn.execute("DELETE FROM outbound_event_log").rowcount

    def _context(self, tenant_id):
        self.conn.execute("SET LOCAL ROLE app_runtime")
        self.conn.execute("SELECT set_config('app.current_tenant_id', %s, true)", (tenant_id,))


def rebuild_from_transcript(messages):
    """Events for a client whose Last-Event-ID is past the window: an expiry marker, then the transcript."""
    return [(None, "stream_expired", {}), *((None, "message", message) for message in messages)]

