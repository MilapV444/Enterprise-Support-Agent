"""M3-03: framework scenario 7, the multi-specialist audit, end to end (AC-7).

"We need an audit report comparing our EU database uptime for Q2 against our SLA contract, and any credited
service adjustments applied." The coordinator (M3-01) delegates with Jev: technical leads and billing joins in
parallel (the generalist only ever leads, so the SLA target arrives with the technical findings); each reads
its own tools through run_tool and returns typed claims; the merge (M3-03) checks numbers in code and
conflicts with Jev, and the coordinator sends one reply. Jev, the tools and the drafting model are scripted
in process; LangGraph's scheduling and checkpointing are real.
"""

import json

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel

from agents.merge import merge
from agents.topology import Role, Specialist, coordinator, registry, start_turn
from core.orchestrator.decisions import Answer, DecisionEngine, Masked
from core.orchestrator.statechart import thread
from tools.registry import Registry
from tools.schemas import arg

AUDIT = ("We need an audit report comparing our EU database uptime for Q2 against our SLA contract, and any "
         "credited service adjustments applied.")
TURN = {"tenant_id": "t_us", "case_id": "case-audit", "session_id": "s-auditor", "principal_id": "auditor"}
OUTPUTS = {"ops.uptime": "EU clusters, Q2: uptime 99.98 percent (13 minutes of downtime)",
           "billing.credit_memos": "Q2 credit memos: CM-7, 1,200.00 USD, for the April 9 incident",
           "kb.search": "Signed SLA: 99.9 percent monthly uptime for EU database clusters"}


class Query(BaseModel):
    q: str = arg(sensitive=True)


def tools():
    reg = Registry()
    for tool_id in OUTPUTS:
        reg.tool(tool_id, args=Query, description="An audit source", risk="read_only",
                 stages={"DELIBERATING"}, author="ana", reviewed_by="ben")(lambda a: {})
    return reg.freeze()


class Jev:
    def __init__(self, redirect=0.05):
        self.redirect, self.questions = redirect, []

    def evaluate(self, state, questions):
        self.questions.append(sorted(questions))
        if "lead" in questions:  # delegation: technical leads, billing joins, nobody waits
            answers = {"lead": Answer("technical", 0.92)}
            for qid in questions:
                if qid != "lead":
                    joins = qid in ("needs_billing",)
                    answers[qid] = Answer(joins, 0.9)
            return answers
        if "redirect" in questions:
            return {"redirect": Answer(self.redirect >= 0.5, max(self.redirect, 1 - self.redirect))}
        return {qid: Answer(4.0, 0.9, 4) for qid in questions}


CLAIMS = {
    "technical": [{"topic": "eu_uptime_q2", "text": "EU database uptime in Q2 was 99.98 percent",
                   "value": "99.98", "unit": "percent", "evidence": ["ops.uptime"]},
                  {"topic": "sla_target", "text": "The SLA target is 99.9 percent", "value": "99.9",
                   "unit": "percent", "evidence": ["ops.uptime"]}],
    "billing": [{"topic": "credits_q2", "text": "One credit memo, CM-7, was applied in Q2",
                 "value": "1200.00", "unit": "USD", "evidence": ["billing.credit_memos"]}],
}


def specialist(role, tool, claims):
    def act(brief, history):
        if not history:
            return {"thought": "read the source", "action": tool, "action_input": {"q": brief["objective"]}}
        return {"thought": "report typed claims", "findings": json.dumps(claims), "evidence": [tool]}
    return act


def team(claims):
    tool_of = {"generalist": "kb.search", "billing": "billing.credit_memos", "technical": "ops.uptime",
               "account_ops": "kb.search"}
    return registry([Specialist(role, f"The {role.replace('_', ' ')} specialist", frozenset({tool_of[role]}),
                                specialist(role, tool_of[role], claims.get(role, [])))
                     for role in tool_of], tools())


class Sources:
    def __init__(self):
        self.calls = []

    def __call__(self, request):
        self.calls.append((request.role, request.tool_id))
        return OUTPUTS[request.tool_id]


def draft(claims):
    """The coordinator's one reply: a table of the accepted claims, in its own voice."""
    rows = "\n".join(f"| {c.topic} | {c.value} {c.unit} | {c.role} |" for c in claims)
    return ("I reviewed your EU database uptime and credits for Q2 with our technical and billing "
            "records.\n\n"
            f"| Item | Value | Source |\n|---|---|---|\n{rows}")


def episode(claims, jev=None):
    jev, sources, saver = jev or Jev(), Sources(), InMemorySaver()
    graph = coordinator(DecisionEngine(jev), team(claims), sources, saver)
    state = start_turn(graph, **TURN, message=Masked(AUDIT))
    outcome = merge(DecisionEngine(jev), state["results"], OUTPUTS, draft)
    return state, outcome, sources, saver


def test_scenario_7_the_specialists_run_in_parallel_and_the_customer_gets_one_merged_reply():
    state, outcome, sources, saver = episode(CLAIMS)
    assert state["plan"]["assignments"] == [{"role": "technical", "steps": 2, "after_lead": False},
                                            {"role": "billing", "steps": 2, "after_lead": False}]
    assert sorted(sources.calls) == [("billing", "billing.credit_memos"), ("technical", "ops.uptime")]
    assert outcome.kind == "reply" and outcome.text.count("| Item |") == 1           # one reply, one table
    assert "| eu_uptime_q2 | 99.98 percent | technical |" in outcome.text
    assert "| credits_q2 | 1200.00 USD | billing |" in outcome.text
    assert all(r["status"] == "completed" for r in state["results"])
    saved = saver.get_tuple(thread("t_us", "case-audit")).checkpoint["channel_values"]
    assert saved["outcome"] == "delegated" and len(saved["results"]) == 2


def test_scenario_7_a_numeric_disagreement_between_specialists_goes_to_a_person():
    billing = [*CLAIMS["billing"], {"topic": "eu_uptime_q2", "text": "Credits were computed on 99.90 percent",
                                    "value": "99.90", "unit": "percent",
                                    "evidence": ["billing.credit_memos"]}]
    jev = Jev()
    _, outcome, _, _ = episode({**CLAIMS, "billing": billing}, jev)
    assert (outcome.kind, outcome.text, outcome.reason) == ("human", None, "NUMERIC_DISCREPANCY")
    assert outcome.detail["values"]["eu_uptime_q2"] == {"technical": "99.98 percent",
                                                        "billing": "99.90 percent"}
    assert all("lead" in q for q in jev.questions)  # Jev delegated; it never saw the numbers to judge them


@pytest.mark.parametrize("redirect", [0.2, 0.95])
def test_scenario_7_a_reply_that_sends_the_auditor_to_another_team_is_held(redirect):
    _, outcome, _, _ = episode(CLAIMS, Jev(redirect=redirect))
    assert outcome.kind == "human" and outcome.reason == "REDIRECT"


def test_scenario_7_the_specialists_never_write_to_the_customer():
    state, outcome, _, _ = episode(CLAIMS)
    assert {r["role"] for r in state["results"]} == {Role.TECHNICAL.value, Role.BILLING.value}
    assert all("I reviewed" not in r["findings"] for r in state["results"])  # only the coordinator speaks
    assert outcome.text.startswith("I reviewed")
