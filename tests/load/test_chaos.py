"""M5-05: chaos tests, in process (NFR-20 / RP-ADP-05: RP-D12; NFR-25 / TQ-ADP-05: TQ-D10).

The faults RP-D12 names, injected into the real modules: Jev dropping out at every decision point, the model
providers failing, tool latency spikes that time out, a worker killed in the middle of a case, and the
admission store partitioned away. Each run draws its faults from a fixed seed; the assertions are what must
stay true however the faults fall. (Chaos on staging infrastructure, pod kills and network partitions with
Chaos Mesh, needs the staging cluster v1 does not have: register L21.)
"""

import json
import random
import threading

import httpx
import pytest
from langgraph.checkpoint.memory import InMemorySaver

from agents.merge import merge
from agents.topology import Specialist, delegate, registry
from core.orchestrator.decisions import Masked, mask
from core.orchestrator.statechart import build, thread
from core.orchestrator.triage import ASK_CUSTOMER, llm_fallback, triage, triage_hook
from reliability.admission import Admission, Limits, Local, Mode, StoreUnavailable, degraded_answer
from reliability.bursts import Incident, Incidents, incident_answer
from reliability.fallbacks import (
    TURN_RETRY_LIMIT,
    AllProvidersFailed,
    Completion,
    Provider,
    ProviderError,
    RetryBudget,
    call_chain,
)
from tests.agents.topology.test_topology import DESCRIPTIONS, TOOL_REGISTRY, TOOLS
from tests.invariants.harness import ScriptedJev, ScriptedModel, engine
from tests.tools.execution.test_execution import INVOICE, Fake, call, executor
from tools.execution import BREAKER_FAILURES, ToolFailure

# Jev drops out ----------------------------------------------------------------------------------------------

OUTAGES = ["unreachable", "http_500", "http_429", "not_json"]


def specialists():
    return registry([Specialist(role, DESCRIPTIONS[role], frozenset(TOOLS[role]), lambda brief, history: {})
                     for role in TOOLS], TOOL_REGISTRY)


@pytest.mark.parametrize("outage", OUTAGES)
def test_with_jev_down_every_decision_point_fails_safe(outage):
    decide = engine(ScriptedJev(random.Random(1), behaviours=[outage]))
    message = {"message": mask("The VPN is down for everyone")}
    assert triage(decide, message) == ASK_CUSTOMER
    assert decide.guard("may_resolve", "Is the customer's problem solved?", message) is False
    assert decide.select_tool({"kb.search": "Search the knowledge base"}, message) is None
    assert delegate(decide, specialists(), Masked("Audit our uptime")).handoff
    claims = [{"topic": "uptime", "text": "It was fine", "evidence": ["ops.uptime"]}]
    result = {"role": "technical", "status": "completed", "findings": json.dumps(claims), "evidence": [],
              "steps": 1}
    assert merge(decide, [result], {"ops.uptime": "fine"}, lambda c: "Uptime was fine.").reason == \
        "JEV_UNAVAILABLE"
    incidents = Incidents()
    incidents.declare(Incident("EU database outage", "We are working on an EU database outage."))
    assert incident_answer(decide, incidents, "t_us", Masked("Is the database down?")) is None


@pytest.mark.parametrize("seed", range(50))
def test_with_jev_down_a_case_waits_for_the_customer_and_runs_nothing(seed):
    rng = random.Random(seed)
    ran = []
    decide, fallback = engine(ScriptedJev(rng, behaviours=OUTAGES)), llm_fallback(ScriptedModel(rng))
    hooks = {"triage": triage_hook(decide, fallback),
             "collect": lambda s: {"parameters": {"amount": 50}, "missing": []},
             "execute_sop": lambda s: ran.append(s) or {"response": "Done."},
             "react_step": lambda s: ran.append(s) or {"thought": "x", "outcome": "answer", "answer": "x"},
             "revalidate": lambda s: True}
    start = {"tenant_id": "t", "case_id": "c", "session_id": "s",
             "event": {"type": "USER_MESSAGE", "text": "help"}}
    state = build(hooks, InMemorySaver()).invoke(start, thread("t", "c"))
    # the fallback classifier may triage, but its confidence is capped below what an SOP needs
    assert "COLLECTING_PARAMS" not in state["path"] and not any(s.get("sop_name") for s in ran)


