"""Hand-off to a person and the wait for one (FR-38 / HL-ADP-04: HL-D6, HL-D7, HL-D8, HL-D14), and structured
feedback on co-pilot drafts (FR-39 / HL-ADP-05: HL-D10).

- wants_human(): the always-visible button, or Jev (yes / no) on the masked message; when Jev cannot answer, a
  keyword match, so a request for a person is never lost to an outage. request() queues it at once.
- mode(conversation): "human" once a specialist has picked the conversation up (cold hand-off: the agent sends
  nothing more), "co_serving" while a hand-off waits to be picked up (the agent may answer with read-only
  tools only), "agent" otherwise. allowed(mode, tool) applies it.
- estimate(): the customer's place in the queue and the wait, (position) / (service rate x active staff on
  the queue); no estimate when nobody staffs it.
- cancel(): the customer withdraws an action waiting for approval. The escalation row is locked first, as
  hitl.approval.Desk.decide() does, so a cancel and an approval are serialized: whichever takes the lock
  first wins, and the other is refused ("Action was already authorized and executed." for a late cancel).
- reply(): a specialist's message, from the person who picked the conversation up, is checked first
  (personal data, credentials and high-entropy strings, internal-only text, links that are not HTTPS to an
  allow-listed domain). Warnings do not block for good: the specialist may send anyway with a structured
  justification, recorded in an append-only table.
- feedback(): the verdict on a co-pilot draft; an edit or a rejection needs a failure reason code.
  Human-edited drafts are diagnostic data, never prompt examples (CI-D5).
"""

import math
import re
from dataclasses import dataclass, field
from enum import Enum

from channels.api.envelope import EventType
from channels.api.turns import publish
from core.orchestrator.decisions import JevUnavailable, mask
from data.events import EventLog
from data.migrate import psql
from hitl.queues import Reason, Refused, context, event
from safety.output.checks import BARE_URL, CANDIDATE, CREDENTIALS, LINK, entropy, safe_url, shared_run
from safety.pii.tokens import find as find_pii
from tools.registry import Risk

SERVICE_MINUTES = 10  # ponytail: a fixed service time per specialist; measured rates when there is history
HUMAN_INTENT = {"type": "noul", "instructions": "Is the customer asking to talk to a human person instead of "
                                                "the assistant?"}
ASKS_FOR_HUMAN = re.compile(r"\b(human|real person|someone real|a person|agent|representative|operator|"
                            r"specialist|supervisor|manager)\b", re.IGNORECASE)
LATE_CANCEL = "Action was already authorized and executed."

SCHEMA_NAME = "hitl_0002_handoff.sql"
SCHEMA = """
-- Who owns a conversation after a cold hand-off; one active owner per conversation.
CREATE TABLE handoffs (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id       text NOT NULL REFERENCES tenants (id),
  conversation_id text NOT NULL,
  escalation_id   uuid NOT NULL UNIQUE REFERENCES escalations (id),
  specialist_id   text NOT NULL,
  started_at      timestamptz NOT NULL DEFAULT now(),
  ended_at        timestamptz
);
CREATE UNIQUE INDEX handoffs_one_owner ON handoffs (tenant_id, conversation_id) WHERE ended_at IS NULL;
ALTER TABLE handoffs ENABLE ROW LEVEL SECURITY;
ALTER TABLE handoffs FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON handoffs
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());
ALTER TABLE handoffs OWNER TO app_owner;
GRANT SELECT, INSERT ON handoffs TO app_runtime;
GRANT UPDATE (ended_at) ON handoffs TO app_runtime;

-- Specialist replies sent despite their warnings (SG-D13), and feedback on co-pilot drafts (HL-D10).
CREATE TABLE reply_overrides (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id     text NOT NULL REFERENCES tenants (id),
  escalation_id uuid NOT NULL REFERENCES escalations (id),
  specialist_id text NOT NULL,
  warnings      text[] NOT NULL,
  justification text NOT NULL,
  at            timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE draft_feedback (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id     text NOT NULL REFERENCES tenants (id),
  escalation_id uuid NOT NULL REFERENCES escalations (id),
  specialist_id text NOT NULL,
  verdict       text NOT NULL CHECK (verdict IN ('accepted', 'edited', 'rejected')),
  reason_code   text,
  prompt_example boolean NOT NULL DEFAULT false CHECK (NOT prompt_example),  -- CI-D5
  at            timestamptz NOT NULL DEFAULT now(),
  CHECK ((verdict = 'accepted') = (reason_code IS NULL))
);
"""
for table in ("reply_overrides", "draft_feedback"):
    SCHEMA += f"""
CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table}
  FOR EACH ROW EXECUTE FUNCTION forbid_change();
CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table}
  FOR EACH STATEMENT EXECUTE FUNCTION forbid_change();
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON {table}
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());
ALTER TABLE {table} OWNER TO app_owner;
GRANT SELECT, INSERT ON {table} TO app_runtime;
"""


