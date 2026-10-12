"""Web API: POST 202 turn submission and the resumable SSE event stream (FR-6, FR-9; UA-ADP-01, UA-ADP-04).

    POST /v1/conversations/{id}/turns    Idempotency-Key header, {"content": ...} -> 202 {"turn_id", "status"}
    GET  /v1/conversations/{id}/events   text/event-stream; Last-Event-ID replays what the client missed

Sign-in, the orchestrator hand-off and transcript loading are passed to create_app() so later tasks plug in
without editing this module. Until sign-in exists (M1-02), dev_header_auth trusts X-Tenant-ID / X-User-ID
headers, and only when SUPPORT_AGENT_DEV_AUTH=1; otherwise every request is 401.
"""

import json
import os
import re
import time

import psycopg
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from channels.api.envelope import EventType, Principal, TurnRequest
from channels.api.turns import events_after, last_event_id, submit_turn
from data.events import EventLog, rebuild_from_transcript
from data.keys.envelope import TENANT_ID

SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


def dev_header_auth(request):
    if os.environ.get("SUPPORT_AGENT_DEV_AUTH") != "1":
        raise HTTPException(401, "sign-in is not configured")
    tenant_id, user_id = request.headers.get("X-Tenant-ID", ""), request.headers.get("X-User-ID", "")
    if not TENANT_ID.match(tenant_id) or not SAFE_ID.match(user_id):
        raise HTTPException(401, "X-Tenant-ID and X-User-ID headers are required")
    return Principal(tenant_id=tenant_id, principal_id=user_id)


def no_orchestrator(turn):
    """Default hand-off until the orchestrator exists: the turn is accepted and recorded, nothing runs it."""


def no_transcript(tenant_id, conversation_id):
    return []


def database_url():
    return os.environ.get("DATABASE_URL") or (
        f"postgresql://{os.environ.get('POSTGRES_USER', 'agent')}:{os.environ['POSTGRES_PASSWORD']}"
        f"@127.0.0.1:5432/{os.environ.get('POSTGRES_DB', 'agent')}")


def sse(event_id, event_type, data):
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {event_type}\ndata: {json.dumps(data)}\n\n"


def create_app(dsn=None, authenticate=dev_header_auth, dispatch=no_orchestrator, transcript=no_transcript,
               poll_seconds=1.0, heartbeat_seconds=15.0, stream_seconds=None):
    app = FastAPI(title="Support Agent API")

    def connect():
        return psycopg.connect(dsn or database_url(), autocommit=True)

    def checked(conversation_id):
        if not SAFE_ID.match(conversation_id):
            raise HTTPException(422, "invalid conversation id")
        return conversation_id

    @app.post("/v1/conversations/{conversation_id}/turns", status_code=202)
    def submit(conversation_id: str, body: TurnRequest, request: Request,
               idempotency_key: str | None = Header(default=None)):
        principal = authenticate(request)
        if not idempotency_key or not SAFE_ID.match(idempotency_key):
            raise HTTPException(400, "an Idempotency-Key header (1-128 safe characters) is required")
        with connect() as conn:
            turn_id, created = submit_turn(conn, principal, checked(conversation_id), idempotency_key, body,
                                           dispatch)
        return {"turn_id": turn_id, "status": "QUEUED" if created else "ALREADY_QUEUED"}

    @app.get("/v1/conversations/{conversation_id}/events")
    def events(conversation_id: str, request: Request, last_event_id_header: str | None = Header(
            default=None, alias="Last-Event-ID")):
        principal = authenticate(request)
        stream = _stream(principal.tenant_id, checked(conversation_id), last_event_id_header)
        return StreamingResponse(stream, media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    def _stream(tenant_id, conversation_id, last_seen):
        with connect() as conn:
            if last_seen is None:
                cursor = last_event_id(conn, tenant_id, conversation_id)
            elif (missed := EventLog(conn).replay(tenant_id, conversation_id, last_seen)) is not None:
                yield from (sse(*event) for event in missed)
                cursor = int(missed[-1][0]) if missed else int(last_seen)
            else:  # unknown or past the 7-day window: tell the client, then send the history
                yield sse(None, EventType.STATUS.value, {"code": "stream_expired"})
                for _, _, message in rebuild_from_transcript(transcript(tenant_id, conversation_id))[1:]:
                    yield sse(None, EventType.FINAL.value, {"history": True, **message})
                cursor = last_event_id(conn, tenant_id, conversation_id)
            deadline = None if stream_seconds is None else time.monotonic() + stream_seconds
            beat = time.monotonic()
            while deadline is None or time.monotonic() < deadline:
                for event in events_after(conn, tenant_id, conversation_id, cursor):
                    yield sse(*event)
                    cursor, beat = int(event[0]), time.monotonic()
                if time.monotonic() - beat >= heartbeat_seconds:
                    yield ": keep-alive\n\n"
                    beat = time.monotonic()
                time.sleep(poll_seconds)

    return app
