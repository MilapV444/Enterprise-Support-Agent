"""M2-10.7: hand-off on request, the waiting experience with an estimate and a cancel, checks on human
replies, and draft feedback with reason codes (FR-38, FR-39 / HL-ADP-04, HL-ADP-05)."""

import subprocess
import threading
import time
import uuid
from pathlib import Path

import psycopg
import pytest

from channels import sessions
from channels.api.envelope import Principal
from channels.identity.oidc import MockIdP
from core.orchestrator.decisions import Answer, DecisionEngine, JevUnavailable
from data import events
from data.migrate import PsqlError, migrate, psql
from hitl import handoff, queues
from hitl.approval import CONSOLE_CLIENT, Desk, StaffCredential, Submission, staff_verifier
from hitl.handoff import LATE_CANCEL, Handoffs, Sent, allowed, check_reply, wants_human
from hitl.queues import Domain, Packet, Queues, Reason, Refused
from safety.authz.cedar import Authorizer, entity
from tests.tools.validation.test_validation import REFUND, REGISTRY, STATE, TOKENS, refund
from tools.validation import approvals, preview
from tools.validation.approvals import ApprovalGate, CallContext

ROOT = Path(__file__).resolve().parents[3]
DB = "test_hitl_handoff"
DSN = f"postgresql://agent:change-me@127.0.0.1:5432/{DB}"  # credentials from .env.example
IDP = MockIdP()
HANDLER = "hank"
INTERNAL = ("Internal runbook: restart the billing reconciler with the force flag and skip the audit hook "
            "first")


class Jev:
    def __init__(self, human=False, down=False):
        self.human, self.down, self.seen = human, down, []

    def evaluate(self, state, questions):
        self.seen.append(state)
        if self.down:
            raise JevUnavailable("down")
        if "human" in questions:
            return {"human": Answer(self.human, 0.9)}
        if "acuity" in questions:
            return {"acuity": Answer(1.0, 0.9, 1)}
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
    for module in (sessions, events, approvals, queues, handoff, handoff):  # the last one: idempotent
        module.apply_schema(DB)
    psql(DB, "INSERT INTO tenants (id, name, region) VALUES ('t_us', 'Acme', 'US'), ('t_eu', 'Globex', 'EU');"
             "INSERT INTO tenant_settings (tenant_id) VALUES ('t_us'), ('t_eu');"
             "INSERT INTO staff_directory (tenant_id, staff_id, roles, queues) VALUES "
             "('t_us', 'sam', '{specialist}', '{queue_billing}'),"
             "('t_us', 'tess', '{specialist}', '{queue_technical}'),"
             "('t_us', 'tom', '{specialist}', '{queue_technical}'),"
             "('t_us', 'hank', '{specialist}', '{queue_technical,queue_billing}')")


class World:
    def __init__(self, jev=None):
        self.alerts = []
        self.verify = staff_verifier(connect, IDP.issuer, IDP.public_key)
        self.gate = ApprovalGate(connect, DecisionEngine(Jev()), Authorizer(), self.verify)
        self.queues = Queues(connect, DecisionEngine(jev or Jev()), TOKENS, self.verify,
                             alert=lambda *a: self.alerts.append(a), notify=lambda *a: None)
        self.desk = Desk(connect, self.gate, self.verify)
        self.handoffs = Handoffs(connect, self.queues, self.verify, alert=lambda *a: self.alerts.append(a),
                                 internal_passages=[INTERNAL], allowed_domains=["acme.com"])


@pytest.fixture
def w(database):
    return World()


def cred(user, item, tenant="t_us"):
    return StaffCredential(tenant, str(item), IDP.id_token(CONSOLE_CLIENT, tenant, user, str(item)))


def case(customer="sarah", tenant="t_us"):
    with connect() as conn:
        session = sessions.start(conn, tenant, customer, "T2_SSO")
        conversation = f"conv-{uuid.uuid4().hex[:8]}"
        sessions.open_conversation(conn, tenant, customer, session, conversation)
        case_id = sessions.link_case(conn, tenant, conversation)
    return CallContext(tenant, case_id, conversation, customer, HANDLER,
                       resource={"action": "update_contact", "type": "Account", "id": "A-1",
                                 "attrs": {"tenant_id": tenant, "owner": entity("User", customer)}})


