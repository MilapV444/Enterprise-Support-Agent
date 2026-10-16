"""System 1: the deterministic LangGraph statechart for one case (FR-1 / ADP-01; FR-18 / MS-ADP-04).

Every stage is a node. A node may only be entered through a transition listed in TRANSITIONS (the ADP-01 guard
table); any non-terminal stage may also trip to ESCALATED_HITL (ADP-04). Waiting stages end the run with the
state checkpointed; the next event (a customer message or an approval outcome) resumes it. A crashed run
resumes from its last checkpoint with graph.invoke(None, thread(...)).

The decisions inside the nodes are hooks, so the triage model (Jev), slot filling, SOP execution and the ReAct
step plug in later without changing the graph:

    triage(state) -> Triage-shaped dict           collect(state) -> {"parameters", "missing", "sop_name"?}
    execute_sop(state) -> {"response"} | {"error"}  react_step(state) -> Step-shaped dict
    revalidate(state) -> bool  (re-check the world before acting after a wait of more than an hour)
"""

import time
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph

from core.orchestrator.planner import after_step
from schemas.thread_state import Stage, Step, ThreadState, Triage, UnsupportedSchema, upgrade

S = Stage
TRANSITIONS = {
    None: {S.INGESTED},
    S.RESOLVED: {S.INGESTED},
    S.INGESTED: {S.TRIAGED},
    S.TRIAGED: {S.COLLECTING_PARAMS, S.DELIBERATING, S.AWAITING_CUSTOMER},
    S.COLLECTING_PARAMS: {S.EXECUTING_SOP, S.AWAITING_CUSTOMER},
    S.EXECUTING_SOP: {S.AWAITING_APPROVAL, S.RESOLVED},
    S.DELIBERATING: {S.DELIBERATING, S.EXECUTING_SOP, S.RESOLVED},
    S.AWAITING_APPROVAL: {S.EXECUTING_SOP, S.RESOLVED},
    S.AWAITING_CUSTOMER: {S.TRIAGED},
}
TERMINAL = {S.ESCALATED_HITL}
STALE_AFTER = 3600  # seconds of waiting after which the world is re-checked before acting (MS-D18)
DEFAULT_APPROVAL_THRESHOLD = 1000.0


class IllegalTransition(RuntimeError):
    pass


def allowed(source, target):
    source = S(source) if source else None
    if target is S.ESCALATED_HITL:
        return source not in TERMINAL
    return target in TRANSITIONS.get(source, set())


def thread(tenant_id, case_id):
    """LangGraph config for a case: one thread per (tenant, case)."""
    return {"configurable": {"thread_id": f"{tenant_id}:{case_id}"}}


@contextmanager
def postgres_checkpointer(dsn):
    with PostgresSaver.from_conn_string(dsn) as saver:
        saver.setup()
        yield saver


