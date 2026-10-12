"""M1-01: POST 202 with an idempotency key, resumable SSE stream and typed event envelope (FR-6, FR-9).
Runs against the compose Postgres through FastAPI's TestClient."""

import subprocess
import threading
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from channels.api import turns
from channels.api.app import create_app
from data import events
from data.events import EventLog
from data.migrate import migrate, psql

ROOT = Path(__file__).resolve().parents[2]
DB = "test_channels"
DSN = f"postgresql://agent:change-me@127.0.0.1:5432/{DB}"  # credentials from .env.example
US = {"X-Tenant-ID": "t_us", "X-User-ID": "sarah"}


@pytest.fixture(scope="module", autouse=True)
def database():
    subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env.example",
                    "up", "-d", "--wait", "postgres"], cwd=ROOT, check=True, capture_output=True)
    psql("postgres", f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
    psql("postgres", f'CREATE DATABASE "{DB}"')
    migrate("main", DB)
    events.apply_schema(DB)
    turns.apply_schema(DB)
    psql(DB, "INSERT INTO tenants (id, name, region) VALUES ('t_us', 'Acme', 'US'), ('t_eu', 'Globex', 'EU')")


@pytest.fixture(autouse=True)
def dev_auth(monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_DEV_AUTH", "1")


@pytest.fixture
def dispatched():
    return []


@pytest.fixture
def client(dispatched):
    history = [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}]
    transcript = {("t_us", "old"): history}
    app = create_app(DSN, dispatch=dispatched.append, transcript=lambda t, c: transcript.get((t, c), []),
                     poll_seconds=0.05, heartbeat_seconds=0.3, stream_seconds=1.0)
    return TestClient(app)


def submit(client, conversation, key, headers=US, content="My invoice is wrong"):
    return client.post(f"/v1/conversations/{conversation}/turns", json={"content": content},
                       headers={**headers, "Idempotency-Key": key})


def read_stream(client, conversation, last_event_id=None, headers=US):
    extra = {"Last-Event-ID": last_event_id} if last_event_id is not None else {}
    url = f"/v1/conversations/{conversation}/events"
    with client.stream("GET", url, headers={**headers, **extra}) as reply:
        assert reply.headers["content-type"].startswith("text/event-stream")
        return parse("".join(reply.iter_text()))


def parse(body):
    frames = []
    for block in body.split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if not line.startswith(":"))
        if fields:
            frames.append((fields.get("id"), fields["event"], fields["data"]))
        elif block.startswith(":"):
            frames.append((None, "comment", block))
    return frames


def without_heartbeats(frames):
    return [frame for frame in frames if frame[1] != "comment"]


def publish(conversation, event_type, data, tenant="t_us"):
    with psycopg.connect(DSN, autocommit=True) as conn:
        return turns.publish(EventLog(conn), tenant, conversation, event_type, data)


def test_duplicate_posts_create_one_turn(client, dispatched):
    first, again = submit(client, "c1", "key-1"), submit(client, "c1", "key-1")
    assert (first.status_code, again.status_code) == (202, 202)
    assert first.json()["status"] == "QUEUED" and again.json()["status"] == "ALREADY_QUEUED"
    assert first.json()["turn_id"] == again.json()["turn_id"]
    assert [t.turn_id for t in dispatched] == [first.json()["turn_id"]]
    assert dispatched[0].content == "My invoice is wrong" and dispatched[0].tenant_id == "t_us"
    assert psql(DB, "SELECT count(*) FROM turns WHERE conversation_id = 'c1'") == [["1"]]
    assert psql(DB, "SELECT count(*) FROM outbound_event_log WHERE conversation_id = 'c1'") == [["1"]]


def test_a_new_key_or_another_user_is_a_new_turn(client):
    base = submit(client, "c2", "key-1").json()["turn_id"]
    assert submit(client, "c2", "key-2").json()["turn_id"] != base
    assert submit(client, "c2", "key-1", headers={**US, "X-User-ID": "bob"}).json()["turn_id"] != base


def test_idempotency_key_is_required(client):
    reply = client.post("/v1/conversations/c3/turns", json={"content": "hi"}, headers=US)
    assert reply.status_code == 400


@pytest.mark.parametrize("body", [{"content": ""}, {"content": "x" * 16385}, {}])
def test_turn_body_is_validated(client, body):
    reply = client.post("/v1/conversations/c3/turns", json=body, headers={**US, "Idempotency-Key": "k"})
    assert reply.status_code == 422


def test_requests_without_sign_in_are_refused(client, monkeypatch):
    assert submit(client, "c3", "k", headers={}).status_code == 401
    monkeypatch.delenv("SUPPORT_AGENT_DEV_AUTH")
    assert submit(client, "c3", "k").status_code == 401
    assert client.get("/v1/conversations/c3/events", headers=US).status_code == 401


def test_failed_hand_off_leaves_no_turn_so_the_client_can_retry():
    def broken(turn):
        raise RuntimeError("orchestrator down")

    with pytest.raises(RuntimeError):
        submit(TestClient(create_app(DSN, dispatch=broken)), "c4", "key-1")
    assert psql(DB, "SELECT count(*) FROM turns WHERE conversation_id = 'c4'") == [["0"]]
    assert psql(DB, "SELECT count(*) FROM outbound_event_log WHERE conversation_id = 'c4'") == [["0"]]


def test_reconnect_with_last_event_id_replays_missed_typed_events(client):
    submit(client, "c5", "key-1")
    [[seen]] = psql(DB, "SELECT max(id) FROM outbound_event_log WHERE conversation_id = 'c5'")
    status = publish("c5", "status", {"text": "Checking invoice history"})
    final = publish("c5", "final", {"text": "Your invoice was corrected."})
    assert without_heartbeats(read_stream(client, "c5", last_event_id=seen)) == [
        (status, "status", '{"text": "Checking invoice history"}'),
        (final, "final", '{"text": "Your invoice was corrected."}')]


def test_expired_last_event_id_sends_stream_expired_then_the_history(client):
    frames = read_stream(client, "old", last_event_id="1")
    assert frames[:3] == [(None, "status", '{"code": "stream_expired"}'),
                          (None, "final", '{"history": true, "role": "user", "content": "Hi"}'),
                          (None, "final", '{"history": true, "role": "assistant", "content": "Hello"}')]


def test_another_tenant_cannot_resume_the_conversation(client):
    submit(client, "c6", "key-1")
    secret = publish("c6", "final", {"text": "private to t_us"})
    frames = read_stream(client, "c6", last_event_id=str(int(secret) - 1),
                         headers={"X-Tenant-ID": "t_eu", "X-User-ID": "eve"})
    assert frames[0] == (None, "status", '{"code": "stream_expired"}')
    assert all("private" not in data for _, _, data in frames)


def test_live_events_arrive_and_idle_streams_get_heartbeats(client):
    timer = threading.Timer(0.2, publish, ("c7", "text_delta", {"text": "Hel"}))
    timer.start()
    frames = read_stream(client, "c7")
    timer.join()
    assert [(event, data) for _, event, data in without_heartbeats(frames)] == [
        ("text_delta", '{"text": "Hel"}')]
    assert any(event == "comment" for _, event, _ in frames)


def test_only_contract_event_types_can_be_published():
    with pytest.raises(ValueError):
        publish("c8", "token", {})
    assert psql(DB, "SELECT count(*) FROM outbound_event_log WHERE conversation_id = 'c8'") == [["0"]]