def packet(ctx, reason=Reason.USER_REQUESTED_HUMAN, domain=Domain.TECHNICAL, **fields):
    return Packet(tenant_id=ctx.tenant_id, case_id=ctx.case_id, conversation_id=ctx.conversation_id,
                  customer_id=ctx.principal_id, handler_id=ctx.handler_id, identity_tier="T2_SSO",
                  channel="web",
                  reason=reason, domain=domain, summary="The API returns errors since this morning",
                  last_turns=["Can I talk to a person?"], **fields)


def staged(w, amount=1240):
    ctx, args = case(), refund(amount)
    decision = w.gate.validate(ctx, REFUND, args, STATE)
    request_id = w.gate.request(ctx, REFUND, args, decision)
    card = preview(REGISTRY, REFUND, args, decision, TOKENS)
    escalation_id = w.queues.escalate(packet(ctx, Reason.ACTION_APPROVAL_REQUIRED, Domain.BILLING,
                                             proposed_action=card, approval_request_id=request_id), args)
    return ctx, request_id, escalation_id


def picked_up(w, user="tess"):
    ctx = case()
    escalation_id, _ = w.handoffs.request(packet(ctx))
    w.handoffs.pick_up("t_us", escalation_id, cred(user, escalation_id))
    return ctx, escalation_id


def stream(conversation_id):
    return [(r[0], r[1]) for r in psql(DB, "SELECT event_type, data::text FROM outbound_event_log "
                                           f"WHERE conversation_id = '{conversation_id}' ORDER BY id")]


def request_status(request_id):
    return psql(DB, f"SELECT status FROM approval_requests WHERE id = '{request_id}'")[0][0]


def escalation(escalation_id, columns="status, outcome_code"):
    return psql(DB, f"SELECT {columns} FROM escalations WHERE id = '{escalation_id}'")[0]


# Asking for a person ----------------------------------------------------------------------------------------

def test_a_request_for_a_person_is_recognised_by_button_jev_or_keywords_when_jev_is_down():
    assert wants_human(DecisionEngine(Jev(human=False)), "anything", pressed=True)
    yes = Jev(human=True)
    assert wants_human(DecisionEngine(yes), "Let me speak with someone, sarah@acme.com")
    assert "sarah@acme.com" not in str(yes.seen)                         # Jev sees masked text only
    assert not wants_human(DecisionEngine(Jev(human=False)), "Where is my invoice?")
    down = DecisionEngine(Jev(down=True))
    assert wants_human(down, "Can I talk to a real person please")
    assert wants_human(down, "I want a human")
    assert not wants_human(down, "Where is my invoice?")


def test_a_hand_off_is_queued_at_once_and_the_customer_told_their_place_and_wait(w):
    ctx = case()
    assert w.handoffs.mode("t_us", ctx.conversation_id) == "agent"
    escalation_id, wait = w.handoffs.request(packet(ctx))
    assert escalation(escalation_id, "status, reason, queue") == ["waiting", "user_requested_human",
                                                                  "queue_technical"]
    assert wait.position >= 1 and wait.minutes is not None
    kind, data = stream(ctx.conversation_id)[-1]
    assert kind == "handoff" and '"state": "queued"' in data and f'"position": {wait.position}' in data
    assert w.handoffs.mode("t_us", ctx.conversation_id) == "co_serving"
    with pytest.raises(ValueError, match="not a hand-off"):
        w.handoffs.request(packet(ctx, Reason.ACTION_APPROVAL_REQUIRED, proposed_action={},
                                  approval_request_id=str(uuid.uuid4())))


def test_the_estimate_follows_place_in_queue_and_staffing(w):
    psql(DB, "UPDATE escalations SET status = 'cancelled' "
             "WHERE queue IN ('queue_technical', 'queue_account')")
    first, _ = w.handoffs.request(packet(case()))
    second, wait = w.handoffs.request(packet(case()))
    assert w.handoffs.estimate("t_us", first).position == 1
    assert wait.position == 2
    assert wait.minutes == 7    # position 2 x 10 minutes / 3 active technical staff, rounded up
    unstaffed, wait = w.handoffs.request(packet(case(), domain=Domain.ACCOUNT))
    assert wait.minutes is None and wait.position == 1


# Co-serving and the cold hand-off ---------------------------------------------------------------------------