@pytest.mark.xfail(strict=True, reason="register B10: triage's fallback lets a provider outage escape (it "
                                       "catches only parse errors), so Jev and the model both down crashes "
                                       "the turn")
def test_with_jev_and_the_fallback_model_both_down_triage_asks_the_customer():
    def down(prompt):
        raise AllProvidersFailed([ProviderError("groq", "down", transient=True)])
    decide = engine(ScriptedJev(random.Random(1), behaviours=["unreachable"]))
    assert triage(decide, {"message": mask("help")}, llm_fallback(down)) == ASK_CUSTOMER


# The model providers fail -----------------------------------------------------------------------------------

def flaky_provider(name, rng, log):
    def complete(messages, max_tokens):
        how = rng.choice(["ok", "transient", "transient", "permanent", "spend_limit"])
        log.append((name, how))
        if how == "ok":
            return Completion("an answer", name, 10, 5)
        raise ProviderError(name, how, transient=how == "transient", spend_limit=how == "spend_limit")
    return Provider(name, complete)


@pytest.mark.parametrize("seed", range(200))
def test_a_provider_outage_moves_down_the_chain_within_the_retry_budget(seed):
    rng, log, turn = random.Random(seed), [], {"retries": 0}
    providers = [flaky_provider(name, rng, log) for name in ("claude", "groq", "gemini")]
    try:
        completion = call_chain(providers, [{"role": "user", "content": "hi"}], 100, RetryBudget(), turn,
                                sleep=lambda s: None)
        assert completion.text == "an answer" and log[-1][1] == "ok"
    except AllProvidersFailed:
        assert all(how != "ok" for _, how in log)
    retried = sum(1 for p in providers if sum(1 for name, _ in log if name == p.name) == 2)
    assert turn["retries"] == retried <= TURN_RETRY_LIMIT        # the turn's count is the retries made
    assert all(sum(1 for name, _ in log if name == p.name) <= 2 for p in providers)
    order = ["claude", "groq", "gemini"]
    assert [name for name, _ in log] == sorted((name for name, _ in log), key=order.index)


def test_with_every_model_down_the_degraded_answer_still_cites_the_knowledge_base():
    def down(prompt):
        raise AllProvidersFailed([])
    passages = [("kb-1", "Restart the VPN client."), ("kb-2", "Check the status page.")]
    answer = degraded_answer(lambda q: passages, down, "VPN down?")
    assert "[kb-1] Restart the VPN client." in answer and "[kb-2]" in answer


# Tool latency spikes ----------------------------------------------------------------------------------------

class Spiky(Fake):
    """The billing system with latency spikes that end in a client timeout, at a seeded rate."""

    def __init__(self, rng, rate):
        super().__init__()
        self.rng, self.rate = rng, rate

    def __call__(self, request):
        if self.rng.random() < self.rate:
            self.requests.append(request)
            raise httpx.ReadTimeout("spike", request=request)
        return super().__call__(request)


