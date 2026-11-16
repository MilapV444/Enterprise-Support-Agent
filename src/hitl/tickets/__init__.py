"""Support tickets the agent raises for a signed-in customer (FR-45, FR-46, FR-47; DECISION-368069f5).

A ticket starts as a proposal: the agent offers it in the chat and nothing is raised until the customer
confirms. Confirming opens it (status open); a proposal nobody confirms expires. Each ticket keeps its history
in ticket_events (created, confirmed, notes, status changes).

    tickets = Tickets(connect)
    proposal = tickets.propose(tenant, principal, conversation, key, category=..., subject=..., ...)
    ticket = tickets.confirm(tenant, principal, proposal.id)    # once; a repeat returns the same ticket
    tickets.add_note(tenant, principal, ticket.id, "customer", masked_text)
    tickets.list_for(tenant, principal); tickets.get(tenant, principal, ticket_id)

Rows are tenant-isolated by row-level security and every read and write names the customer, so a customer only
ever reaches their own tickets. Texts are stored masked (PII tokens). One proposal per (tenant,
conversation, key): proposing again with the same key, a retried turn for instance, returns the first one.
Amounts are integer cents with a currency, set and compared in code. The module owns its tables
(DECISION-d4b79fe1), applied with apply_schema(); memory.lifecycle erases them with the customer's data and
retention expires them.
"""

from dataclasses import dataclass, field
from datetime import datetime

from data.migrate import psql
from hitl.queues import Refused, context

PROPOSAL_TTL = "24 hours"   # an unconfirmed proposal expires after this
RAISED = ("open", "in_review", "resolved", "closed")  # what My tickets lists; a proposal is only an offer
CATEGORIES = ("refund", "billing", "technical", "account", "security", "general")

SCHEMA_NAME = "hitl_0003_tickets.sql"
SCHEMA = """
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'lifecycle_service') THEN
    CREATE ROLE lifecycle_service NOLOGIN;
  END IF;
END $$;

CREATE TABLE support_tickets (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id       text NOT NULL REFERENCES tenants (id),
  principal_id    text NOT NULL,
  conversation_id text NOT NULL,
  proposal_key    text NOT NULL,
  created_turn    text,
  category        text NOT NULL CHECK (category IN ('refund', 'billing', 'technical', 'account', 'security',
                                                    'general')),
  subject         text NOT NULL,
  description     text NOT NULL DEFAULT '',                  -- masked
  invoice_id      text,
  amount_cents    bigint CHECK (amount_cents >= 0),
  currency        text CHECK (currency ~ '^[A-Z]{3}$'),
  status          text NOT NULL DEFAULT 'proposed'
                  CHECK (status IN ('proposed', 'open', 'in_review', 'resolved', 'closed', 'expired')),
  queue           text NOT NULL,
  reason          text NOT NULL,
  expires_at      timestamptz NOT NULL DEFAULT now() + interval '24 hours',
  created_at      timestamptz NOT NULL DEFAULT now(),
  opened_at       timestamptz,
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, conversation_id, proposal_key)
);
CREATE INDEX support_tickets_owner ON support_tickets (tenant_id, principal_id, status);

CREATE TABLE ticket_events (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id  text NOT NULL REFERENCES tenants (id),
  ticket_id  bigint NOT NULL REFERENCES support_tickets (id) ON DELETE CASCADE,
  kind       text NOT NULL CHECK (kind IN ('proposed', 'confirmed', 'note', 'status')),
  actor      text NOT NULL,
  text       text NOT NULL DEFAULT '',                       -- masked
  at         timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX ticket_events_ticket ON ticket_events (ticket_id, id);

ALTER TABLE support_tickets ENABLE ROW LEVEL SECURITY;
ALTER TABLE support_tickets FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON support_tickets
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());
ALTER TABLE ticket_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE ticket_events FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON ticket_events
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());

ALTER TABLE support_tickets OWNER TO app_owner;
ALTER TABLE ticket_events OWNER TO app_owner;
GRANT SELECT, INSERT, UPDATE ON support_tickets TO app_runtime;
GRANT SELECT, INSERT ON ticket_events TO app_runtime;
-- erasure and retention (memory.lifecycle)
GRANT SELECT, UPDATE, DELETE ON support_tickets TO lifecycle_service;
GRANT SELECT, DELETE ON ticket_events TO lifecycle_service;
"""

COLUMNS = ("id, tenant_id, principal_id, conversation_id, proposal_key, category, subject, description, "
           "invoice_id, amount_cents, currency, status, queue, reason, expires_at, created_at, opened_at, "
           "updated_at")


@dataclass(frozen=True)
class Ticket:
    id: int
    tenant_id: str
    principal_id: str
    conversation_id: str
    proposal_key: str
    category: str
    subject: str
    description: str
    invoice_id: str | None
    amount_cents: int | None
    currency: str | None
    status: str
    queue: str
    reason: str
    expires_at: datetime
    created_at: datetime
    opened_at: datetime | None
    updated_at: datetime
    events: tuple = field(default=(), compare=False)

    @property
    def number(self):
        return f"TKT-{self.id:05d}"

    def card(self):
        """The fields a chat card and the ticket list show (JSON-safe)."""
        return {"ticket_id": self.number, "status": self.status, "category": self.category,
                "subject": self.subject, "invoice_id": self.invoice_id, "amount_cents": self.amount_cents,
                "currency": self.currency, "queue": self.queue, "created_at": self.created_at.isoformat()}


