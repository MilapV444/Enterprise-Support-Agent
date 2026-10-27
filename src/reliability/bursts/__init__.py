"""Bursts and latency (NFR-18 / RP-ADP-03: RP-D6, RP-D8).

- SingleFlight: identical read-only calls (same tenant, action and normalised arguments, SHA-256 key) that
  arrive while one is in flight, within 200 ms of its start, wait for it and share its result or its error:
  fifty identical status checks make one backend call. Writes are never coalesced.
- Incidents: on-call declares an incident (brief, pre-approved status answer, the tenants it touches).
  incident_answer() asks Jev one yes / no question on the masked message; a confident yes (P >= 0.80) gets
  the status answer, through the output checks, and the turn skips the agent entirely. Unsure, or Jev
  unavailable: None, the normal path.
- Budgets per route (FAQ 5 s, diagnostic 20 s, multi-specialist 45 s at p95; hard 8 / 28 / 60 s); the first
  status event within 1 s; step allocations must fit the target. Deadline tells a turn what is left, which
  optional steps no longer fit (skip them) and when the hard ceiling has passed (take the route's fallback).
"""

import hashlib
import json
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass, field

from core.orchestrator.decisions import JevUnavailable, Masked
from safety.output.checks import check

COALESCE_WINDOW = 0.200   # seconds
INCIDENT_AT = 0.80
FIRST_STATUS = 1.0        # seconds, every route

INCIDENT_QUESTION = {"type": "noul",
                     "instructions": "Is this customer asking about or experiencing the active service "
                                     "disruption described in the incident brief?"}


# Single-flight ----------------------------------------------------------------------------------------------

def flight_key(tenant_id, action, arguments):
    normalised = {k: " ".join(v.casefold().split()) if isinstance(v, str) else v
                  for k, v in arguments.items()}
    material = json.dumps([tenant_id, action, normalised], sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(material.encode()).hexdigest()


class SingleFlight:
    def __init__(self, clock=time.monotonic, window=COALESCE_WINDOW):
        self.clock, self.window, self.lock, self.flights = clock, window, threading.Lock(), {}

    def run(self, tenant_id, action, arguments, call, read_only):
        """call() once for identical concurrent reads; every caller gets its result (or its exception)."""
        if not read_only:
            raise ValueError("only read-only calls are coalesced")
        key = flight_key(tenant_id, action, arguments)
        with self.lock:
            flight = self.flights.get(key)
            if flight and self.clock() - flight[0] <= self.window:
                future, leader = flight[1], False
            else:
                future, leader = Future(), True
                self.flights[key] = (self.clock(), future)
        if leader:
            try:
                future.set_result(call())
            except BaseException as error:  # noqa: BLE001 - every waiter sees the leader's failure
                future.set_exception(error)
            finally:
                with self.lock:
                    if self.flights.get(key, (None, None))[1] is future:
                        del self.flights[key]
        return future.result()


# Incident mode ----------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Incident:
    brief: str                                    # masked, from on-call
    status_answer: str                            # pre-approved text for customers
    tenants: frozenset[str] | None = None         # None: every tenant
    declared_by: str = ""


class Incidents:
    """The active incident (one at a time), set and cleared by on-call through the admin API."""

    def __init__(self):
        self.current, self.lock = None, threading.Lock()

    def declare(self, incident):
        with self.lock:
            self.current = incident

    def clear(self):
        with self.lock:
            self.current = None

    def for_tenant(self, tenant_id):
        with self.lock:
            incident = self.current
        if incident and (incident.tenants is None or tenant_id in incident.tenants):
            return incident
        return None


def incident_answer(engine, incidents, tenant_id, message):
    """The status answer when the masked message is about the tenant's active incident, else None."""
    incident = incidents.for_tenant(tenant_id)
    if incident is None:
        return None
    try:
        answer = engine.ask({"incident": Masked(incident.brief), "message": message},
                            {"incident": INCIDENT_QUESTION})["incident"]
    except JevUnavailable:
        return None
    p_yes = round(answer.confidence if answer.value is True else 1 - answer.confidence, 9)
    if p_yes < INCIDENT_AT:
        return None
    checked = check(incident.status_answer)
    return checked.text if checked.verdict == "deliver" else None


# Latency budgets --------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Budget:
    route: str
    target: float               # p95 seconds for the final checked reply
    hard: float                 # absolute ceiling: past it, the fallback
    fallback: str
    steps: dict = field(default_factory=dict)   # step -> seconds; must fit the target

    def __post_init__(self):
        if not 0 < self.target < self.hard or sum(self.steps.values()) > self.target:
            raise ValueError(f"{self.route}: the steps must fit the target and the target the hard ceiling")


BUDGETS = {
    "faq": Budget("faq", 5.0, 8.0, "top_snippet",
                  {"screening": 0.3, "triage": 0.4, "retrieval": 2.0, "rerank": 0.5, "generation": 1.5,
                   "safety": 0.3}),
    "diagnostic": Budget("diagnostic", 20.0, 28.0, "summarise_findings",
                         {"screening": 0.3, "triage": 0.5, "retrieval": 3.0, "tools": 9.0, "generation": 6.0,
                          "safety": 0.5}),
    "multi_specialist": Budget("multi_specialist", 45.0, 60.0, "human_co_pilot",
                               {"screening": 0.3, "triage": 0.5, "delegation": 0.7, "specialists": 30.0,
                                "merge": 3.0, "generation": 8.0, "safety": 0.5}),
}


class Deadline:
    """One turn's clock against its route's budget."""

    def __init__(self, route, clock=time.monotonic):
        self.budget, self.clock = BUDGETS[route], clock
        self.start = clock()

    def elapsed(self):
        return self.clock() - self.start

    def status_due(self):
        """Seconds left to send the first status event (the progress message)."""
        return max(0.0, FIRST_STATUS - self.elapsed())

    def fits(self, step, then=()):
        """Whether an optional step still fits the target with the steps that must follow it (then), e.g.
        reranking before generation and safety; otherwise skip it."""
        needed = self.budget.steps[step] + sum(self.budget.steps[s] for s in then)
        return self.elapsed() + needed <= self.budget.target

    def timeout(self, step):
        """The seconds a step may take: its allocation, never past the hard ceiling."""
        return max(0.0, min(self.budget.steps[step], self.budget.hard - self.elapsed()))

    def expired(self):
        """Past the hard ceiling: stop and take budget.fallback."""
        return self.elapsed() >= self.budget.hard
