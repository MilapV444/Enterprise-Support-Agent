"""M2-09.7: the escalation packet, skills-based queues with SLAs and aging, approval rights by role and
amount, and the approval card (FR-36, FR-37 / HL-ADP-02, HL-ADP-03)."""

import subprocess
import time
import uuid
from datetime import timedelta
from pathlib import Path

import psycopg
import pytest
from pydantic import ValidationError

from channels import sessions
from channels.identity.oidc import MockIdP
from core.orchestrator.decisions import Answer, DecisionEngine, JevUnavailable
from data.migrate import PsqlError, migrate, psql
from hitl import queues
from hitl.approval import CONSOLE_CLIENT, Desk, RejectReason, StaffCredential, Submission, staff_verifier
from hitl.queues import CANCEL_AFTER, CANCEL_NOTICE, SENIOR, Domain, Packet, Queues, Reason, Refused
from safety.authz.cedar import Authorizer, entity
from tests.tools.validation.test_validation import REFUND, REGISTRY, STATE, TOKENS, refund
from tools.validation import approvals, preview
from tools.validation.approvals import ApprovalGate, CallContext, NotApproved, UnverifiedApprover

ROOT = Path(__file__).resolve().parents[3]
DB = "test_hitl_approval"
DSN = f"postgresql://agent:change-me@127.0.0.1:5432/{DB}"  # credentials from .env.example
IDP = MockIdP()
HANDLER = "hank"


class Jev:
    """The approval gate's questions answered 'allow, serves the request'; acuity at a set level, or down."""

    def __init__(self, acuity=1, down=False):
        self.acuity, self.down = acuity, down

    def evaluate(self, state, questions):
        if "acuity" in questions:
            if self.down:
                raise JevUnavailable("down")
            return {"acuity": Answer(float(self.acuity), 0.9, self.acuity)}
        return {"verdict": Answer("ALLOW", 0.9), "serves": Answer(True, 0.97)}


def connect():
    return psycopg.connect(DSN, autocommit=True)


