"""M2-11: framework scenarios 3 and 4 end to end on the local compose stack (AC-3, AC-4).

A customer turn runs through the M1 and M2 components the way the dispatch hook will chain them:

    PII tokens (M1-13) -> statechart on the Postgres checkpointer (M1-04) with Jev triage (M1-06) -> an SOP
    that needs approval waits in AWAITING_APPROVAL -> action validation and a sealed approval request
    (M2-05) with its card (dry run or current state) -> the escalation packet in a skills queue (M2-09) ->
    a specialist signed in through SSO takes it, confirms every field and approves (M2-09) -> the case
    resumes, re-checks the world after a long wait (MS-D18) and the gate re-decides before the call runs
    once (M2-05) -> the reply passes the output checks, which allow a success claim only for an action the
    read-back confirmed (M1-14). A customer correction cancels the pending action first (M2-10).

Postgres is real; Jev, the slot filler, the ERP and the cloud API are scripted in process.

Two pieces of glue stand in for wiring not built yet (open-issues register): the statechart waits for
approval on amount only, so the ingress sets a high-risk SOP's threshold to zero; and Cedar has no
credential-reset action, so the reset is authorized as a production change of the instance's environment.
"""

import subprocess
import uuid
from pathlib import Path

import psycopg
import pytest
from pydantic import BaseModel

from channels import sessions
from channels.api.envelope import Principal
from channels.identity.oidc import MockIdP
from channels.identity.service import AGENT
from core.orchestrator.decisions import Answer, DecisionEngine, Masked
from core.orchestrator.statechart import build, postgres_checkpointer, thread
from core.orchestrator.triage import triage_hook
from data import events
from data.migrate import migrate, psql
from hitl import handoff, queues
from hitl.approval import CONSOLE_CLIENT, Desk, StaffCredential, Submission, staff_verifier
from hitl.handoff import Handoffs
from hitl.queues import Domain, Packet, Queues, Reason, Refused
from safety.authz.cedar import Authorizer, entity
from safety.output.checks import finalise
from safety.pii.tokens import Tokenizer
from tools.registry import Registry
from tools.schemas import arg
from tools.validation import approvals, masked, preview
from tools.validation.approvals import ApprovalGate, CallContext, NotApproved

ROOT = Path(__file__).resolve().parents[2]
DB = "test_e2e_actions"
DSN = f"postgresql://agent:change-me@127.0.0.1:5432/{DB}"  # credentials from .env.example
TENANT = "t_us"
IDP = MockIdP()
TOKENS = Tokenizer(b"e2e-actions")
HOUR = 3600

DISPUTE = ("Our auto-renew charged us $48,000 instead of our contracted $32,000 rate. I need an immediate "
           "$16,000 refund processed to our corporate Amex today.")
RESET = "I need to reset the root credentials on instance srv-alpha-12."
CORRECTION = ("Wait, stop! Do NOT reset srv-alpha-12, I read the ticket wrong, it's srv-bravo-99 in "
              "staging.")


class RefundArgs(BaseModel):
    invoice_id: str = arg(sensitive=True)
    amount: float = arg(sensitive=True, json_schema_extra={"financial": True})
    currency: str = arg(sensitive=True)


class InvoiceArgs(BaseModel):
    invoice_id: str = arg(sensitive=True)


class InstanceArgs(BaseModel):
    instance_id: str = arg(sensitive=True)
    environment: str = arg(sensitive=True)


class World:
    """The scripted ERP and cloud API, with a log of every call that changed something."""

    def __init__(self):
        self.invoices = {"INV-4471": {"invoice_id": "INV-4471", "charged": 48000.0, "refunded": 0.0}}
        self.contracts = {"INV-4471": {"contracted_rate": 32000.0, "term": "annual auto-renew"}}
        self.instances = {name: {"instance_id": name, "environment": env, "credentials_version": 7}
                          for name, env in (("srv-alpha-12", "production"), ("srv-bravo-99", "staging"))}
        self.changes, self.refunds_stick = [], True

    def refund(self, args):
        self.changes.append(("refund", args.invoice_id, args.amount))
        if self.refunds_stick:  # a write the ERP accepts but does not apply is caught by the read-back
            self.invoices[args.invoice_id]["refunded"] += args.amount
        return {"accepted": True}

    def reset(self, args):
        self.changes.append(("reset", args.instance_id))
        self.instances[args.instance_id]["credentials_version"] += 1
        return {"accepted": True}


