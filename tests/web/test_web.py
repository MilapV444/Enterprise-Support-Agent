"""M1-03: the web portal end to end (FR-6, FR-9). The real API with sign-in runs on a free port behind the
Next.js production server's /v1 rewrite; a stand-in orchestrator answers each turn with a status event and
then the reply; the same client and reducer the portal uses (web/smoke.ts) must show the status first, then
the checked reply. Needs `npm ci` in web/ first."""

import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import httpx
import psycopg
import pytest
import uvicorn

from channels import sessions
from channels.api import turns
from channels.identity import otp
from channels.identity.server import build_app
from channels.identity.service import Identity
from data import events
from data.events import EventLog
from data.migrate import migrate, psql

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
DB = "test_web"
DSN = f"postgresql://agent:change-me@127.0.0.1:5432/{DB}"  # credentials from .env.example
NODE = shutil.which("node")
NEXT = WEB / "node_modules" / "next" / "dist" / "bin" / "next"


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_for(port, seconds=30):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.1)
    raise TimeoutError(f"nothing listening on {port}")


def orchestrator(turn):
    """Stand-in for the agent: progress first, then the checked reply, after the turn has committed."""
    def work():
        time.sleep(0.3)
        with psycopg.connect(DSN, autocommit=True) as conn:
            log, where = EventLog(conn), (turn.tenant_id, turn.conversation_id)
            turns.publish(log, *where, "status", {"text": "Checking invoice history"})
            time.sleep(0.3)
            turns.publish(log, *where, "final", {"text": "Your invoice was corrected."})
    threading.Thread(target=work, daemon=True).start()


@pytest.fixture(scope="module")
def site():
    assert NODE, "Node.js is required for the web tests"
    assert NEXT.exists(), "run `npm ci` in web/ first"
    subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env.example",
                    "up", "-d", "--wait", "postgres"], cwd=ROOT, check=True, capture_output=True)
    psql("postgres", f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
    psql("postgres", f'CREATE DATABASE "{DB}"')
    migrate("main", DB)
    for module in (events, turns, sessions, otp):
        module.apply_schema(DB)
    psql(DB, "INSERT INTO tenants (id, name, region) VALUES ('t_us', 'Acme', 'US')")

    identity = Identity(lambda: psycopg.connect(DSN, autocommit=True))
    app = build_app(DSN, identity, dispatch=orchestrator, poll_seconds=0.05, heartbeat_seconds=0.2)
    api_port, web_port = free_port(), free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=api_port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    wait_for(api_port)
    env = {**os.environ, "API_ORIGIN": f"http://127.0.0.1:{api_port}", "NEXT_TELEMETRY_DISABLED": "1"}
    subprocess.run([NODE, str(NEXT), "build"], cwd=WEB, env=env, check=True,
                   capture_output=True)  # the /v1 rewrite is baked in at build time
    portal = subprocess.Popen([NODE, str(NEXT), "start", "-H", "127.0.0.1", "-p", str(web_port)], cwd=WEB,
                              stdout=subprocess.DEVNULL, env=env)
    wait_for(web_port)
    yield f"http://127.0.0.1:{web_port}"
    portal.terminate()
    server.should_exit = True
    thread.join(timeout=10)


def test_status_shows_while_the_reply_is_held_then_the_checked_reply_renders(site):
    run = subprocess.run([NODE, "smoke.ts", site, "t_us"], cwd=WEB, capture_output=True, text=True,
                         timeout=30)
    assert run.returncode == 0, run.stderr
    states = [json.loads(line) for line in run.stdout.splitlines()]
    replies = [i for i, s in enumerate(states) if any(m["role"] == "assistant" for m in s["messages"])]
    held = [i for i, s in enumerate(states) if s["status"] == "Checking invoice history"]
    assert held and replies and held[0] < replies[0]
    assert all(not any(m["role"] == "assistant" for m in states[i]["messages"]) for i in held)
    last = states[-1]
    assert last["status"] is None
    assert [(m["role"], m["text"]) for m in last["messages"]] == [
        ("user", "My invoice is wrong"), ("assistant", "Your invoice was corrected.")]


def test_the_portal_loads_only_its_own_scripts_under_a_strict_per_request_policy(site):
    pages = [httpx.get(f"{site}{path}") for path in ("/", "/", "/t/t_us")]
    assert all(page.status_code == 200 and "Support Portal" in page.text for page in pages)
    policy = pages[0].headers["Content-Security-Policy"]
    nonce = re.search(r"'nonce-([^']+)'", policy).group(1)
    assert "default-src 'self'" in policy and "unsafe" not in policy and "frame-ancestors 'none'" in policy
    assert nonce not in pages[1].headers["Content-Security-Policy"]                   # fresh per request
    scripts = re.findall(r"<script\b[^>]*>", pages[0].text)
    assert scripts and all(f'nonce="{nonce}"' in tag for tag in scripts)
    assert 'src="http' not in pages[0].text and 'href="http' not in pages[0].text
    assert pages[0].headers["X-Content-Type-Options"] == "nosniff"