@pytest.fixture(scope="module")
def database():
    subprocess.run(["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env.example",
                    "up", "-d", "--wait", "postgres"], cwd=ROOT, check=True, capture_output=True)
    psql("postgres", f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
    psql("postgres", f'CREATE DATABASE "{DB}"')
    migrate("main", DB)
    sessions.apply_schema(DB)
    approvals.apply_schema(DB)
    queues.apply_schema(DB)
    queues.apply_schema(DB)  # idempotent
    psql(DB, "INSERT INTO tenants (id, name, region) VALUES ('t_us', 'Acme', 'US'), ('t_eu', 'Globex', 'EU');"
             "INSERT INTO tenant_settings (tenant_id) VALUES ('t_us'), ('t_eu');"
             "INSERT INTO staff_directory (tenant_id, staff_id, roles, queues, active) VALUES "
             "('t_us', 'sam', '{specialist}', '{queue_billing}', true),"
             "('t_us', 'tess', '{specialist}', '{queue_technical}', true),"
             "('t_us', 'sue', '{senior_specialist}', '{queue_billing,queue_senior}', true),"
             "('t_us', 'olga', '{specialist}', '{queue_billing}', false),"
             "('t_us', 'hank', '{specialist}', '{queue_billing}', true),"
             "('t_us', 'sarah', '{senior_specialist}', '{queue_billing,queue_senior}', true),"
             "('t_eu', 'eve', '{senior_specialist}', '{queue_billing,queue_senior}', true)")


class Desks:
    def __init__(self, acuity=1, jev_down=False, notify=None):
        self.alerts, self.notices = [], []
        self.verify = staff_verifier(connect, IDP.issuer, IDP.public_key)
        self.gate = ApprovalGate(connect, DecisionEngine(Jev()), Authorizer(), self.verify)
        self.queues = Queues(connect, DecisionEngine(Jev(acuity, jev_down)), TOKENS, self.verify,
                             alert=lambda *item: self.alerts.append(item),
                             notify=notify or (lambda *notice: self.notices.append(notice)))
        self.desk = Desk(connect, self.gate, self.verify)


@pytest.fixture
def desks(database):
    return Desks()


def cred(user, item, tenant="t_us", mfa=True, client=CONSOLE_CLIENT, nonce=None, now=None):
    token = IDP.id_token(client, tenant, user, str(nonce or item), mfa, now)
    return StaffCredential(tenant, str(item), token)


def case(customer="sarah", tenant="t_us"):
    with connect() as conn:
        session = sessions.start(conn, tenant, customer, "T2_SSO")
        conversation = f"conv-{uuid.uuid4().hex[:8]}"
        sessions.open_conversation(conn, tenant, customer, session, conversation)
        case_id = sessions.link_case(conn, tenant, conversation)
    return CallContext(tenant, case_id, conversation, customer, HANDLER,
                       resource={"action": "update_contact", "type": "Account", "id": "A-1",
                                 "attrs": {"tenant_id": tenant, "owner": entity("User", customer)}})


def packet(ctx, reason=Reason.ACTION_APPROVAL_REQUIRED, domain=Domain.BILLING, **fields):
    return Packet(**{"tenant_id": ctx.tenant_id, "case_id": ctx.case_id,
                     "conversation_id": ctx.conversation_id, "customer_id": ctx.principal_id,
                     "handler_id": ctx.handler_id, "identity_tier": "T2_SSO",
                     "channel": "web", "reason": reason, "domain": domain,
                     "summary": "Sarah (sarah@acme.com) was charged twice on INV-9821",
                     "last_turns": ["I was charged twice", "Please refund it"],
                     "citations": ["kb://billing/double-charge"], **fields})


def staged(d, amount, ctx=None, **changes):
    """An approval request for a refund and its packet, queued; returns (ctx, args, request id,
    escalation id)."""
    ctx = ctx or case()
    args = refund(amount)
    decision = d.gate.validate(ctx, REFUND, args, STATE)
    request_id = d.gate.request(ctx, REFUND, args, decision, ttl=CANCEL_AFTER)
    card = preview(REGISTRY, REFUND, args, decision, TOKENS, dry_run_id="billing.refund_preview")
    escalation_id = d.queues.escalate(packet(ctx, proposed_action={**card, **changes},
                                             approval_request_id=request_id), args)
    return ctx, args, request_id, escalation_id


def approve(d, user, escalation_id, request_id):
    d.queues.claim("t_us", escalation_id, cred(user, escalation_id))
    card = d.desk.card("t_us", escalation_id, cred(user, escalation_id))
    d.desk.decide("t_us", escalation_id, cred(user, request_id),
                  Submission(verdict="approve", confirmed=card.confirm))
    return card


def row(escalation_id, columns="status, queue, assignee_id"):
    return psql(DB, f"SELECT {columns} FROM escalations WHERE id = '{escalation_id}'")[0]


def events(escalation_id):
    return [r[0] for r in psql(DB, "SELECT event FROM escalation_events "
                                   f"WHERE escalation_id = '{escalation_id}' ORDER BY id")]


def request_status(request_id):
    return psql(DB, f"SELECT status, approver_id FROM approval_requests WHERE id = '{request_id}'")[0]


# Rights by role and amount ----------------------------------------------------------------------------------

def test_below_the_senior_amount_a_billing_specialist_approves_and_the_refund_runs_once(desks):
    ctx, args, request_id, escalation_id = staged(desks, 1240)
    assert row(escalation_id) == ["waiting", "queue_billing", ""]
    card = approve(desks, "sam", escalation_id, request_id)
    assert card.level == "specialist" and card.confirm["amount_usd"] == "1240.0"
    assert card.confirm["tool_id"] == "billing.refund" and card.packet["proposed_action"]["mode"] == "dry_run"
    assert row(escalation_id) == ["approved", "queue_billing", "sam"]
    assert request_status(request_id) == ["approved", "sam"]
    desks.gate.execute(ctx, REFUND, args, STATE, request_id)
    assert request_status(request_id) == ["consumed", "sam"]
    with pytest.raises(NotApproved):
        desks.gate.execute(ctx, REFUND, args, STATE, request_id)
    assert events(escalation_id) == ["escalated", "claimed", "approved"]


def test_at_the_senior_amount_only_a_senior_specialist_can_take_and_approve(desks):
    _, _, request_id, escalation_id = staged(desks, 5000)
    assert row(escalation_id)[:2] == ["waiting", SENIOR]
    with pytest.raises(Refused, match="not staffed"):
        desks.queues.claim("t_us", escalation_id, cred("sam", escalation_id))
    approve(desks, "sue", escalation_id, request_id)
    assert request_status(request_id) == ["approved", "sue"]


def test_a_specialist_promoted_to_the_senior_queue_by_mistake_still_cannot_take_a_senior_approval(desks):
    psql(DB, "UPDATE staff_directory SET queues = '{queue_billing,queue_senior}' WHERE staff_id = 'sam'")
    try:
        _, _, _, escalation_id = staged(desks, 7000)
        with pytest.raises(Refused, match="senior specialist"):
            desks.queues.claim("t_us", escalation_id, cred("sam", escalation_id))
    finally:
        psql(DB, "UPDATE staff_directory SET queues = '{queue_billing}' WHERE staff_id = 'sam'")


def test_neither_the_handler_nor_the_customer_can_take_or_approve(desks):
    _, _, request_id, escalation_id = staged(desks, 1240)
    for user in (HANDLER, "sarah"):
        with pytest.raises(Refused, match="handler or customer"):
            desks.queues.claim("t_us", escalation_id, cred(user, escalation_id))
        with pytest.raises(NotApproved):  # and the gate refuses them on its own
            desks.gate.grant("t_us", request_id, cred(user, request_id))
    assert row(escalation_id)[0] == "waiting" and request_status(request_id) == ["pending", ""]


def test_only_staff_skilled_for_the_queue_can_take_an_item(desks):
    _, _, _, escalation_id = staged(desks, 1240)
    with pytest.raises(Refused, match="not staffed on queue_billing"):
        desks.queues.claim("t_us", escalation_id, cred("tess", escalation_id))


def test_only_the_assignee_sees_the_card_and_decides(desks):
    _, _, request_id, escalation_id = staged(desks, 1240)
    with pytest.raises(Refused, match="only the person who took"):
        desks.desk.card("t_us", escalation_id, cred("sam", escalation_id))
    desks.queues.claim("t_us", escalation_id, cred("sam", escalation_id))
    with pytest.raises(Refused, match="is claimed"):
        desks.queues.claim("t_us", escalation_id, cred("sue", escalation_id))
    with pytest.raises(Refused, match="only the person who took"):
        desks.desk.card("t_us", escalation_id, cred("sue", escalation_id))
    confirm = desks.desk.card("t_us", escalation_id, cred("sam", escalation_id)).confirm
    with pytest.raises(Refused, match="only the person who took"):
        desks.desk.decide("t_us", escalation_id, cred("sue", request_id),
                          Submission(verdict="approve", confirmed=confirm))
    assert request_status(request_id) == ["pending", ""]


# Staff identity ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("credential", [
    lambda item: cred("sam", item, mfa=False),                            # no MFA
    lambda item: cred("sam", item, client="support-agent"),               # the customer app's client id
    lambda item: cred("sam", item, nonce=uuid.uuid4()),                   # minted for another sign-in
    lambda item: cred("sam", item, now=time.time() - 3600),               # expired
    lambda item: cred("olga", item),                                      # not active
    lambda item: cred("zed", item),                                       # not in the directory
    lambda item: StaffCredential("t_us", str(item), MockIdP().id_token(CONSOLE_CLIENT, "t_us", "sam",
                                                                       str(item))),  # another provider
    lambda item: "sam",                                                   # a bare name
])
def test_staff_are_who_the_sso_provider_and_the_directory_say(desks, credential):
    _, _, _, escalation_id = staged(desks, 1240)
    with pytest.raises(UnverifiedApprover):
        desks.queues.claim("t_us", escalation_id, credential(escalation_id))
    assert row(escalation_id)[0] == "waiting"