def registry(world):
    reg = Registry()

    def tool(tool_id, args, description, risk, func):
        reg.tool(tool_id, args=args, description=description, risk=risk, stages={"EXECUTING_SOP"},
                 author="ana", reviewed_by="ben")(func)

    def refund_preview(a):
        before = dict(world.invoices[a.invoice_id])
        return before, {**before, "refunded": before["refunded"] + a.amount}
    tool("billing.get_invoice", InvoiceArgs, "Read an invoice", "read_only",
         lambda a: dict(world.invoices[a.invoice_id]))
    tool("billing.get_contract", InvoiceArgs, "Read the contract terms behind an invoice", "read_only",
         lambda a: dict(world.contracts[a.invoice_id]))
    tool("billing.refund", RefundArgs, "Refund an amount on an invoice", "low_risk_write", world.refund)
    tool("billing.refund_preview", RefundArgs, "Preview a refund", "read_only", refund_preview)
    tool("cloud.get_instance", InstanceArgs, "Read an instance", "read_only",
         lambda a: dict(world.instances[a.instance_id]))
    tool("cloud.reset_root_credentials", InstanceArgs, "Reset the root credentials of an instance",
         "high_risk_write", world.reset)
    return reg.freeze()


def account(parameters, who):
    return {"action": "update_contact", "type": "Account", "id": "acct-globex",
            "attrs": {"tenant_id": TENANT, "owner": entity("User", who)}}


def environment(parameters, who):
    return {"action": "restart_cluster", "type": "Environment", "id": parameters["instance_id"],
            "attrs": {"tenant_id": TENANT, "name": parameters["environment"]}}


SOPS = {  # sop name -> (tool, its arguments from the slot filler's parameters, Cedar resource)
    "billing_inquiry": ("billing.refund", lambda p: RefundArgs(**p), account),
    "password_reset": ("cloud.reset_root_credentials", lambda p: InstanceArgs(**p), environment),
}
SLOTS = {  # what the (scripted) slot filler reads from each message
    "auto-renew charged": ("billing_inquiry",
                           {"invoice_id": "INV-4471", "amount": 16000.0, "currency": "USD"}),
    "srv-bravo-99": ("password_reset", {"instance_id": "srv-bravo-99", "environment": "staging"}),
    "srv-alpha-12": ("password_reset", {"instance_id": "srv-alpha-12", "environment": "production"}),
}
TRIAGE = {"auto-renew charged": "BILLING_INQUIRY", "credentials": "PASSWORD_RESET",
          "srv-bravo-99": "PASSWORD_RESET"}


class Jev:
    def evaluate(self, state, questions):
        text = str(state)
        if "intent" in questions:
            intent = next(i for key, i in TRIAGE.items() if key in text)
            return {"intent": Answer(intent, 0.97), "severity": Answer(1.0, 0.95, 1),
                    "missing_details": Answer(False, 0.95)}
        if "acuity" in questions:
            return {"acuity": Answer(2.0, 0.9, 2)}
        if "correction" in questions:
            return {"correction": Answer("stop" in text.lower(), 0.95)}
        return {"verdict": Answer("ALLOW", 0.9), "serves": Answer(True, 0.95)}


CORRECTS = {"type": "noul", "instructions": "Does the customer withdraw or change the action that is waiting "
                                            "for approval?"}


def connect():
    return psycopg.connect(DSN, autocommit=True)


