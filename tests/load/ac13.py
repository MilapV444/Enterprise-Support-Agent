"""AC-13 for the release load test: the first status event within 1 s, and the final reply's p95 within the
route budget (FAQ 5 s, diagnostics 20 s, multi-specialist 45 s) for turns without human approval
(NFR-20 / RP-ADP-05: RP-D12; NFR-25 / TQ-ADP-05: TQ-D10).

Shared by locustfile.py (on the VM, against the deployed API) and test_api_load.py (in CI, against the API in
process with a mocked agent). One customer turn is measured as a client sees it: the stream is open, the
message is posted, and the clock runs from the POST to the turn's first status event and to its final event.

Traffic is shaped by the evaluation personas (EV-D1): the framework seed episodes, each weighted by its
stratum's production share.
"""

import json
import time
import uuid
from dataclasses import dataclass

from evals.datasets import PRODUCTION_MIX, framework_episodes
from evals.gate import p95
from reliability.bursts import BUDGETS, FIRST_STATUS

APPROVAL_EVENTS = {"action_card", "handoff"}      # a person is involved: excluded from the reply budgets


@dataclass(frozen=True)
class Sample:
    route: str
    first_status: float | None        # seconds from the POST; None if it never came
    final: float | None
    needed_a_person: bool = False


def personas():
    """[(route, first message, weight)]: each seed episode weighted by P(stratum) / episodes in it."""
    episodes = framework_episodes()
    per_stratum = {s: sum(e.stratum == s for e in episodes) for s in PRODUCTION_MIX}
    return [(e.route, e.turns[0], PRODUCTION_MIX[e.stratum] / per_stratum[e.stratum]) for e in episodes]


def failures(samples, budgets=BUDGETS, first_status=FIRST_STATUS):
    """What AC-13 finds wrong with a load run; [] when it passes."""
    out = []
    if not samples:
        return ["no turns were measured"]
    lost = [s for s in samples if s.first_status is None]
    if lost:
        out.append(f"{len(lost)} turns never got a status event")
    firsts = [s.first_status for s in samples if s.first_status is not None]
    if firsts and p95(firsts) > first_status:
        out.append(f"first status p95 {p95(firsts):.2f} s over {first_status} s")
    for route, budget in budgets.items():
        timed = [s for s in samples if s.route == route and not s.needed_a_person]
        if not timed:
            continue
        unanswered = [s for s in timed if s.final is None]
        if unanswered:
            out.append(f"{route}: {len(unanswered)} turns never got a final reply")
        finals = [s.final for s in timed if s.final is not None]
        if finals and p95(finals) > budget.target:
            out.append(f"{route}: final reply p95 {p95(finals):.2f} s over {budget.target} s")
    return out


def frames(lines):
    """SSE frames {"id", "event", "data"} from an iterator of decoded lines; comments as {"event": None}."""
    frame = {}
    for line in lines:
        if line.startswith(":"):
            yield {"event": None}
        elif line == "":
            if frame:
                yield frame
            frame = {}
        else:
            name, _, value = line.partition(": ")
            frame[name] = value


def measure(open_stream, post, route, text, think=0.0, timeout=None, clock=time.monotonic, sleep=time.sleep):
    """One turn as a client sees it. open_stream() -> an iterator of decoded SSE lines, once the response
    headers are in; post(text, idempotency_key) -> the turn id. The customer types for `think` seconds, posts,
    and reads until the turn's final event or the route's hard ceiling."""
    stream = frames(open_stream())
    sleep(think)
    started = clock()
    turn_id = post(text, str(uuid.uuid4()))
    limit = started + (timeout or BUDGETS[route].hard)
    first = final = None
    person = False
    for frame in stream:
        if clock() > limit:
            break
        if frame["event"] is None:
            continue
        data = json.loads(frame.get("data", "{}"))
        if data.get("turn_id") not in (None, turn_id):
            continue
        if frame["event"] == "status" and first is None:
            first = clock() - started
        if frame["event"] in APPROVAL_EVENTS:
            person = True
        if frame["event"] == "final":
            final = clock() - started
            break
    return Sample(route, first, final, person)
