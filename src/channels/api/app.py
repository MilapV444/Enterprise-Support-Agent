"""Web API: POST 202 turn submission and the resumable SSE event stream (FR-6, FR-9; UA-ADP-01, UA-ADP-04).

    POST /v1/conversations/{id}/turns    Idempotency-Key header, {"content": ...} -> 202 {"turn_id", "status"}
    GET  /v1/conversations/{id}/events   text/event-stream; Last-Event-ID replays what the client missed

Sign-in, the orchestrator hand-off and transcript loading are passed to create_app() so later tasks plug in
without editing this module. Until sign-in exists (M1-02), dev_header_auth trusts X-Tenant-ID / X-User-ID
headers, and only when SUPPORT_AGENT_DEV_AUTH=1; otherwise every request is 401.
"""

import asyncio
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from psycopg_pool import ConnectionPool

from channels.api.envelope import EventType, Principal, TurnRequest
from channels.api.turns import events_after, last_event_id, submit_turn
from data.events import EventLog, rebuild_from_transcript
from data.keys.envelope import TENANT_ID

SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
WORK = ThreadPoolExecutor(max_workers=256)  # polls and posts; streams themselves stay on the event loop (B12)


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
    """APP_DATABASE_URL is the non-bypass login role (register S17); DATABASE_URL stays the owner for
    migrations. Local tests keep using DATABASE_URL (the compose superuser) when the app URL is unset."""
    return os.environ.get("APP_DATABASE_URL") or os.environ.get("DATABASE_URL") or (
        f"postgresql://{os.environ.get('POSTGRES_USER', 'agent')}:{os.environ['POSTGRES_PASSWORD']}"
        f"@127.0.0.1:5432/{os.environ.get('POSTGRES_DB', 'agent')}")


def sse(event_id, event_type, data):
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {event_type}\ndata: {json.dumps(data)}\n\n"


def create_app(dsn=None, authenticate=dev_header_auth, dispatch=no_orchestrator, transcript=no_transcript,
               poll_seconds=0.05, heartbeat_seconds=15.0, stream_seconds=None):
    app = FastAPI(title="Support Agent API")
    pool = ConnectionPool(dsn or database_url(), min_size=2, max_size=64, open=True,
                          kwargs={"autocommit": True})

    def connect():
        return pool.connection()

    def checked(conversation_id):
        if not SAFE_ID.match(conversation_id):
            raise HTTPException(422, "invalid conversation id")
        return conversation_id

    async def in_pool(fn, *args):
        return await asyncio.get_running_loop().run_in_executor(WORK, fn, *args)

    @app.post("/v1/conversations/{conversation_id}/turns", status_code=202)
    async def submit(conversation_id: str, body: TurnRequest, request: Request,
                     idempotency_key: str | None = Header(default=None)):
        principal = authenticate(request)
        if not idempotency_key or not SAFE_ID.match(idempotency_key):
            raise HTTPException(400, "an Idempotency-Key header (1-128 safe characters) is required")
        conversation_id = checked(conversation_id)

        def go():
            with connect() as conn:
                return submit_turn(conn, principal, conversation_id, idempotency_key, body, dispatch)

        turn_id, created = await in_pool(go)
        return {"turn_id": turn_id, "status": "QUEUED" if created else "ALREADY_QUEUED"}

    @app.get("/v1/conversations/{conversation_id}/events")
    async def events(conversation_id: str, request: Request, last_event_id_header: str | None = Header(
            default=None, alias="Last-Event-ID")):
        principal = authenticate(request)
        conversation_id = checked(conversation_id)
        cursor = None
        if last_event_id_header is None:
            def snapshot():
                with connect() as conn:  # on connect, not when the generator first runs (B13)
                    return last_event_id(conn, principal.tenant_id, conversation_id)
            cursor = await in_pool(snapshot)
        return StreamingResponse(_stream(principal.tenant_id, conversation_id, last_event_id_header, cursor),
                                 media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    async def _stream(tenant_id, conversation_id, last_seen, cursor):
        """Async so an open stream does not occupy a worker thread (B12). DB work is short and sync."""
        def replay():
            with connect() as conn:
                return EventLog(conn).replay(tenant_id, conversation_id, last_seen), last_event_id(
                    conn, tenant_id, conversation_id)

        if last_seen is not None:
            missed, latest = await in_pool(replay)
            if missed is not None:
                for event in missed:
                    yield sse(*event)
                cursor = int(missed[-1][0]) if missed else int(last_seen)
            else:
                yield sse(None, EventType.STATUS.value, {"code": "stream_expired"})
                for _, _, message in rebuild_from_transcript(transcript(tenant_id, conversation_id))[1:]:
                    yield sse(None, EventType.FINAL.value, {"history": True, **message})
                cursor = latest
        def poll():
            with connect() as conn:
                return events_after(conn, tenant_id, conversation_id, cursor)

        deadline = None if stream_seconds is None else time.monotonic() + stream_seconds
        beat = time.monotonic()
        while deadline is None or time.monotonic() < deadline:
            batch = await in_pool(poll)
            for event in batch:
                yield sse(*event)
                cursor, beat = int(event[0]), time.monotonic()
            if time.monotonic() - beat >= heartbeat_seconds:
                yield ": keep-alive\n\n"
                beat = time.monotonic()
            wait = poll_seconds
            if deadline is not None:
                wait = min(wait, max(0.01, deadline - time.monotonic()))
            await asyncio.sleep(wait)

    return app
