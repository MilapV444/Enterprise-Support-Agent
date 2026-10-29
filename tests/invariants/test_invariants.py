"""M5-05: the platform's safety invariants over pseudo-random model and Jev outputs (NFR-21 / TQ-ADP-01:
TQ-D1, TQ-D2). Models and Jev are mocked by tests/invariants/harness.py; each property runs over a few hundred
seeded draws, and a failure names its seed so it replays exactly.

Hypothesis is not a dependency yet (pyproject), so the draws are random.Random loops over fixed seeds rather
than shrinking strategies."""

import json
import random
import threading
import time
from decimal import Decimal
from itertools import pairwise

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from agents.merge import TOLERANCE, merge
from agents.topology import (
    STEPS_PER_SPECIALIST,
    STEPS_PER_TURN,
    Role,
    Specialist,
    coordinator,
    ledger,
    registry,
    start_turn,
)
from core.orchestrator.decisions import Masked
from core.orchestrator.planner import MAX_REFLEXION, MAX_STEPS
from core.orchestrator.statechart import DEFAULT_APPROVAL_THRESHOLD, allowed, build, thread
from core.orchestrator.triage import llm_fallback, triage_hook
from reliability.admission import Admission, Limits, Local, Mode
from safety.output.checks import check
from schemas.thread_state import Stage
from tests.agents.topology.test_topology import DESCRIPTIONS, TOOL_REGISTRY, TOOLS, TURN
from tests.invariants.harness import ScriptedJev, ScriptedModel, engine

SEEDS = range(300)
READ_ONLY = frozenset({"kb.search", "status.check"})
AT_REST = {Stage.AWAITING_CUSTOMER.value, Stage.AWAITING_APPROVAL.value, Stage.RESOLVED.value,
           Stage.ESCALATED_HITL.value}


# The statechart ---------------------------------------------------------------------------------------------

class World:
    """Hooks for one random case: Jev and the fallback model are scripted; slot filling, the SOP and the
    ReAct steps draw random but well-typed outputs. Every SOP execution is recorded with what allowed it."""

    def __init__(self, rng):
        self.rng, self.jev, self.model = rng, ScriptedJev(rng), ScriptedModel(rng)
        self.executions = []
        self.persona = rng.choice(["random", "random", "random", "persistent", "critic"])
        self.hooks = {"triage": triage_hook(engine(self.jev), llm_fallback(self.model)),
                      "collect": self.collect, "execute_sop": self.execute, "react_step": self.react,
                      "revalidate": lambda state: rng.random() < 0.5}

    def collect(self, state):
        amount = self.rng.choice([0, 25.5, 999.99, 1000, 1000.01, 4200, self.rng.uniform(0, 20000)])
        return {"parameters": {"amount": amount}, "missing": self.rng.choice([[], [], ["account_id"]])}

    def execute(self, state):
        trigger = (state.get("event") or {}).get("type")
        self.executions.append((float(state["parameters"].get("amount", 0)), trigger))
        return self.rng.choice([{"response": "Done."}, {"response": "Done."}, {"error": "the SOP failed"}])

    def react(self, state):
        if self.persona == "persistent":                # never stops looking
            return {"thought": "one more look", "outcome": "continue", "action": "kb.search"}
        if self.persona == "critic":                    # finds fault with every step
            return {"thought": "that was wrong", "outcome": "critique", "action": "kb.search"}
        outcome = self.rng.choice(["continue", "continue", "critique", "answer", "needs_sop"])
        step = {"thought": "look", "outcome": outcome,
                "action": self.rng.choice([None, "kb.search", "status.check", "billing.refund",
                                           "shell.exec"])}
        if outcome == "answer":
            step["answer"] = "It is fixed."
        if outcome == "needs_sop":
            step |= {"sop_name": "update_address", "parameters": {"amount": self.rng.choice([10, 5000])}}
        return step


def next_event(stage, rng):
    if stage == Stage.AWAITING_CUSTOMER.value:
        return {"type": "USER_MESSAGE", "text": rng.choice(["It is the VPN", "Refund invoice INV-7 please"])}
    if stage == Stage.AWAITING_APPROVAL.value:
        return {"type": rng.choice(["APPROVAL_GRANTED", "APPROVAL_DENIED"])}
    return None