@pytest.mark.parametrize("seed", range(30))
def test_tool_latency_spikes_retry_reads_within_limits_then_open_the_breaker(seed):
    rng = random.Random(seed)
    fake = Spiky(rng, rate=rng.choice([0.2, 0.6, 1.0]))
    run, _ = executor(fake, clock=lambda: 1000.0)       # frozen clock: an opened breaker stays open
    opened_at = None
    for n in range(12):
        before = len(fake.requests)
        try:
            run.run(call("billing.get_invoice", INVOICE, tool_call_id=f"call-{n}"))
        except ToolFailure as failure:
            assert failure.code.isupper()
            if failure.code == "SYSTEM_UNAVAILABLE" and opened_at is None and len(fake.requests) == before:
                opened_at = n
        assert len(fake.requests) - before <= 4                       # one call and three retries at most
        if opened_at is not None:
            assert len(fake.requests) == before, "nothing reaches a system while its breaker is open"
    if fake.rate == 1.0:
        assert opened_at is not None and opened_at <= -(-BREAKER_FAILURES // 4) + 1


# A worker dies in the middle of a case ----------------------------------------------------------------------

class Killed(BaseException):
    """A worker dying: not an Exception, so nothing in the graph can catch it."""


HOOKS = ("triage", "collect", "execute_sop")


@pytest.mark.parametrize("victim", HOOKS)
def test_a_case_resumed_after_its_worker_died_runs_its_procedure_exactly_once(victim):
    effects, armed = [], {"kill": True}

    def hook(name, result):
        def call_hook(state):
            if name == victim and armed["kill"]:
                armed["kill"] = False
                raise Killed(name)
            if name == "execute_sop":
                effects.append(state["parameters"])
            return result
        return call_hook

    hooks = {"triage": hook("triage", {"intent": "update_address", "acuity": 2, "confidence": 0.95,
                                       "sop_name": "update_address"}),
             "collect": hook("collect", {"parameters": {"zip": "10115"}, "missing": []}),
             "execute_sop": hook("execute_sop", {"response": "Done."}),
             "react_step": lambda s: {}, "revalidate": lambda s: True}
    saver, config = InMemorySaver(), thread("t", "c")
    graph = build(hooks, saver)
    with pytest.raises(Killed):
        graph.invoke({"tenant_id": "t", "case_id": "c", "session_id": "s",
                      "event": {"type": "USER_MESSAGE", "text": "new address"}}, config)
    state = build(hooks, saver).invoke(None, config)        # a new worker picks the case up
    assert state["stage"] == "RESOLVED" and effects == [{"zip": "10115"}]
    assert state["path"] == ["INGESTED", "TRIAGED", "COLLECTING_PARAMS", "EXECUTING_SOP", "RESOLVED"]


# The admission store is partitioned away --------------------------------------------------------------------

class Partitioned(Local):
    """The shared store, unreachable at a seeded rate (a network partition between the API and Upstash)."""

    def __init__(self, rng, rate):
        super().__init__()
        self.rng, self.rate, self.guard = rng, rate, threading.Lock()

    def __getattribute__(self, name):
        attribute = super().__getattribute__(name)
        if name in ("add", "read", "acquire", "holder", "release", "extend"):
            with super().__getattribute__("guard"):
                down = super().__getattribute__("rng").random() < super().__getattribute__("rate")
            if down:
                def unavailable(*args):
                    raise StoreUnavailable("partitioned")
                return unavailable
        return attribute


@pytest.mark.parametrize("seed", range(10))
def test_admission_keeps_answering_while_its_store_is_partitioned(seed):
    """Every request still gets a verdict (the local fallback), never an exception. The one-turn guarantee
    across the store and the fallback is not claimed here: register L20."""
    rng = random.Random(seed)
    admission = Admission(Partitioned(rng, rate=0.5), Limits(user_rpm=10_000, tenant_rpm=10_000))
    for n in range(200):
        conv = f"conv-{rng.randrange(5)}"
        verdict = admission.admit("t_us", "sarah", conv, f"turn-{n}")
        assert verdict.mode in set(Mode)
        if verdict.mode in (Mode.FULL, Mode.KB_ONLY) and rng.random() < 0.7:
            admission.finish("t_us", conv, f"turn-{n}")


class Switchable(Local):
    """The shared store, up until the test cuts it off."""

    def __init__(self):
        super().__init__()
        self.down = False

    def __getattribute__(self, name):
        operations = ("add", "read", "acquire", "holder", "release", "extend")
        if name in operations and super().__getattribute__("down"):
            def unavailable(*args):
                raise StoreUnavailable("partitioned")
            return unavailable
        return super().__getattribute__(name)


@pytest.mark.xfail(strict=True, reason="register B11: the local fallback cannot see a lock held in the "
                                       "shared store, so a partition lets a second turn start on a busy "
                                       "conversation")
def test_a_partition_does_not_let_a_second_turn_start_on_a_busy_conversation():
    store = Switchable()
    admission = Admission(store)
    assert admission.admit("t_us", "sarah", "conv-1", "turn-1").mode is Mode.FULL
    store.down = True
    assert admission.admit("t_us", "sarah", "conv-1", "turn-2").mode is Mode.BUSY