def apply_schema(database):
    """Needs hitl.queues' schema and data.events' outbound_event_log in the same database."""
    if not psql(database, f"SELECT 1 FROM schema_migrations WHERE name = '{SCHEMA_NAME}'"):
        psql(database, f"BEGIN;\n{SCHEMA}\nINSERT INTO schema_migrations (name) VALUES ('{SCHEMA_NAME}');\n"
                       "COMMIT;\n")


class Justification(str, Enum):  # why a warned reply was sent anyway
    CUSTOMERS_OWN_DATA = "customers_own_data"
    APPROVED_DISCLOSURE = "approved_disclosure"
    FALSE_POSITIVE = "false_positive"
    LINK_VERIFIED = "link_verified"


class DraftFailure(str, Enum):  # HL-D10
    GROUNDING_HALLUCINATION = "grounding_hallucination"
    RETRIEVAL_IRRELEVANCE = "retrieval_irrelevance"
    NUMERIC_MISCALCULATION = "numeric_miscalculation"
    TONE_OR_POLICY_VIOLATION = "tone_or_policy_violation"
    TOOL_ARGUMENT_ERROR = "tool_argument_error"


@dataclass(frozen=True)
class Estimate:
    position: int
    minutes: int | None   # None: nobody staffs the queue


@dataclass(frozen=True)
class Sent:
    sent: bool
    warnings: list[str] = field(default_factory=list)


def wants_human(engine, message, pressed=False):
    if pressed:
        return True
    try:
        return engine.ask({"message": mask(message)}, {"human": HUMAN_INTENT})["human"].value is True
    except JevUnavailable:
        return bool(ASKS_FOR_HUMAN.search(message))


def allowed(mode, tool):
    """May the agent run this tool in this conversation mode?"""
    return mode == "agent" or (mode == "co_serving" and tool.risk is Risk.READ_ONLY)


def check_reply(text, internal_passages=(), allowed_domains=()):
    """Warnings on a specialist's message before it goes to the customer."""
    warnings = [f"personal data: {kind.lower()}" for _, _, kind, _ in find_pii(text)]
    if CREDENTIALS.search(text) or any(entropy(m.group(0)) >= 4.5 for m in CANDIDATE.finditer(text)):
        warnings.append("a credential or secret-like string")
    if any(shared_run(text, passage) for passage in internal_passages):
        warnings.append("text from internal-only documentation")
    links = [m.group(2) for m in LINK.finditer(text)] + [m.group(0).rstrip(".,;:!?")
                                                         for m in BARE_URL.finditer(text)]
    if any(not safe_url(url, allowed_domains) for url in links):
        warnings.append("a link that is not HTTPS to an allow-listed domain")
    return warnings