def test_co_serving_allows_reads_only_and_a_picked_up_conversation_is_the_specialists_alone(w):
    read, write = REGISTRY.tools["billing.get_invoice"], REFUND
    assert allowed("agent", read) and allowed("agent", write)
    assert allowed("co_serving", read) and not allowed("co_serving", write)
    assert not allowed("human", read) and not allowed("human", write)
    ctx, escalation_id = picked_up(w)
    assert w.handoffs.mode("t_us", ctx.conversation_id) == "human"
    assert stream(ctx.conversation_id)[-1] == ("handoff", '{"state": "specialist_joined"}')
    assert psql(DB, f"SELECT event FROM escalation_events WHERE escalation_id = '{escalation_id}' "
                    "ORDER BY id") == [["escalated"], ["claimed"], ["picked_up"]]
    w.handoffs.hand_back("t_us", escalation_id, cred("tess", escalation_id))
    assert w.handoffs.mode("t_us", ctx.conversation_id) == "agent"
    assert stream(ctx.conversation_id)[-1] == ("handoff", '{"state": "specialist_left"}')


def test_the_packet_reaches_the_specialist_and_a_failed_take_over_can_be_retried(w):
    ctx = case()
    escalation_id, _ = w.handoffs.request(packet(ctx))
    w.queues.claim("t_us", escalation_id, cred("tess", escalation_id))      # claimed, take-over not recorded
    assert w.handoffs.mode("t_us", ctx.conversation_id) == "co_serving"
    received = w.handoffs.pick_up("t_us", escalation_id, cred("tess", escalation_id))
    assert received["summary"] == "The API returns errors since this morning"
    assert w.handoffs.mode("t_us", ctx.conversation_id) == "human"
    with pytest.raises(Refused, match="is claimed"):                        # nobody else takes it over
        w.handoffs.pick_up("t_us", escalation_id, cred("tom", escalation_id))


def test_one_specialist_owns_a_conversation_at_a_time(w):
    ctx, _ = picked_up(w)
    again, _ = w.handoffs.request(packet(ctx))
    with pytest.raises(psycopg.errors.UniqueViolation):
        w.handoffs.pick_up("t_us", again, cred("tom", again))
    assert w.handoffs.mode("t_us", ctx.conversation_id) == "human"


def test_who_may_take_a_conversation_over(w):
    ctx = case()
    escalation_id, _ = w.handoffs.request(packet(ctx))
    with pytest.raises(Refused, match="handler or customer"):
        w.handoffs.pick_up("t_us", escalation_id, cred(HANDLER, escalation_id))
    with pytest.raises(Refused, match="not made for this item"):
        w.handoffs.pick_up("t_us", escalation_id, cred("tess", uuid.uuid4()))
    missing = str(uuid.uuid4())
    with pytest.raises(Refused, match="no such escalation"):
        w.handoffs.pick_up("t_us", missing, cred("tess", missing))
    _, _, approval = staged(w)
    with pytest.raises(Refused, match="decided on its card"):
        w.handoffs.pick_up("t_us", approval, cred("sam", approval))


# Specialist replies -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, warning", [
    ("Your contact is bob@example.org", "personal data: email"),
    ("Use key sk_live_4eC39HqLyjWDarjtT1zdp7dc to test", "a credential or secret-like string"),
    (f"Here is what we do: {INTERNAL}", "text from internal-only documentation"),
    ("See http://acme.com/status", "a link that is not HTTPS to an allow-listed domain"),
    ("See [the docs](https://evil.example.net/acme)", "a link that is not HTTPS to an allow-listed domain"),
])
def test_replies_are_checked_for_leaks_and_unsafe_links(text, warning):
    assert warning in check_reply(text, [INTERNAL], ["acme.com"])


def test_a_clean_reply_and_an_allow_listed_link_have_no_warnings():
    assert check_reply("Hello Sarah, see https://docs.acme.com/status.", [INTERNAL], ["acme.com"]) == []


