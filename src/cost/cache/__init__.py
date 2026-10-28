"""The per-tenant answer cache (FR-42 / CR-ADP-03: CR-D3, CR-D14).

- key(): SHA-256 over the normalised question, the tenant, the product version and the knowledge-base index
  version, so a nightly sync (a new index version) turns every older entry into a miss.
- put(): an answer is stored only when the turn ran no tool, every passage it cites is public, it holds no
  personal data, the question names no version (v2.3, 4.1.0: version-volatile, always deliberated), and Jev
  says, confidently (P >= 0.80), that it is answerable from public documentation alone. Jev unavailable: not
  stored. Entries live seven days.
- get(): a live entry of this tenant only (row-level security as well as the key), and it passes the output
  checks again before it is served.
- evict_document(): a deleted or tombstoned document takes every entry that cited it along (DP-D13).
"""

import hashlib
import re
from datetime import timedelta

from core.orchestrator.decisions import JevUnavailable, Masked
from data.migrate import psql
from safety.output.checks import check
from safety.pii.tokens import find as find_pii

TTL = timedelta(days=7)
ELIGIBLE_AT = 0.80
VERSION = re.compile(r"\bv?\d+\.\d+(?:\.\d+)?\b", re.IGNORECASE)
PUBLIC_ONLY = {"type": "noul",
               "instructions": "Is this question answerable from public product documentation alone, "
                               "without any account-specific or customer data?"}

SCHEMA_NAME = "cost_0001_answer_cache.sql"
SCHEMA = """
CREATE TABLE answer_cache (
  tenant_id  text NOT NULL REFERENCES tenants (id),
  key        text NOT NULL,
  answer     text NOT NULL,
  doc_ids    text[] NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, key)
);
CREATE INDEX answer_cache_docs ON answer_cache USING gin (doc_ids);
ALTER TABLE answer_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE answer_cache FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON answer_cache
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());
ALTER TABLE answer_cache OWNER TO app_owner;
GRANT SELECT, INSERT, UPDATE, DELETE ON answer_cache TO app_runtime;
"""


def apply_schema(database):
    if not psql(database, f"SELECT 1 FROM schema_migrations WHERE name = '{SCHEMA_NAME}'"):
        psql(database, f"BEGIN;\n{SCHEMA}\nINSERT INTO schema_migrations (name) VALUES ('{SCHEMA_NAME}');\n"
                       "COMMIT;\n")


def normalise(question):
    return " ".join(re.sub(r"[^\w\s]", " ", question.casefold()).split())


def key(tenant_id, question, product_version, kb_version):
    material = "\x1f".join([normalise(question), tenant_id, product_version, kb_version])
    return hashlib.sha256(material.encode()).hexdigest()


def _context(conn, tenant_id):
    conn.execute("SET LOCAL ROLE app_runtime")
    conn.execute("SELECT set_config('app.current_tenant_id', %s, true)", (tenant_id,))


class AnswerCache:
    def __init__(self, connect, engine):
        self.connect, self.engine = connect, engine

    def eligible(self, question, answer, passages, tools_called):
        """Why an answer may not be cached, or None. passages: [(doc_id, audience)] it cites."""
        if tools_called:
            return "a tool ran in this turn"
        if not passages or any(audience != "public" for _, audience in passages):
            return "it cites non-public or no documentation"
        if VERSION.search(question):
            return "the question names a version"
        if find_pii(question) or find_pii(answer):
            return "it holds personal data"
        try:
            verdict = self.engine.ask({"question": Masked(question), "answer": Masked(answer)},
                                      {"public": PUBLIC_ONLY})["public"]
        except JevUnavailable:
            return "eligibility could not be decided"
        p_yes = round(verdict.confidence if verdict.value is True else 1 - verdict.confidence, 9)
        return None if p_yes >= ELIGIBLE_AT else "it may depend on account data"

    def put(self, tenant_id, question, answer, product_version, kb_version, passages, tools_called=()):
        """Store an eligible answer; returns None when stored, else the reason it was not."""
        reason = self.eligible(question, answer, passages, tools_called)
        if reason:
            return reason
        with self.connect() as conn, conn.transaction():
            _context(conn, tenant_id)
            conn.execute("INSERT INTO answer_cache (tenant_id, key, answer, doc_ids, expires_at) "
                         "VALUES (%s, %s, %s, %s, now() + %s) ON CONFLICT (tenant_id, key) DO UPDATE "
                         "SET answer = excluded.answer, doc_ids = excluded.doc_ids, created_at = now(), "
                         "expires_at = excluded.expires_at",
                         (tenant_id, key(tenant_id, question, product_version, kb_version), answer,
                          sorted({doc for doc, _ in passages}), TTL))
        return None

    def get(self, tenant_id, question, product_version, kb_version):
        """The cached answer, checked again for delivery, or None."""
        if VERSION.search(question):
            return None
        with self.connect() as conn, conn.transaction():
            _context(conn, tenant_id)
            row = conn.execute("SELECT answer FROM answer_cache WHERE key = %s AND expires_at > now()",
                               (key(tenant_id, question, product_version, kb_version),)).fetchone()
        if row is None:
            return None
        checked = check(row[0])
        return checked.text if checked.verdict == "deliver" else None

    def evict_document(self, tenant_id, doc_id):
        with self.connect() as conn, conn.transaction():
            _context(conn, tenant_id)
            return conn.execute("DELETE FROM answer_cache WHERE %s = ANY (doc_ids)", (doc_id,)).rowcount

    def prune(self, tenant_id):
        with self.connect() as conn, conn.transaction():
            _context(conn, tenant_id)
            return conn.execute("DELETE FROM answer_cache WHERE expires_at <= now()").rowcount