def apply_schema(database):
    if not psql(database, f"SELECT 1 FROM schema_migrations WHERE name = '{SCHEMA_NAME}'"):
        psql(database, f"BEGIN;\n{SCHEMA}\nINSERT INTO schema_migrations (name) VALUES ('{SCHEMA_NAME}');\n"
                       "COMMIT;\n")


def number_id(number):
    """TKT-00042 -> 42; anything else -> None."""
    digits = str(number).removeprefix("TKT-")
    return int(digits) if digits.isdigit() else None


class Tickets:
    def __init__(self, connect):
        self.connect = connect  # () -> autocommit psycopg connection to the main database

    def _ticket(self, conn, where, args):
        row = conn.execute(f"SELECT {COLUMNS} FROM support_tickets WHERE {where}", args).fetchone()
        return Ticket(*row) if row else None

    def _event(self, conn, tenant_id, ticket_id, kind, actor, text=""):
        conn.execute("INSERT INTO ticket_events (tenant_id, ticket_id, kind, actor, text) "
                     "VALUES (%s, %s, %s, %s, %s)", (tenant_id, ticket_id, kind, actor, text))

    def propose(self, tenant_id, principal_id, conversation_id, key, *, category, subject, queue, reason,
                description="", invoice_id=None, amount_cents=None, currency=None, turn_id=None):
        """The conversation's proposal for `key`; the first one if it was proposed before."""
        if category not in CATEGORIES:
            raise ValueError(f"unknown ticket category {category!r}")
        with self.connect() as conn, conn.transaction():
            context(conn, tenant_id)
            row = conn.execute(
                "INSERT INTO support_tickets (tenant_id, principal_id, conversation_id, proposal_key, "
                "created_turn, category, subject, description, invoice_id, amount_cents, currency, queue, "
                f"reason, expires_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                f"now() + interval '{PROPOSAL_TTL}') ON CONFLICT DO NOTHING RETURNING id",
                (tenant_id, principal_id, conversation_id, key, turn_id, category, subject, description,
                 invoice_id, amount_cents, currency, queue, reason)).fetchone()
            if row:
                self._event(conn, tenant_id, row[0], "proposed", "agent", subject)
            return self._ticket(conn, "tenant_id = %s AND conversation_id = %s AND proposal_key = %s",
                                (tenant_id, conversation_id, key))

    def confirm(self, tenant_id, principal_id, ticket_id):
        """Open the customer's proposal. A repeat returns the same open ticket; an expired, someone else's or
        unknown proposal is Refused."""
        with self.connect() as conn, conn.transaction():
            context(conn, tenant_id)
            ticket = self._ticket(conn, "tenant_id = %s AND principal_id = %s AND id = %s FOR UPDATE",
                                  (tenant_id, principal_id, ticket_id))
            if ticket is None:
                raise Refused("no such ticket proposal")
            if ticket.status in RAISED:
                return ticket
            expired = conn.execute("SELECT now() > %s", (ticket.expires_at,)).fetchone()[0]
            if ticket.status != "proposed" or expired:
                raise Refused("this ticket proposal has expired")
            conn.execute("UPDATE support_tickets SET status = 'open', opened_at = now(), updated_at = now() "
                         "WHERE id = %s", (ticket_id,))
            self._event(conn, tenant_id, ticket_id, "confirmed", principal_id)
            return self._ticket(conn, "id = %s", (ticket_id,))

    def add_note(self, tenant_id, principal_id, ticket_id, actor, text):
        """A masked note on the customer's raised ticket; Refused for anything else."""
        with self.connect() as conn, conn.transaction():
            context(conn, tenant_id)
            ticket = self._ticket(conn, "tenant_id = %s AND principal_id = %s AND id = %s",
                                  (tenant_id, principal_id, ticket_id))
            if ticket is None or ticket.status not in RAISED:
                raise Refused("no such ticket")
            self._event(conn, tenant_id, ticket_id, "note", actor, text)
            conn.execute("UPDATE support_tickets SET updated_at = now() WHERE id = %s", (ticket_id,))

    def raised_in(self, tenant_id, conversation_id):
        """The conversation's latest raised ticket that is not closed yet, or None."""
        with self.connect() as conn, conn.transaction():
            context(conn, tenant_id)
            return self._ticket(conn, "tenant_id = %s AND conversation_id = %s AND status IN "
                                      "('open', 'in_review') ORDER BY id DESC LIMIT 1",
                                (tenant_id, conversation_id))

    def list_for(self, tenant_id, principal_id):
        """The customer's raised tickets, newest first (proposals are not listed)."""
        with self.connect() as conn, conn.transaction():
            context(conn, tenant_id)
            rows = conn.execute(f"SELECT {COLUMNS} FROM support_tickets WHERE tenant_id = %s AND "
                                "principal_id = %s AND status = ANY(%s) ORDER BY id DESC",
                                (tenant_id, principal_id, list(RAISED))).fetchall()
        return [Ticket(*row) for row in rows]

    def get(self, tenant_id, principal_id, ticket_id):
        """The customer's ticket (a proposal included) with its history, or None."""
        with self.connect() as conn, conn.transaction():
            context(conn, tenant_id)
            ticket = self._ticket(conn, "tenant_id = %s AND principal_id = %s AND id = %s",
                                  (tenant_id, principal_id, ticket_id))
            if ticket is None:
                return None
            events = conn.execute("SELECT kind, actor, text, at FROM ticket_events WHERE ticket_id = %s "
                                  "ORDER BY id", (ticket_id,)).fetchall()
        return Ticket(*[getattr(ticket, f) for f in Ticket.__dataclass_fields__ if f != "events"],
                      events=tuple({"kind": k, "actor": a, "text": t, "at": at.isoformat()}
                                   for k, a, t, at in events))
