"""Ingestion: labelled sources, nightly batch and instant purge (FR-10 / KR-ADP-01; FR-11 / KR-ADP-02).

Every chunk carries: audience (internal unless the source marks it customer_visible), provenance (human or
agent), source kind (curated / operational / ticket) and the source's ACL. Text is masked before embedding.

Deletions do not wait for the batch: purge() writes a durable tombstone first, then removes the document's
chunks and checks none are left. The nightly batch skips tombstoned documents, re-indexes the rest in place,
purges documents the source no longer has, and ends with an audit that no tombstoned document is indexed.
Tombstones are module-owned schema (DECISION-d4b79fe1).
"""

from dataclasses import dataclass, field
from datetime import date

from core.orchestrator.decisions import mask
from data.migrate import psql
from data.storage import write_snapshot
from knowledge.ingest.chunker import chunk

AUDIENCES = ("internal", "customer_visible")
PROVENANCE = ("human", "agent")
SOURCE_KINDS = ("curated", "operational", "ticket")

SCHEMA_NAME = "knowledge_0001_tombstones.sql"
SCHEMA = """
CREATE TABLE knowledge_tombstones (
  scope      text NOT NULL,  -- 'public' or the tenant id whose private collection held the document
  doc_id     text NOT NULL,
  reason     text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (scope, doc_id)
);
ALTER TABLE knowledge_tombstones OWNER TO app_owner;
GRANT SELECT, INSERT ON knowledge_tombstones TO app_runtime;
"""


class TombstoneLeak(RuntimeError):
    pass


def apply_schema(database):
    if not psql(database, f"SELECT 1 FROM schema_migrations WHERE name = '{SCHEMA_NAME}'"):
        psql(database, f"BEGIN;\n{SCHEMA}\nINSERT INTO schema_migrations (name) VALUES ('{SCHEMA_NAME}');\n"
                       "COMMIT;\n")


@dataclass
class Document:
    doc_id: str
    source_system: str             # e.g. "zendesk", "confluence"
    source_kind: str               # curated | operational | ticket (KR-D1)
    title: str
    markdown: str
    audience: str = "internal"     # KR-D13: internal unless the source says customer_visible
    provenance: str = "human"      # KR-D16: human | agent
    acl_groups: list[str] = field(default_factory=list)  # empty = everyone in the scope
    is_restricted: bool = False    # restricted docs get a live permission check at retrieval
    updated_at: str = ""

    def __post_init__(self):
        if self.audience not in AUDIENCES or self.provenance not in PROVENANCE:
            raise ValueError(f"{self.doc_id}: bad audience or provenance label")
        if self.source_kind not in SOURCE_KINDS:
            raise ValueError(f"{self.doc_id}: unknown source kind {self.source_kind!r}")


def chunks_of(document, scope):
    """Payloads for every child chunk, masked and labelled."""
    payloads = []
    for parent_id, heading, parent_text, children in chunk(document.doc_id, document.markdown):
        for child_id, child_text in children:
            payloads.append({
                "chunk_id": child_id, "doc_id": document.doc_id, "parent_id": parent_id,
                "scope": scope, "title": document.title, "heading": heading,
                "text": mask(child_text).text, "parent_text": mask(parent_text).text,
                "source_system": document.source_system, "source_kind": document.source_kind,
                "audience": document.audience, "provenance": document.provenance,
                "acl_groups": list(document.acl_groups), "is_restricted": document.is_restricted,
                "updated_at": document.updated_at,
            })
    return payloads


class Ingestion:
    def __init__(self, index, embed, conn, snapshots=None):
        """embed(texts) -> vectors; conn: autocommit psycopg connection; snapshots: object store or None."""
        self.index, self.embed, self.conn, self.snapshots = index, embed, conn, snapshots

    def tombstones(self, scope):
        rows = self.conn.execute("SELECT doc_id FROM knowledge_tombstones WHERE scope = %s", (scope,))
        return {doc_id for (doc_id,) in rows.fetchall()}

    def purge(self, scope, doc_id, reason):
        """Instant out-of-band deletion: tombstone first, so a running batch cannot bring it back."""
        self.conn.execute("INSERT INTO knowledge_tombstones (scope, doc_id, reason) VALUES (%s, %s, %s) "
                          "ON CONFLICT DO NOTHING", (scope, doc_id, reason))
        self.index.delete_document(scope, doc_id)
        if self.index.count(scope, doc_id):
            raise TombstoneLeak(f"{doc_id} still indexed in {scope} after purge")

    def run_batch(self, scope, source_system, documents, batch_date=None):
        """Nightly sync of one source's full snapshot into a scope. Returns a report."""
        documents = [d for d in documents if d.source_system == source_system]
        tombstoned = self.tombstones(scope)
        keep = [d for d in documents if d.doc_id not in tombstoned]
        if self.snapshots is not None:
            raw = {f"{d.doc_id}.md": d.markdown.encode() for d in keep}
            write_snapshot(self.snapshots, scope, batch_date or date.today(), raw)
        for document in keep:
            payloads = chunks_of(document, scope)
            vectors = self.embed([p["text"] for p in payloads]) if payloads else []
            self.index.replace_document(scope, document.doc_id, payloads, vectors)
        gone = self.index.doc_ids(scope, source_system) - {d.doc_id for d in keep}
        for doc_id in gone:
            self.purge(scope, doc_id, "no longer in the source")
        leaked = [doc_id for doc_id in self.tombstones(scope) if self.index.count(scope, doc_id)]
        for doc_id in leaked:  # post-batch audit: purge again and report
            self.index.delete_document(scope, doc_id)
        return {"indexed": len(keep), "skipped_tombstoned": len(documents) - len(keep),
                "purged_missing": sorted(gone), "leaked_and_repurged": leaked}