@pytest.mark.parametrize("seed", SEEDS)
def test_the_statechart_stays_legal_and_safe_whatever_the_models_say(seed):
    rng, saver = random.Random(seed), InMemorySaver()
    world = World(rng)
    graph, config = build(world.hooks, saver, read_only_tools=READ_ONLY), thread("t_us", f"case-{seed}")
    event, seen = {"type": "USER_MESSAGE", "text": "My invoice is wrong and the VPN is down"}, 0
    state = {}
    for _ in range(4):
        first = {"tenant_id": "t_us", "case_id": f"case-{seed}", "session_id": "s1"} if not seen else {}
        state = graph.invoke({**first, "event": event}, config)
        segment = state["path"][seen:]
        # every stage was entered through a listed transition, and the run stopped at rest
        assert all(allowed(a, Stage(b)) for a, b in pairwise([state["path"][seen - 1] if seen else None,
                                                               *segment])), (seed, state["path"])
        assert state["stage"] in AT_REST, (seed, state["stage"])
        # an SOP is collected only on a confident Jev triage, never on a fallback guess or "ask the customer"
        for before, after in pairwise(segment):
            if (before, after) == (Stage.TRIAGED.value, Stage.COLLECTING_PARAMS.value):
                assert state["triage"]["confidence"] >= 0.90
                assert state["triage"]["rationale"].startswith("jev")
        # diagnosis is bounded, and never continues after a tool that is not read-only
        steps = segment.count(Stage.DELIBERATING.value)
        assert steps <= MAX_STEPS, seed
        trajectory = state.get("trajectory", [])
        outcomes = [s["outcome"] for s in trajectory[len(trajectory) - steps:]]   # this segment's steps
        critiques = [n for n, outcome in enumerate(outcomes) if outcome == "critique"]
        if len(critiques) > MAX_REFLEXION:                # the critique past the limit ends the episode
            assert critiques[MAX_REFLEXION] == len(outcomes) - 1, (seed, outcomes)
        for step in state.get("trajectory", []):
            if step["action"] and step["action"] not in READ_ONLY:
                assert state["stage"] == Stage.ESCALATED_HITL.value, (seed, step)
        seen = len(state["path"])
        event = next_event(state["stage"], rng)
        if event is None:
            break
    # money at or above the threshold moved only after an approval was granted
    for amount, trigger in world.executions:
        assert amount < DEFAULT_APPROVAL_THRESHOLD or trigger == "APPROVAL_GRANTED", (seed, amount, trigger)


def test_the_draws_reach_every_stage_and_every_jev_failure():
    """The property above is only as good as its draws: they must cover the stages and the failure modes."""
    stages, behaviours = set(), set()
    for seed in SEEDS:
        rng = random.Random(seed)
        world = World(rng)
        graph, config = build(world.hooks, InMemorySaver(), read_only_tools=READ_ONLY), thread("t", str(seed))
        state = graph.invoke({"tenant_id": "t", "case_id": str(seed), "session_id": "s",
                              "event": {"type": "USER_MESSAGE", "text": "help"}}, config)
        if state["stage"] == Stage.AWAITING_APPROVAL.value:
            state = graph.invoke({"event": {"type": "APPROVAL_GRANTED"}}, config)
        stages |= set(state["path"])
        behaviours |= {how for _, how in world.jev.log}
    assert stages == {s.value for s in Stage}
    assert behaviours >= {"valid", "unknown_option", "bad_confidence", "missing_answer", "unreachable"}


# Delegation, depth and step budgets -------------------------------------------------------------------------

ALL_TOOLS = sorted(set().union(*TOOLS.values()) | {"billing.issue_credit", "shell.exec"})


def wandering(role, rng):
    """A specialist whose model does anything: its own tools, other agents' tools, writes, bad findings."""
    def act(brief, history):
        move = rng.choice(["own", "own", "other", "findings", "bad_findings", "bad_arguments"])
        if move == "own":
            return {"thought": "read", "action": rng.choice(sorted(TOOLS[role])), "action_input": {"q": "x"}}
        if move == "other":
            return {"thought": "reach", "action": rng.choice(ALL_TOOLS), "action_input": {"q": "x"}}
        if move == "bad_arguments":
            return {"thought": "read", "action": rng.choice(sorted(TOOLS[role])), "action_input": ["x"]}
        if move == "bad_findings":
            return {"thought": "report", "findings": rng.choice([None, 7, "x" * 5000]),
                    "evidence": rng.choice([[], ["kb"] * 30, [3]])}
        return {"thought": "report", "findings": f"{role} found it", "evidence": [f"{role}.source"]}
    return act


