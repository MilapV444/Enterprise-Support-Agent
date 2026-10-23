"""Long-term facts about one user, with validity dates (FR-16 / MS-ADP-02: MS-D3, MS-D4, MS-D6).

- Per user only: row-level security keys every row on tenant and principal, so one user's facts are invisible
  to another user of the same tenant, whatever the query says. The principal must come from the verified
  token context, never from conversation text.
- Validity dates: a fact is valid from valid_from until valid_to (NULL = still true). Changing a fact closes
  the old row and adds a new one; a closed row can never change again (only valid_to is updatable, once).
  as_of() answers what was true at a past moment.
- Encrypted at rest under the user's own data key (data.keys), statement and embedding both, so shredding the
  user's key makes every fact unreadable.
- Account facts (SLA, contract, billing, plan) are never stored: the write path refuses them and the CRM is
  asked live instead.

ponytail: no pgvector in the compose Postgres, so nearest neighbours are found in Python over the user's
active facts (tens per user); the recency / importance / relevance ranking for the profile slot comes with
the context wiring.
"""

import json
import math
import uuid
from dataclasses import dataclass
from datetime import datetime

from data.keys import KeyShredded, decrypt_field, encrypt_field
from data.migrate import psql

CATEGORIES = ("user_preference", "technical_env", "episodic_hist", "comm_style")

SCHEMA_NAME = "memory_0002_user_facts.sql"
SCHEMA = """
CREATE TABLE user_facts (
  id             uuid PRIMARY KEY,
  tenant_id      text NOT NULL REFERENCES tenants (id),
  principal_id   text NOT NULL,
  category       text NOT NULL CHECK (category IN ('user_preference', 'technical_env', 'episodic_hist',
                                                   'comm_style')),
  importance     smallint NOT NULL CHECK (importance BETWEEN 1 AND 10),
  statement_enc  bytea NOT NULL,
  embedding_enc  bytea NOT NULL,
  source_case_id text,
  replaces       uuid REFERENCES user_facts (id),
  valid_from     timestamptz NOT NULL DEFAULT now(),
  valid_to       timestamptz CHECK (valid_to IS NULL OR valid_to >= valid_from)
);
CREATE INDEX user_facts_active ON user_facts (tenant_id, principal_id) WHERE valid_to IS NULL;

CREATE FUNCTION keep_closed_facts() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.valid_to IS NOT NULL THEN
    RAISE EXCEPTION 'fact % was closed at % and cannot change', OLD.id, OLD.valid_to;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER user_facts_closed_immutable BEFORE UPDATE ON user_facts
  FOR EACH ROW EXECUTE FUNCTION keep_closed_facts();

ALTER TABLE user_facts ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_facts FORCE ROW LEVEL SECURITY;
CREATE POLICY own_facts ON user_facts
  USING (tenant_id = current_tenant()
         AND principal_id = NULLIF(current_setting('app.current_principal_id', true), ''))
  WITH CHECK (tenant_id = current_tenant()
              AND principal_id = NULLIF(current_setting('app.current_principal_id', true), ''));
ALTER TABLE user_facts OWNER TO app_owner;
GRANT SELECT, INSERT ON user_facts TO app_runtime;
GRANT UPDATE (valid_to) ON user_facts TO app_runtime;
"""


@dataclass
class Fact:
    id: str
    statement: str
    category: str
    importance: int
    embedding: list[float]
    valid_from: datetime
    valid_to: datetime | None
    replaces: str | None


def apply_schema(database):
    if not psql(database, f"SELECT 1 FROM schema_migrations WHERE name = '{SCHEMA_NAME}'"):
        psql(database, f"BEGIN;\n{SCHEMA}\nINSERT INTO schema_migrations (name) VALUES ('{SCHEMA_NAME}');\n"
                       "COMMIT;\n")


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


class FactStore:
    def __init__(self, conn, keys):
        """conn: autocommit connection to the main database; keys: data.keys.KeyStore."""
        self.conn, self.keys = conn, keys

    def context(self, tenant_id, principal_id):
        """Call inside a transaction: every statement after it sees only this user's facts."""
        self.conn.execute("SET LOCAL ROLE app_runtime")
        self.conn.execute("SELECT set_config('app.current_tenant_id', %s, true), "
                          "set_config('app.current_principal_id', %s, true)", (tenant_id, principal_id))

    def _open(self, tenant_id, principal_id, row):
        fact_id, category, importance, statement, embedding, valid_from, valid_to, replaces = row
        fact_id = str(fact_id)
        text = self._decrypt(tenant_id, principal_id, f"fact:{fact_id}", statement).decode()
        vector = json.loads(self._decrypt(tenant_id, principal_id, f"fact-embedding:{fact_id}", embedding))
        return Fact(fact_id, text, category, importance, vector, valid_from, valid_to,
                    str(replaces) if replaces else None)

    def _decrypt(self, tenant_id, principal_id, field, blob):
        return decrypt_field(self.keys, tenant_id, principal_id, field, bytes(blob))

    def as_of(self, tenant_id, principal_id, at=None):
        """Facts true at `at` (default: now). Empty once the user's key is shredded."""
        with self.conn.transaction():
            self.context(tenant_id, principal_id)
            rows = self.conn.execute(
                "SELECT id, category, importance, statement_enc, embedding_enc, valid_from, valid_to, "
                "replaces FROM user_facts WHERE valid_from <= coalesce(%s, now()) "
                "AND (valid_to IS NULL OR valid_to > coalesce(%s, now())) ORDER BY valid_from, id",
                (at, at)).fetchall()
        try:
            return [self._open(tenant_id, principal_id, row) for row in rows]
        except KeyShredded:
            return []

    def nearest(self, tenant_id, principal_id, embedding, k=3):
        facts = self.as_of(tenant_id, principal_id)
        return sorted(facts, key=lambda fact: -cosine(embedding, fact.embedding))[:k]

    def add(self, tenant_id, principal_id, statement, category, importance, embedding, case_id=None,
            replaces=None):
        """Insert a new fact, closing `replaces` in the same transaction; returns the new id, or None when
        `replaces` was already closed by someone else."""
        if category not in CATEGORIES:
            raise ValueError(f"unknown fact category {category!r}")
        fact_id = str(uuid.uuid4())
        statement_enc = encrypt_field(self.keys, tenant_id, principal_id, f"fact:{fact_id}",
                                      statement.encode())
        embedding_enc = encrypt_field(self.keys, tenant_id, principal_id, f"fact-embedding:{fact_id}",
                                      json.dumps(embedding).encode())
        with self.conn.transaction():
            self.context(tenant_id, principal_id)
            if replaces and not self._close(replaces):
                return None
            self.conn.execute(
                "INSERT INTO user_facts (id, tenant_id, principal_id, category, importance, statement_enc, "
                "embedding_enc, source_case_id, replaces) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (fact_id, tenant_id, principal_id, category, importance, statement_enc, embedding_enc,
                 case_id, replaces))
        return fact_id

    def close(self, tenant_id, principal_id, fact_id):
        """The fact stops being true now; False if it was already closed."""
        with self.conn.transaction():
            self.context(tenant_id, principal_id)
            return self._close(fact_id)

    def _close(self, fact_id):
        return self.conn.execute("UPDATE user_facts SET valid_to = now() WHERE id = %s AND valid_to IS NULL",
                                 (fact_id,)).rowcount == 1
