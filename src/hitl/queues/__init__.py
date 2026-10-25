"""Escalations to people: one typed packet, skills-based queues with SLA timers, aging alerts, senior
promotion and the 72-hour cancellation of undecided approvals (FR-36 / HL-ADP-02: HL-D3, HL-D9, HL-D12).

- escalate(): the packet is checked against server-side state (the conversation belongs to that customer and
  case; for an approval, the pending request matches the packet's case, customer and handler, and the
  proposed action's tool, level, tokenized arguments and USD amount match the request and the real
  arguments), tokenized (the PII tokens the vault resolves for an authorized viewer), given an acuity by Jev
  (the most urgent level when Jev cannot answer) and an SLA deadline by reason, and queued by domain. A
  senior-level approval goes straight to the senior queue.
- claim(): by a person verify_staff(credential) vouches for (SSO + the staff directory, hitl.approval), for
  this item (the credential names it), skilled for its queue (the senior queue, where every senior-level
  approval goes, needs a senior specialist), and neither the conversation's handler nor its customer.
- sweep(tenant): run on a schedule. Undecided approvals 72 hours old are cancelled (the request revoked, the
  customer told, with a way to ask for a person); items past their SLA move, unassigned, to the senior queue
  and page the queue lead; waiting items past half their SLA alert the lead once. Alerts and notices go out
  inside the transaction, so a failed one rolls its step back and the next sweep retries it (at least once).

Every step is appended to escalation_events.
"""

from datetime import timedelta
from enum import Enum

from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.orchestrator.decisions import JevUnavailable, Masked
from data.migrate import psql
from tools.validation import arguments_hash, financial_amount, masked

CANCEL_AFTER = timedelta(hours=72)  # HL-Q4(i)
ALERT_AT = 0.5                      # of the SLA window, unassigned
CANCEL_NOTICE = ("Your requested transaction could not be authorized within our standard review window. "
                 "Please reply to re-open or request immediate specialist assistance.")
OPEN = ("waiting", "claimed")


class Reason(str, Enum):
    CONFIDENCE_GATE_LOW = "confidence_gate_low"
    ACTION_APPROVAL_REQUIRED = "action_approval_required"
    REFLEXION_LIMIT_EXCEEDED = "reflexion_limit_exceeded"
    USER_REQUESTED_HUMAN = "user_requested_human"
    SIGNIFICANT_DECISION_REVIEW = "significant_decision_review"
    SYSTEM_DEPENDENCY_HELD = "system_dependency_held"


class Domain(str, Enum):
    BILLING = "billing"
    TECHNICAL = "technical"
    ACCOUNT = "account"


SENIOR = "queue_senior"
QUEUES = (*(f"queue_{domain.value}" for domain in Domain), SENIOR)

SLA = {  # HL-Q2(i)
    Reason.USER_REQUESTED_HUMAN: timedelta(minutes=15),
    Reason.CONFIDENCE_GATE_LOW: timedelta(minutes=15),
    Reason.ACTION_APPROVAL_REQUIRED: timedelta(hours=1),
    Reason.REFLEXION_LIMIT_EXCEEDED: timedelta(hours=1),
    # ponytail: a business day counted as 24 hours; a business calendar when weekends matter
    Reason.SIGNIFICANT_DECISION_REVIEW: timedelta(days=1),
    Reason.SYSTEM_DEPENDENCY_HELD: timedelta(days=1),
}

ACUITY = {"type": "score",
          "instructions": "How urgently does the customer need a person to act on this case?",
          "criteria": ["Low: a question that can wait", "Moderate: their work is slowed but continues",
                       "High: their work is blocked",
                       "Critical: an outage, a security issue or money at risk"]}
MOST_URGENT = len(ACUITY["criteria"]) - 1


