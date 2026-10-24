"""Approvals that cannot be forged, replayed or outlived, and the final check before a call runs (FR-22 /
TA-ADP-03; AC-10; DECISION-bdad33ce).

    validate() -> request() -> grant() -> execute()

- request(): an approval request is a server-side row, bound by a SHA-256 binding over tenant, case,
  conversation, customer, handler, tool, canonical arguments, decision id, policy version (tenant_settings
  .version), approval level, its own id and its expiry. It starts pending and expires after APPROVAL_TTL.
- grant(): the approver is whoever verify_approver(credential) says: never an id or role a caller passes in.
  The approver must be in the request's tenant and must not be the conversation's handler. A customer-level
  request can be confirmed only by the customer of that conversation; a specialist-level one only by a
  specialist or senior specialist, a senior-level one only by a senior specialist, never by the customer,
  and only when Cedar permits approve_action on the request (policies/; without that policy every grant is
  refused). pending -> approved happens in one conditional UPDATE.
- execute(): one transaction, under a lock on (tenant, case): the decision is made again from current state
  (tenant limits and policy version, the case's ledger, the conversation and case, Cedar on the target
  resource, Jev); DENY stops it; an approval-requiring verdict needs an approved, unexpired request whose
  binding still matches the current context exactly (any change - other case, other tenant, new policy
  version, other level, other arguments - fails), consumed with a conditional UPDATE so it works once. The
  financial amount is written to the append-only ledger in the same transaction, then the tool runs. A call
  that fails after that keeps its approval consumed and its ledger row (conservative: it counts toward
  threshold splitting).

Lifecycle: pending -> approved -> consumed; pending / approved -> revoked; past expires_at a request can
neither be granted nor consumed (expiry is checked against the database clock at each step).
"""

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal

from data.migrate import psql
from safety.authz.cedar import User
from tools.validation import Limits, Verdict, arguments_hash, decide

APPROVAL_TTL = "30 minutes"
SPLIT_WINDOW = "24 hours"
CLOSED_CASES = ["resolved", "closed"]

SCHEMA_NAME = "validation_0001_approvals.sql"
SCHEMA = """
CREATE TABLE approval_requests (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),  -- also the approval's nonce
  tenant_id       text NOT NULL REFERENCES tenants (id),
  case_id         text NOT NULL,
  conversation_id text NOT NULL,
  principal_id    text NOT NULL,   -- the customer the action is for
  handler_id      text NOT NULL,   -- who handles the conversation; never an approver
  tool_id         text NOT NULL,
  arguments_hash  text NOT NULL,
  decision_id     uuid NOT NULL,
  policy_version  integer NOT NULL,
  level           text NOT NULL CHECK (level IN ('customer', 'specialist', 'senior_specialist')),
  binding         text NOT NULL,
  status          text NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'approved', 'consumed', 'expired', 'revoked')),
  approver_id     text,
  approver_roles  text[],
  created_at      timestamptz NOT NULL DEFAULT now(),
  expires_at      timestamptz NOT NULL,
  approved_at     timestamptz,
  consumed_at     timestamptz
);
ALTER TABLE approval_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE approval_requests FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON approval_requests
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());
ALTER TABLE approval_requests OWNER TO app_owner;
GRANT SELECT, INSERT ON approval_requests TO app_runtime;
GRANT UPDATE (status, approver_id, approver_roles, approved_at, consumed_at) ON approval_requests
  TO app_runtime;

-- The authoritative record of financial writes, per tenant and case (threshold splitting reads it).
CREATE TABLE financial_writes (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id   text NOT NULL REFERENCES tenants (id),
  case_id     text NOT NULL,
  tool_id     text NOT NULL,
  decision_id uuid NOT NULL UNIQUE,
  approval_id uuid REFERENCES approval_requests (id),
  amount_usd  numeric(14, 2) NOT NULL CHECK (amount_usd >= 0),
  executed_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX financial_writes_case ON financial_writes (tenant_id, case_id, executed_at);
CREATE TRIGGER financial_writes_append_only BEFORE UPDATE OR DELETE ON financial_writes
  FOR EACH ROW EXECUTE FUNCTION forbid_change();
CREATE TRIGGER financial_writes_no_truncate BEFORE TRUNCATE ON financial_writes
  FOR EACH STATEMENT EXECUTE FUNCTION forbid_change();
ALTER TABLE financial_writes ENABLE ROW LEVEL SECURITY;
ALTER TABLE financial_writes FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON financial_writes
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());
ALTER TABLE financial_writes OWNER TO app_owner;
GRANT SELECT, INSERT ON financial_writes TO app_runtime;
"""