def test_a_sign_in_works_for_its_own_item_and_tenant_only(desks):
    _, _, request_id, escalation_id = staged(desks, 1240)
    other = uuid.uuid4()
    with pytest.raises(Refused, match="not made for this item"):
        desks.queues.claim("t_us", escalation_id, cred("sam", other))
    desks.queues.claim("t_us", escalation_id, cred("sam", escalation_id))
    with pytest.raises(Refused, match="not made for this item"):  # the approval's sign-in does not open it
        desks.desk.card("t_us", escalation_id, cred("sam", request_id))
    confirm = desks.desk.card("t_us", escalation_id, cred("sam", escalation_id)).confirm
    with pytest.raises(Refused, match="this approval request"):  # the claim's sign-in is not an approval
        desks.desk.decide("t_us", escalation_id, cred("sam", escalation_id),
                          Submission(verdict="approve", confirmed=confirm))
    with pytest.raises(Refused, match="another tenant"):
        desks.desk.card("t_us", escalation_id, cred("eve", escalation_id, tenant="t_eu"))
    with pytest.raises(Refused, match="no such escalation"):  # row-level security hides it from t_eu
        desks.queues.claim("t_eu", escalation_id, cred("eve", escalation_id, tenant="t_eu"))
    assert desks.queues.waiting("t_eu", "queue_billing") == []