class Packet(BaseModel):
    """The one escalation record a person receives (HL-D12): provenance, context, evidence, diagnosis and the
    proposed action. Built by the agent runtime from its own state, never from customer input as such."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: str
    case_id: str
    conversation_id: str
    customer_id: str
    handler_id: str
    identity_tier: str
    channel: str
    reason: Reason
    domain: Domain
    summary: str
    last_turns: list[str] = Field(max_length=3)
    pinned_facts: list[str] = []
    citations: list[str] = []
    tool_outputs: list[str] = []
    diagnostic_trace: str | None = None
    proposed_action: dict | None = None     # tools.validation.preview(): the tokenized approval card
    approval_request_id: str | None = None

    @model_validator(mode="after")
    def _approval_has_its_action(self):
        approval = self.reason is Reason.ACTION_APPROVAL_REQUIRED
        if not approval == (self.approval_request_id is not None) == (self.proposed_action is not None):
            raise ValueError("an action approval needs its request id and proposed action, and only it "
                             "has them")
        return self


class Refused(PermissionError):
    pass


def apply_schema(database):
    """Needs channels.sessions' and tools.validation.approvals' schemas in the same database."""
    if not psql(database, f"SELECT 1 FROM schema_migrations WHERE name = '{SCHEMA_NAME}'"):
        psql(database, f"BEGIN;\n{SCHEMA}\nINSERT INTO schema_migrations (name) VALUES ('{SCHEMA_NAME}');\n"
                       "COMMIT;\n")


SCHEMA_NAME = "hitl_0001_queues.sql"
QUEUE_LIST = ", ".join(f"'{queue}'" for queue in QUEUES)
SCHEMA = f"""
-- Who the staff are, per tenant: written by administrators (app_owner), read by the runtime.
CREATE TABLE staff_directory (
  tenant_id text NOT NULL REFERENCES tenants (id),
  staff_id  text NOT NULL,
  roles     text[] NOT NULL DEFAULT '{{}}',
  queues    text[] NOT NULL DEFAULT '{{}}',
  active    boolean NOT NULL DEFAULT true,
  PRIMARY KEY (tenant_id, staff_id)
);
ALTER TABLE staff_directory ENABLE ROW LEVEL SECURITY;
ALTER TABLE staff_directory FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON staff_directory
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());
ALTER TABLE staff_directory OWNER TO app_owner;
GRANT SELECT ON staff_directory TO app_runtime;

CREATE TABLE escalations (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           text NOT NULL REFERENCES tenants (id),
  case_id             text NOT NULL,
  conversation_id     text NOT NULL,
  customer_id         text NOT NULL,
  handler_id          text NOT NULL,
  reason              text NOT NULL,
  queue               text NOT NULL CHECK (queue IN ({QUEUE_LIST})),
  acuity              smallint NOT NULL,
  packet              jsonb NOT NULL,     -- tokenized
  approval_request_id uuid UNIQUE REFERENCES approval_requests (id),
  approval_level      text,
  status              text NOT NULL DEFAULT 'waiting'
                      CHECK (status IN ('waiting', 'claimed', 'approved', 'rejected', 'cancelled')),
  assignee_id         text,
  outcome_code        text,
  created_at          timestamptz NOT NULL DEFAULT now(),
  sla_due_at          timestamptz NOT NULL,
  alerted_at          timestamptz,
  promoted_at         timestamptz,
  claimed_at          timestamptz,
  closed_at           timestamptz
);
CREATE INDEX escalations_open ON escalations (tenant_id, queue, acuity DESC, sla_due_at)
  WHERE status IN ('waiting', 'claimed');
ALTER TABLE escalations ENABLE ROW LEVEL SECURITY;
ALTER TABLE escalations FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON escalations
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());
ALTER TABLE escalations OWNER TO app_owner;
GRANT SELECT, INSERT ON escalations TO app_runtime;
GRANT UPDATE (queue, status, assignee_id, outcome_code, alerted_at, promoted_at, claimed_at, closed_at)
  ON escalations TO app_runtime;

