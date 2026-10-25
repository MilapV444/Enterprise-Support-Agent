"""M2-10.7: the Streamlit specialist console, driven with fake services (the rules themselves are the server
modules' and are tested there)."""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

from hitl.approval import Card, RejectReason
from hitl.handoff import Sent

APP = str(Path(__file__).resolve().parents[3] / "console" / "app.py")
DUE = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
CARD = Card("e-1", "r-1", "specialist",
            {"summary": "Charged twice", "proposed_action": {"tool_id": "billing.refund"}},
            {"tool_id": "billing.refund", "amount_usd": "1240.0", "arguments.invoice_id": "INV-9821"})


SENT = Sent(True, [])


class Fake:
    def __init__(self, reason="action_approval_required", sent=SENT):
        self.calls, self.sent = [], sent
        self.tenant_id, self.staff_id = "t_us", "sam"
        self.queues = SimpleNamespace(waiting=lambda tenant, queue: [("e-1", reason, 2, DUE, "waiting")],
                                      claim=self.record("claim"))
        self.desk = SimpleNamespace(card=lambda *a: CARD, decide=self.record("decide"))
        self.handoffs = SimpleNamespace(pick_up=self.record("pick_up"), feedback=self.record("feedback"),
                                        hand_back=self.record("hand_back"), reply=self.record("reply", sent))

    def record(self, name, result="ok"):
        def call(*args):
            self.calls.append((name, args))
            return result
        return call

    def sign_in(self, staff_id, item_id):
        return f"{staff_id}@{item_id}"

    def named(self, name):
        return [args for call, args in self.calls if call == name]


def opened(fake):
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["services"] = fake
    at.run()
    at.button(key="take-e-1").click().run()
    return at


def test_taking_an_approval_signs_in_for_that_item_and_opens_its_card():
    fake = Fake()
    at = opened(fake)
    assert fake.named("claim") == [("t_us", "e-1", "sam@e-1")]
    assert [box.label for box in at.checkbox] == ["tool_id: billing.refund", "amount_usd: 1240.0",
                                                  "arguments.invoice_id: INV-9821"]


def test_approve_stays_disabled_until_every_field_is_checked():
    fake = Fake()
    at = opened(fake)
    assert at.button(key="approve").proto.disabled
    for box in at.checkbox[:-1]:
        box.check()
    at.run()
    assert at.button(key="approve").proto.disabled
    at.checkbox[-1].check().run()
    assert not at.button(key="approve").proto.disabled
    at.button(key="approve").click().run()
    (tenant, item, credential, submission), = fake.named("decide")
    assert (item, credential, submission.verdict, submission.confirmed) == ("e-1", "sam@r-1", "approve",
                                                                            CARD.confirm)


def test_reject_needs_a_reason_code():
    fake = Fake()
    at = opened(fake)
    assert at.button(key="reject").proto.disabled
    at.selectbox(key="reject-reason").select(RejectReason.SUSPECTED_FRAUD).run()
    at.button(key="reject").click().run()
    (_, _, _, submission), = fake.named("decide")
    assert (submission.verdict, submission.reason_code) == ("reject", RejectReason.SUSPECTED_FRAUD)


def test_a_hand_off_shows_reply_warnings_and_feedback_needs_a_code_for_an_edit():
    fake = Fake(reason="user_requested_human", sent=Sent(False, ["personal data: email"]))
    at = opened(fake)
    assert fake.named("pick_up") == [("t_us", "e-1", "sam@e-1")]
    assert at.button(key="send").proto.disabled
    at.text_area(key="reply-e-1").input("Your contact is sarah@acme.com").run()
    at.button(key="send").click().run()
    assert [warning.value for warning in at.warning] == ["personal data: email"]
    assert fake.named("reply")[0][3:] == ("Your contact is sarah@acme.com", None)
    at.radio(key="verdict").set_value("edited").run()
    assert at.button(key="feedback").proto.disabled
    at.selectbox(key="failure").select_index(2).run()
    at.button(key="feedback").click().run()
    assert fake.named("feedback") == [("t_us", "e-1", "sam@e-1", "edited", "numeric_miscalculation")]
    at.button(key="hand-back").click().run()
    assert fake.named("hand_back") == [("t_us", "e-1", "sam@e-1")]


def test_a_refusal_from_the_server_is_shown_not_swallowed():
    fake = Fake()

    def refuse(*args):
        raise PermissionError("not staffed on queue_billing")
    fake.queues.claim = refuse
    at = opened(fake)
    assert [error.value for error in at.error] == ["not staffed on queue_billing"]
    assert not at.checkbox