class RecordingTools:
    def __init__(self, rng):
        self.rng, self.requests, self.lock = rng, [], threading.Lock()

    def __call__(self, request):
        with self.lock:
            self.requests.append(request)
            how = self.rng.choice(["text", "text", "raise", "not_text"])
        if how == "raise":
            raise TimeoutError("the API timed out")
        return {"raw": "unscreened"} if how == "not_text" else f"{request.tool_id} ok"


@pytest.mark.parametrize("seed", SEEDS)
def test_delegation_never_exceeds_its_limits_or_reaches_a_tool_off_the_allow_list(seed):
    rng = random.Random(seed)
    jev, tools = ScriptedJev(rng), RecordingTools(rng)
    specs = registry([Specialist(role, DESCRIPTIONS[role], frozenset(TOOLS[role]), wandering(role, rng))
                      for role in TOOLS], TOOL_REGISTRY)
    graph = coordinator(engine(jev), specs, tools, InMemorySaver())
    state = start_turn(graph, **{**TURN, "case_id": f"case-{seed}"}, message=Masked("Audit our EU uptime"))
    results, plan = state.get("results", []), state["plan"]
    per, total = ledger(results, plan)          # raises if anything ran outside its assignment
    assert total <= STEPS_PER_TURN and all(steps <= STEPS_PER_SPECIALIST for steps in per.values())
    assert len([r for r in results if r["status"] != "skipped"]) <= 3
    if plan["handoff"]:
        assert results == [] and tools.requests == []
    if not jev.all_valid:                       # Jev could not decide: nobody is dispatched
        assert plan["handoff"] and tools.requests == []
    for request in tools.requests:
        assert request.tool_id in TOOLS[request.role], (seed, request.role, request.tool_id)
        context = (request.tenant_id, request.case_id, request.session_id, request.principal_id)
        assert context == ("t_us", f"case-{seed}", "s-sarah", "sarah")
    for result in results:
        assert result["status"] in {"completed", "blocked", "skipped"}
        if result["status"] == "completed":
            assert isinstance(result["findings"], str) and len(result["evidence"]) <= 20
    assert {Role(r["role"]) for r in results} <= {Role(a["role"]) for a in plan["assignments"]}


# Merging: numbers never pass on a model's say ---------------------------------------------------------------

TOPICS = ("uptime", "credits", "latency")
UNITS = ("percent", "count", None)


def random_claim(rng):
    claim = {"topic": rng.choice(TOPICS), "text": rng.choice(["It was fine", "It was not fine", "Two memos"]),
             "evidence": [rng.choice(["ops.uptime", "billing.memos", "kb.sla"])]}
    if rng.random() < 0.6:
        value = rng.choice([Decimal("99.98"), Decimal("99.98"), Decimal("99.981"), Decimal("99.99"),
                            Decimal(rng.randrange(0, 3))])
        claim |= {"value": str(value), "unit": rng.choice(UNITS)}
    return claim


def conflicting(claims):
    """Topics where numeric claims differ beyond the unit's tolerance or are in different units (an
    independent statement of the rule)."""
    out = set()
    for topic in TOPICS:
        numeric = [c for c in claims if c["topic"] == topic and c.get("value") is not None]
        units = {c["unit"] for c in numeric}
        values = [Decimal(c["value"]) for c in numeric]
        tolerance = TOLERANCE.get(next(iter(units), None) or "", 0)
        if len(units) > 1 or (values and max(values) - min(values) > tolerance):
            out.add(topic)
    return out


@pytest.mark.parametrize("seed", SEEDS)
def test_a_numeric_disagreement_always_goes_to_a_person_and_a_reply_is_drafted_at_most_once(seed):
    rng = random.Random(seed)
    jev, drafts = ScriptedJev(rng), []
    results = [{"role": role, "status": rng.choice(["completed", "completed", "blocked"]), "steps": 1,
                "evidence": [],
                "findings": json.dumps([random_claim(rng) for _ in range(rng.randrange(0, 3))])}
               for role in rng.sample(["billing", "technical", "account_ops"], rng.randrange(1, 4))]
    evidence = {"ops.uptime": "uptime 99.98 percent", "billing.memos": "two memos", "kb.sla": "SLA text"}
    def draft(claims):
        drafts.append(claims)
        return "Here is the audit."
    outcome = merge(engine(jev), results, evidence, draft)
    used = [json.loads(r["findings"]) for r in results if r["status"] == "completed"]
    claims = [c for group in used for c in group]
    if conflicting(claims):
        assert (outcome.kind, outcome.reason) == ("human", "NUMERIC_DISCREPANCY"), seed
        assert drafts == []
    assert len(drafts) <= 1
    if outcome.kind == "reply":
        assert jev.all_valid and outcome.text == "Here is the audit." and len(drafts) == 1
        assert not conflicting([c.model_dump(mode="json") for c in outcome.accepted])