def test_a_warned_reply_needs_a_justification_which_is_recorded(w):
    ctx, escalation_id = picked_up(w)
    assert w.handoffs.reply("t_us", escalation_id, cred("tess", escalation_id), "Hello, I am on it.") == \
        Sent(True, [])
    warned = "Your contact is sarah@acme.com"
    assert w.handoffs.reply("t_us", escalation_id, cred("tess", escalation_id), warned) == \
        Sent(False, ["personal data: email"])
    with pytest.raises(ValueError):
        w.handoffs.reply("t_us", escalation_id, cred("tess", escalation_id), warned, "trust me")
    sent = w.handoffs.reply("t_us", escalation_id, cred("tess", escalation_id), warned, "customers_own_data")
    assert sent == Sent(True, ["personal data: email"])
    finals = [data for kind, data in stream(ctx.conversation_id) if kind == "final"]
    assert len(finals) == 2 and '"from": "specialist"' in finals[-1] and "sarah@acme.com" in finals[-1]
    assert psql(DB, "SELECT specialist_id, warnings, justification FROM reply_overrides "
                    f"WHERE escalation_id = '{escalation_id}'") == [["tess", "{\"personal data: email\"}",
                                                                     "customers_own_data"]]


def test_only_the_specialist_who_picked_it_up_replies_and_not_after_handing_back(w):
    _, escalation_id = picked_up(w)
    with pytest.raises(Refused, match="only the specialist"):
        w.handoffs.reply("t_us", escalation_id, cred("tom", escalation_id), "Hi")
    with pytest.raises(Refused, match="not made for this item"):
        w.handoffs.reply("t_us", escalation_id, cred("tess", uuid.uuid4()), "Hi")
    w.handoffs.hand_back("t_us", escalation_id, cred("tess", escalation_id))
    for action in (lambda: w.handoffs.reply("t_us", escalation_id, cred("tess", escalation_id), "Hi"),
                   lambda: w.handoffs.hand_back("t_us", escalation_id, cred("tess", escalation_id))):
        with pytest.raises(Refused, match="only the specialist"):
            action()


# Draft feedback with reason codes ---------------------------------------------------------------------------

def test_draft_feedback_needs_a_failure_code_for_edits_and_rejections(w):
    _, escalation_id = picked_up(w)
    for verdict, code in (("accepted", None), ("edited", "numeric_miscalculation"),
                          ("rejected", "grounding_hallucination")):
        w.handoffs.feedback("t_us", escalation_id, cred("tess", escalation_id), verdict, code)
    for verdict, code in (("edited", None), ("rejected", None), ("accepted", "tool_argument_error"),
                          ("rejected", "the agent was wrong"), ("great", None)):
        with pytest.raises(ValueError):
            w.handoffs.feedback("t_us", escalation_id, cred("tess", escalation_id), verdict, code)
    with pytest.raises(Refused, match="only the specialist"):
        w.handoffs.feedback("t_us", escalation_id, cred("tom", escalation_id), "accepted")
    rows = psql(DB, "SELECT verdict, reason_code, prompt_example FROM draft_feedback "
                    f"WHERE escalation_id = '{escalation_id}' ORDER BY id")
    assert rows == [["accepted", "", "f"], ["edited", "numeric_miscalculation", "f"],
                    ["rejected", "grounding_hallucination", "f"]]


def test_human_edited_drafts_can_never_become_prompt_examples(w):
    _, escalation_id = picked_up(w)
    with pytest.raises(PsqlError):
        psql(DB, "INSERT INTO draft_feedback (tenant_id, escalation_id, specialist_id, verdict, reason_code, "
                 f"prompt_example) VALUES ('t_us', '{escalation_id}', 'tess', 'edited', 'x', true)")


def test_overrides_and_feedback_are_append_only(w):
    _, escalation_id = picked_up(w)
    w.handoffs.feedback("t_us", escalation_id, cred("tess", escalation_id), "accepted")
    for statement in ("UPDATE draft_feedback SET verdict = 'rejected'", "DELETE FROM draft_feedback",
                      "TRUNCATE draft_feedback", "DELETE FROM reply_overrides"):
        with pytest.raises(PsqlError):
            psql(DB, statement)


# Cancel against approve: the first one wins -----------------------------------------------------------------

def customer(ctx):
    return Principal(tenant_id=ctx.tenant_id, principal_id=ctx.principal_id, assurance_tier="T2_SSO")


def take_and_confirm(w, escalation_id):
    w.queues.claim("t_us", escalation_id, cred("sam", escalation_id))
    return w.desk.card("t_us", escalation_id, cred("sam", escalation_id))


