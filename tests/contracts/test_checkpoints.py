"""M5-05: the versioned checkpoint library (NFR-25 / TQ-ADP-05: TQ-D14; MS-ADP-04 MS-D13).

tests/contracts/checkpoints/v<N>/ keeps case states as the statechart checkpointed them under schema version
N: waiting for the customer, waiting for an approval (fresh and stale), resolved, escalated. Every archived
checkpoint must still load into today's graph, upgrade through the registered migrations and resume to the
outcome it records. The library is never edited, only added to: when SCHEMA_VERSION goes up, capture the new
version's states with UPDATE_CHECKPOINTS=1 (it writes the current version only) and keep the old ones.
"""

import json
import os
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from core.orchestrator.statechart import build, thread
from schemas import thread_state
from schemas.thread_state import SCHEMA_VERSION, Stage

LIBRARY = Path(__file__).with_name("checkpoints")
NOW = 1_800_000_000.0                         # the library's clock: waits are measured against it
SOP = {"intent": "BILLING_INQUIRY", "acuity": 2, "confidence": 0.95, "sop_name": "billing_inquiry"}
AMBIGUOUS = {"intent": "UNKNOWN", "acuity": 3, "confidence": 0.4, "missing_params": True}
REFUND = {**SOP, "parameters": {"amount": 4200.0}}


class Hooks(dict):
    """Fixed decisions, so a checkpoint's outcome depends only on its state and its event."""

    def __init__(self, triage=SOP, revalidate=True):
        self.executed = []
        super().__init__(
            triage=lambda state: triage,
            collect=lambda state: {"parameters": {**(state.get("parameters") or {}), "invoice_id": "INV-7"},
                                   "missing": []},
            execute_sop=lambda state: self.executed.append(state["parameters"]) or {"response": "Done."},
            react_step=lambda state: {"thought": "x", "outcome": "answer", "answer": "x"},
            revalidate=lambda state: revalidate)


def message(text):
    return {"type": "USER_MESSAGE", "text": text}


# name: (how to reach the state, the event that resumes it, revalidate, the outcome)
CASES = {
    "awaiting_customer": ([({**AMBIGUOUS}, message("It is broken"))], message("Invoice INV-7 is wrong"), True,
                          {"stage": "RESOLVED", "executed": 1}),
    "awaiting_approval": ([(REFUND, message("Refund INV-7 in full"))], {"type": "APPROVAL_GRANTED"}, True,
                          {"stage": "RESOLVED", "executed": 1}),
    "awaiting_approval_denied": ([(REFUND, message("Refund INV-7 in full"))], {"type": "APPROVAL_DENIED"},
                                 True,
                                 {"stage": "RESOLVED", "executed": 0}),
    "awaiting_approval_stale": ([(REFUND, message("Refund INV-7 in full"))], {"type": "APPROVAL_GRANTED"},
                                False,
                                {"stage": "ESCALATED_HITL", "executed": 0, "after_hours": 5}),
    "resolved": ([(SOP, message("What is on invoice INV-7?"))], message("And INV-8?"), True,
                 {"stage": "RESOLVED", "executed": 1}),
    "escalated": ([({**SOP, "confidence": 0.2}, message("asdf"))], message("hello?"), True,
                  {"stage": "ESCALATED_HITL", "executed": 0}),
}


def capture(name):
    """Run the graph to the case's waiting state and return the checkpointed values as plain JSON."""
    steps, _, _, _ = CASES[name]
    saver, config = InMemorySaver(), thread("t_us", name)
    for triage, event in steps:
        graph = build(Hooks(triage), saver, now=lambda: NOW)
        graph.invoke({"tenant_id": "t_us", "case_id": name, "session_id": "s1", "event": event}, config)
    return json.loads(json.dumps(graph.get_state(config).values))


