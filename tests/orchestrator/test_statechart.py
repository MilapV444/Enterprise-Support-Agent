"""M1-04: statechart transitions, scoped ReAct bounds, waits, schema versions and crash-resume from the
Postgres checkpointer (FR-1, FR-18)."""

import subprocess
from itertools import pairwise
from pathlib import Path

import pytest

from core.orchestrator.planner import MAX_STEPS
from core.orchestrator.statechart import IllegalTransition, allowed, build, postgres_checkpointer, thread
from data.migrate import psql
from schemas import thread_state
from schemas.thread_state import SCHEMA_VERSION, Stage

ROOT = Path(__file__).resolve().parents[2]
DB = "test_orchestrator"
DSN = f"postgresql://agent:change-me@127.0.0.1:5432/{DB}"  # credentials from .env.example
SOP = {"intent": "update_address", "acuity": 2, "confidence": 0.95, "sop_name": "update_address"}
DIAGNOSTIC = {"intent": "vpn_down", "acuity": 4, "confidence": 0.9}


@pytest.fixture(scope="module", autouse=True)
def database():
    subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env.example",
                    "up", "-d", "--wait", "postgres"], cwd=ROOT, check=True, capture_output=True)
    psql("postgres", f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
    psql("postgres", f'CREATE DATABASE "{DB}"')


@pytest.fixture
def saver():
    with postgres_checkpointer(DSN) as checkpointer:
        yield checkpointer


class Hooks(dict):
    """Fake decisions that count their calls."""

    def __init__(self, triage=SOP, collect=None, sop=None, steps=(), revalidate=True):
        self.calls = {"triage": 0, "collect": 0, "execute_sop": 0, "react_step": 0, "revalidate": 0}
        triages = list(triage) if isinstance(triage, list) else [triage]
        steps = list(steps)

        def counted(name, fn):
            def call(state):
                self.calls[name] += 1
                return fn(state)
            return call

        super().__init__(
            triage=counted("triage", lambda s: triages.pop(0) if len(triages) > 1 else triages[0]),
            collect=counted("collect", lambda s: collect or {"parameters": {"zip": "1"}, "missing": []}),
            execute_sop=counted("execute_sop", sop or (lambda s: {"response": "Done."})),
            react_step=counted("react_step", lambda s: steps.pop(0)),
            revalidate=counted("revalidate", lambda s: revalidate),
        )


def start(case, text="hello"):
    return {"tenant_id": "t_us", "case_id": case, "session_id": "s1",
            "event": {"type": "USER_MESSAGE", "text": text}}


def assert_legal(path):
    for source, target in pairwise([None, *path]):
        assert allowed(source, Stage(target)), f"{source} -> {target}"


def test_sop_runs_through_the_deterministic_path(saver):
    hooks = Hooks()
    state = build(hooks, saver).invoke(start("c1"), thread("t_us", "c1"))
    assert state["path"] == ["INGESTED", "TRIAGED", "COLLECTING_PARAMS", "EXECUTING_SOP", "RESOLVED"]
    assert state["final_response"] == "Done." and state["schema_version"] == SCHEMA_VERSION


def test_ambiguous_message_waits_for_the_customer_then_continues(saver):
    hooks = Hooks(triage=[{"intent": "?", "acuity": 3, "confidence": 0.6}, SOP])
    graph, config = build(hooks, saver), thread("t_us", "c2")
    assert graph.invoke(start("c2"), config)["stage"] == "AWAITING_CUSTOMER"
    state = graph.invoke({"event": {"type": "USER_MESSAGE", "text": "my new address"}}, config)
    assert state["stage"] == "RESOLVED" and len(state["messages"]) == 2
    assert_legal(state["path"])


def test_low_confidence_goes_to_a_human(saver):
    state = build(Hooks(triage={"intent": "x", "acuity": 2, "confidence": 0.3}), saver).invoke(
        start("c3"), thread("t_us", "c3"))
    assert state["path"][-1] == "ESCALATED_HITL"


def test_large_amounts_wait_for_approval_before_any_change(saver):
    hooks = Hooks(collect={"parameters": {"amount": 1500}, "missing": []})
    graph, config = build(hooks, saver), thread("t_us", "c4")
    assert graph.invoke(start("c4"), config)["stage"] == "AWAITING_APPROVAL"
    assert hooks.calls["execute_sop"] == 0
    state = graph.invoke({"event": {"type": "APPROVAL_GRANTED"}}, config)
    assert (state["stage"], hooks.calls["execute_sop"]) == ("RESOLVED", 1)
    assert_legal(state["path"])


def test_denied_approval_changes_nothing(saver):
    hooks = Hooks(collect={"parameters": {"amount": 5000}, "missing": []})
    graph, config = build(hooks, saver), thread("t_us", "c5")
    graph.invoke(start("c5"), config)
    state = graph.invoke({"event": {"type": "APPROVAL_DENIED"}}, config)
    assert (state["stage"], state["final_response"], hooks.calls["execute_sop"]) == (
        "RESOLVED", "The request was not approved.", 0)


@pytest.mark.parametrize("still_valid, outcome, executed",
                         [(True, "RESOLVED", 1), (False, "ESCALATED_HITL", 0)])
def test_resuming_after_more_than_an_hour_rechecks_the_world_first(saver, still_valid, outcome, executed):
    clock = [1000.0]
    hooks = Hooks(collect={"parameters": {"amount": 1500}, "missing": []}, revalidate=still_valid)
    graph, config = build(hooks, saver, now=lambda: clock[0]), thread("t_us", f"c6-{still_valid}")
    graph.invoke(start("c6"), config)
    clock[0] += 3601
    state = graph.invoke({"event": {"type": "APPROVAL_GRANTED"}}, config)
    assert (state["stage"], hooks.calls["revalidate"], hooks.calls["execute_sop"]) == (outcome, 1, executed)


def test_a_short_wait_needs_no_recheck(saver):
    clock = [1000.0]
    hooks = Hooks(collect={"parameters": {"amount": 1500}, "missing": []})
    graph, config = build(hooks, saver, now=lambda: clock[0]), thread("t_us", "c7")
    graph.invoke(start("c7"), config)
    clock[0] += 600
    graph.invoke({"event": {"type": "APPROVAL_GRANTED"}}, config)
    assert hooks.calls["revalidate"] == 0


def test_a_crashed_run_resumes_from_its_last_checkpoint(saver):
    crashes = [RuntimeError("worker died")]

    def flaky(state):
        if crashes:
            raise crashes.pop()
        return {"response": "Done."}

    hooks, config = Hooks(sop=flaky), thread("t_us", "c8")
    with pytest.raises(RuntimeError, match="worker died"):
        build(hooks, saver).invoke(start("c8"), config)
    with postgres_checkpointer(DSN) as fresh:  # a new process: new connection, new graph
        snapshot = build(hooks, fresh).get_state(config)
        assert snapshot.values["stage"] == "COLLECTING_PARAMS" and snapshot.next == ("EXECUTING_SOP",)
        state = build(hooks, fresh).invoke(None, config)
    assert state["path"] == ["INGESTED", "TRIAGED", "COLLECTING_PARAMS", "EXECUTING_SOP", "RESOLVED"]
    assert (hooks.calls["triage"], hooks.calls["collect"], hooks.calls["execute_sop"]) == (1, 1, 2)


def test_diagnosis_takes_bounded_steps_and_answers(saver):
    steps = [{"thought": "check status", "action": "status_page", "observation": "VPN degraded"},
             {"thought": "check logs", "action": "read_logs", "observation": "cert expired"},
             {"thought": "explain", "outcome": "answer", "answer": "The VPN certificate expired; renew it."}]
    hooks = Hooks(triage=DIAGNOSTIC, steps=steps)
    state = build(hooks, saver, read_only_tools={"status_page", "read_logs"}).invoke(
        start("c9"), thread("t_us", "c9"))
    assert state["path"] == ["INGESTED", "TRIAGED", *["DELIBERATING"] * 3, "RESOLVED"]
    assert len(state["trajectory"]) == 3 and state["final_response"].startswith("The VPN")


def test_diagnosis_stops_at_the_step_ceiling(saver):
    hooks = Hooks(triage=DIAGNOSTIC, steps=[{"thought": "again"}] * 10)
    state = build(hooks, saver).invoke(start("c10"), thread("t_us", "c10"))
    assert (state["stage"], hooks.calls["react_step"]) == ("ESCALATED_HITL", MAX_STEPS)


def test_diagnosis_stops_after_two_critiques(saver):
    hooks = Hooks(triage=DIAGNOSTIC, steps=[{"thought": "wrong", "outcome": "critique"}] * 3)
    state = build(hooks, saver).invoke(start("c11"), thread("t_us", "c11"))
    assert (state["stage"], hooks.calls["react_step"]) == ("ESCALATED_HITL", 3)


def test_diagnosis_cannot_call_a_changing_tool_and_hands_off_to_an_sop(saver):
    blocked = build(Hooks(triage=DIAGNOSTIC, steps=[{"thought": "fix it", "action": "reset_vpn"}]), saver,
                    read_only_tools={"status_page"}).invoke(start("c12"), thread("t_us", "c12"))
    assert blocked["stage"] == "ESCALATED_HITL" and "read-only" in blocked["error"]
    hooks = Hooks(triage=DIAGNOSTIC, steps=[{"thought": "needs a reset", "outcome": "needs_sop",
                                             "sop_name": "reset_vpn", "parameters": {"site": "hq"}}])
    state = build(hooks, saver).invoke(start("c13"), thread("t_us", "c13"))
    assert state["path"][-3:] == ["DELIBERATING", "EXECUTING_SOP", "RESOLVED"]
    assert hooks.calls["execute_sop"] == 1


def test_illegal_transitions_are_refused(saver):
    assert not allowed(None, Stage.EXECUTING_SOP)
    assert not allowed("TRIAGED", Stage.RESOLVED)
    assert not allowed("ESCALATED_HITL", Stage.ESCALATED_HITL)
    graph, config = build(Hooks(), saver), thread("t_us", "c14")
    graph.invoke(start("c14"), config)
    graph.update_state(config, {"next_stage": "EXECUTING_SOP"}, as_node="RESOLVED")
    with pytest.raises(IllegalTransition, match="RESOLVED -> EXECUTING_SOP"):
        graph.invoke(None, config)


def test_events_that_do_not_fit_the_stage_change_nothing(saver):
    graph = build(Hooks(triage={"intent": "x", "acuity": 2, "confidence": 0.1}), saver)
    config = thread("t_us", "c15")
    escalated = graph.invoke(start("c15"), config)
    assert escalated["stage"] == "ESCALATED_HITL"
    after = graph.invoke({"event": {"type": "USER_MESSAGE", "text": "hello?"}}, config)
    assert after["stage"] == "ESCALATED_HITL" and after["path"] == escalated["path"]
    assert graph.invoke({"event": {"type": "APPROVAL_GRANTED"}}, thread("t_us", "c16")).get("stage") is None


def test_unknown_schema_versions_go_to_a_human_and_known_ones_migrate(saver, monkeypatch):
    graph, config = build(Hooks(), saver), thread("t_us", "c17")
    graph.invoke(start("c17"), config)
    graph.update_state(config, {"schema_version": 99})
    state = graph.invoke(start("c17"), config)
    assert state["stage"] == "ESCALATED_HITL" and "schema version 99" in state["error"]
    monkeypatch.setitem(thread_state.MIGRATIONS, 0, lambda s: {"approval_threshold": 500.0})
    config = thread("t_us", "c18")
    graph.invoke(start("c18"), config)
    graph.update_state(config, {"schema_version": 0})
    migrated = graph.invoke(start("c18"), config)
    got = (migrated["schema_version"], migrated["approval_threshold"], migrated["stage"])
    assert got == (1, 500.0, "RESOLVED")
