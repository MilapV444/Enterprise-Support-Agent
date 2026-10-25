"""The tool audit log: one append-only record per tool call, personal data crypto-shredded (FR-24 / TA-ADP-05:
TA-D12, TA-D15).

Records go into tool_audit_records (M0-03: append-only by trigger, tenant row-level security, part of the
erasure inventory). Each holds, in plain text, what an auditor needs: tenant, case, conversation, user, tool,
forward or compensating action, outcome and error code, the saga step, idempotency key, credential basis
(on-behalf-of or service account), risk class, the approval request, and the USD amount. Everything personal
(the call's arguments and the before / after snapshots of a financial write) is sealed in payload_enc under
the user's own data key (data.keys, field "tool_audit:<audit_id>"): erasing the user deletes the key, and the
record stays intact but its personal part can no longer be read.
"""

import json
import uuid

from data.keys import KeyShredded, decrypt_field, encrypt_field
from data.migrate import psql

SCHEMA_NAME = "tools_0001_audit.sql"
SCHEMA = """
ALTER TABLE tool_audit_records
  ADD COLUMN audit_id            uuid UNIQUE,
  ADD COLUMN case_id             text,
  ADD COLUMN call_id             text,
  ADD COLUMN saga_id             text,
  ADD COLUMN step_id             text,
  ADD COLUMN idempotency_key     text,
  ADD COLUMN credential_basis    text,
  ADD COLUMN risk_class          text,
  ADD COLUMN approval_request_id uuid,
  ADD COLUMN amount_usd          numeric(14, 2),
  ADD COLUMN error_code          text;
CREATE INDEX tool_audit_records_case ON tool_audit_records (tenant_id, case_id, created_at);
"""
COLUMNS = ("tenant_id", "conversation_id", "user_id", "tool", "action", "outcome", "audit_id", "case_id",
           "call_id", "saga_id", "step_id", "idempotency_key", "credential_basis", "risk_class",
           "approval_request_id", "amount_usd", "error_code")


def apply_schema(database):
    if not psql(database, f"SELECT 1 FROM schema_migrations WHERE name = '{SCHEMA_NAME}'"):
        psql(database, f"BEGIN;\n{SCHEMA}\nINSERT INTO schema_migrations (name) VALUES ('{SCHEMA_NAME}');\n"
                       "COMMIT;\n")


class AuditLog:
    def __init__(self, connect, keys):
        """connect(): autocommit connection to the main database; keys(): a data.keys.KeyStore."""
        self.connect, self.keys = connect, keys

    @staticmethod
    def _context(conn, tenant_id):
        conn.execute("SET LOCAL ROLE app_runtime")
        conn.execute("SELECT set_config('app.current_tenant_id', %s, true)", (tenant_id,))

    def record(self, *, tenant_id, conversation_id, user_id, tool_id, action, outcome, personal=None,
               **fields):
        """Append one record; `personal` (JSON-able) is sealed under the user's key. Returns the audit id."""
        audit_id = str(uuid.uuid4())
        sealed = None
        if personal is not None:
            sealed = encrypt_field(self.keys(), tenant_id, user_id, f"tool_audit:{audit_id}",
                                   json.dumps(personal, sort_keys=True, default=str).encode())
        values = {"tenant_id": tenant_id, "conversation_id": conversation_id, "user_id": user_id,
                  "tool": tool_id, "action": action, "outcome": outcome, "audit_id": audit_id, **fields}
        unknown = set(values) - set(COLUMNS)
        if unknown:
            raise ValueError(f"unknown audit fields: {sorted(unknown)}")
        names = [*values, "payload_enc"]
        with self.connect() as conn, conn.transaction():
            self._context(conn, tenant_id)
            conn.execute(f"INSERT INTO tool_audit_records ({', '.join(names)}) "
                         f"VALUES ({', '.join(['%s'] * len(names))})", [*values.values(), sealed])
        return audit_id

    def read(self, tenant_id, case_id):
        """The case's records, oldest first; "personal" is None once the user's key has been shredded."""
        with self.connect() as conn, conn.transaction():
            self._context(conn, tenant_id)
            cursor = conn.execute(f"SELECT {', '.join(COLUMNS)}, payload_enc FROM tool_audit_records "
                                  "WHERE case_id = %s ORDER BY id", (case_id,))
            rows = [dict(zip([*COLUMNS, "payload_enc"], row, strict=True)) for row in cursor.fetchall()]
        store = self.keys()
        for row in rows:
            sealed = row.pop("payload_enc")
            row["personal"] = None
            if sealed is not None:
                try:
                    field = f"tool_audit:{row['audit_id']}"
                    row["personal"] = json.loads(decrypt_field(store, tenant_id, row["user_id"], field,
                                                               bytes(sealed)))
                except KeyShredded:
                    pass
        return rows