# The approval card: field-by-field confirmation, structured rejections --------------------------------------

@pytest.mark.parametrize("change", [
    lambda confirm: {k: v for k, v in confirm.items() if k != "amount_usd"},          # a field left out
    lambda confirm: {**confirm, "amount_usd": "124"},                                 # the wrong value
    lambda confirm: {**confirm, "arguments.invoice_id": "INV-1"},
    lambda confirm: {**confirm, "extra": True},                                  # a field not on the card
    lambda confirm: {},                                                               # one click
])
def test_approving_needs_every_field_confirmed_with_the_value_on_the_card(desks, change):
    _, _, request_id, escalation_id = staged(desks, 1240)
    desks.queues.claim("t_us", escalation_id, cred("sam", escalation_id))
    confirm = desks.desk.card("t_us", escalation_id, cred("sam", escalation_id)).confirm
    shown = {"tool_id", "amount_usd", "arguments.invoice_id", "arguments.amount", "arguments.notify"}
    assert shown <= set(confirm)
    with pytest.raises(Refused, match="confirm every field"):
        desks.desk.decide("t_us", escalation_id, cred("sam", request_id),
                          Submission(verdict="approve", confirmed=change(confirm)))
    assert row(escalation_id)[0] == "claimed" and request_status(request_id) == ["pending", ""]


@pytest.mark.parametrize("fields", [
    {"verdict": "reject"}, {"verdict": "reject", "reason_code": "because I said so"},
    {"verdict": "approve", "reason_code": "suspected_fraud"}, {"verdict": "maybe"},
    {"verdict": "approve", "note": "free text"},
])
def test_submissions_are_structured(fields):
    with pytest.raises(ValidationError):
        Submission(**fields)


def test_a_rejection_records_its_reason_and_revokes_the_request(desks):
    ctx, args, request_id, escalation_id = staged(desks, 1240)
    desks.queues.claim("t_us", escalation_id, cred("sam", escalation_id))
    desks.desk.decide("t_us", escalation_id, cred("sam", request_id),
                      Submission(verdict="reject", reason_code=RejectReason.SUSPECTED_FRAUD))
    assert row(escalation_id, "status, outcome_code") == ["rejected", "suspected_fraud"]
    assert request_status(request_id)[0] == "revoked"
    with pytest.raises(NotApproved):
        desks.gate.execute(ctx, REFUND, args, STATE, request_id)
    assert events(escalation_id) == ["escalated", "claimed", "rejected"]


def test_staff_who_lose_their_role_after_taking_an_item_cannot_decide_it(desks):
    _, _, request_id, escalation_id = staged(desks, 1240)
    desks.queues.claim("t_us", escalation_id, cred("sam", escalation_id))
    confirm = desks.desk.card("t_us", escalation_id, cred("sam", escalation_id)).confirm
    psql(DB, "UPDATE staff_directory SET roles = '{}' WHERE staff_id = 'sam'")
    try:
        with pytest.raises(Refused, match="higher role"):
            desks.desk.decide("t_us", escalation_id, cred("sam", request_id),
                              Submission(verdict="reject", reason_code=RejectReason.WRONG_ACCOUNT))
        with pytest.raises(NotApproved):
            desks.desk.decide("t_us", escalation_id, cred("sam", request_id),
                              Submission(verdict="approve", confirmed=confirm))
    finally:
        psql(DB, "UPDATE staff_directory SET roles = '{specialist}' WHERE staff_id = 'sam'")
    assert row(escalation_id)[0] == "claimed" and request_status(request_id) == ["pending", ""]


