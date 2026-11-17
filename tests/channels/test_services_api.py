"""The Services API (tools.services, outside Genesis): signed-in customers see only their own servers, apps and
activity; a service action card's button is a turn carrying the action, idempotent like any turn."""

import subprocess
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from channels.api import turns
from channels.api.app import create_app
from channels.api.envelope import Principal
from data import events
from data.migrate import migrate, psql
from tools import services

ROOT = Path(__file__).resolve().parents[2]
DB = "test_services_api"
DSN = f"postgresql://agent:change-me@127.0.0.1:5432/{DB}"  # credentials from .env.example
PRINCIPALS = {"sarah": Principal(tenant_id="t_us", principal_id="sarah", assurance_tier="T1_VERIFIED",
                                 session_id="s-sarah"),
              "bob": Principal(tenant_id="t_us", principal_id="bob", assurance_tier="T1_VERIFIED",
                               session_id="s-bob"),
              "guest": Principal(tenant_id="t_us", principal_id="anon:1")}


def connect():
    return psycopg.connect(DSN, autocommit=True)


@pytest.fixture(scope="module")
def database():
    subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env.example",
                    "up", "-d", "--wait", "postgres"], cwd=ROOT, check=True, capture_output=True)
    psql("postgres", f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
    psql("postgres", f'CREATE DATABASE "{DB}"')
    migrate("main", DB)
    for module in (events, turns, services):
        module.apply_schema(DB)
    psql(DB, "INSERT INTO tenants (id, name, region) VALUES ('t_us', 'Acme', 'US')")
    services.seed(connect, "t_us", "sarah")
    services.seed(connect, "t_us", "bob")


@pytest.fixture
def api(database):
    dispatched = []
    app = create_app(DSN, authenticate=lambda request: PRINCIPALS[request.headers.get("X-Who", "guest")],
                     dispatch=dispatched.append)
    return TestClient(app), dispatched


def test_customers_see_only_their_own_services_and_what_was_done_on_them(api):
    client, _ = api
    mine = services.services(connect, "t_us", "sarah")
    stop = services.propose(connect, "t_us", "sarah", "c-list", "k", mine[0]["service_id"], "stop")
    services.confirm(connect, "t_us", "sarah", services.number_id(stop))
    body = client.get("/v1/services", headers={"X-Who": "sarah"}).json()
    assert [s["name"] for s in body["services"]] == ["batch-worker-02", "payments-api-01", "staging-web-01",
                                                     "checkout-worker", "notifications"]
    assert {s["service_id"] for s in body["services"]} == {s["service_id"] for s in mine}
    assert [(a["action_id"], a["action"], a["conversation_id"]) for a in body["activity"]] == [
        (stop, "stop", "c-list")]
    theirs = client.get("/v1/services", headers={"X-Who": "bob"}).json()
    assert theirs["activity"] == [] and {s["status"] for s in theirs["services"]} == {"running", "stopped"}
    assert client.get("/v1/services", headers={"X-Who": "guest"}).status_code == 403


def test_confirming_submits_a_turn_carrying_the_action_once(api):
    client, dispatched = api
    target = services.services(connect, "t_us", "sarah")[-1]
    offer = services.propose(connect, "t_us", "sarah", "c-confirm", "k", target["service_id"], "restart")
    path = f"/v1/conversations/c-confirm/actions/{offer}/confirm"
    first = client.post(path, headers={"X-Who": "sarah", "Idempotency-Key": "act-1"})
    again = client.post(path, headers={"X-Who": "sarah", "Idempotency-Key": "act-1"})
    assert (first.status_code, first.json()["status"]) == (202, "QUEUED")
    assert again.json()["status"] == "ALREADY_QUEUED"
    (turn,) = dispatched
    assert turn.action.type == "confirm_action" and turn.action.proposal == offer
    assert turn.session_id == "s-sarah" and turn.assurance_tier == "T1_VERIFIED"
    assert services.service(connect, "t_us", "sarah", target["service_id"])["status"] == "running"


@pytest.mark.parametrize("who, path, status", [
    ("guest", "/v1/conversations/c1/actions/ACT-00001/confirm", 403),
    ("sarah", "/v1/conversations/c1/actions/TKT-00001/confirm", 422),
    ("sarah", "/v1/conversations/bad%20id/actions/ACT-00001/confirm", 422)])
def test_a_confirmation_needs_a_signed_in_customer_and_an_action_number(api, who, path, status):
    client, dispatched = api
    assert client.post(path, headers={"X-Who": who, "Idempotency-Key": "k-1"}).status_code == status
    assert dispatched == []