class Handoffs:
    def __init__(self, connect, queues, verify_staff, alert, internal_passages=(), allowed_domains=(),
                 service_minutes=SERVICE_MINUTES):
        """queues: hitl.queues.Queues; verify_staff: hitl.approval.staff_verifier(...); alert(tenant_id,
        escalation_id, kind) tells the specialist ("customer_cancelled")."""
        self.connect, self.queues, self.verify_staff, self.alert = connect, queues, verify_staff, alert
        self.internal_passages, self.allowed_domains = internal_passages, allowed_domains
        self.service_minutes = service_minutes

    def _publish(self, conn, tenant_id, conversation_id, event_type, data):
        publish(EventLog(conn), tenant_id, conversation_id, event_type, data)

    def request(self, packet):
        """Queue a hand-off now and tell the customer their place and wait; returns (escalation id,
        Estimate)."""
        if packet.reason is Reason.ACTION_APPROVAL_REQUIRED:
            raise ValueError("an action approval is not a hand-off")
        escalation_id = self.queues.escalate(packet)
        wait = self.estimate(packet.tenant_id, escalation_id)
        with self.connect() as conn:
            self._publish(conn, packet.tenant_id, packet.conversation_id, EventType.HANDOFF,
                          {"state": "queued", "escalation_id": escalation_id, "position": wait.position,
                           "estimate_minutes": wait.minutes})
        return escalation_id, wait

    def estimate(self, tenant_id, escalation_id):
        with self.connect() as conn, conn.transaction():
            context(conn, tenant_id)
            ahead, staff = conn.execute(
                "SELECT (SELECT count(*) FROM escalations o WHERE o.queue = e.queue AND o.status = 'waiting' "
                "AND o.id <> e.id AND (o.acuity, -extract(epoch FROM o.sla_due_at)) "
                "> (e.acuity, -extract(epoch FROM e.sla_due_at))), "
                "(SELECT count(*) FROM staff_directory s WHERE s.active AND e.queue = ANY (s.queues)) "
                "FROM escalations e WHERE e.id = %s", (escalation_id,)).fetchone()
        position = ahead + 1
        return Estimate(position, math.ceil(position * self.service_minutes / staff) if staff else None)

    def mode(self, tenant_id, conversation_id):
        with self.connect() as conn, conn.transaction():
            context(conn, tenant_id)
            if conn.execute("SELECT 1 FROM handoffs WHERE conversation_id = %s AND ended_at IS NULL",
                            (conversation_id,)).fetchone():
                return "human"
            waiting = conn.execute("SELECT 1 FROM escalations e WHERE conversation_id = %s "
                                   "AND status IN ('waiting', 'claimed') AND reason <> %s AND NOT EXISTS "
                                   "(SELECT 1 FROM handoffs h WHERE h.escalation_id = e.id)",
                                   (conversation_id, Reason.ACTION_APPROVAL_REQUIRED.value)).fetchone()
        return "co_serving" if waiting else "agent"

    def pick_up(self, tenant_id, escalation_id, credential):
        """A specialist takes the conversation over (cold hand-off); returns the escalation packet."""
        staff = self.verify_staff(credential)
        if staff.tenant_id != tenant_id or credential.item_id != str(escalation_id):
            raise Refused("the sign-in was not made for this item in this tenant")
        with self.connect() as conn, conn.transaction():
            context(conn, tenant_id)
            row = conn.execute("SELECT reason, status, assignee_id FROM escalations WHERE id = %s",
                               (escalation_id,)).fetchone()
        if row is None:
            raise Refused("no such escalation in this tenant")
        if row[0] == Reason.ACTION_APPROVAL_REQUIRED.value:
            raise Refused("an action approval is decided on its card, not taken over")
        if (row[1], row[2]) != ("claimed", staff.approver_id):  # a retry after a failed take-over keeps it
            self.queues.claim(tenant_id, escalation_id, credential)
        with self.connect() as conn, conn.transaction():
            context(conn, tenant_id)
            conversation_id, packet = conn.execute("SELECT conversation_id, packet FROM escalations "
                                                   "WHERE id = %s", (escalation_id,)).fetchone()
            conn.execute("INSERT INTO handoffs (tenant_id, conversation_id, escalation_id, specialist_id) "
                         "VALUES (%s, %s, %s, %s) ON CONFLICT (escalation_id) DO NOTHING",
                         (tenant_id, conversation_id, escalation_id, staff.approver_id))
            event(conn, tenant_id, escalation_id, "picked_up", staff.approver_id)
            self._publish(conn, tenant_id, conversation_id, EventType.HANDOFF, {"state": "specialist_joined"})
        return packet

    def _owner(self, conn, escalation_id, staff):
        row = conn.execute("SELECT conversation_id, specialist_id FROM handoffs WHERE escalation_id = %s "
                           "AND ended_at IS NULL FOR UPDATE", (escalation_id,)).fetchone()
        if row is None or row[1] != staff.approver_id:
            raise Refused("only the specialist who picked the conversation up can act on it")
        return row[0]

    def _staff(self, tenant_id, escalation_id, credential):
        staff = self.verify_staff(credential)
        if staff.tenant_id != tenant_id or credential.item_id != str(escalation_id):
            raise Refused("the sign-in was not made for this item in this tenant")
        return staff

    def reply(self, tenant_id, escalation_id, credential, text, justification=None):
        """Send a specialist's message; Sent(False, warnings) until the warnings are justified."""
        staff = self._staff(tenant_id, escalation_id, credential)
        warnings = check_reply(text, self.internal_passages, self.allowed_domains)
        with self.connect() as conn, conn.transaction():
            context(conn, tenant_id)
            conversation_id = self._owner(conn, escalation_id, staff)
            if warnings and justification is None:
                return Sent(False, warnings)
            if warnings:
                conn.execute("INSERT INTO reply_overrides (tenant_id, escalation_id, specialist_id, "
                             "warnings, justification) VALUES (%s, %s, %s, %s, %s)",
                             (tenant_id, escalation_id, staff.approver_id, warnings,
                              Justification(justification).value))
            self._publish(conn, tenant_id, conversation_id, EventType.FINAL,
                          {"text": text, "from": "specialist"})
        return Sent(True, warnings)

    def hand_back(self, tenant_id, escalation_id, credential):
        """The specialist is done; the agent may serve the conversation again."""
        staff = self._staff(tenant_id, escalation_id, credential)
        with self.connect() as conn, conn.transaction():
            context(conn, tenant_id)
            conversation_id = self._owner(conn, escalation_id, staff)
            conn.execute("UPDATE handoffs SET ended_at = now() WHERE escalation_id = %s", (escalation_id,))
            event(conn, tenant_id, escalation_id, "handed_back", staff.approver_id)
            self._publish(conn, tenant_id, conversation_id, EventType.HANDOFF, {"state": "specialist_left"})

    def feedback(self, tenant_id, escalation_id, credential, verdict, reason_code=None):
        """A specialist's verdict on the co-pilot draft of a conversation they picked up."""
        staff = self._staff(tenant_id, escalation_id, credential)
        if verdict not in ("accepted", "edited", "rejected") or \
                (verdict == "accepted") != (reason_code is None):
            raise ValueError("an edit or a rejection needs a failure reason code, and only they have one")
        code = None if reason_code is None else DraftFailure(reason_code).value
        with self.connect() as conn, conn.transaction():
            context(conn, tenant_id)
            self._owner(conn, escalation_id, staff)
            conn.execute("INSERT INTO draft_feedback (tenant_id, escalation_id, specialist_id, verdict, "
                         "reason_code) VALUES (%s, %s, %s, %s, %s)",
                         (tenant_id, escalation_id, staff.approver_id, verdict, code))

    def cancel(self, principal, escalation_id):
        """The customer withdraws an action waiting for approval. Returns (cancelled, message)."""
        tenant_id = principal.tenant_id
        with self.connect() as conn, conn.transaction():
            context(conn, tenant_id)
            row = conn.execute("SELECT customer_id, approval_request_id, status, assignee_id "
                               "FROM escalations WHERE id = %s FOR UPDATE", (escalation_id,)).fetchone()
            if row is None or row[0] != principal.principal_id:
                raise Refused("no such request for this customer")
            _, request_id, status, assignee = row
            if request_id is None:
                raise Refused("only an action waiting for approval can be cancelled")
            (request_status,) = conn.execute("SELECT status FROM approval_requests WHERE id = %s FOR UPDATE",
                                             (request_id,)).fetchone()
            if request_status in ("approved", "consumed"):
                return False, LATE_CANCEL
            if status not in ("waiting", "claimed") or request_status != "pending":
                return False, "The request is no longer open."
            conn.execute("UPDATE approval_requests SET status = 'revoked' WHERE id = %s", (request_id,))
            conn.execute("UPDATE escalations SET status = 'cancelled', outcome_code = 'customer_cancelled', "
                         "closed_at = now() WHERE id = %s", (escalation_id,))
            event(conn, tenant_id, escalation_id, "customer_cancelled", principal.principal_id)
            if assignee:
                self.alert(tenant_id, str(escalation_id), "customer_cancelled")
        return True, "Your request was cancelled."
