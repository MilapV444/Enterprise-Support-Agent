"""The turn loop: what happens to an accepted turn (M7-01; FR-1, FR-6, FR-9, FR-13, FR-30, FR-32, FR-40).

channels.api accepts a turn (202) and hands it to dispatch(); workflows.dispatch.TemporalDispatcher signals
the case's ticket workflow, which runs its turns one at a time as retried activities, and TurnLoop.run() takes
it from there. A retry applies nothing twice: a turn that already ended returns at once, the status is not
republished, and a statechart run the crash interrupted resumes at its pending stage:

1. a status event ("Looking into it");
2. input screening (safety.screening): a blocked message is answered at once and nothing else sees it;
3. PII tokens (safety.pii): from here on only tokenized text reaches Jev, the models or the case state;
4. the statechart (core.orchestrator) on the case's thread, with Jev triage, or the LLM classifier when Jev is
   not configured (its confidence is capped below what an SOP needs);
5. the answer: retrieval once per turn (knowledge.retrieval, the public collection for an anonymous customer,
   plus the tenant's own once signed in: customer_visible passages and the internal runbooks, which are read
   but never cited), then the specialists (agents.topology): Jev picks a lead and any co-specialists, each
   may first read one of the customer's own records (its read-only tools.nimbus tools, at the turn's tier,
   through the audited executor; the output is tokenized and is evidence too), reads the passages for its
   domain and returns typed claims, and agents.merge checks them and has the
   coordinator draft the one reply through the model router (cost.router, free tiers first) behind the
   output checks (safety.output). Without Jev the generalist answers alone, with every tool. No claim means
   the documentation
   does not cover it, and the case goes to a person. A clarifying question when the case waits for the
   customer; a hand-off notice when it goes to a person;
6. citation events for the customer_visible passages the accepted claims cite, then one final event with the
   AI disclosure, and a decision record with its why view (safety.governance) and the steps the turn took,
   which channels.api.trace shows the customer as a tier-filtered "how this was answered" view.

Any failure publishes an error event: a customer never waits on silence. The case is the conversation for
now (case linking is not wired); procedures (SOPs) have no tools yet, so a procedure turn answers from the
knowledge base and changes nothing. See the open-issues register.
"""

import json
import logging
import re
import uuid
from dataclasses import dataclass

import psycopg

from agents.merge import COMPLETED, Claim, Outcome, claims_from, human, merge
from agents.topology import (
    MAX_FINDINGS,
    STEPS_PER_SPECIALIST,
    Role,
    Specialist,
    coordinator,
    executor_tool,
    registry,
    specialist_graph,
)
from channels.api import turns as turn_events
from channels.identity.tiers import Tier
from core.context.assembler import delimit
from core.orchestrator.decisions import JevUnavailable, Masked, mask
from core.orchestrator.statechart import build, thread
from core.orchestrator.triage import llm_fallback, triage_hook
from data.events import EventLog
from runtime import tickets
from safety.governance.disclosure import disclose
from safety.output.checks import finalise
from safety.screening.pipeline import SPOTLIGHT_RULE
from tools.registry import Registry

log = logging.getLogger(__name__)

SYSTEM = ("You are the customer support assistant. Answer only from the knowledge given (passages or "
          "specialist findings); if it does not answer the question, say so plainly and offer to bring in a "
          "person. Be direct and concrete, and never promise refunds, credits or changes. " + SPOTLIGHT_RULE)
ENDS_A_TURN = {"final", "handoff", "error"}  # the event types a turn ends with
BLOCKED = "Your message was stopped by our safety checks. A person can help if you need it."
HANDOFF = "A specialist will take it from here. You can keep writing here in the meantime."
FAILED = ("Something went wrong on our side while answering. A person will follow up, or try again in a "
          "moment.")
PROCEDURE = ("No change has been made to your account: describe what the customer can do themselves, and say "
             "a person will carry out anything that needs an account change.")