if os.environ.get("UPDATE_CHECKPOINTS") == "1":
    (LIBRARY / f"v{SCHEMA_VERSION}").mkdir(parents=True, exist_ok=True)
    for case in CASES:
        target = LIBRARY / f"v{SCHEMA_VERSION}" / f"{case}.json"
        if not target.exists():                                     # never rewrite an archived checkpoint
            target.write_text(json.dumps(capture(case), indent=1, sort_keys=True) + "\n", encoding="utf-8")

ARCHIVE = sorted(LIBRARY.glob("v*/*.json"))


def resume(path, hooks):
    """Load an archived checkpoint into a fresh checkpointer and resume it with the case's event."""
    _, event, _, outcome = CASES[path.stem]
    values = json.loads(path.read_text(encoding="utf-8"))
    saver, config = InMemorySaver(), thread("t_us", path.stem)
    clock = NOW + 3600 * outcome.get("after_hours", 0)
    graph = build(hooks, saver, now=lambda: clock)
    graph.update_state(config, {**values, "next_stage": None}, as_node="resume")
    return graph.invoke({"event": event}, config), values


def test_the_library_covers_every_schema_version_and_every_old_one_has_a_migration():
    versions = {int(p.name[1:]) for p in LIBRARY.glob("v*")}
    assert versions == set(range(1, SCHEMA_VERSION + 1))
    assert all(v in thread_state.MIGRATIONS for v in range(1, SCHEMA_VERSION))
    for version in versions:
        assert {p.stem for p in (LIBRARY / f"v{version}").glob("*.json")} == set(CASES)


@pytest.mark.parametrize("path", ARCHIVE, ids=[f"{p.parent.name}/{p.stem}" for p in ARCHIVE])
def test_an_archived_checkpoint_upgrades_and_resumes_to_its_outcome(path):
    _, _, revalidate, outcome = CASES[path.stem]
    hooks = Hooks(revalidate=revalidate)
    state, archived = resume(path, hooks)
    assert archived["schema_version"] == int(path.parent.name[1:])
    assert state["stage"] == outcome["stage"] and state["schema_version"] == SCHEMA_VERSION
    assert len(hooks.executed) == outcome["executed"]
    assert state["path"][:len(archived["path"])] == archived["path"]          # history is kept, not rewritten
    assert Stage(archived["stage"]) in {Stage.AWAITING_CUSTOMER, Stage.AWAITING_APPROVAL, Stage.RESOLVED,
                                        Stage.ESCALATED_HITL}


@pytest.mark.parametrize("path", ARCHIVE, ids=[f"{p.parent.name}/{p.stem}" for p in ARCHIVE])
def test_the_next_schema_version_would_load_the_whole_library_through_its_migration(path, monkeypatch):
    """A rehearsal of the next bump: with version two and a one-to-two migration registered, every archived
    checkpoint arrives upgraded and still resumes to its outcome."""
    monkeypatch.setattr(thread_state, "SCHEMA_VERSION", SCHEMA_VERSION + 1)
    monkeypatch.setitem(thread_state.MIGRATIONS, SCHEMA_VERSION, lambda s: {"approval_threshold": 1000.0})
    _, _, revalidate, outcome = CASES[path.stem]
    state, _ = resume(path, Hooks(revalidate=revalidate))
    assert state["schema_version"] == SCHEMA_VERSION + 1 and state["approval_threshold"] == 1000.0
    assert state["stage"] == outcome["stage"]


def test_a_checkpoint_from_a_version_with_no_migration_goes_to_a_person():
    values = json.loads((LIBRARY / "v1" / "awaiting_customer.json").read_text(encoding="utf-8"))
    saver, config = InMemorySaver(), thread("t_us", "orphan")
    graph = build(Hooks(), saver, now=lambda: NOW)
    graph.update_state(config, {**values, "schema_version": 0, "next_stage": None}, as_node="resume")
    state = graph.invoke({"event": message("hello")}, config)
    assert state["stage"] == "ESCALATED_HITL" and "schema version 0" in state["error"]
