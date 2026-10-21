"""Decision records and the customer "why" view (FR-34 / SG-ADP-05: SG-D13, SG-D14).

Every automated decision is appended to decision_records (append-only, tenant row-level security) with:
- reason and checks: plain language, for the customer's "why" view;
- trace: the specialist's forensic detail (Jev answers and confidences, Cedar verdicts, classifier scores,
  model ids, prompt version), which the "why" view never selects.
record() refuses a reason or check that would leak a number, score, threshold, prompt or policy syntax (UU3:
probing the "why" view to map cut-offs); reasons are written by code, so a leak is a bug, caught before the
write. Decisions on the significant list (SG-Q5) are recorded as needing human review until a named human
signs them off, and require_sign_off() refuses to finalise one without that sign-off.
"""

import re

from psycopg.types.json import Jsonb

from data.migrate import psql

SCHEMA_NAME = "governance_0001_decisions_archive.sql"
SCHEMA = """
ALTER TABLE decision_records
  ADD COLUMN checks      jsonb   NOT NULL DEFAULT '[]',
  ADD COLUMN trace       jsonb   NOT NULL DEFAULT '{}',
  ADD COLUMN needs_human boolean NOT NULL DEFAULT false;
-- 2 years from archiving, never less; the sweeper may delete only what the retention trigger lets go.
ALTER TABLE transcript_legal_archive
  ADD CONSTRAINT retained_two_years CHECK (retain_until >= archived_at + interval '2 years');
GRANT DELETE ON transcript_legal_archive TO legal_archive;
"""

SIGNIFICANT = frozenset({  # SG-Q5: never final without a human
    "account_suspension", "account_termination", "dispute_rejection", "refund_denial",
    "contract_change", "contract_downgrade", "sla_breach_denial",
})
LEAK = re.compile(r"\d|score|confiden|threshold|probab|prompt|permit\s*\(|forbid\s*\(", re.IGNORECASE)


class LeakyExplanation(ValueError):
    pass


class HumanReviewRequired(PermissionError):
    pass


def apply_schema(database):
    if not psql(database, f"SELECT 1 FROM schema_migrations WHERE name = '{SCHEMA_NAME}'"):
        psql(database, f"BEGIN;\n{SCHEMA}\nINSERT INTO schema_migrations (name) VALUES ('{SCHEMA_NAME}');\n"
                       "COMMIT;\n")


def require_sign_off(decision, signed_by=None):
    if decision in SIGNIFICANT and not signed_by:
        raise HumanReviewRequired(f"{decision} needs a human specialist's sign-off")


class DecisionLog:
    def __init__(self, connect):
        """connect(): autocommit psycopg connection to the main database."""
        self.connect = connect

    def _context(self, conn, tenant_id):
        conn.execute("SET LOCAL ROLE app_runtime")
        conn.execute("SELECT set_config('app.current_tenant_id', %s, true)", (tenant_id,))

    def record(self, tenant_id, conversation_id, decision, reason, checks, trace, turn_id=None,
               signed_by=None):
        """Append one decision; returns its id. trace must be JSON-serialisable and already PII-masked."""
        for text in (decision, reason, *checks):
            if LEAK.search(text):
                raise LeakyExplanation(f"not for the customer's why view: {text!r}")
        trace = {**trace, "signed_by": signed_by} if signed_by else trace
        with self.connect() as conn, conn.transaction():
            self._context(conn, tenant_id)
            return conn.execute(
                "INSERT INTO decision_records (tenant_id, conversation_id, turn_id, decision, reason, "
                "checks, trace, needs_human) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (tenant_id, conversation_id, turn_id, decision, reason, Jsonb(list(checks)), Jsonb(trace),
                 decision in SIGNIFICANT and not signed_by)).fetchone()[0]

    def why(self, tenant_id, conversation_id):
        """The customer's view: what was decided, why, and which checks passed. Nothing else."""
        with self.connect() as conn, conn.transaction():
            self._context(conn, tenant_id)
            rows = conn.execute("SELECT decision, reason, checks, needs_human FROM decision_records "
                                "WHERE conversation_id = %s ORDER BY id", (conversation_id,)).fetchall()
        return [{"decision": decision, "reason": reason, "checks": checks, "requires_human_review": human,
                 "human_available": True} for decision, reason, checks, human in rows]

    def audit(self, tenant_id, conversation_id):
        """The specialist's view: every column, including the forensic trace."""
        with self.connect() as conn, conn.transaction():
            self._context(conn, tenant_id)
            cursor = conn.execute("SELECT * FROM decision_records WHERE conversation_id = %s ORDER BY id",
                                  (conversation_id,))
            names = [column.name for column in cursor.description]
            return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]