NO_EVIDENCE = "Our documentation does not cover this, so a specialist will look at it with you."
EVIDENCE = 5                       # passages the specialists read
MAX_CLAIMS = 8
CUSTOMER = ("customer_visible",)   # a customer's answer cites only these chunks (S18)
UNCITED = ("runbooks",)            # also read for a customer's answer, never cited: the internal runbooks
TEAM = {  # what Jev reads to pick the lead (no digits: the Jev rule)
    Role.GENERALIST: "General product questions and how-to guidance that fit no other specialist",
    Role.BILLING: "Invoices, charges, payments, refunds, credits, plan pricing and service level credits",
    Role.TECHNICAL: ("Outages, errors and failing services: networking and VPN, databases, containers, APIs, "
                     "webhooks, infrastructure as code and point of sale terminals"),
    Role.ACCOUNT_OPS: ("Sign-in, passwords, multi-factor authentication, single sign-on, identity "
                       "verification, users and roles, subscriptions and data privacy"),
}
TOOLS = {  # each specialist's read-only tools (tools.nimbus, W41); without Jev the generalist has all
    Role.GENERALIST: ("nimbus_status.service_status",),
    Role.BILLING: ("nimbus_account.my_invoices", "nimbus_support.my_subscriptions"),
    Role.TECHNICAL: ("nimbus_status.service_status", "nimbus_support.my_tickets"),
    Role.ACCOUNT_OPS: ("nimbus_account.my_account", "nimbus_support.my_subscriptions"),
}
# B26: the team that owns a restricted article (its acl_groups) and its hitl.queues queue
TEAMS = {"billing-team": ("billing", "queue_billing"), "security-team": ("security", "queue_account")}
DEFAULT_TEAM = ("support", "queue_senior")
FINDINGS = """You are the {role} specialist of the support team ({about}).
From the knowledge passages and customer records above, list the facts and steps that answer the customer's
message within your domain. Passages labelled internal are staff runbooks: keep only what the customer can do
or should know, never internal tools, teams, document names or steps only staff can perform. Reply with JSON
only, at most eight items:
[{{"topic": "short_snake_case name unique to this item", "text": "one fact or step, with its exact commands",
"evidence": ["<passage or record id>"]}}]
Add "value" (a number) and "unit" only when the fact is a quantity. Reply [] when nothing in the passages
or records answers it."""
TOOL_STEP = """Before answering you may read one of the customer's own records, if it would help:
{tools}
To read one, reply with JSON only: {{"action": "<record id>"}}. Otherwise reply with the findings as asked."""
DRAFT = ("Answer the customer from the specialist findings only. Do not tell them to contact another team, "
         "department, person or specialist, and do not end with offers of further help: if a person is "
         "needed, the conversation is handed over without being asked.")
# internal trace only (the customer view shows none of these): what agents.merge's redirect check saw
REDIRECT_TRACE = ("redirect", "redirect_confidence", "redrafted", "rejected_draft")
# B25: one redraft, then a person
REDRAFT = ("Your previous draft pointed the customer to another team or person. Rewrite it with only the "
           "facts and steps from the findings that the customer can use themselves.")
FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


class NoDraft(RuntimeError):
    """The coordinator's draft did not pass the router (no model answered, or the checks held it twice)."""


class Remasked:
    """The decision engine behind decisions.mask(): its personal-data guard reads dates and long numbers as
    phone numbers, which the token vault leaves alone, so text is masked its way before Jev is asked."""

    def __init__(self, engine):
        self.engine = engine

    def ask(self, state, questions):
        return self.engine.ask({k: mask(v.text) if isinstance(v, Masked) else v for k, v in state.items()},
                               questions)