def test_a_failed_grant_leaves_the_item_undecided(desks):
    _, _, request_id, escalation_id = staged(desks, 1240)
    desks.queues.claim("t_us", escalation_id, cred("sam", escalation_id))
    confirm = desks.desk.card("t_us", escalation_id, cred("sam", escalation_id)).confirm
    psql(DB, "UPDATE approval_requests SET expires_at = now() - interval '1 second' "
             f"WHERE id = '{request_id}'")
    with pytest.raises(NotApproved, match="expired"):
        desks.desk.decide("t_us", escalation_id, cred("sam", request_id),
                          Submission(verdict="approve", confirmed=confirm))
    assert row(escalation_id)[0] == "claimed" and events(escalation_id) == ["escalated", "claimed"]


# The packet ------------------------------------------------------------------------------------------------

def test_the_packet_is_stored_tokenized(desks):
    _, _, _, escalation_id = staged(desks, 1240)
    stored = psql(DB, f"SELECT packet::text FROM escalations WHERE id = '{escalation_id}'")[0][0]
    assert "sarah@acme.com" not in stored and "<EMAIL_" in stored and "charged twice" in stored


@pytest.mark.parametrize("changes, arguments, message", [
    ({"amount_usd": "12.40"}, None, "not the requested one"),       # the card shows another amount
    ({"approval_level": "customer"}, None, "not the requested one"),
    ({"tool_id": "billing.void_invoice"}, None, "not the requested one"),
    ({"arguments": {"invoice_id": "INV-1"}}, None, "not the requested one"),
    ({}, refund(1240, invoice="INV-1"), "not the ones the request was made for"),
    ({}, "none", "not the ones the request was made for"),
])
def test_the_proposed_action_must_be_the_requested_one(desks, changes, arguments, message):
    ctx = case()
    args = refund(1240)
    decision = desks.gate.validate(ctx, REFUND, args, STATE)
    request_id = desks.gate.request(ctx, REFUND, args, decision)
    card = preview(REGISTRY, REFUND, args, decision, TOKENS)
    shown = packet(ctx, proposed_action={**card, **changes}, approval_request_id=request_id)
    with pytest.raises(Refused, match=message):
        desks.queues.escalate(shown, None if arguments == "none" else arguments or args)
    assert psql(DB, f"SELECT count(*) FROM escalations WHERE approval_request_id = '{request_id}'") == [["0"]]


def test_the_packet_must_match_the_conversation_and_the_request(desks):
    ctx, other = case(), case()
    args = refund(1240)
    decision = desks.gate.validate(ctx, REFUND, args, STATE)
    request_id = desks.gate.request(ctx, REFUND, args, decision)
    card = preview(REGISTRY, REFUND, args, decision, TOKENS)
    with pytest.raises(Refused, match="another case"):
        desks.queues.escalate(packet(other, proposed_action=card, approval_request_id=request_id), args)
    with pytest.raises(Refused, match="does not belong"):
        desks.queues.escalate(packet(ctx, customer_id="bob", proposed_action=card,
                                     approval_request_id=request_id), args)
    with pytest.raises(Refused, match="no such approval request"):
        desks.queues.escalate(packet(ctx, proposed_action=card, approval_request_id=str(uuid.uuid4())), args)
    desks.queues.escalate(packet(ctx, proposed_action=card, approval_request_id=request_id), args)
    with pytest.raises(psycopg.errors.UniqueViolation):  # one escalation per request
        desks.queues.escalate(packet(ctx, proposed_action=card, approval_request_id=request_id), args)
    desks.gate.revoke("t_us", request_id)
    with pytest.raises(Refused, match="is revoked"):
        desks.queues.escalate(packet(ctx, proposed_action=card, approval_request_id=request_id), args)


def test_an_expired_request_is_not_queued(desks):
    ctx = case()
    args = refund(1240)
    decision = desks.gate.validate(ctx, REFUND, args, STATE)
    request_id = desks.gate.request(ctx, REFUND, args, decision)
    card = preview(REGISTRY, REFUND, args, decision, TOKENS)
    psql(DB, "UPDATE approval_requests SET expires_at = now() - interval '1 second' "
             f"WHERE id = '{request_id}'")
    with pytest.raises(Refused, match="is expired"):
        desks.queues.escalate(packet(ctx, proposed_action=card, approval_request_id=request_id), args)