class NotApproved(PermissionError):
    pass


class UnverifiedApprover(PermissionError):
    pass


@dataclass(frozen=True)
class Approver:
    """Who an approval credential verifiably belongs to (from verify_approver, never from the caller)."""

    tenant_id: str
    approver_id: str
    roles: frozenset[str]


@dataclass(frozen=True)
class CallContext:
    """Where a call happens, from the verified session and the case record."""

    tenant_id: str
    case_id: str
    conversation_id: str
    principal_id: str      # the customer
    handler_id: str        # the agent identity (or human) handling the conversation
    roles: tuple[str, ...] = ()
    resource: dict = field(default_factory=dict)  # {"action", "type", "id", "attrs"} for Cedar


def apply_schema(database):
    """Needs channels.sessions' schema (conversations, cases) in the same database."""
    if not psql(database, f"SELECT 1 FROM schema_migrations WHERE name = '{SCHEMA_NAME}'"):
        psql(database, f"BEGIN;\n{SCHEMA}\nINSERT INTO schema_migrations (name) VALUES ('{SCHEMA_NAME}');\n"
                       "COMMIT;\n")


def no_staff_identity(credential):
    """The default verify_approver for staff: there is no staff identity yet (M2-09), so nobody verifies."""
    raise UnverifiedApprover("no staff identity provider is configured")


def customer_approver(identity):
    """verify_approver for customer confirmations: the customer's own live access token
    (channels.identity)."""
    class Request:
        def __init__(self, token):
            self.headers, self.path_params = {"Authorization": f"Bearer {token}"}, {}

    def verify(credential):
        try:
            principal = identity.authenticate(Request(credential))
        except Exception as error:  # HTTPException 401 and anything else: not verified
            raise UnverifiedApprover("customer token not accepted") from error
        return Approver(principal.tenant_id, principal.principal_id, frozenset({"customer"}))
    return verify


def binding(ctx, tool_id, args_hash, decision_id, policy_version, level, request_id, expires_at):
    fields = {"tenant": ctx.tenant_id, "case": ctx.case_id, "conversation": ctx.conversation_id,
              "principal": ctx.principal_id, "handler": ctx.handler_id, "tool": tool_id, "args": args_hash,
              "decision": str(decision_id), "policy_version": policy_version, "level": level,
              "request": str(request_id), "expires_at": expires_at.isoformat()}
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


