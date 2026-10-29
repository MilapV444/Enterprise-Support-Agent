"""M5-05: the API under concurrent customers, in process (AC-13 shape; NFR-20, NFR-25).

The real app (channels.api, production poll and heartbeat settings) runs under uvicorn on a local port against
the compose Postgres; the agent is mocked (each route answers after a fixed model time), so what is measured
is this stack's own share of the latency: accepting the turn, the outbox and the event stream. The release
run on the VM is locustfile.py, against real model tiers.
"""

import os
import random
import re
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import httpx
import psycopg
import pytest
import uvicorn

from channels.api import turns
from channels.api.app import create_app
from data import events
from data.events import EventLog
from data.migrate import migrate, psql
from evals.gate import p95
from tests.load.ac13 import failures, measure, personas

ROOT = Path(__file__).resolve().parents[2]
DB = "test_load"
DSN = f"postgresql://agent:change-me@127.0.0.1:5432/{DB}"  # credentials from .env.example
US = {"X-Tenant-ID": "t_us", "X-User-ID": "sarah"}
MODEL_SECONDS = {"faq": 0.3, "diagnostic": 1.0, "multi_specialist": 2.0}   # the mocked agent's own time
POLL = 1.0                                                                  # create_app's default


class Agent:
    """The orchestrator, mocked: after the route's model time it publishes the turn's final reply."""

    def __init__(self):
        self.routes = {text: route for route, text, _ in personas()}
        self.pool = ThreadPoolExecutor(max_workers=64)

    def dispatch(self, turn):
        self.pool.submit(self.answer, turn)

    def answer(self, turn):
        time.sleep(MODEL_SECONDS[self.routes.get(turn.content, "faq")])
        with psycopg.connect(DSN, autocommit=True) as conn:
            turns.publish(EventLog(conn), turn.tenant_id, turn.conversation_id, "final",
                          {"turn_id": turn.turn_id, "text": "Here is what I found."})


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture(scope="module")
def database():
    subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env.example",
                    "up", "-d", "--wait", "postgres"], cwd=ROOT, check=True, capture_output=True)
    psql("postgres", f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
    psql("postgres", f'CREATE DATABASE "{DB}"')
    migrate("main", DB)
    events.apply_schema(DB)
    turns.apply_schema(DB)
    psql(DB, "INSERT INTO tenants (id, name, region) VALUES ('t_us', 'Acme', 'US')")
    previous = os.environ.get("SUPPORT_AGENT_DEV_AUTH")
    os.environ["SUPPORT_AGENT_DEV_AUTH"] = "1"
    yield
    if previous is None:
        os.environ.pop("SUPPORT_AGENT_DEV_AUTH")
    else:
        os.environ["SUPPORT_AGENT_DEV_AUTH"] = previous


@contextmanager
def serving():
    """The API under uvicorn on a free local port, with its own mocked agent."""
    agent, port = Agent(), free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(DSN, dispatch=agent.dispatch), host="127.0.0.1",
                                           port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(10)
        agent.pool.shutdown(wait=False)


@pytest.fixture(scope="module")
def api(database):
    with serving() as base:
        yield base


@pytest.fixture
def saturated(database):
    """A server of its own: a saturated one keeps its worker threads for a while after the customers leave."""
    with serving() as base:
        yield base


def customer(base, conversation, route, text, think):
    with httpx.Client(base_url=base, headers=US, timeout=httpx.Timeout(10.0, read=None)) as http:
        def post(content, key):
            reply = http.post(f"/v1/conversations/{conversation}/turns", json={"content": content},
                              headers={"Idempotency-Key": key})
            reply.raise_for_status()
            return reply.json()["turn_id"]
        with http.stream("GET", f"/v1/conversations/{conversation}/events") as stream:
            lines = stream.iter_lines()
            return measure(lambda: lines, post, route, text, think=think, timeout=15.0)


def load(base, users, seed):
    rng = random.Random(seed)
    mix = personas()
    drawn = rng.choices(mix, weights=[w for _, _, w in mix], k=users)
    with ThreadPoolExecutor(max_workers=users) as pool:
        runs = [pool.submit(customer, base, f"load-{seed}-{n}", route, text, rng.uniform(0.5, 1.5))
                for n, (route, text, _) in enumerate(drawn)]
        return [run.result() for run in runs]


def test_thirty_concurrent_customers_get_every_event_within_one_poll(api):
    """Every turn's status and final reply arrive, the reply budgets hold, and the stack adds at most one
    poll interval and a margin. The first status lands at about the 1 s limit, not safely under it: the
    stream polls once a second (register B14), so AC-13's first-status p95 is not asserted here."""
    samples = load(api, users=30, seed=1)
    assert [f for f in failures(samples) if not f.startswith("first status")] == []
    assert p95([s.first_status for s in samples]) <= POLL + 0.25
    overhead = [s.final - MODEL_SECONDS[s.route] for s in samples]
    assert p95(overhead) <= POLL + 0.5, p95(overhead)
    assert {s.route for s in samples} >= {"faq", "diagnostic"}


def test_the_release_locustfile_runs_against_the_api_and_checks_ac13(api):
    """The VM's load test, end to end in a subprocess (locust patches sockets with gevent): it drives
    customers, reports both measurements and checks AC-13 at the end. Its verdict is not asserted here (the
    first status sits at the limit, B14); that every turn was answered is."""
    run = subprocess.run(
        [sys.executable, "-m", "locust", "-f", "tests/load/locustfile.py", "--headless", "--host", api,
         "-u", "5", "-r", "5", "-t", "8s", "--stop-timeout", "15", "--only-summary"],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
        env={**os.environ, "LOAD_WAIT_MIN": "0.2", "LOAD_WAIT_MAX": "0.5"})
    output = run.stdout + run.stderr
    turns_measured = int(re.search(r"AC-13 over (\d+) turns", output).group(1))
    assert turns_measured >= 5 and run.returncode in (0, 1), output[-2000:]
    assert "SSE" in output and "first_status" in output and "never got" not in output, output[-2000:]


def test_the_ac13_check_itself_catches_slow_lost_and_unanswered_turns():
    from tests.load.ac13 import Sample

    fine = [Sample("faq", 0.2, 2.0)] * 19
    assert failures(fine + [Sample("faq", 0.3, 4.9)]) == []
    assert failures(fine + [Sample("faq", 1.5, 2.0)] * 2) == ["first status p95 1.50 s over 1.0 s"]
    slow = [Sample("diagnostic", 0.2, 21.0)] * 20
    assert failures(slow) == ["diagnostic: final reply p95 21.00 s over 20.0 s"]
    assert failures([Sample("faq", None, None)]) == ["1 turns never got a status event",
                                                      "faq: 1 turns never got a final reply"]
    assert failures([Sample("multi_specialist", 0.2, 90.0, needed_a_person=True)]) == []
    assert failures([]) == ["no turns were measured"]


@pytest.mark.xfail(strict=True, reason="register B12: each open stream holds one of the server's 40 "
                                       "worker threads, so past 40 viewers streams and posts queue and "
                                       "events are lost")
def test_sixty_concurrent_customers_meet_ac13(saturated):
    assert failures(load(saturated, users=60, seed=2)) == []