# Output checks: a credential never reaches the customer -----------------------------------------------------

ALNUM = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def credential(rng):
    pick = lambda n, alphabet=ALNUM: "".join(rng.choice(alphabet) for _ in range(n))  # noqa: E731
    return rng.choice([
        f"sk_live_{pick(rng.randrange(16, 40))}", f"sk_test_{pick(24)}", f"sk-ant-api03-{pick(32)}",
        f"AKIA{pick(16, ALNUM[26:])}", f"ghp_{pick(36)}", f"xoxb-{pick(12)}-{pick(16)}",
        f"eyJ{pick(16)}.eyJ{pick(24)}.{pick(20)}"])        # PEM headers: see the xfail below


def wrapped(secret, rng):
    return rng.choice([
        f"Your key is {secret}.", f"```\nexport KEY={secret}\n```",
        f"[click here](https://docs.acme.com/?k={secret})", f"<b>{secret}</b>",
        f"Use '{secret}' in the header", f"{secret}", f"Step 1: copy {secret}\nStep 2: paste"])


@pytest.mark.parametrize("seed", SEEDS)
def test_a_reply_holding_a_credential_is_never_delivered(seed):
    rng = random.Random(seed)
    secret = credential(rng)
    result = check(wrapped(secret, rng), allowed_domains=("docs.acme.com",))
    assert result.verdict == "block" and secret not in result.text, (seed, secret)


@pytest.mark.xfail(strict=True, reason="register B9: the PEM header pattern sits behind \b, which cannot "
                                       "match before '-----' after a space, a line break or punctuation")
@pytest.mark.parametrize("before", [" ", "\n", ""])
def test_a_private_key_header_alone_is_never_delivered(before):
    assert check(f"Here it is:{before}-----BEGIN RSA PRIVATE KEY-----").verdict == "block"


def test_a_private_key_block_is_caught_by_its_body_meanwhile():
    pem = ("-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyF8PbnGy0AHB7MaC0KxJ8\n"
           "-----END RSA PRIVATE KEY-----")
    assert check(f"Here it is:\n{pem}").verdict == "block"


@pytest.mark.parametrize("seed", range(100))
def test_a_reply_copying_twelve_words_of_the_system_prompt_is_never_delivered(seed):
    rng = random.Random(seed)
    vocabulary = ["never", "reveal", "the", "refund", "rules", "to", "customers", "always", "escalate",
                  "disputes", "above", "threshold", "internal"]
    prompt = " ".join(rng.choice(vocabulary) for _ in range(60))
    words = prompt.split()
    start = rng.randrange(0, len(words) - 12)
    leak = " ".join(words[start:start + rng.randrange(12, 20)])
    reply = rng.choice([f"Sure! {leak}", f"My instructions: {leak.upper()}", f"{leak}. Anything else?"])
    assert check(reply, system_prompt=prompt).verdict == "block", seed


# One active turn per conversation (RP-D3) -------------------------------------------------------------------

@pytest.mark.parametrize("seed", range(20))
def test_at_most_one_turn_runs_per_conversation_under_random_interleavings(seed):
    admission = Admission(Local(), Limits(user_rpm=10_000, tenant_rpm=10_000, tenant_tpm=10**9))
    active, guard, violations, admitted = {}, threading.Lock(), [], []
    conversations = [f"conv-{n}" for n in range(3)]

    def client(worker):
        local = random.Random(seed * 100 + worker)
        for n in range(15):
            conv, turn = local.choice(conversations), f"turn-{worker}-{n}"
            verdict = admission.admit("t_us", f"user-{worker}", conv, turn)
            if verdict.mode not in (Mode.FULL, Mode.KB_ONLY):
                assert verdict.mode is Mode.BUSY and verdict.active_turn_id
                continue
            with guard:
                if conv in active:
                    violations.append((conv, active[conv], turn))
                active[conv] = turn
                admitted.append(turn)
            time.sleep(local.uniform(0, 0.002))
            if local.random() < 0.2:            # someone else's turn id cannot release it
                assert not admission.finish("t_us", conv, f"turn-{worker}-intruder")
            with guard:
                del active[conv]
            assert admission.finish("t_us", conv, turn)

    workers = [threading.Thread(target=client, args=(w,)) for w in range(6)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    assert violations == [] and admitted, seed