def build(hooks, checkpointer=None, read_only_tools=frozenset(), now=time.time):
    graph = StateGraph(ThreadState)

    def stage(target, work=lambda state: {}):
        def run(state):
            if not allowed(state.get("stage"), target):
                raise IllegalTransition(f"{state.get('stage')} -> {target.value}")
            return {"next_stage": None, **work(state), "stage": target.value, "path": [target.value]}
        graph.add_node(target.value, run)

    def resume(state):
        """Entry: upgrade the state, then pick where this event takes the case."""
        try:
            update = upgrade(state)
        except UnsupportedSchema as error:
            return {"error": str(error), "next_stage": S.ESCALATED_HITL.value}
        event, current = state.get("event") or {}, state.get("stage")
        kind = event.get("type")
        if kind == "USER_MESSAGE":
            update["messages"] = [{"role": "user", "content": event.get("text", "")}]
        if kind == "USER_MESSAGE" and current in (None, S.RESOLVED.value):
            return {**update, "next_stage": S.INGESTED.value}
        if kind == "USER_MESSAGE" and current == S.AWAITING_CUSTOMER.value:
            return {**update, "next_stage": S.TRIAGED.value}
        if kind == "APPROVAL_GRANTED" and current == S.AWAITING_APPROVAL.value:
            return {**update, "next_stage": S.EXECUTING_SOP.value}
        if kind == "APPROVAL_DENIED" and current == S.AWAITING_APPROVAL.value:
            return {**update, "next_stage": S.RESOLVED.value,
                    "final_response": "The request was not approved."}
        return {**update, "next_stage": None}  # nothing to do, e.g. a human owns the case

    def ingest(state):
        missing = [k for k in ("tenant_id", "case_id", "session_id") if not state.get(k)]
        if missing:
            return {"error": f"ingress is missing {', '.join(missing)}", "next_stage": S.ESCALATED_HITL.value}
        return {"error": None, "final_response": None, "next_stage": S.TRIAGED.value}

    def triage(state):
        result = Triage.model_validate(hooks["triage"](state))
        if result.acuity == 3 or result.missing_params:
            target = S.AWAITING_CUSTOMER
        elif result.confidence < 0.50:
            target = S.ESCALATED_HITL
        elif result.acuity <= 2 and result.confidence >= 0.90:
            target = S.COLLECTING_PARAMS
        elif result.acuity >= 4 and result.confidence >= 0.85:
            target = S.DELIBERATING
        else:
            target = S.AWAITING_CUSTOMER
        return {"triage": result.model_dump(), "sop_name": result.sop_name, "parameters": result.parameters,
                "next_stage": target.value}

    def collect(state):
        result = hooks["collect"](state)
        missing = list(result.get("missing", []))
        return {"parameters": result.get("parameters", {}), "missing": missing,
                "sop_name": result.get("sop_name", state.get("sop_name")),
                "next_stage": (S.AWAITING_CUSTOMER if missing else S.EXECUTING_SOP).value}

    def execute_sop(state):
        resumed = state.get("stage") == S.AWAITING_APPROVAL.value
        approved = resumed and (state.get("event") or {}).get("type") == "APPROVAL_GRANTED"
        waited = now() - (state.get("waiting_since") or now())
        if resumed and waited > STALE_AFTER and not hooks["revalidate"](state):
            return {"error": f"state changed during a {waited / 3600:.1f} h wait",
                    "next_stage": S.ESCALATED_HITL.value}
        amount = float((state.get("parameters") or {}).get("amount", 0) or 0)
        if amount >= state.get("approval_threshold", DEFAULT_APPROVAL_THRESHOLD) and not approved:
            return {"needs_approval": True, "next_stage": S.AWAITING_APPROVAL.value}
        result = hooks["execute_sop"](state)
        if result.get("error"):
            return {"error": result["error"], "next_stage": S.ESCALATED_HITL.value}
        return {"needs_approval": False, "final_response": result.get("response"),
                "next_stage": S.RESOLVED.value}

    def deliberate(state):
        episode = state if state.get("stage") == S.DELIBERATING.value else {
            **state, "iterations": 0, "reflexion_trials": 0}
        step = Step.model_validate(hooks["react_step"](episode))
        return {"iterations": 0, "reflexion_trials": 0, **after_step(episode, step, read_only_tools)}

    def wait(state):
        return {"waiting_since": now(), "next_stage": None}

    graph.add_node("resume", resume)
    stage(S.INGESTED, ingest)
    stage(S.TRIAGED, triage)
    stage(S.COLLECTING_PARAMS, collect)
    stage(S.EXECUTING_SOP, execute_sop)
    stage(S.DELIBERATING, deliberate)
    stage(S.AWAITING_APPROVAL, wait)
    stage(S.AWAITING_CUSTOMER, wait)
    stage(S.RESOLVED)
    stage(S.ESCALATED_HITL)

    targets = {s.value: s.value for s in S} | {END: END}
    graph.add_edge(START, "resume")
    for name in ["resume", *(s.value for s in S)]:
        graph.add_conditional_edges(name, lambda state: state.get("next_stage") or END, targets)
    return graph.compile(checkpointer=checkpointer)
