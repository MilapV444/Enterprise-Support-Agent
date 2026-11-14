"""Case state: one row per (tenant, case), the single source of truth for a case's thread (FR-18 / MS-ADP-04
MS-D8; DECISION-bc6301b4 replaces the LangGraph checkpointer with it).

    store.load(tenant_id, case_id) -> (state, version)       ({}, 0) for a case with no state yet
    store.save(tenant_id, case_id, state, version) -> version  StaleState if another run saved it since load

The version is an optimistic lock: a save names the version it loaded, so two runs of one case cannot both
win. States are plain JSON (schemas.thread_state). The table is module-owned (DECISION-d4b79fe1), applied with
apply_schema(); queries run as app_runtime under the tenant's row-level security. MemoryStore is the same
contract in memory, for tests.
"""

import json

from psycopg.types.json import Jsonb

from data.migrate import psql

SCHEMA_NAME = "orchestrator_0001_case_state.sql"
SCHEMA = """
CREATE TABLE case_state (
  tenant_id  text NOT NULL REFERENCES tenants (id),
  case_id    text NOT NULL,
  state      jsonb NOT NULL,
  version    integer NOT NULL CHECK (version > 0),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, case_id)
);

ALTER TABLE case_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE case_state FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON case_state
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());

ALTER TABLE case_state OWNER TO app_owner;
GRANT SELECT, INSERT, UPDATE ON case_state TO app_runtime;
"""


class StaleState(RuntimeError):
    """Another run saved this case after it was loaded."""


def apply_schema(database):
    if not psql(database, f"SELECT 1 FROM schema_migrations WHERE name = '{SCHEMA_NAME}'"):
        psql(database, f"BEGIN;\n{SCHEMA}\nINSERT INTO schema_migrations (name) VALUES ('{SCHEMA_NAME}');\n"
                       "COMMIT;\n")


class PostgresStore:
    def __init__(self, connect):
        self.connect = connect  # () -> autocommit psycopg connection to the main database

    def _run(self, tenant_id, sql, args):
        with self.connect() as conn, conn.transaction():
            conn.execute("SET LOCAL ROLE app_runtime")
            conn.execute("SELECT set_config('app.current_tenant_id', %s, true)", (tenant_id,))
            return conn.execute(sql, args).fetchone()

    def load(self, tenant_id, case_id):
        row = self._run(tenant_id,
                        "SELECT state, version FROM case_state WHERE tenant_id = %s AND case_id = %s",
                        (tenant_id, case_id))
        return (row[0], row[1]) if row else ({}, 0)

    def save(self, tenant_id, case_id, state, version):
        if version == 0:
            sql = ("INSERT INTO case_state (tenant_id, case_id, state, version) VALUES (%s, %s, %s, 1) "
                   "ON CONFLICT DO NOTHING RETURNING version")
            args = (tenant_id, case_id, Jsonb(state))
        else:
            sql = ("UPDATE case_state SET state = %s, version = version + 1, updated_at = now() "
                   "WHERE tenant_id = %s AND case_id = %s AND version = %s RETURNING version")
            args = (Jsonb(state), tenant_id, case_id, version)
        row = self._run(tenant_id, sql, args)
        if row is None:
            raise StaleState(f"case {tenant_id}:{case_id} changed since version {version}")
        return row[0]


class MemoryStore:
    def __init__(self):
        self.rows = {}  # (tenant, case) -> (JSON text, version): a state that is not JSON fails here too

    def load(self, tenant_id, case_id):
        text, version = self.rows.get((tenant_id, case_id), ("{}", 0))
        return json.loads(text), version

    def save(self, tenant_id, case_id, state, version):
        if self.rows.get((tenant_id, case_id), (None, 0))[1] != version:
            raise StaleState(f"case {tenant_id}:{case_id} changed since version {version}")
        self.rows[(tenant_id, case_id)] = (json.dumps(state), version + 1)
        return version + 1
