"""TK-01: the support ticket store (FR-45; DECISION-368069f5): proposals, one confirmation, the customer's own
tickets only, history, expiry and tenant isolation."""

import subprocess
from pathlib import Path

import psycopg
import pytest

from data.migrate import migrate, psql
from hitl import tickets
from hitl.queues import Refused
from hitl.tickets import Tickets, number_id

ROOT = Path(__file__).resolve().parents[3]
DB = "test_hitl_tickets"
DSN = f"postgresql://agent:change-me@127.0.0.1:5432/{DB}"  # credentials from .env.example
REFUND = {"category": "refund", "subject": "Duplicate charge on INV-1001", "queue": "queue_billing",
          "reason": "refund request", "description": "Charged twice on <EMAIL_1a2b3c4d>",
          "invoice_id": "INV-1001", "amount_cents": 50000, "currency": "USD"}


def connect():
    return psycopg.connect(DSN, autocommit=True)


@pytest.fixture(scope="module")
def store():
    subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env.example", "up",
                    "-d", "--wait", "postgres"], cwd=ROOT, check=True, capture_output=True)
    psql("postgres", f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
    psql("postgres", f'CREATE DATABASE "{DB}"')
    migrate("main", DB)
    tickets.apply_schema(DB)
    tickets.apply_schema(DB)  # a second apply is a no-op
    psql(DB, "INSERT INTO tenants (id, name, region) VALUES ('t_us', 'Acme', 'US'), ('t_eu', 'Globex', 'EU')")
    return Tickets(connect)


def test_a_proposal_is_offered_once_per_key_and_raised_only_when_confirmed(store):
    proposal = store.propose("t_us", "sarah", "c1", "turn-1", turn_id="turn-1", **REFUND)
    assert proposal.status == "proposed" and proposal.number == f"TKT-{proposal.id:05d}"
    again = store.propose("t_us", "sarah", "c1", "turn-1", **{**REFUND, "subject": "other"})  # a retry
    assert again == proposal
    assert store.list_for("t_us", "sarah") == []                                 # an offer is not a ticket
    ticket = store.confirm("t_us", "sarah", proposal.id)
    assert ticket.status == "open" and ticket.opened_at is not None
    assert store.confirm("t_us", "sarah", proposal.id) == ticket           # a repeat raises nothing more
    assert [t.number for t in store.list_for("t_us", "sarah")] == [ticket.number]
    assert ticket.card() == {"ticket_id": ticket.number, "status": "open", "category": "refund",
                             "subject": "Duplicate charge on INV-1001", "invoice_id": "INV-1001",
                             "amount_cents": 50000, "currency": "USD", "queue": "queue_billing",
                             "created_at": ticket.created_at.isoformat()}


def test_a_customer_reaches_only_their_own_tickets(store):
    proposal = store.propose("t_us", "sarah", "c2", "k", **REFUND)
    with pytest.raises(Refused):
        store.confirm("t_us", "bob", proposal.id)
    with pytest.raises(Refused):
        store.confirm("t_eu", "sarah", proposal.id)             # another tenant's row is invisible
    assert store.get("t_us", "bob", proposal.id) is None and store.list_for("t_us", "bob") == []
    assert store.get("t_eu", "sarah", proposal.id) is None


def test_an_expired_proposal_cannot_be_confirmed(store):
    proposal = store.propose("t_us", "sarah", "c3", "k", **REFUND)
    psql(DB, f"UPDATE support_tickets SET expires_at = now() - interval '1 minute' WHERE id = {proposal.id}")
    with pytest.raises(Refused, match="expired"):
        store.confirm("t_us", "sarah", proposal.id)


def test_a_ticket_keeps_its_history_and_notes_go_only_on_raised_tickets(store):
    proposal = store.propose("t_us", "sarah", "c4", "k", **REFUND)
    with pytest.raises(Refused):
        store.add_note("t_us", "sarah", proposal.id, "customer", "anything new?")
    ticket = store.confirm("t_us", "sarah", proposal.id)
    store.add_note("t_us", "sarah", ticket.id, "customer", "It was charged a third time")
    assert store.raised_in("t_us", "c4") == store.get("t_us", "sarah", ticket.id)
    full = store.get("t_us", "sarah", ticket.id)
    assert [(e["kind"], e["actor"]) for e in full.events] == [("proposed", "agent"), ("confirmed", "sarah"),
                                                               ("note", "customer")]
    assert full.events[-1]["text"] == "It was charged a third time"
    assert store.raised_in("t_us", "no-such-conversation") is None


def test_unknown_categories_and_ticket_numbers_are_refused(store):
    with pytest.raises(ValueError, match="category"):
        store.propose("t_us", "sarah", "c5", "k", **{**REFUND, "category": "lottery"})
    assert number_id("TKT-00042") == 42 and number_id("42") == 42 and number_id("TKT-4x") is None


def test_the_runtime_role_cannot_delete_tickets(store):
    with connect() as conn, conn.transaction():
        conn.execute("SET LOCAL ROLE app_runtime")
        conn.execute("SELECT set_config('app.current_tenant_id', 't_us', true)")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("DELETE FROM support_tickets")