@pytest.fixture(scope="module")
def saver():
    subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env.example",
                    "up", "-d", "--wait", "postgres"], cwd=ROOT, check=True, capture_output=True)
    psql("postgres", f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
    psql("postgres", f'CREATE DATABASE "{DB}"')
    migrate("main", DB)
    for module in (sessions, events, approvals, queues, handoff):
        module.apply_schema(DB)
    psql(DB, f"INSERT INTO tenants (id, name, region) VALUES ('{TENANT}', 'Globex', 'US');"
             f"INSERT INTO tenant_settings (tenant_id) VALUES ('{TENANT}');"
             "INSERT INTO staff_directory (tenant_id, staff_id, roles, queues) VALUES "
             f"('{TENANT}', 'sam', '{{specialist}}', '{{queue_billing}}'),"
             f"('{TENANT}', 'sue', '{{senior_specialist}}', '{{queue_billing,queue_senior}}'),"
             f"('{TENANT}', 'tess', '{{specialist}}', '{{queue_technical}}')")
    with postgres_checkpointer(DSN) as checkpointer:
        yield checkpointer


def cred(user, item):
    return StaffCredential(TENANT, str(item), IDP.id_token(CONSOLE_CLIENT, TENANT, user, str(item)))


class Agent:
    """One customer's case, wired the way dispatch will wire it."""

    def __init__(self, saver, customer, roles=()):
        self.world, self.clock, self.replies = World(), [1_000_000.0], []
        self.tools = registry(self.world)
        self.engine = DecisionEngine(Jev())
        verify = staff_verifier(connect, IDP.issuer, IDP.public_key)
        self.gate = ApprovalGate(connect, self.engine, Authorizer(), verify)
        self.queues = Queues(connect, self.engine, TOKENS, verify, alert=lambda *a: None,
                             notify=lambda *a: None)
        self.desk, self.handoffs = Desk(connect, self.gate, verify), Handoffs(connect, self.queues, verify,
                                                                              alert=lambda *a: None)
        with connect() as conn:
            session = sessions.start(conn, TENANT, customer, "T2_SSO")
            self.conversation = f"conv-{uuid.uuid4().hex[:8]}"
            sessions.open_conversation(conn, TENANT, customer, session, self.conversation)
            self.case_id = sessions.link_case(conn, TENANT, self.conversation)
        self.customer, self.roles, self.pending, self.verified = customer, roles, None, []
        self.graph = build({"triage": triage_hook(self.engine), "collect": self.collect,
                            "execute_sop": self.execute, "revalidate": self.revalidate,
                            "react_step": lambda state: {"thought": "unused", "outcome": "critique"}},
                           checkpointer=saver, now=lambda: self.clock[0])

    # statechart hooks --------------------------------------------------------------------------------------

    def collect(self, state):
        sop, parameters = next(slot for key, slot in SLOTS.items() if key in state["messages"][-1]["content"])
        return {"sop_name": sop, "parameters": parameters, "missing": []}

    def call(self, state):
        tool_id, to_args, resource = SOPS[state["sop_name"]]
        ctx = CallContext(TENANT, self.case_id, self.conversation, self.customer, AGENT, self.roles,
                          resource(state["parameters"], self.customer))
        return ctx, self.tools.tools[tool_id], to_args(state["parameters"])

    def revalidate(self, state):
        """MS-D18: after a long wait, the target must still be what the approver saw on the card."""
        _, tool, args = self.call(state)
        return masked(self.current(tool, args), TOKENS) == self.pending["card"].get("current")

    def current(self, tool, args):
        """The target as it is now, for an action without a dry run (shown on the card, re-read later)."""
        if tool.tool_id == "cloud.reset_root_credentials":
            return self.tools.tools["cloud.get_instance"].func(args)
        return None

    def execute(self, state):
        ctx, tool, args = self.call(state)
        self.gate.execute(ctx, tool, args, {"message": Masked("approved action")}, self.pending["request_id"])
        self.verified = self.read_back(tool, args)
        return {"response": "done"}

    def read_back(self, tool, args):
        """The executed actions the target system confirms: only these may be claimed."""
        if tool.tool_id == "billing.refund":
            invoice = self.tools.tools["billing.get_invoice"].func(InvoiceArgs(invoice_id=args.invoice_id))
            return [{"type": "refund", "status": "executed"}] if invoice["refunded"] >= args.amount else []
        instance = self.world.instances[args.instance_id]
        return [{"type": "reset", "status": "executed"}] if instance["credentials_version"] > 7 else []

    # the turn ----------------------------------------------------------------------------------------------

    def invoke(self, event, **state):
        return self.graph.invoke({"tenant_id": TENANT, "case_id": self.case_id, "session_id": "s-1",
                                  "event": event, **state}, thread(TENANT, self.case_id))

    def say(self, draft, rewrite=None):
        """The reply after the output checks; a success claim needs a verified action."""
        check = finalise(draft, lambda instruction: rewrite or draft, verified_actions=self.verified)
        self.replies.append(check)
        return check

    def turn(self, text):
        masked_text, _ = TOKENS.mask(text)
        if self.pending and self.engine.ask({"message": Masked(masked_text)}, {"correction": CORRECTS})[
                "correction"].value:
            cancelled, _ = self.handoffs.cancel(Principal(tenant_id=TENANT, principal_id=self.customer),
                                                self.pending["escalation_id"])
            if cancelled:
                self.invoke({"type": "APPROVAL_DENIED"})
                self.pending = None
        state = self.invoke({"type": "USER_MESSAGE", "text": masked_text},
                            approval_threshold=0.0 if "credentials" in text or "srv-" in text else 1000.0)
        if state["stage"] == "AWAITING_APPROVAL":
            self.stage_approval(state, masked_text)
        return state

    def stage_approval(self, state, masked_text):
        ctx, tool, args = self.call(state)
        decision = self.gate.validate(ctx, tool, args, {"message": Masked(masked_text)})
        request_id = self.gate.request(ctx, tool, args, decision, ttl=queues.CANCEL_AFTER)
        dry_run = "billing.refund_preview" if tool.tool_id == "billing.refund" else None
        card = preview(self.tools, tool, args, decision, TOKENS, dry_run_id=dry_run,
                       read_current=lambda a: self.current(tool, a))
        evidence = []
        if tool.tool_id == "billing.refund":  # the contract comparison travels with the escalation
            invoice = InvoiceArgs(invoice_id=args.invoice_id)
            evidence = [str(self.tools.tools[t].func(invoice))
                        for t in ("billing.get_invoice", "billing.get_contract")]
        escalation_id = self.queues.escalate(Packet(
            tenant_id=TENANT, case_id=self.case_id, conversation_id=self.conversation,
            customer_id=self.customer,
            handler_id=AGENT, identity_tier="T2_SSO", channel="web", reason=Reason.ACTION_APPROVAL_REQUIRED,
            domain=Domain.BILLING if tool.tool_id == "billing.refund" else Domain.TECHNICAL,
            summary=masked_text, last_turns=[masked_text], tool_outputs=evidence, proposed_action=card,
            approval_request_id=request_id), args)
        self.pending = {"request_id": request_id, "escalation_id": escalation_id, "card": card, "args": args,
                        "ctx": ctx, "tool": tool}

    def approve(self, specialist, after_hours=0.0):
        escalation_id, request_id = self.pending["escalation_id"], self.pending["request_id"]
        self.queues.claim(TENANT, escalation_id, cred(specialist, escalation_id))
        card = self.desk.card(TENANT, escalation_id, cred(specialist, escalation_id))
        self.desk.decide(TENANT, escalation_id, cred(specialist, request_id),
                         Submission(verdict="approve", confirmed=card.confirm))
        self.clock[0] += after_hours * HOUR
        return self.invoke({"type": "APPROVAL_GRANTED"})


# Scenario 3: a high-risk financial dispute ----------------------------------------------------------------

PENDING = ("I verified the discrepancy against your contract. The refund needs a senior billing specialist's "
           "approval and is pending review; they have the contract comparison.")
PROMISE = "We will refund you today."
DONE = "Your refund is complete: the amount will be credited to your corporate Amex."
PAST_TENSE = "Your refund has been processed."


@pytest.fixture
def finance(saver):
    return Agent(saver, "vp-finance")


def test_scenario_3_no_money_moves_before_a_senior_approves(finance):
    state = finance.turn(DISPUTE)
    assert state["path"][-4:] == ["TRIAGED", "COLLECTING_PARAMS", "EXECUTING_SOP", "AWAITING_APPROVAL"]
    assert finance.world.changes == []
    pending = finance.pending
    assert pending["card"]["approval_level"] == "senior_specialist" and pending["card"]["mode"] == "dry_run"
    assert psql(DB, f"SELECT queue, packet->'tool_outputs' FROM escalations WHERE id = "
                    f"'{pending['escalation_id']}'")[0][0] == "queue_senior"
    assert "contracted_rate" in psql(DB, f"SELECT packet::text FROM escalations WHERE id = "
                                         f"'{pending['escalation_id']}'")[0][0]  # the comparison is attached
    for request_id in (None, pending["request_id"]):          # neither without nor with a pending approval
        with pytest.raises(NotApproved):
            finance.gate.execute(pending["ctx"], pending["tool"], pending["args"], {}, request_id)
    with pytest.raises(Refused, match="not staffed"):         # a specialist cannot take a senior approval
        finance.queues.claim(TENANT, pending["escalation_id"], cred("sam", pending["escalation_id"]))
    assert finance.world.changes == []
    assert psql(DB, f"SELECT count(*) FROM financial_writes WHERE case_id = '{finance.case_id}'") == [["0"]]


def test_scenario_3_no_success_is_claimed_before_the_read_back(finance):
    finance.turn(DISPUTE)
    assert finance.say(PENDING).verdict == "deliver"
    held = finance.say(PROMISE, rewrite=PROMISE)               # a promise with nothing executed behind it
    assert held.verdict == "escalate" and "unbacked refund commitment" in held.findings
    state = finance.approve("sue")
    assert state["stage"] == "RESOLVED"
    assert finance.world.changes == [("refund", "INV-4471", 16000.0)]   # once, after the senior's approval
    assert psql(DB, f"SELECT amount_usd FROM financial_writes WHERE case_id = '{finance.case_id}'") == [
        ["16000.00"]]
    assert finance.say(DONE).verdict == "deliver"              # the read-back confirmed it


def test_scenario_3_a_refund_the_erp_did_not_apply_is_not_claimed(finance):
    finance.world.refunds_stick = False
    finance.turn(DISPUTE)
    finance.approve("sue")
    assert finance.world.changes == [("refund", "INV-4471", 16000.0)] and finance.verified == []
    assert finance.say(DONE, rewrite=DONE).verdict == "escalate"


@pytest.mark.xfail(strict=True,
                   reason="open-issues register B7: the output checks miss past-tense success claims")
def test_scenario_3_a_past_tense_success_claim_is_held_without_a_verified_action(finance):
    finance.turn(DISPUTE)
    assert finance.say(PAST_TENSE, rewrite=PAST_TENSE).verdict == "escalate"


# Scenario 4: mid-flight state invalidation ----------------------------------------------------------------

@pytest.fixture
def sysadmin(saver):
    return Agent(saver, "jun-sysadmin", roles=("cloud_admin",))


def test_scenario_4_a_correction_cancels_the_pending_action_and_only_the_right_instance_is_reset(sysadmin):
    sysadmin.turn(RESET)
    first = sysadmin.pending
    assert first["args"].instance_id == "srv-alpha-12" and sysadmin.world.changes == []
    sysadmin.turn(CORRECTION)
    status = psql(DB, f"SELECT status FROM approval_requests WHERE id = '{first['request_id']}'")
    assert status == [["revoked"]]
    with pytest.raises(Refused):                                # nobody can approve the withdrawn one
        sysadmin.queues.claim(TENANT, first["escalation_id"], cred("tess", first["escalation_id"]))
    second = sysadmin.pending
    assert second["args"].instance_id == "srv-bravo-99" and second["args"].environment == "staging"
    with pytest.raises(NotApproved):                            # the withdrawn approval covers nothing
        sysadmin.gate.execute(second["ctx"], second["tool"], second["args"], {}, first["request_id"])
    state = sysadmin.approve("tess")
    assert state["stage"] == "RESOLVED"
    assert sysadmin.world.changes == [("reset", "srv-bravo-99")]
    assert sysadmin.world.instances["srv-alpha-12"]["credentials_version"] == 7     # untouched
    assert sysadmin.say("Done: srv-bravo-99 in staging has new root credentials; srv-alpha-12 was not "
                        "touched.").verdict == "deliver"


def test_scenario_4_a_case_resumed_after_a_long_wait_re_checks_the_target_before_acting(sysadmin):
    sysadmin.turn(RESET)
    sysadmin.turn(CORRECTION)
    sysadmin.world.instances["srv-bravo-99"]["environment"] = "production"  # promoted during the wait
    state = sysadmin.approve("tess", after_hours=2)
    assert state["stage"] == "ESCALATED_HITL" and "state changed" in state["error"]
    assert sysadmin.world.changes == []                                       # no side effect


def test_scenario_4_an_unchanged_target_still_runs_after_a_long_wait(sysadmin):
    sysadmin.turn(RESET)
    sysadmin.turn(CORRECTION)
    state = sysadmin.approve("tess", after_hours=2)
    assert state["stage"] == "RESOLVED" and sysadmin.world.changes == [("reset", "srv-bravo-99")]


def test_scenario_4_a_correction_after_the_approval_cannot_undo_it(sysadmin):
    sysadmin.turn(RESET)
    first = sysadmin.pending
    sysadmin.approve("tess")
    assert sysadmin.world.changes == [("reset", "srv-alpha-12")]
    cancelled, message = sysadmin.handoffs.cancel(Principal(tenant_id=TENANT, principal_id="jun-sysadmin"),
                                                  first["escalation_id"])
    assert not cancelled and message == handoff.LATE_CANCEL