def test_a_customer_confirmation_is_not_queued_for_staff(database):
    class Ask(Jev):
        def evaluate(self, state, questions):
            return {"verdict": Answer("ASK", 0.9), "serves": Answer(True, 0.97)}
    d = Desks()
    d.gate = ApprovalGate(connect, DecisionEngine(Ask()), Authorizer(), d.verify)
    ctx = case()
    args = refund(10)
    decision = d.gate.validate(ctx, REFUND, args, STATE)
    request_id = d.gate.request(ctx, REFUND, args, decision)
    card = preview(REGISTRY, REFUND, args, decision, TOKENS)
    with pytest.raises(Refused, match="customer confirmation"):
        d.queues.escalate(packet(ctx, proposed_action=card, approval_request_id=request_id), args)


@pytest.mark.parametrize("fields", [
    {"reason": Reason.ACTION_APPROVAL_REQUIRED},                                     # no request, no action
    {"reason": Reason.USER_REQUESTED_HUMAN, "approval_request_id": "r", "proposed_action": {}},
    {"reason": Reason.USER_REQUESTED_HUMAN, "last_turns": ["a", "b", "c", "d"]},       # three at most
    {"reason": Reason.USER_REQUESTED_HUMAN, "domain": "sales"},
    {"reason": Reason.USER_REQUESTED_HUMAN, "priority": "high"},                       # unknown field
])
def test_the_packet_is_typed(fields):
    ctx = CallContext("t_us", "k", "c", "sarah", HANDLER)
    with pytest.raises(ValidationError):
        packet(ctx, **fields)


# Queues: SLA, acuity, aging, promotion and the 72-hour cancellation ----------------------------------------

def handoff(d, domain=Domain.TECHNICAL, reason=Reason.USER_REQUESTED_HUMAN):
    return d.queues.escalate(packet(case(), reason=reason, domain=domain))


@pytest.mark.parametrize("reason, minutes", [(Reason.USER_REQUESTED_HUMAN, 15),
                                             (Reason.CONFIDENCE_GATE_LOW, 15),
                                             (Reason.REFLEXION_LIMIT_EXCEEDED, 60),
                                             (Reason.SIGNIFICANT_DECISION_REVIEW, 1440)])
def test_sla_deadlines_follow_the_reason(desks, reason, minutes):
    escalation_id = handoff(desks, reason=reason)
    assert row(escalation_id, "extract(epoch FROM sla_due_at - created_at)::int / 60") == [str(minutes)]


def test_an_action_approval_has_an_hour(desks):
    _, _, _, escalation_id = staged(desks, 1240)
    assert row(escalation_id, "extract(epoch FROM sla_due_at - created_at)::int / 60") == ["60"]


def test_the_queue_is_most_urgent_first_and_an_unscored_case_counts_as_most_urgent(database):
    psql(DB, "UPDATE escalations SET status = 'cancelled' WHERE queue = 'queue_account'")
    low, high, unscored = (handoff(Desks(acuity=0), Domain.ACCOUNT), handoff(Desks(acuity=2), Domain.ACCOUNT),
                           handoff(Desks(jev_down=True), Domain.ACCOUNT))
    order = [(item[0], item[2]) for item in Desks().queues.waiting("t_us", "queue_account")]
    assert order == [(unscored, 3), (high, 2), (low, 0)]


def backdate(escalation_id, created, sla):
    psql(DB, f"UPDATE escalations SET created_at = now() - interval '{created}', "
             f"sla_due_at = now() - interval '{created}' + interval '{sla}' WHERE id = '{escalation_id}'")


def test_aging_alerts_once_past_half_the_sla(desks):
    psql(DB, "UPDATE escalations SET status = 'cancelled' WHERE status IN ('waiting', 'claimed')")
    early, aging = handoff(desks), handoff(desks)
    backdate(early, "7 minutes", "15 minutes")
    backdate(aging, "8 minutes", "15 minutes")
    assert desks.queues.sweep("t_us") == [("aging", aging)]
    assert desks.queues.sweep("t_us") == []
    assert desks.alerts == [("t_us", aging, "aging")]
    assert events(aging) == ["escalated", "aging"]


