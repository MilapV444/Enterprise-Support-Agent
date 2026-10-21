"""The legal transcript archive (FR-34 / SG-ADP-05: SG-D12; DP-D8).

Closed conversations are kept for 2 years in transcript_legal_archive, which only the legal_archive role can
read or write (the agent runtime has no grant). The archive is kept under GDPR Art. 17(3)(e): a customer
erasure purges the agent's memory, not this archive. Transcripts are stored tokenized: archive() refuses one
that still holds raw PII. sweep() deletes transcripts whose 2 years are up; the table's trigger refuses any
earlier deletion and a check constraint refuses a shorter retention.

ponytail: a Postgres table with triggers stands in for the S3 Object Lock vault; legal holds and the General
Counsel dual sign-off for reads are not modelled yet.
"""

from psycopg.types.json import Jsonb

from safety.pii.tokens import find


class RawPII(ValueError):
    pass


class TranscriptArchive:
    def __init__(self, connect):
        """connect(): autocommit psycopg connection to the main database, with the legal archive's
        credentials."""
        self.connect = connect

    def _context(self, conn, tenant_id):
        conn.execute("SET LOCAL ROLE legal_archive")
        conn.execute("SELECT set_config('app.current_tenant_id', %s, true)", (tenant_id,))

    def archive(self, tenant_id, conversation_id, transcript):
        """transcript: [{"role", "content"}] as tokenized by the PII vault; returns the archive id."""
        kinds = sorted({span[2] for message in transcript for span in find(message["content"])})
        if kinds:
            # name the kinds, never the values
            raise RawPII(f"transcript {conversation_id} still holds raw {', '.join(kinds)}")
        with self.connect() as conn, conn.transaction():
            self._context(conn, tenant_id)
            return conn.execute("INSERT INTO transcript_legal_archive (tenant_id, conversation_id, "
                                "transcript) VALUES (%s, %s, %s) RETURNING id",
                                (tenant_id, conversation_id, Jsonb(transcript))).fetchone()[0]

    def read(self, tenant_id, conversation_id):
        with self.connect() as conn, conn.transaction():
            self._context(conn, tenant_id)
            return conn.execute("SELECT transcript, archived_at, retain_until FROM transcript_legal_archive "
                                "WHERE conversation_id = %s ORDER BY id", (conversation_id,)).fetchall()

    def sweep(self, tenant_id):
        """Delete this tenant's transcripts whose retention has ended; returns how many."""
        with self.connect() as conn, conn.transaction():
            self._context(conn, tenant_id)
            return len(conn.execute("DELETE FROM transcript_legal_archive WHERE retain_until <= now() "
                                    "RETURNING id").fetchall())
