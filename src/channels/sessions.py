"""Session -> conversation -> case (FR-8; UA-D5 resolved by MS-D1, UA-D6, UA-Q3).

- A session ends after 30 min without an authenticated request or 12 h after it began, whichever is first.
  Any authenticated request, an open event stream included, counts as activity (touch()).
- A conversation belongs to one principal and outlives the session it started in.
- Several conversations can link to one case.

Tables are module-owned (DECISION-d4b79fe1) and applied with apply_schema(); every query runs as app_runtime
under the tenant's row-level security context. Connections must be in autocommit mode.
"""

from data.migrate import psql

IDLE = "30 minutes"
ABSOLUTE = "12 hours"

SCHEMA_NAME = "sessions_0001_sessions_conversations_cases.sql"
SCHEMA = """
CREATE TABLE sessions (
  id           text PRIMARY KEY DEFAULT gen_random_uuid()::text,
  tenant_id    text NOT NULL REFERENCES tenants (id),
  principal_id text NOT NULL,
  tier         text NOT NULL CHECK (tier IN ('T0_ANON', 'T1_VERIFIED', 'T2_SSO')),
  created_at   timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  ended_at     timestamptz
);

CREATE TABLE cases (
  id         text PRIMARY KEY DEFAULT gen_random_uuid()::text,
  tenant_id  text NOT NULL REFERENCES tenants (id),
  status     text NOT NULL DEFAULT 'open',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE conversations (
  tenant_id    text NOT NULL REFERENCES tenants (id),
  id           text NOT NULL,
  principal_id text NOT NULL,
  session_id   text NOT NULL REFERENCES sessions (id),  -- the session it started in; it outlives it
  case_id      text REFERENCES cases (id),
  created_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, id)
);

ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON sessions
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());
ALTER TABLE cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE cases FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON cases
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON conversations
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());

ALTER TABLE sessions OWNER TO app_owner;
ALTER TABLE cases OWNER TO app_owner;
ALTER TABLE conversations OWNER TO app_owner;
GRANT SELECT, INSERT, UPDATE ON sessions, cases, conversations TO app_runtime;
"""


def apply_schema(database):
    if not psql(database, f"SELECT 1 FROM schema_migrations WHERE name = '{SCHEMA_NAME}'"):
        psql(database, f"BEGIN;\n{SCHEMA}\nINSERT INTO schema_migrations (name) VALUES ('{SCHEMA_NAME}');\n"
                       "COMMIT;\n")


def _context(conn, tenant_id):
    conn.execute("SET LOCAL ROLE app_runtime")
    conn.execute("SELECT set_config('app.current_tenant_id', %s, true)", (tenant_id,))


def start(conn, tenant_id, principal_id, tier):
    with conn.transaction():
        _context(conn, tenant_id)
        (session_id,) = conn.execute(
            "INSERT INTO sessions (tenant_id, principal_id, tier) VALUES (%s, %s, %s) RETURNING id",
            (tenant_id, principal_id, tier)).fetchone()
    return session_id


def touch(conn, tenant_id, session_id):
    """Record activity on a live session and return (principal_id, tier); None if it has ended or expired."""
    with conn.transaction():
        _context(conn, tenant_id)
        row = conn.execute(
            "UPDATE sessions SET last_seen_at = now() WHERE id = %s AND ended_at IS NULL "
            "AND last_seen_at > now() - %s::interval AND created_at > now() - %s::interval "
            "RETURNING principal_id, tier", (session_id, IDLE, ABSOLUTE)).fetchone()
    return tuple(row) if row else None


def raise_tier(conn, tenant_id, session_id, principal_id, tier):
    """Step-up inside a live session. Conversations an anonymous principal started move to the new one."""
    with conn.transaction():
        _context(conn, tenant_id)
        (previous,) = conn.execute(
            "SELECT principal_id FROM sessions WHERE id = %s FOR UPDATE", (session_id,)).fetchone()
        conn.execute("UPDATE sessions SET principal_id = %s, tier = %s, last_seen_at = now() WHERE id = %s",
                     (principal_id, tier, session_id))
        if previous != principal_id:
            conn.execute("UPDATE conversations SET principal_id = %s "
                         "WHERE session_id = %s AND principal_id = %s", (principal_id, session_id, previous))


def end(conn, tenant_id, session_id):
    with conn.transaction():
        _context(conn, tenant_id)
        conn.execute("UPDATE sessions SET ended_at = now() WHERE id = %s AND ended_at IS NULL", (session_id,))


def open_conversation(conn, tenant_id, principal_id, session_id, conversation_id):
    """Create the conversation for this principal if new; False if it belongs to someone else."""
    with conn.transaction():
        _context(conn, tenant_id)
        conn.execute("INSERT INTO conversations (tenant_id, id, principal_id, session_id) "
                     "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                     (tenant_id, conversation_id, principal_id, session_id))
        (owner,) = conn.execute("SELECT principal_id FROM conversations WHERE id = %s",
                                (conversation_id,)).fetchone()
    return owner == principal_id


def link_case(conn, tenant_id, conversation_id, case_id=None):
    """Link a conversation to a case, opening a new case when none is given; returns the case id."""
    with conn.transaction():
        _context(conn, tenant_id)
        if case_id is None:
            (case_id,) = conn.execute("INSERT INTO cases (tenant_id) VALUES (%s) RETURNING id",
                                      (tenant_id,)).fetchone()
        elif conn.execute("SELECT 1 FROM cases WHERE id = %s", (case_id,)).fetchone() is None:
            # Foreign keys are checked without row-level security, so check visibility here.
            raise LookupError(f"unknown case {case_id!r}")
        updated = conn.execute("UPDATE conversations SET case_id = %s WHERE id = %s",
                               (case_id, conversation_id)).rowcount
        if updated != 1:
            raise LookupError(f"unknown conversation {conversation_id!r}")
    return case_id