def findings(text, ids):
    """A specialist's reply as the findings JSON agents.merge reads, or None: at most eight valid claims, each
    with its own topic, citing only passages it was given."""
    try:
        items = json.loads(FENCE.sub("", (text or "").strip()))
        claims = [Claim(**item) for item in items] if isinstance(items, list) else None
    except (TypeError, ValueError):  # pydantic's ValidationError is a ValueError
        return None
    if claims is None or len(claims) > MAX_CLAIMS or len({c.topic for c in claims}) != len(claims) \
            or any(set(c.evidence) - ids for c in claims):
        return None
    text = json.dumps(items)
    return text if len(text) <= MAX_FINDINGS else None


def chosen(text, offered):
    """The record a specialist asked to read ({"action": id} naming one it was offered), or None."""
    try:
        move = json.loads(FENCE.sub("", (text or "").strip()))
    except ValueError:
        return None
    return move["action"] if isinstance(move, dict) and move.get("action") in offered else None


def passages(sections):
    """The passages as a model reads them; a passage's label is its id, which claims cite."""
    def label(section):
        return f"{'knowledge' if section.audience in CUSTOMER else 'internal knowledge'} {section.parent_id}"
    return "\n\n".join(delimit(f"{s.title}\n{s.text}", label(s)) for s in sections) \
        or "(no knowledge passage matched)"


class NoJev:
    """Jev is not configured: every decision fails safe (triage falls back to the LLM classifier)."""

    def evaluate(self, state, questions):
        raise JevUnavailable("no Jev API key configured")


@dataclass
class Services:
    engine: object                 # core.orchestrator.decisions.DecisionEngine
    router: object                 # cost.router.Router
    retriever: object              # knowledge.retrieval.pipeline.Retriever
    screener: object               # safety.screening.pipeline.Screener
    tokens: object                 # safety.pii.tokens.Tokenizer
    complete: object               # prompt -> text, a small model (triage fallback)
    connect: object                # () -> autocommit psycopg connection to the main database
    store: object                  # core.orchestrator.case_state store (PostgresStore; MemoryStore in tests)
    decisions: object = None       # safety.governance.records.DecisionLog
    executor: object = None        # tools.execution.Executor over `tools`, audited; None: no tools
    tools: object = None           # the frozen tool registry (tools.nimbus.catalog)


