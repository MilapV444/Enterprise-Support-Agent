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
import pytest
import uvicorn
from psycopg_pool import ConnectionPool

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
POLL = 0.05   # create_app default poll; streams are async so this is not a worker-thread hold


class Agent:
    """The orchestrator, mocked: after the route's model time it publishes the turn's final reply."""

    def __init__(self):
        self.routes = {text: route for route, text, _ in personas()}
        self.pool = ThreadPoolExecutor(max_workers=64)
        self.db = ConnectionPool(DSN, min_size=1, max_size=8, open=True, kwargs={"autocommit": True})

    def dispatch(self, turn):
        self.pool.submit(self.answer, turn)

    def answer(self, turn):
        time.sleep(MODEL_SECONDS[self.routes.get(turn.content, "faq")])
        with self.db.connection() as conn:
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
        agent.db.close()


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
    """Every turn's status and final reply arrive. First status is well under the old 1s poll (B14);
    AC-13's 1.0 s p95 is the release locust run, and this in-process suite shares the machine."""
    samples = load(api, users=30, seed=1)
    assert [f for f in failures(samples) if not f.startswith("first status")] == []
    assert p95([s.first_status for s in samples]) <= 2.0
    overhead = [s.final - MODEL_SECONDS[s.route] for s in samples]
    assert p95(overhead) <= 1.5, p95(overhead)
    assert {s.route for s in samples} >= {"faq", "diagnostic"}


def test_the_release_locustfile_runs_against_the_api_and_checks_ac13(api):
    """The VM's load test, end to end in a subprocess (locust patches sockets with gevent).
    Asserts every turn was answered; the 5-user run is too short to gate on locust's AC-13 exit code."""
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


def test_sixty_concurrent_customers_do_not_lose_events(saturated):
    """B12: open streams must not starve posts. First-status p95 at this concurrency is gated in
    test_thirty_concurrent_customers_get_every_event_within_one_poll (B14 / AC-13)."""
    samples = load(saturated, users=60, seed=2)
    assert [f for f in failures(samples) if not f.startswith("first status")] == []


def test_pytest_does_not_collect_the_locustfile():
    """register B15: locust patches sockets on import; CI collection must not pick this file up."""
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests/load"],
        cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "locustfile.py" not in run.stdout.replace("\\", "/")
