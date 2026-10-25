"""Approving a queued action (FR-37 / HL-ADP-03: HL-D4, HL-D5): staff identity, the approval card and the
decision.

- Staff are who the SSO provider says: an MFA ID token for the console's client id, minted for one item (its
  nonce is the escalation id for claim() and card(), the approval request id for decide()). Their roles come
  from the staff directory, active staff only; never from the caller or the token's own claims.
- card(): the item's assignee sees the tokenized packet (summary, last turns, evidence, diagnosis and the
  proposed action with its dry run or current state) and the fields to confirm: the tool (the destination
  system), the USD amount and every argument.
- decide(): the assignee only. Approving needs every field confirmed with the value shown on the card (no
  one-click approval), then tools.validation's grant() applies the rights by role and amount (Cedar:
  specialists below the tenant's senior amount, senior specialists at or above it, never the handler or the
  customer). Rejecting needs a structured reason code and revokes the request.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from channels.identity.oidc import verify_id_token
from channels.identity.tokens import TokenError
from hitl.queues import Refused, context, event, may_approve
from tools.validation.approvals import Approver, UnverifiedApprover

CONSOLE_CLIENT = "support-console"


@dataclass(frozen=True)
class StaffCredential:
    tenant_id: str
    item_id: str    # the escalation or approval request this sign-in was made for: the ID token's nonce
    id_token: str


def staff_verifier(connect, issuer, public_key, client_id=CONSOLE_CLIENT):
    """verify_approver / verify_staff: StaffCredential -> Approver, raising UnverifiedApprover."""
    def verify(credential):
        if not isinstance(credential, StaffCredential):
            raise UnverifiedApprover("a staff sign-in is required")
        try:
            staff_id = verify_id_token(credential.id_token, public_key, issuer, client_id,
                                       credential.tenant_id, credential.item_id)
        except TokenError as error:
            raise UnverifiedApprover(f"staff sign-in not accepted: {error}") from None
        with connect() as conn, conn.transaction():
            context(conn, credential.tenant_id)
            row = conn.execute("SELECT roles FROM staff_directory WHERE staff_id = %s AND active",
                               (staff_id,)).fetchone()
        if row is None:
            raise UnverifiedApprover("not active in the staff directory")
        return Approver(credential.tenant_id, staff_id, frozenset(row[0]))
    return verify


class RejectReason(str, Enum):  # HL-D10: no free-form rejections
    MISMATCHED_AMOUNT = "mismatched_amount"
    WRONG_ACCOUNT = "wrong_account"
    UNAUTHORIZED_USER = "unauthorized_user"
    SUSPECTED_FRAUD = "suspected_fraud"
    POLICY_VIOLATION = "policy_violation"
    STATE_CHANGED = "state_changed"


@dataclass(frozen=True)
class Card:
    escalation_id: str
    request_id: str
    level: str
    packet: dict     # tokenized
    confirm: dict    # field -> the value the approver must confirm


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict: Literal["approve", "reject"]
    confirmed: dict[str, Any] = {}
    reason_code: RejectReason | None = None

    @model_validator(mode="after")
    def _complete(self):
        if (self.verdict == "reject") != (self.reason_code is not None):
            raise ValueError("a rejection needs a reason code, and only a rejection has one")
        return self


def fields_to_confirm(action):
    return {"tool_id": action["tool_id"], "amount_usd": action["amount_usd"],
            **{f"arguments.{name}": value for name, value in action["arguments"].items()}}


class Desk:
    def __init__(self, connect, gate, verify_staff):
        """gate: tools.validation.approvals.ApprovalGate built with verify_approver=verify_staff."""
        self.connect, self.gate, self.verify_staff = connect, gate, verify_staff

    def _staff(self, tenant_id, credential):
        staff = self.verify_staff(credential)
        if staff.tenant_id != tenant_id:
            raise Refused("the sign-in is for another tenant")
        return staff

    @staticmethod
    def _assigned(conn, escalation_id, staff):
        row = conn.execute("SELECT status, assignee_id, approval_request_id, approval_level, packet "
                           "FROM escalations WHERE id = %s FOR UPDATE", (escalation_id,)).fetchone()
        if row is None:
            raise Refused("no such escalation in this tenant")
        status, assignee, request_id, level, packet = row
        if status != "claimed" or assignee != staff.approver_id:
            raise Refused("only the person who took the item can see or decide it")
        if request_id is None:
            raise Refused("the item is not an action approval")
        return str(request_id), level, packet

    def card(self, tenant_id, escalation_id, credential):
        staff = self._staff(tenant_id, credential)
        if credential.item_id != str(escalation_id):
            raise Refused("the sign-in was not made for this item")
        with self.connect() as conn, conn.transaction():
            context(conn, tenant_id)
            request_id, level, packet = self._assigned(conn, escalation_id, staff)
        confirm = fields_to_confirm(packet["proposed_action"])
        return Card(str(escalation_id), request_id, level, packet, confirm)

    def decide(self, tenant_id, escalation_id, credential, submission):
        staff = self._staff(tenant_id, credential)
        with self.connect() as conn, conn.transaction():
            context(conn, tenant_id)
            request_id, level, packet = self._assigned(conn, escalation_id, staff)
            if credential.item_id != request_id:
                raise Refused("the sign-in was not made for this approval request")
            if submission.verdict == "approve":
                expected = fields_to_confirm(packet["proposed_action"])
                unconfirmed = sorted(name for name, value in expected.items()
                                     if submission.confirmed.get(name, object()) != value)
                if unconfirmed or set(submission.confirmed) != set(expected):
                    raise Refused(f"confirm every field with the value on the card: {unconfirmed}")
                self.gate.grant(tenant_id, request_id, credential)
                status, code = "approved", None
            else:
                if not may_approve(staff.roles, level):
                    raise Refused(f"a {level} decision needs a higher role")
                if not self.gate.revoke(tenant_id, request_id):
                    raise Refused("the approval request is no longer open")
                status, code = "rejected", submission.reason_code.value
            conn.execute("UPDATE escalations SET status = %s, outcome_code = %s, closed_at = now() "
                         "WHERE id = %s", (status, code, escalation_id))
            event(conn, tenant_id, escalation_id, status, staff.approver_id, code)
