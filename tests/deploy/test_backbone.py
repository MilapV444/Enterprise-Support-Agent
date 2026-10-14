"""M1-05a: the backbone containers actually start from deploy/compose.yaml on fresh volumes (NFR-26, NFR-36).

Each service runs under a throwaway compose project (new volumes, like a fresh VM) on random host ports, so
it does not collide with a stack already running on this machine. Postgres and OpenBao are started by the data and
key tests; Ollama is skipped here because its image is several GB.
"""

import asyncio
import socket
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path

import pytest
from temporalio.client import Client

ROOT = Path(__file__).resolve().parents[2]
PROJECT = f"sa-test-{uuid.uuid4().hex[:8]}"
COMPOSE = ["docker", "compose", "-p", PROJECT, "-f", "deploy/compose.yaml", "--env-file", ".env.example"]


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def eventually(check, seconds=90):
    deadline = time.monotonic() + seconds
    while True:
        try:
            return check()
        except Exception:
            if time.monotonic() > deadline:
                raise
            time.sleep(1)


@pytest.fixture(scope="module")
def started():
    ports = {}
    try:
        for service, inner in (("temporal", 7233), ("qdrant", 6333), ("jaeger", 16686)):
            ports[service] = free_port()
            subprocess.run([*COMPOSE, "run", "-d", "--no-deps", "--name", f"{PROJECT}-{service}",
                            "-p", f"127.0.0.1:{ports[service]}:{inner}", service],
                           cwd=ROOT, check=True, capture_output=True, timeout=600)
        yield ports
    finally:
        for service in ports:
            subprocess.run(["docker", "rm", "-f", f"{PROJECT}-{service}"], capture_output=True)
        subprocess.run([*COMPOSE, "down", "-v"], cwd=ROOT, capture_output=True)


def test_temporal_starts_on_a_fresh_volume_and_answers(started):
    async def healthy():
        client = await Client.connect(f"127.0.0.1:{started['temporal']}")
        return await client.service_client.check_health()

    assert eventually(lambda: asyncio.run(healthy())) is True
    owner = subprocess.run(["docker", "exec", f"{PROJECT}-temporal", "stat", "-c", "%U",
                            "/home/temporal/temporal.db"], capture_output=True, text=True, check=True)
    assert owner.stdout.strip() == "temporal"


@pytest.mark.parametrize("service, path", [("qdrant", "/readyz"), ("jaeger", "/")])
def test_http_services_answer(started, service, path):
    url = f"http://127.0.0.1:{started[service]}{path}"
    assert eventually(lambda: urllib.request.urlopen(url, timeout=5).status) == 200
