"""TK-05: the tickets API and the Raise ticket action (FR-47, FR-6, FR-7; DECISION-368069f5): signed-in
customers only, a confirmation is a turn carrying the action (idempotent like any turn), and a customer reads
only their own tickets."""

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from channels.api import turns
from channels.api.app import create_app
from channels.api.envelope import Principal
from data import events
from data.migrate import migrate, psql
from hitl import tickets
from hitl.tickets import Tickets

ROOT = Path(__file__).resolve().parents[2]
DB = "test_tickets_api"
DSN = f"postgresql://agent:change-me@127.0.0.1:5432/{DB}"  # credentials from .env.example
PRINCIPALS = {"sarah": Principal(tenant_id="t_us", principal_id="sarah", assurance_tier="T1_VERIFIED",
                                 session_id="s-sarah"),
              "bob": Principal(tenant_id="t_us", principal_id="bob", assurance_tier="T1_VERIFIED",
                               session_id="s-bob"),
              "guest": Principal(tenant_id="t_us", principal_id="anon:1")}


def connect():
    import psycopg
    return psycopg.connect(DSN, autocommit=True)


@pytest.fixture(scope="module")
def desk():
    subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env.example",
                    "up", "-d", "--wait", "postgres"], cwd=ROOT, check=True, capture_output=True)
    psql("postgres", f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
    psql("postgres", f'CREATE DATABASE "{DB}"')
    migrate("main", DB)
    for module in (events, turns, tickets):
        module.apply_schema(DB)
    psql(DB, "INSERT INTO tenants (id, name, region) VALUES ('t_us', 'Acme', 'US')")
    return Tickets(connect)


@pytest.fixture
def api(desk):
    dispatched = []
    app = create_app(DSN, authenticate=lambda request: PRINCIPALS[request.headers.get("X-Who", "guest")],
                     dispatch=dispatched.append)
    return TestClient(app), dispatched


def raised(desk, principal="sarah", conversation="c1", key="k"):
    proposal = desk.propose("t_us", principal, conversation, key, category="refund",
                            subject="Duplicate charge", queue="queue_billing", reason="refund request",
                            invoice_id="inv-sarah-1", amount_cents=50000, currency="USD")
    return desk.confirm("t_us", principal, proposal.id)


def test_confirming_submits_a_turn_carrying_the_action_once(api, desk):
    client, dispatched = api
    proposal = desk.propose("t_us", "sarah", "c-confirm", "k", category="billing", subject="Wrong charge",
                            queue="queue_billing", reason="billing request")
    path = f"/v1/conversations/c-confirm/tickets/{proposal.number}/confirm"
    first = client.post(path, headers={"X-Who": "sarah", "Idempotency-Key": "raise-1"})
    again = client.post(path, headers={"X-Who": "sarah", "Idempotency-Key": "raise-1"})
    assert (first.status_code, first.json()["status"]) == (202, "QUEUED")
    assert again.json()["status"] == "ALREADY_QUEUED"
    (turn,) = dispatched
    assert turn.action.type == "confirm_ticket" and turn.action.proposal == proposal.number
    assert turn.session_id == "s-sarah" and turn.assurance_tier == "T1_VERIFIED"
    assert desk.get("t_us", "sarah", proposal.id).status == "proposed"     # the turn loop raises it


@pytest.mark.parametrize("who, path, status", [
    ("guest", "/v1/conversations/c1/tickets/TKT-00001/confirm", 403),
    ("sarah", "/v1/conversations/c1/tickets/INV-1/confirm", 422),
    ("sarah", "/v1/conversations/bad%20id/tickets/TKT-00001/confirm", 422)])
def test_a_confirmation_needs_a_signed_in_customer_and_a_ticket_number(api, who, path, status):
    client, dispatched = api
    assert client.post(path, headers={"X-Who": who, "Idempotency-Key": "k-1"}).status_code == status
    assert dispatched == []


def test_customers_list_and_open_only_their_own_raised_tickets(api, desk):
    client, _ = api
    mine, theirs = raised(desk, "sarah", "c-list", "k1"), raised(desk, "bob", "c-bob", "k1")
    desk.add_note("t_us", "sarah", mine.id, "customer", "Any news?")
    listed = client.get("/v1/tickets", headers={"X-Who": "sarah"}).json()["tickets"]
    numbers = [t["ticket_id"] for t in listed]
    assert mine.number in numbers and theirs.number not in numbers
    detail = client.get(f"/v1/tickets/{mine.number}", headers={"X-Who": "sarah"}).json()
    assert (detail["ticket_id"], detail["status"]) == (mine.number, "open")
    assert detail["conversation_id"] == "c-list"
    assert [e["kind"] for e in detail["events"]] == ["proposed", "confirmed", "note"]
    assert client.get(f"/v1/tickets/{theirs.number}", headers={"X-Who": "sarah"}).status_code == 404
    assert client.get("/v1/tickets/nonsense", headers={"X-Who": "sarah"}).status_code == 404
    assert client.get("/v1/tickets", headers={"X-Who": "guest"}).status_code == 403