CREATE TABLE escalation_events (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id     text NOT NULL REFERENCES tenants (id),
  escalation_id uuid NOT NULL REFERENCES escalations (id),
  event         text NOT NULL,
  actor         text NOT NULL,
  detail        text,
  at            timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER escalation_events_append_only BEFORE UPDATE OR DELETE ON escalation_events
  FOR EACH ROW EXECUTE FUNCTION forbid_change();
CREATE TRIGGER escalation_events_no_truncate BEFORE TRUNCATE ON escalation_events
  FOR EACH STATEMENT EXECUTE FUNCTION forbid_change();
ALTER TABLE escalation_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE escalation_events FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON escalation_events
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());
ALTER TABLE escalation_events OWNER TO app_owner;
GRANT SELECT, INSERT ON escalation_events TO app_runtime;
"""


def context(conn, tenant_id):
    conn.execute("SET LOCAL ROLE app_runtime")
    conn.execute("SELECT set_config('app.current_tenant_id', %s, true)", (tenant_id,))


def event(conn, tenant_id, escalation_id, name, actor, detail=None):
    conn.execute("INSERT INTO escalation_events (tenant_id, escalation_id, event, actor, detail) "
                 "VALUES (%s, %s, %s, %s, %s)", (tenant_id, escalation_id, name, actor, detail))


def may_approve(roles, level):
    """Whether these roles reach an approval level (Cedar decides the grant itself, tools.validation)."""
    return bool(set(roles) & ({"senior_specialist"} if level == "senior_specialist"
                              else {"specialist", "senior_specialist"}))


class Queues:
    def __init__(self, connect, engine, tokenizer, verify_staff, alert, notify):
        """connect(): autocommit psycopg connection to the main database; engine: Jev DecisionEngine;
        tokenizer: safety.pii Tokenizer; verify_staff(credential) -> tools.validation.approvals.Approver,
        raising UnverifiedApprover; alert(tenant_id, escalation_id, kind) pages the queue lead ("aging" or
        "sla_breached"); notify(tenant_id, conversation_id, text) tells the customer."""
        self.connect, self.engine, self.tokenizer = connect, engine, tokenizer
        self.verify_staff, self.alert, self.notify = verify_staff, alert, notify

    def _acuity(self, packet):
        state = {"summary": Masked(packet.summary), "last_turns": Masked("\n".join(packet.last_turns))}
        try:
            return self.engine.ask(state, {"acuity": ACUITY})["acuity"].index
        except JevUnavailable:
            return MOST_URGENT

    def escalate(self, packet, arguments=None):
        """Queue a packet; returns the escalation id. arguments: the proposed call's real arguments, required
        for an action approval (the proposed action shown to the approver is checked against them)."""
        packet = packet.model_copy(update={
            name: masked(getattr(packet, name), self.tokenizer)
            for name in ("summary", "last_turns", "pinned_facts", "citations", "tool_outputs",
                         "diagnostic_trace")})
        acuity = self._acuity(packet)
        queue, level = f"queue_{packet.domain.value}", None
        with self.connect() as conn, conn.transaction():
            context(conn, packet.tenant_id)
            row = conn.execute("SELECT c.principal_id, c.case_id, k.status FROM conversations c "
                               "LEFT JOIN cases k ON k.id = c.case_id WHERE c.id = %s",
                               (packet.conversation_id,)).fetchone()
            if row is None or row[:2] != (packet.customer_id, packet.case_id):
                raise Refused("the conversation does not belong to this customer and case")
            if packet.approval_request_id is not None:
                level = self._check_approval(conn, packet, arguments)
                if level == "senior_specialist":
                    queue = SENIOR
            escalation_id = conn.execute(
                "INSERT INTO escalations (tenant_id, case_id, conversation_id, customer_id, handler_id, "
                "reason, queue, acuity, packet, approval_request_id, approval_level, sla_due_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now() + %s) RETURNING id",
                (packet.tenant_id, packet.case_id, packet.conversation_id, packet.customer_id,
                 packet.handler_id, packet.reason.value, queue, acuity, Jsonb(packet.model_dump(mode="json")),
                 packet.approval_request_id, level, SLA[packet.reason])).fetchone()[0]
            event(conn, packet.tenant_id, escalation_id, "escalated", packet.handler_id, queue)
        return str(escalation_id)

    def _check_approval(self, conn, packet, arguments):
        row = conn.execute("SELECT case_id, conversation_id, principal_id, handler_id, tool_id, "
                           "arguments_hash, level, status, expires_at > now() FROM approval_requests "
                           "WHERE id = %s",
                           (packet.approval_request_id,)).fetchone()
        if row is None:
            raise Refused("no such approval request in this tenant")
        case_id, conversation_id, principal_id, handler_id, tool_id, args_hash, level, status, live = row
        if (case_id, conversation_id, principal_id, handler_id) != (
                packet.case_id, packet.conversation_id, packet.customer_id, packet.handler_id):
            raise Refused("the approval request is for another case, conversation, customer or handler")
        if status != "pending" or not live:
            raise Refused(f"the approval request is {status if live else 'expired'}")
        if level == "customer":
            raise Refused("a customer confirmation is not a specialist approval")
        action = packet.proposed_action
        if arguments is None or arguments_hash(arguments) != args_hash:
            raise Refused("the arguments are not the ones the request was made for")
        shown = (action.get("tool_id"), action.get("approval_level"), action.get("arguments"),
                 action.get("amount_usd"))
        real = (tool_id, level, masked(arguments.model_dump(mode="json"), self.tokenizer),
                str(financial_amount(arguments)[0]))
        if shown != real:
            raise Refused("the proposed action shown to the approver is not the requested one")
        return level

    def waiting(self, tenant_id, queue):
        """The open items of a queue, most urgent first: (id, reason, acuity, sla_due_at, status)."""
        with self.connect() as conn, conn.transaction():
            context(conn, tenant_id)
            return [(str(row[0]), *row[1:]) for row in conn.execute(
                "SELECT id, reason, acuity, sla_due_at, status FROM escalations WHERE queue = %s "
                "AND status IN ('waiting', 'claimed') ORDER BY acuity DESC, sla_due_at", (queue,))]

    def claim(self, tenant_id, escalation_id, credential):
        """Take an item; returns the staff id. Raises Refused or UnverifiedApprover."""
        staff = self.verify_staff(credential)
        if staff.tenant_id != tenant_id or credential.item_id != str(escalation_id):
            raise Refused("the sign-in was not made for this item in this tenant")
        with self.connect() as conn, conn.transaction():
            context(conn, tenant_id)
            row = conn.execute("SELECT queue, status, handler_id, customer_id FROM escalations "
                               "WHERE id = %s FOR UPDATE", (escalation_id,)).fetchone()
            if row is None:
                raise Refused("no such escalation in this tenant")
            queue, status, handler_id, customer_id = row
            skills = conn.execute("SELECT queues FROM staff_directory WHERE staff_id = %s AND active",
                                  (staff.approver_id,)).fetchone()
            if status != "waiting":
                raise Refused(f"the item is {status}")
            if staff.approver_id in (handler_id, customer_id):
                raise Refused("the conversation's handler or customer cannot take its escalation")
            if skills is None or queue not in skills[0]:
                raise Refused(f"not staffed on {queue}")
            if queue == SENIOR and "senior_specialist" not in staff.roles:
                raise Refused("the senior queue needs a senior specialist")
            conn.execute("UPDATE escalations SET status = 'claimed', assignee_id = %s, claimed_at = now() "
                         "WHERE id = %s", (staff.approver_id, escalation_id))
            event(conn, tenant_id, escalation_id, "claimed", staff.approver_id)
        return staff.approver_id

    def sweep(self, tenant_id):
        """One pass of the aging rules over a tenant's open items; returns [(event, escalation id)]."""
        done = []
        with self.connect() as conn, conn.transaction():
            context(conn, tenant_id)
            for escalation_id, request_id, conversation_id in conn.execute(
                    "UPDATE escalations SET status = 'cancelled', outcome_code = 'undecided_72h', "
                    "closed_at = now() WHERE status IN ('waiting', 'claimed') "
                    "AND approval_request_id IS NOT NULL "
                    "AND created_at <= now() - %s RETURNING id, approval_request_id, conversation_id",
                    (CANCEL_AFTER,)).fetchall():
                conn.execute("UPDATE approval_requests SET status = 'revoked' WHERE id = %s "
                             "AND status IN ('pending', 'approved')", (request_id,))
                event(conn, tenant_id, escalation_id, "action.approval.auto_cancelled", "system")
                self.notify(tenant_id, conversation_id, CANCEL_NOTICE)
                done.append(("auto_cancelled", str(escalation_id)))
            for (escalation_id,) in conn.execute(
                    "UPDATE escalations SET queue = %s, status = 'waiting', assignee_id = NULL, "
                    "promoted_at = now(), alerted_at = coalesce(alerted_at, now()) "
                    "WHERE status IN ('waiting', 'claimed') "
                    "AND promoted_at IS NULL AND sla_due_at <= now() RETURNING id", (SENIOR,)).fetchall():
                event(conn, tenant_id, escalation_id, "sla_breached", "system", SENIOR)
                self.alert(tenant_id, str(escalation_id), "sla_breached")
                done.append(("sla_breached", str(escalation_id)))
            for (escalation_id,) in conn.execute(
                    "UPDATE escalations SET alerted_at = now() WHERE status = 'waiting' "
                    "AND alerted_at IS NULL AND now() >= created_at + (sla_due_at - created_at) * %s "
                    "RETURNING id", (ALERT_AT,)).fetchall():
                event(conn, tenant_id, escalation_id, "aging", "system")
                self.alert(tenant_id, str(escalation_id), "aging")
                done.append(("aging", str(escalation_id)))
        return done
