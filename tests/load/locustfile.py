"""The release load test on the VM (AC-13; NFR-20 / RP-ADP-05: RP-D12; NFR-25 / TQ-ADP-05: TQ-D10).

    locust -f tests/load/locustfile.py --headless --host https://<api> -u 200 -r 10 -t 15m

Each simulated customer opens its conversation's event stream, types for a moment, posts one message drawn
from the evaluation personas (tests/load/ac13.py), and times the first status event and the final reply.
Locust shows them as "SSE first_status" and "SSE final:<route>"; when the run ends, AC-13 is checked over
every turn and a failure makes the process exit 1, so a release job can gate on it.

Sign-in: SUPPORT_AGENT_DEV_AUTH on staging (LOAD_TENANT / LOAD_USER headers), or LOAD_BEARER_TOKEN.
This file is not collected by pytest (locust patches sockets with gevent when imported); CI runs it in a
subprocess against the in-process API (test_locustfile.py).
"""

import os
import random
import sys
import uuid
from pathlib import Path

from locust import HttpUser, between, events, task

sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parents[2] / "src")]

from tests.load.ac13 import failures, measure, personas  # noqa: E402

SAMPLES = []
MIX = personas()


def headers():
    token = os.environ.get("LOAD_BEARER_TOKEN")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {"X-Tenant-ID": os.environ.get("LOAD_TENANT", "t_us"), "X-User-ID": os.environ.get("LOAD_USER",
                                                                                              "load-test")}


def report(name, seconds):
    events.request.fire(request_type="SSE", name=name, response_time=(seconds or 0.0) * 1000,
                        response_length=0, exception=None if seconds is not None else TimeoutError(name),
                        context={})


class Customer(HttpUser):
    wait_time = between(float(os.environ.get("LOAD_WAIT_MIN", 5)), float(os.environ.get("LOAD_WAIT_MAX", 15)))

    @task
    def one_turn(self):
        route, text, _ = random.choices(MIX, weights=[w for _, _, w in MIX])[0]
        conversation = f"load-{uuid.uuid4().hex[:16]}"

        def post(content, key):
            reply = self.client.post(f"/v1/conversations/{conversation}/turns", json={"content": content},
                                     headers={**headers(), "Idempotency-Key": key}, name="POST turn")
            reply.raise_for_status()
            return reply.json()["turn_id"]

        with self.client.get(f"/v1/conversations/{conversation}/events", headers=headers(), stream=True,
                             name="GET events", timeout=90, catch_response=True) as stream:
            lines = (line.decode() if isinstance(line, bytes) else line
                     for line in stream.iter_lines(decode_unicode=True))
            sample = measure(lambda: lines, post, route, text, think=random.uniform(1.0, 3.0))
            stream.success()
        SAMPLES.append(sample)
        report("first_status", sample.first_status)
        if not sample.needed_a_person:
            report(f"final:{route}", sample.final)


@events.quitting.add_listener
def ac13(environment, **kwargs):
    found = failures(SAMPLES)
    print(f"AC-13 over {len(SAMPLES)} turns: {'pass' if not found else 'FAIL'}")
    for failure in found:
        print(f"  {failure}")
    if found:
        environment.process_exit_code = 1