class ApprovalGate:
    def __init__(self, connect, engine, authorizer, verify_approver=no_staff_identity):
        """connect(): autocommit psycopg connection to the main database; authorizer: Cedar Authorizer;
        verify_approver(credential) -> Approver, raising UnverifiedApprover."""
        self.connect, self.engine, self.authorizer, self.verify_approver = (connect, engine, authorizer,
                                                                            verify_approver)

    @staticmethod
    def _context(conn, tenant_id):
        conn.execute("SET LOCAL ROLE app_runtime")
        conn.execute("SELECT set_config('app.current_tenant_id', %s, true)", (tenant_id,))

    @staticmethod
    def _limits(conn):
        row = conn.execute("SELECT approval_threshold_usd, senior_amount_usd, version FROM tenant_settings"
                           ).fetchone()
        return Limits(Decimal(row[0]), Decimal(row[1]), row[2]) if row else Limits()

    @staticmethod
    def _recent(conn, case_id):
        return [row[0] for row in conn.execute(
            "SELECT amount_usd FROM financial_writes WHERE case_id = %s "
            f"AND executed_at > now() - interval '{SPLIT_WINDOW}' AND amount_usd > 0", (case_id,))]

    def _checks(self, conn, ctx, tool):
        """(floor verdict, reasons) from the current conversation, case and Cedar state."""
        row = conn.execute("SELECT c.principal_id, c.case_id, k.status FROM conversations c "
                           "LEFT JOIN cases k ON k.id = c.case_id WHERE c.id = %s",
                           (ctx.conversation_id,)).fetchone()
        if row is None or row[0] != ctx.principal_id or row[1] != ctx.case_id:
            return Verdict.DENY, ["the conversation does not belong to this customer and case"]
        if row[2] is None or row[2] in CLOSED_CASES:
            return Verdict.DENY, ["the case is not open"]
        if not tool.mutating and not ctx.resource:
            return Verdict.ALLOW, []
        resource = ctx.resource
        if not resource:
            return Verdict.DENY, ["a write needs its target resource for the authorization check"]
        verdict = self.authorizer.check(User(ctx.tenant_id, ctx.principal_id, tuple(ctx.roles)),
                                        resource.get("action", ""), resource.get("type", ""),
                                        resource.get("id", ""), resource.get("attrs", {}))
        if verdict == "allow":
            return Verdict.ALLOW, []
        if verdict == "approval_required":
            return Verdict.ASK_SPECIALIST, ["the authorization policy requires approval"]
        return Verdict.DENY, ["the authorization policy refuses this call"]

    def _decide(self, conn, ctx, tool, arguments, masked_state):
        floor, reasons = self._checks(conn, ctx, tool)
        return decide(tool, arguments, self._limits(conn), self.engine, masked_state,
                      recent=self._recent(conn, ctx.case_id), floor=floor, extra_reasons=reasons)

    def validate(self, ctx, tool, arguments, masked_state):
        with self.connect() as conn, conn.transaction():
            self._context(conn, ctx.tenant_id)
            return self._decide(conn, ctx, tool, arguments, masked_state)

    def request(self, ctx, tool, arguments, decision):
        """Open an approval request for a decision that needs one; returns its id."""
        if decision.level is None:
            raise ValueError(f"{decision.verdict.name} needs no approval request")
        with self.connect() as conn, conn.transaction():
            self._context(conn, ctx.tenant_id)
            request_id, expires_at = conn.execute(
                f"SELECT gen_random_uuid(), now() + interval '{APPROVAL_TTL}'").fetchone()
            seal = binding(ctx, tool.tool_id, arguments_hash(arguments), decision.decision_id,
                           decision.policy_version, decision.level, request_id, expires_at)
            conn.execute(
                "INSERT INTO approval_requests (id, tenant_id, case_id, conversation_id, principal_id, "
                "handler_id, tool_id, arguments_hash, decision_id, policy_version, level, binding, "
                "expires_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (request_id, ctx.tenant_id, ctx.case_id, ctx.conversation_id, ctx.principal_id,
                 ctx.handler_id, tool.tool_id, arguments_hash(arguments), decision.decision_id,
                 decision.policy_version, decision.level, seal, expires_at))
        return str(request_id)

    def grant(self, tenant_id, request_id, credential):
        """Approve a pending request with an approver credential; raises NotApproved / UnverifiedApprover."""
        approver = self.verify_approver(credential)
        if approver.tenant_id != tenant_id:
            raise NotApproved("the approver belongs to another tenant")
        with self.connect() as conn, conn.transaction():
            self._context(conn, tenant_id)
            row = conn.execute("SELECT level, principal_id, handler_id, status, expires_at > now() "
                               "FROM approval_requests WHERE id = %s FOR UPDATE", (request_id,)).fetchone()
            if row is None:
                raise NotApproved("no such approval request in this tenant")
            level, principal_id, handler_id, status, live = row
            if status != "pending" or not live:
                raise NotApproved(f"the request is {status if live else 'expired'}")
            if approver.approver_id == handler_id:
                raise NotApproved("the conversation's handler cannot approve their own action")
            if level == "customer":
                if approver.approver_id != principal_id or "customer" not in approver.roles:
                    raise NotApproved("only the customer of this conversation can confirm it")
            else:
                allowed = {"senior_specialist"} if level == "senior_specialist" else {"specialist",
                                                                                      "senior_specialist"}
                if approver.approver_id == principal_id or not (approver.roles & allowed):
                    raise NotApproved(f"a {level} approval needs one of {sorted(allowed)}")
                as_approver = User(approver.tenant_id, approver.approver_id, tuple(sorted(approver.roles)))
                verdict = self.authorizer.check(
                    as_approver, "approve_action", "ApprovalRequest", str(request_id),
                    {"tenant_id": tenant_id, "level": level, "handler": {"__entity": {"type": "User",
                                                                                      "id": handler_id}},
                     "customer": {"__entity": {"type": "User", "id": principal_id}}})
                if verdict != "allow":
                    raise NotApproved("the authorization policy does not let this approver approve this")
            updated = conn.execute(
                "UPDATE approval_requests SET status = 'approved', approver_id = %s, approver_roles = %s, "
                "approved_at = now() WHERE id = %s AND status = 'pending' AND expires_at > now()",
                (approver.approver_id, sorted(approver.roles), request_id)).rowcount
            if updated != 1:
                raise NotApproved("the request changed meanwhile")

    def revoke(self, tenant_id, request_id):
        with self.connect() as conn, conn.transaction():
            self._context(conn, tenant_id)
            return conn.execute("UPDATE approval_requests SET status = 'revoked' WHERE id = %s "
                                "AND status IN ('pending', 'approved')", (request_id,)).rowcount == 1

    def execute(self, ctx, tool, arguments, masked_state, request_id=None):
        """Re-validate against current state, consume the approval once, record the financial write, run."""
        with self.connect() as conn, conn.transaction():
            self._context(conn, ctx.tenant_id)
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                         (f"{ctx.tenant_id}:{ctx.case_id}",))
            decision = self._decide(conn, ctx, tool, arguments, masked_state)
            if decision.verdict is Verdict.DENY:
                raise NotApproved(f"{tool.tool_id}: denied ({'; '.join(decision.reasons)})")
            approval_id = None
            if decision.level is not None:
                approval_id = self._consume(conn, ctx, tool, arguments, decision, request_id)
            if decision.amount > 0:
                conn.execute("INSERT INTO financial_writes (tenant_id, case_id, tool_id, decision_id, "
                             "approval_id, amount_usd) VALUES (%s, %s, %s, %s, %s, %s)",
                             (ctx.tenant_id, ctx.case_id, tool.tool_id, decision.decision_id, approval_id,
                              decision.amount))
        return tool.func(arguments)

    def _consume(self, conn, ctx, tool, arguments, decision, request_id):
        if request_id is None:
            reasons = "; ".join(decision.reasons)
            raise NotApproved(f"{tool.tool_id}: needs {decision.level} approval ({reasons})")
        row = conn.execute("SELECT status, expires_at, expires_at > now(), decision_id, binding "
                           "FROM approval_requests WHERE id = %s FOR UPDATE", (request_id,)).fetchone()
        if row is None:
            raise NotApproved("no such approval request in this tenant")
        status, expires_at, live, decision_id, seal = row
        if not live:
            raise NotApproved("the approval has expired")
        if status != "approved":
            raise NotApproved(f"the approval is {status}")
        current = binding(ctx, tool.tool_id, arguments_hash(arguments), decision_id, decision.policy_version,
                          decision.level, request_id, expires_at)
        if current != seal:
            raise NotApproved("the approval was given for a different call, context, policy or level")
        if conn.execute("UPDATE approval_requests SET status = 'consumed', consumed_at = now() WHERE id = %s "
                        "AND status = 'approved' AND expires_at > now()", (request_id,)).rowcount != 1:
            raise NotApproved("the approval was used meanwhile")
        return request_id