def test_a_breached_item_moves_unassigned_to_the_senior_queue_and_pages_the_lead(desks):
    psql(DB, "UPDATE escalations SET status = 'cancelled' WHERE status IN ('waiting', 'claimed')")
    _, _, request_id, escalation_id = staged(desks, 1240)
    desks.queues.claim("t_us", escalation_id, cred("sam", escalation_id))
    backdate(escalation_id, "61 minutes", "60 minutes")
    assert desks.queues.sweep("t_us") == [("sla_breached", escalation_id)]
    assert row(escalation_id) == ["waiting", SENIOR, ""]
    assert desks.alerts == [("t_us", escalation_id, "sla_breached")]
    assert desks.queues.sweep("t_us") == []                                   # no second alert
    with pytest.raises(Refused, match="not staffed"):
        desks.queues.claim("t_us", escalation_id, cred("sam", escalation_id))
    approve(desks, "sue", escalation_id, request_id)                          # a senior takes it over
    assert request_status(request_id) == ["approved", "sue"]


def test_an_approval_undecided_for_72_hours_is_cancelled_and_the_customer_told(desks):
    psql(DB, "UPDATE escalations SET status = 'cancelled' WHERE status IN ('waiting', 'claimed')")
    ctx, args, request_id, escalation_id = staged(desks, 1240)
    _, _, kept_request, kept = staged(desks, 1240)
    backdate(escalation_id, "72 hours 1 minute", "1 hour")
    backdate(kept, "71 hours 59 minutes", "1 hour")
    done = desks.queues.sweep("t_us")
    assert ("auto_cancelled", escalation_id) in done and ("auto_cancelled", kept) not in done
    assert row(escalation_id, "status, outcome_code") == ["cancelled", "undecided_72h"]
    assert request_status(request_id)[0] == "revoked" and request_status(kept_request)[0] == "pending"
    assert desks.notices == [("t_us", ctx.conversation_id, CANCEL_NOTICE)]
    assert "action.approval.auto_cancelled" in events(escalation_id)
    with pytest.raises(NotApproved):
        desks.gate.execute(ctx, REFUND, args, STATE, request_id)


def test_a_failed_notice_rolls_the_cancellation_back_for_the_next_sweep(database):
    psql(DB, "UPDATE escalations SET status = 'cancelled' WHERE status IN ('waiting', 'claimed')")

    def down(*notice):
        raise ConnectionError("inbox down")
    failing = Desks(notify=down)
    _, _, request_id, escalation_id = staged(failing, 1240)
    backdate(escalation_id, "73 hours", "1 hour")
    with pytest.raises(ConnectionError):
        failing.queues.sweep("t_us")
    assert row(escalation_id)[0] == "waiting" and request_status(request_id)[0] == "pending"
    working = Desks()
    assert ("auto_cancelled", escalation_id) in working.queues.sweep("t_us")
    assert request_status(request_id)[0] == "revoked" and len(working.notices) == 1


def test_the_escalation_history_is_append_only(desks):
    escalation_id = handoff(desks)
    for statement in (f"UPDATE escalation_events SET actor = 'x' WHERE escalation_id = '{escalation_id}'",
                      f"DELETE FROM escalation_events WHERE escalation_id = '{escalation_id}'",
                      "TRUNCATE escalation_events CASCADE"):
        with pytest.raises(PsqlError):
            psql(DB, statement)
    assert events(escalation_id) == ["escalated"]


def test_the_runtime_cannot_rewrite_a_packet_or_the_staff_directory(desks):
    escalation_id = handoff(desks)
    with connect() as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        with conn.transaction():
            queues.context(conn, "t_us")
            conn.execute("UPDATE escalations SET packet = '{}' WHERE id = %s", (escalation_id,))
    with connect() as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        with conn.transaction():
            queues.context(conn, "t_us")
            conn.execute("UPDATE staff_directory SET roles = '{senior_specialist}' WHERE staff_id = 'sam'")


def test_the_cancellation_window_is_the_longest_an_approval_may_live():
    assert CANCEL_AFTER == approvals.MAX_APPROVAL_TTL == timedelta(hours=72)