class TurnLoop:
    def __init__(self, services):
        self.s = services
        self.evidence = {}             # (tenant, conversation) -> sections this turn's answer cites
        self.passages = {}             # (tenant, conversation) -> sections the specialists read this turn
        self.steps = {}                # (tenant, conversation) -> retrieval and answer steps, for the trace
        self.turns = {}                # (tenant, conversation) -> this turn's session, principal, tier, id
        self.records = {}              # (tenant, conversation) -> {tool id: masked output} read this turn
        self.restricted = {}           # (tenant, conversation) -> this turn's RestrictedMatch (B26), if any
        self.cards = {}                # (tenant, conversation) -> this turn's action card (a ticket proposal)
        self.decide = Remasked(services.engine)
        tooled = services.executor is not None and services.tools is not None
        self.catalog = services.tools if tooled else Registry().freeze()
        self.team = registry([Specialist(role, about, self.allowed(TOOLS[role]), self.specialist(role))
                              for role, about in TEAM.items()], self.catalog)
        # runs inside a statechart stage, saved with the case; each turn passes its run_tool in the config
        # (consult)
        self.coordinator = coordinator(self.decide, self.team, run_tool=None)
        everything = self.allowed(self.catalog.tools)
        self.generalist = specialist_graph(Specialist(Role.GENERALIST, "every topic", everything,
                                                      self.specialist(Role.GENERALIST, "every topic")), None)
        triage = self.triage(triage_hook(services.engine, llm_fallback(services.complete)))
        self.graph = build({"triage": triage,
                            "collect": self.collect,
                            "execute_sop": self.procedure, "react_step": self.diagnose,
                            "revalidate": lambda state: True}, store=services.store)

    # Publishing --------------------------------------------------------------------------------------------

    def publish(self, turn, event_type, data):
        with self.s.connect() as conn:
            turn_events.publish(EventLog(conn), turn.tenant_id, turn.conversation_id, event_type,
                                {"turn_id": turn.turn_id, **data})

    def published(self, turn):
        """(type, data) of the events this turn has published so far."""
        # ponytail: reads the whole conversation's log; filter by turn in SQL if conversations grow long
        with self.s.connect() as conn:
            rows = turn_events.events_after(conn, turn.tenant_id, turn.conversation_id, 0)
        return [(kind, data) for _, kind, data in rows if data.get("turn_id") == turn.turn_id]

    def record(self, turn, decision, reason, checks, trace):
        if self.s.decisions is None:
            return
        try:
            self.s.decisions.record(turn.tenant_id, turn.conversation_id, decision, reason, checks, trace,
                                    turn_id=turn.turn_id)
        except Exception:  # noqa: BLE001 - a missing audit row must not cost the customer their reply
            log.exception("decision record failed for turn %s", turn.turn_id)

    # The answer --------------------------------------------------------------------------------------------

    def check(self, draft):
        return finalise(draft, lambda instruction: draft, system_prompt=SYSTEM)

    def customer_query(self, messages):
        texts = [m.get("content", "") for m in messages if m.get("role") == "user"]
        return " ".join(texts[-4:]) or (messages[-1]["content"] if messages else "")

    def retrieve(self, state, query):
        """This turn's passages: customer_visible ones plus the internal runbooks, which are never cited."""
        key, failed = (state["tenant_id"], state["case_id"]), False
        tier = (state.get("event") or {}).get("tier", "T0_ANON")
        try:
            result = self.s.retriever.retrieve(tier, state["tenant_id"], state["messages"][:-1], query,
                                               audiences=CUSTOMER, sources=UNCITED)
            sections, query = result.sections[:EVIDENCE], result.query.text
        except Exception:  # noqa: BLE001 - the embedder or index is down: no passages, so no claims
            log.warning("retrieval failed; the specialists read no knowledge passages", exc_info=True)
            sections, failed = [], True
        self.passages[key] = sections
        self.steps.setdefault(key, {})["retrieval"] = {
            "query": query, "failed": failed, "collections": sorted({s.collection for s in sections}),
            "sources": [], "internal": sum(s.audience not in CUSTOMER for s in sections)}
        return sections

    def allowed(self, tool_ids):
        return frozenset(t for t in tool_ids if t in self.catalog.tools)

    def offered(self, key, tools):
        """What a specialist may read this turn: its own tools, at the turn's tier, with a live session."""
        turn = self.turns.get(key) or {}
        if not turn.get("session_id"):
            return []
        tier = Tier[turn["tier"]]
        return sorted(t for t in tools if tier >= self.catalog.tools[t].min_tier)

    def tool_runner(self, key):
        """run_tool for this turn's specialists: the audited executor, its output tokenized (safety.pii)
        before any model reads it and kept as evidence for agents.merge."""
        if self.s.executor is None:
            return None
        run = executor_tool(self.s.executor)

        def masked_run(request):
            text = self.s.tokens.mask(run(request))[0]
            self.records.setdefault(key, {})[request.tool_id] = text
            self.steps.setdefault(key, {}).setdefault("tools", []).append(
                {"role": request.role, "tool": request.tool_id})
            return text
        return masked_run

    def specialist(self, role, about=None):
        """A specialist's step (agents.topology act): on its first step it may ask to read one of the
        customer's records (a tool it is offered); then it reads this turn's passages and what it read, and
        reports typed claims; [] when none of them answers it, or when no model gave valid findings."""
        def act(brief, history):
            key = (brief["tenant_id"], brief["case_id"])
            sections = self.passages.get(key, [])
            read = [h["action"] for h in history if "ok" in (h.get("observation") or {})]
            records = "".join(f"\n\n{self.records[key][t]}" for t in read)
            tools = self.catalog.tools if about else self.team[role].tools  # about: the generalist alone
            offered = [] if history else self.offered(key, tools)
            upstream = brief.get("upstream")
            lead = delimit(upstream["findings"], f"{upstream['role']} findings") + "\n" if upstream else ""
            choice = ("\n" + TOOL_STEP.format(tools="\n".join(f"- {t}: {self.catalog.tools[t].description}"
                                                               for t in offered))) if offered else ""
            task = FINDINGS.format(role=role.value.replace("_", " "), about=about or TEAM[role])
            prompt = (f"{passages(sections)}{records}\n\n{delimit(brief['objective'], 'customer message')}\n"
                      f"{lead}{task}{choice}")
            ids = {s.parent_id for s in sections} | set(read)
            reply = self.s.router.answer([{"role": "system", "content": SPOTLIGHT_RULE},
                                          {"role": "user", "content": prompt}],
                                         self.decide, {"message": Masked(brief["objective"])},
                                         verify=lambda text: findings(text, ids) is not None
                                         or chosen(text, offered) is not None)
            action = chosen(reply.text, offered) if reply.outcome == "answered" else None
            if action:
                return {"thought": f"read {action}", "action": action, "action_input": {}}
            found = (reply.outcome == "answered" and findings(reply.text, ids)) or "[]"
            claims = json.loads(found)
            self.steps.setdefault(key, {}).setdefault("specialists", []).append(
                {"role": role.value, "outcome": reply.outcome, "claims": len(claims)})
            return {"thought": f"read the passages as the {role.value} specialist", "findings": found,
                    "evidence": sorted({e for claim in claims for e in claim["evidence"]})}
        return act

    def draft(self, state, instruction):
        """agents.merge's draft(claims): the coordinator, the only author of customer text, writes one
        reply."""
        key, messages = (state["tenant_id"], state["case_id"]), state["messages"]

        def write(claims):
            facts = "\n".join(f"- {claim.text}" for claim in claims)
            conversation = "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}"
                                     for m in messages[-8:])
            content = (f"{delimit(facts, 'specialist findings')}\n\n{delimit(conversation, 'conversation')}\n"
                       f"{instruction}{DRAFT}")
            reply = self.s.router.answer(
                [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}],
                self.decide, {"message": Masked(self.customer_query(messages))},
                verify=lambda text: self.check(text).verdict == "deliver")
            self.steps.setdefault(key, {})["answer"] = {"outcome": reply.outcome, "retried": reply.cascaded}
            if reply.outcome != "answered":
                raise NoDraft(f"NO_DRAFT_{reply.outcome.upper()}")
            return reply.text
        return write

    # Staff-only answers (register B26) -------------------------------------------------------------------

    def probe_restricted(self, turn, masked):
        """Before triage: does the message's best match sit in a restricted article the customer cannot see?
        Only its id and groups are read; a probe that fails is no match."""
        key = (turn.tenant_id, turn.conversation_id)
        try:
            match = self.s.retriever.restricted_match(turn.assurance_tier, turn.tenant_id, masked,
                                                      audiences=CUSTOMER, sources=UNCITED)
        except Exception:  # noqa: BLE001 - the probe is a router, not a gate: no match, answer as usual
            log.warning("restricted-match probe failed", exc_info=True)
            match = None
        if match is not None:
            team, queue = TEAMS.get(next(iter(match.groups), ""), DEFAULT_TEAM)
            self.restricted[key] = (match, team, queue)
            self.steps.setdefault(key, {})["restricted"] = {"doc_id": match.doc_id, "team": team,
                                                            "queue": queue, "score": match.score,
                                                            "margin": match.margin}

    def triage(self, hook):
        """Triage, except that more detail cannot open a staff-only article: no clarifying question then."""
        def run(state):
            result = hook(state)
            if (state["tenant_id"], state["case_id"]) in self.restricted:
                result = {**result, "missing_params": False}
            return result
        return run

    def consult(self, state, instruction=""):
        """Retrieval, the specialists and the merge: (reply text, "answered"), or (None, why a person takes
        it: NOTHING_TO_SAY when no passage answers it, RESTRICTED_ANSWER when the answer is staff-only, or an
        agents.merge / delegation code)."""
        key, query = (state["tenant_id"], state["case_id"]), self.customer_query(state["messages"])
        if key in self.restricted:
            self.steps.setdefault(key, {})["answer"] = {"outcome": "RESTRICTED_ANSWER", "retried": False}
            return None, "RESTRICTED_ANSWER"
        sections, draft = self.retrieve(state, query), self.draft(state, instruction)
        evidence = {s.parent_id: f"{s.title}\n{s.text}" for s in sections}
        who = self.turns.get(key) or {}
        brief = {"tenant_id": key[0], "case_id": key[1], "turn_id": who.get("turn_id") or str(uuid.uuid4()),
                 # no session (a turn from before AGENT-02): offered() offers no tool, so it is never used
                 "session_id": who.get("session_id") or "none",
                 "principal_id": who.get("principal_id") or state["session_id"]}
        config = {"configurable": {"run_tool": self.tool_runner(key)}}
        try:
            if isinstance(getattr(self.s.engine, "jev", None), NoJev):
                outcome = self.alone(brief, query, draft, config)
            else:
                turn = self.coordinator({**brief, "message": query}, config)
                if turn["plan"]["handoff"]:
                    outcome = human("NO_DELEGATION")
                elif self.unanswered(key, turn["plan"]["lead"]):
                    outcome = human("LEAD_UNAVAILABLE")
                else:
                    outcome = merge(self.decide, turn["results"], {**evidence, **self.records.get(key, {})},
                                    draft, redraft=self.draft(state, instruction + REDRAFT + "\n"))
        except NoDraft as error:
            outcome = human(str(error))
        used = {e for claim in outcome.accepted for e in claim.evidence}
        self.evidence[key] = [s for s in sections if s.parent_id in used and s.audience in CUSTOMER]
        steps = self.steps.setdefault(key, {})
        steps["retrieval"]["sources"] = [{"doc_id": s.doc_id, "title": s.title} for s in self.evidence[key]]
        answer = steps.setdefault("answer", {"retried": False})
        answer["outcome"] = "answered" if outcome.kind == "reply" else outcome.reason
        answer.update({k: outcome.detail[k] for k in REDIRECT_TRACE if k in outcome.detail})
        return (outcome.text, "answered") if outcome.kind == "reply" else (None, outcome.reason)

    def unanswered(self, key, role):
        """The lead specialist got no model answer (degraded or escalated, register B23): its domain was not
        read, so a reply from the others alone would mislead."""
        return any(s["role"] == role and s["outcome"] != "answered"
                   for s in self.steps.get(key, {}).get("specialists", []))

    def alone(self, brief, query, draft, config):
        """Without Jev nothing delegates or adjudicates: the generalist reads for every domain, with every
        tool; agents.merge's code-only check still applies (topics are unique per specialist: nothing to
        adjudicate)."""
        done = self.generalist({"brief": {**brief, "role": Role.GENERALIST.value, "objective": query,
                                          "steps": STEPS_PER_SPECIALIST}, "history": []}, config)
        if self.unanswered((brief["tenant_id"], brief["case_id"]), Role.GENERALIST.value):
            return human("LEAD_UNAVAILABLE")
        claims = tuple(claims_from(done["result"]))
        if not claims:
            return human("NOTHING_TO_SAY")
        text = draft(claims)
        if COMPLETED.search(text):
            return human("UNVERIFIED_COMPLETION")
        return Outcome("reply", text, accepted=claims)

    def diagnose(self, state):
        text, why = self.consult(state)
        return {"thought": f"the specialists' answer ({why})", "outcome": "answer", "answer": text}

    def collect(self, state):
        """COLLECTING_PARAMS (FR-45): a request for the billing team to act on one of the customer's own
        charges collects a ticket's details (runtime.tickets); anything else has nothing to collect, and the
        procedure answers from the documentation."""
        key = (state["tenant_id"], state["case_id"])
        texts = [m.get("content", "") for m in state.get("messages") or [] if m.get("role") == "user"]
        wanted, category = tickets.wants(self.decide, "\n".join(texts[-4:]))
        if not wanted:
            return {"parameters": {}, "missing": []}
        who = self.turns.get(key) or {}
        if Tier[who.get("tier") or "T0_ANON"] < Tier.T1_VERIFIED:
            return {"parameters": {"ticket": {"sign_in": True}}, "missing": [], "sop_name": "ticket"}
        invoice = tickets.latest_invoice(texts)
        owned = tickets.own_invoice(self.s.connect, key[0], who["principal_id"], invoice) if invoice else None
        ticket = {"category": category, "invoice": invoice, "reason": texts[-1] if texts else ""}
        if owned is None:
            return {"parameters": {"ticket": ticket}, "missing": ["own_invoice" if invoice else "invoice"],
                    "sop_name": "ticket"}
        stated = tickets.amount_cents(texts)
        return {"parameters": {"ticket": {**ticket, "amount_cents": owned if stated is None else stated}},
                "missing": [], "sop_name": "ticket"}

    def propose_ticket(self, state, ticket):
        """The ticket proposal and its card (a guest's card asks to sign in first); nothing is raised here."""
        key = (state["tenant_id"], state["case_id"])
        if ticket.get("sign_in"):
            self.cards[key] = tickets.SIGN_IN_CARD
            return {"response": tickets.SIGN_IN}
        proposal = tickets.propose(self.s.connect, state, self.turns[key], ticket)
        self.cards[key] = tickets.proposal_card(proposal)
        self.steps.setdefault(key, {})["ticket"] = {"proposal": proposal.number,
                                                    "category": proposal.category}
        return {"response": tickets.proposal_reply(proposal)}

    def procedure(self, state):
        ticket = (state.get("parameters") or {}).get("ticket")
        if ticket:
            return self.propose_ticket(state, ticket)
        text, why = self.consult(state, PROCEDURE + "\n")
        return {"response": text} if text else {"error": f"no answer for the procedure ({why})"}

    def clarifying_question(self, state, masked):
        thread = "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}"
                           for m in (state.get("messages") or [])[-8:]) or masked
        reply = self.s.router.answer(
            [{"role": "system", "content": SYSTEM},
             {"role": "user", "content": f"{delimit(thread, 'conversation')}\nAsk the customer one short, "
                                         "calm question that is not already answered in the conversation. "
                                         "Do not guess a diagnosis."}],
            self.decide, {"message": Masked(masked)},
            verify=lambda text: self.check(text).verdict == "deliver")
        return reply.text if reply.outcome == "answered" else None

    # One turn ----------------------------------------------------------------------------------------------

    def run(self, turn):
        """Answer one accepted turn (channels.api.envelope.InboundTurn); always ends with a final, handoff or
        error event."""
        key = (turn.tenant_id, turn.conversation_id)
        self.evidence[key], self.passages[key], self.steps[key] = [], [], {}
        self.turns[key] = {"session_id": turn.session_id, "principal_id": turn.principal_id,
                           "tier": turn.assurance_tier, "turn_id": turn.turn_id}
        try:
            done = self.published(turn)
            if any(kind in ENDS_A_TURN for kind, _ in done):  # a retry of a turn that was already answered
                return "already_answered"
            if not any(kind == "status" and data.get("state") == "working" for kind, data in done):
                self.publish(turn, "status", {"state": "working", "text": "Looking into it"})
            verdict = self.s.screener.screen("user_message", turn.content)
            steps = {"screening": verdict.band}
            if verdict.band == "block":
                self.record(turn, "block", "Your message was stopped by our safety checks.",
                            ["Content safety"],
                            {"screening": {"score": verdict.score, "categories": verdict.categories},
                             "steps": steps})
                self.publish(turn, "final", disclose({"role": "assistant", "text": BLOCKED}))
                return "blocked"
            masked, found = self.s.tokens.mask(turn.content)
            self.probe_restricted(turn, masked)
            config = thread(turn.tenant_id, turn.conversation_id)
            saved = self.graph.get_state(config)
            if (saved.get("event") or {}).get("id") == turn.turn_id:  # a retry: the event is applied once
                seen = saved["event"].get("seen", 0)
                state = self.graph.invoke(None, config) if saved.get("pending") else saved
            else:
                seen = len(saved.get("path") or [])  # path spans the whole case
                state = self.graph.invoke(
                    {"tenant_id": turn.tenant_id, "case_id": turn.conversation_id,
                     # the statechart only checks one is there; tools take the live one from self.turns (B22)
                     "session_id": turn.session_id or turn.principal_id,
                     "event": {"type": "USER_MESSAGE", "text": masked, "tier": turn.assurance_tier,
                               "id": turn.turn_id, "seen": seen}}, config)
            triage = state.get("triage") or {}
            steps.update(self.steps.get(key, {}), masked=bool(found), stages=(state.get("path") or [])[seen:],
                         intent=triage.get("intent"),
                         classifier=str(triage.get("rationale") or "").split(":", 1)[0] or None)
            trace = {"triage": state.get("triage"), "path": state.get("path"), "steps": steps}
            if state.get("stage") == "RESOLVED" and state.get("final_response"):
                checked = self.check(state["final_response"])
                steps["review"] = checked.verdict
                for section in self.evidence.get(key, []):
                    self.publish(turn, "citation", {"doc_id": section.doc_id, "title": section.title,
                                                    "heading": section.heading,
                                                    "excerpt": section.text[:600]})
                if key in self.cards:  # before the final event: a retried turn that ended republishes nothing
                    self.publish(turn, "action_card", self.cards[key])
                why = ("We offered to raise a ticket." if key in self.cards
                       else "We answered from our documentation.")
                self.record(turn, "answer", why, ["Content safety"], trace)
                self.publish(turn, "final", disclose({"role": "assistant", "text": checked.text}))
                return "answered"
            if state.get("stage") == "AWAITING_CUSTOMER":
                collected = "COLLECTING_PARAMS" in steps["stages"] and state.get("missing")
                question = (tickets.missing_question(state["missing"]) if collected
                            else self.clarifying_question(state, masked))
                if question:
                    self.record(turn, "ask_customer", "We need one more detail before we can help.",
                                ["Content safety"], trace)
                    self.publish(turn, "final", disclose({"role": "assistant", "text": question}))
                    return "asked"
            uncovered = steps.get("answer", {}).get("outcome") == "NOTHING_TO_SAY"
            reason = NO_EVIDENCE if uncovered else "A specialist will look at this with you."
            notice = HANDOFF
            if key in self.restricted:  # ponytail: queue only in the trace until hand-offs reach queues (W11)
                reason = f"This is handled by our {self.restricted[key][1]} team."
                notice = f"{reason} {HANDOFF}"
            self.record(turn, "escalate", reason, [], trace)
            self.publish(turn, "handoff", {"text": notice})
            return "handed_off"
        except Exception:  # noqa: BLE001 - the customer gets an answer whatever broke
            log.exception("turn %s failed", turn.turn_id)
            try:
                self.publish(turn, "error", {"text": FAILED})
            except Exception:  # noqa: BLE001 - the event log itself is down: nothing more to tell anyone
                log.exception("could not publish the error for turn %s", turn.turn_id)
            return "failed"
        finally:
            for per_turn in (self.evidence, self.passages, self.steps, self.turns, self.records,
                             self.restricted, self.cards):
                per_turn.pop(key, None)


def connector(dsn):
    def connect():
        return psycopg.connect(dsn, autocommit=True)
    return connect