def test_a_cancel_before_the_approval_revokes_it_and_tells_the_specialist(w):
    ctx, request_id, escalation_id = staged(w)
    card = take_and_confirm(w, escalation_id)
    assert w.handoffs.cancel(customer(ctx), escalation_id) == (True, "Your request was cancelled.")
    assert request_status(request_id) == "revoked"
    assert escalation(escalation_id) == ["cancelled", "customer_cancelled"]
    assert ("t_us", escalation_id, "customer_cancelled") in w.alerts
    with pytest.raises(Refused):
        w.desk.decide("t_us", escalation_id, cred("sam", request_id),
                      Submission(verdict="approve", confirmed=card.confirm))
    assert w.handoffs.cancel(customer(ctx), escalation_id) == (False, "The request is no longer open.")


def test_a_cancel_after_the_approval_is_refused_with_an_explanation(w):
    ctx, request_id, escalation_id = staged(w)
    card = take_and_confirm(w, escalation_id)
    w.desk.decide("t_us", escalation_id, cred("sam", request_id),
                  Submission(verdict="approve", confirmed=card.confirm))
    assert w.handoffs.cancel(customer(ctx), escalation_id) == (False, LATE_CANCEL)
    assert request_status(request_id) == "approved"


def test_only_the_customer_cancels_and_only_an_action(w):
    ctx, _, escalation_id = staged(w)
    with pytest.raises(Refused, match="no such request"):
        w.handoffs.cancel(Principal(tenant_id="t_us", principal_id="bob"), escalation_id)
    with pytest.raises(Refused, match="no such request"):
        w.handoffs.cancel(Principal(tenant_id="t_eu", principal_id="sarah"), escalation_id)
    other = case()
    handoff_id, _ = w.handoffs.request(packet(other))
    with pytest.raises(Refused, match="only an action"):
        w.handoffs.cancel(customer(other), handoff_id)


def race(w):
    """An approval and a cancel released at the same instant; returns who won."""
    ctx, request_id, escalation_id = staged(w)
    card = take_and_confirm(w, escalation_id)
    start, outcome = threading.Barrier(2), {}

    def approve():
        start.wait()
        try:
            w.desk.decide("t_us", escalation_id, cred("sam", request_id),
                          Submission(verdict="approve", confirmed=card.confirm))
            outcome["approve"] = True
        except Refused:
            outcome["approve"] = False

    def cancel():
        start.wait()
        outcome["cancel"] = w.handoffs.cancel(customer(ctx), escalation_id)[0]
    threads = [threading.Thread(target=approve), threading.Thread(target=cancel)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert outcome["approve"] != outcome["cancel"]
    expected = ("approved", ["approved", ""]) if outcome["approve"] else \
        ("revoked", ["cancelled", "customer_cancelled"])
    assert (request_status(request_id), escalation(escalation_id)) == expected
    return "approve" if outcome["approve"] else "cancel"


def test_cancel_and_approve_at_the_same_moment_exactly_one_wins(w):
    for _ in range(8):
        race(w)


def test_a_cancel_locks_in_the_same_order_as_an_approval_so_the_two_cannot_deadlock(w):
    ctx, request_id, escalation_id = staged(w)
    result = []
    with connect() as holder, holder.transaction():  # stands in for Desk.decide holding the escalation row
        queues.context(holder, "t_us")
        holder.execute("SELECT 1 FROM escalations WHERE id = %s FOR UPDATE", (escalation_id,))
        waiter = threading.Thread(target=lambda: result.append(w.handoffs.cancel(customer(ctx),
                                                                                 escalation_id)))
        waiter.start()
        time.sleep(0.5)
        assert result == []                                         # the cancel waits for the escalation row
        with connect() as probe, probe.transaction():               # and holds nothing the approval needs
            queues.context(probe, "t_us")
            probe.execute("SELECT 1 FROM approval_requests WHERE id = %s FOR UPDATE NOWAIT", (request_id,))
    waiter.join()
    assert result == [(True, "Your request was cancelled.")]


def test_the_runtime_cannot_reassign_a_hand_off(w):
    _, escalation_id = picked_up(w)
    with connect() as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        with conn.transaction():
            queues.context(conn, "t_us")
            conn.execute("UPDATE handoffs SET specialist_id = 'tom' WHERE escalation_id = %s",
                         (escalation_id,))
