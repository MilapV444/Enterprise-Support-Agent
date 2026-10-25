"""Approvals that cannot be forged, replayed or outlived, and the final check before a call runs (FR-22 /
TA-ADP-03; AC-10; DECISION-bdad33ce).

    validate() -> request() -> grant() -> execute()

- request(): an approval request is a server-side row, bound by a SHA-256 binding over tenant, case,
  conversation, customer, handler, tool, canonical arguments, decision id, policy version (tenant_settings
  .version), approval level, its own id and its expiry. It starts pending and expires after the gate's ttl
  (APPROVAL_TTL by default) or the ttl the request asks for: an approval queue lets an action approval live
  through its SLA and senior promotion, but never longer than MAX_APPROVAL_TTL (72 hours, HL-D9).
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

Trusted authorization inputs (the caller identifies the call; it does not define its privileges):
- tenant and principal are bound to the server-side conversation record: the conversation must exist in the
  tenant (row-level security) and belong to that principal and case, or the call is denied;
- roles come from roles_of(tenant, principal), the trusted directory, when the gate has one; ctx.roles is
  then ignored. (Without a directory the gate falls back to ctx.roles: a legacy path for callers not yet
  switched over, see the open items in the M2-09a knowledge record.)
- with a tool_authz map, each tool's Cedar action and resource type come from its registered rule: a call
  whose resource names another action or type, another id than the tool's own argument, or another tenant is
  denied, and a tool without a rule is denied. resource_attrs(tenant, type, id), when given, supplies the
  resource's attributes from application state instead of the caller.
- a read is never authorized by omission: without a target resource it is denied unless its rule declares
  it public.

Decisions: a decision id is random per evaluation, so approvals are bound to a deterministic digest of what
was decided (tenant, case, tool, arguments, verdict, level, USD amount, policy version). request() recomputes
the code-level verdict itself and never stores a weaker one than the caller claims; execute() compares the
stored digest with the digest of the fresh decision and refuses any difference.

financial_writes records authorized, committed attempts: the row is written with the approval's consumption,
before the external call, so a call that then fails still counts toward threshold splitting (conservative).
Each execute() writes at most one row (decision_id is unique per evaluation) under the case's advisory lock;
a retry is a new execute() and so a new attempt.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from data.migrate import psql
from safety.authz.cedar import User
from tools.validation import Limits, Verdict, arguments_hash, decide, required_level, static_gate

APPROVAL_TTL = timedelta(minutes=30)
MAX_APPROVAL_TTL = timedelta(hours=72)  # HL-D9: an approval still undecided after 3 days is cancelled
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


DIGEST_SCHEMA_NAME = "validation_0002_decision_digest.sql"
DIGEST_SCHEMA = """
ALTER TABLE approval_requests ADD COLUMN decision_digest text;
"""


class NotApproved(PermissionError):
    pass


@dataclass(frozen=True)
class ToolAuthorization:
    """How a registered tool is authorized: the Cedar action and resource type it performs, the argument that
    names the resource, or public=True for a read that needs no resource (e.g. the public help articles)."""

    action: str | None = None
    resource_type: str | None = None
    id_argument: str | None = None
    public: bool = False


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
    for name, sql in ((SCHEMA_NAME, SCHEMA), (DIGEST_SCHEMA_NAME, DIGEST_SCHEMA)):
        if not psql(database, f"SELECT 1 FROM schema_migrations WHERE name = '{name}'"):
            psql(database, f"BEGIN;\n{sql}\nINSERT INTO schema_migrations (name) VALUES ('{name}');\n"
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


def decision_digest(ctx, tool_id, args_hash, verdict, level, amount, policy_version):
    """A deterministic fingerprint of what was decided; equal for the same decision reached again."""
    fields = {"tenant": ctx.tenant_id, "case": ctx.case_id, "tool": tool_id, "args": args_hash,
              "verdict": Verdict(verdict).name, "level": level, "amount_usd": str(Decimal(amount)),
              "policy_version": policy_version}
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def binding(ctx, tool_id, args_hash, digest, policy_version, level, request_id, expires_at):
    fields = {"tenant": ctx.tenant_id, "case": ctx.case_id, "conversation": ctx.conversation_id,
              "principal": ctx.principal_id, "handler": ctx.handler_id, "tool": tool_id, "args": args_hash,
              "decision": digest, "policy_version": policy_version, "level": level,
              "request": str(request_id), "expires_at": expires_at.isoformat()}
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def lifetime(ttl):
    """A valid approval lifetime: more than zero, at most MAX_APPROVAL_TTL."""
    if not isinstance(ttl, timedelta) or not timedelta(0) < ttl <= MAX_APPROVAL_TTL:
        raise ValueError(f"an approval lifetime must be a timedelta in (0, {MAX_APPROVAL_TTL}]")
    return ttl


def request_id_of(value):
    """The request id as a UUID, or NotApproved: a malformed id is refused, never sent to the database."""
    try:
        return uuid.UUID(str(value))
    except ValueError:
        raise NotApproved(f"{value!r} is not an approval request id") from None


class ApprovalGate:
    def __init__(self, connect, engine, authorizer, verify_approver=no_staff_identity, ttl=APPROVAL_TTL,
                 roles_of=None, tool_authz=None, resource_attrs=None):
        """connect(): autocommit psycopg connection to the main database; authorizer: Cedar Authorizer;
        verify_approver(credential) -> Approver, raising UnverifiedApprover; ttl: how long a request stays
        valid unless request() asks otherwise; roles_of(tenant, principal): the trusted role directory;
        tool_authz: {tool_id: ToolAuthorization}; resource_attrs(tenant, type, id): the resource's attributes
        from application state."""
        self.connect, self.engine, self.authorizer, self.verify_approver = (connect, engine, authorizer,
                                                                            verify_approver)
        self.ttl = lifetime(ttl)
        self.roles_of, self.tool_authz, self.resource_attrs = roles_of, tool_authz, resource_attrs

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

    def _checks(self, conn, ctx, tool, arguments):
        """(floor verdict, reasons) from the current conversation, case and Cedar state."""
        row = conn.execute("SELECT c.principal_id, c.case_id, k.status FROM conversations c "
                           "LEFT JOIN cases k ON k.id = c.case_id WHERE c.id = %s",
                           (ctx.conversation_id,)).fetchone()
        if row is None or row[0] != ctx.principal_id or row[1] != ctx.case_id:
            return Verdict.DENY, ["the conversation does not belong to this customer and case"]
        if row[2] is None or row[2] in CLOSED_CASES:
            return Verdict.DENY, ["the case is not open"]
        rule = None
        if self.tool_authz is not None:
            rule = self.tool_authz.get(tool.tool_id)
            if rule is None:
                return Verdict.DENY, ["the tool has no registered authorization rule"]
            if rule.public:
                if tool.mutating:
                    return Verdict.DENY, ["a write cannot be declared public"]
                return Verdict.ALLOW, []
        resource = ctx.resource
        if not resource:  # reads included: nothing is authorized by leaving the resource out
            return Verdict.DENY, ["the call needs its target resource for the authorization check"]
        attrs = resource.get("attrs", {})
        if rule is not None:
            if (resource.get("action"), resource.get("type")) != (rule.action, rule.resource_type):
                return Verdict.DENY, ["the authorization resource does not match what the tool does"]
            named = str(getattr(arguments, rule.id_argument, None)) if rule.id_argument else None
            if rule.id_argument and str(resource.get("id")) != named:
                return Verdict.DENY, ["the authorization resource is not the one the tool acts on"]
            if self.resource_attrs is not None:
                attrs = self.resource_attrs(ctx.tenant_id, rule.resource_type, resource.get("id"))
            if (attrs or {}).get("tenant_id") != ctx.tenant_id:
                return Verdict.DENY, ["the resource belongs to another tenant"]
        roles = self.roles_of(ctx.tenant_id, ctx.principal_id) if self.roles_of is not None else ctx.roles
        verdict = self.authorizer.check(User(ctx.tenant_id, ctx.principal_id, tuple(roles)),
                                        resource.get("action", ""), resource.get("type", ""),
                                        resource.get("id", ""), attrs or {})
        if verdict == "allow":
            return Verdict.ALLOW, []
        if verdict == "approval_required":
            return Verdict.ASK_SPECIALIST, ["the authorization policy requires approval"]
        return Verdict.DENY, ["the authorization policy refuses this call"]

    def _decide(self, conn, ctx, tool, arguments, masked_state):
        floor, reasons = self._checks(conn, ctx, tool, arguments)
        return decide(tool, arguments, self._limits(conn), self.engine, masked_state,
                      recent=self._recent(conn, ctx.case_id), floor=floor, extra_reasons=reasons)

    def validate(self, ctx, tool, arguments, masked_state):
        with self.connect() as conn, conn.transaction():
            self._context(conn, ctx.tenant_id)
            return self._decide(conn, ctx, tool, arguments, masked_state)

    def request(self, ctx, tool, arguments, decision, ttl=None):
        """Open an approval request for a decision that needs one; returns its id. ttl: this request's
        lifetime (default: the gate's), at most MAX_APPROVAL_TTL.

        The caller's decision is not trusted: the code-level verdict (tenant limits and policy version, the
        ledger, the conversation and case, Cedar) is recomputed here, and the request records the stricter of
        that and the caller's verdict (Jev's part can only tighten). A decision that would need a weaker
        approval than the current state requires cannot produce one."""
        ttl = lifetime(ttl) if ttl is not None else self.ttl
        args_hash = arguments_hash(arguments)
        with self.connect() as conn, conn.transaction():
            self._context(conn, ctx.tenant_id)
            limits = self._limits(conn)
            floor, reasons = self._checks(conn, ctx, tool, arguments)
            recent = self._recent(conn, ctx.case_id)
            static, static_reasons, amount = static_gate(tool, arguments, limits, recent)
            verdict = max(Verdict(decision.verdict), static, floor)
            if verdict is Verdict.DENY:
                raise NotApproved(f"{tool.tool_id}: denied ({'; '.join(reasons + static_reasons)})")
            level = required_level(verdict, amount, limits)
            if level is None:
                raise ValueError(f"{verdict.name} needs no approval request")
            digest = decision_digest(ctx, tool.tool_id, args_hash, verdict, level, amount, limits.version)
            request_id, expires_at = conn.execute("SELECT gen_random_uuid(), now() + %s", (ttl,)).fetchone()
            seal = binding(ctx, tool.tool_id, args_hash, digest, limits.version, level, request_id,
                           expires_at)
            conn.execute(
                "INSERT INTO approval_requests (id, tenant_id, case_id, conversation_id, principal_id, "
                "handler_id, tool_id, arguments_hash, decision_id, decision_digest, policy_version, level, "
                "binding, expires_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (request_id, ctx.tenant_id, ctx.case_id, ctx.conversation_id, ctx.principal_id,
                 ctx.handler_id, tool.tool_id, args_hash, decision.decision_id, digest, limits.version,
                 level, seal, expires_at))
        return str(request_id)

    def grant(self, tenant_id, request_id, credential):
        """Approve a pending request with an approver credential; raises NotApproved / UnverifiedApprover."""
        request_id = request_id_of(request_id)
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
        request_id = request_id_of(request_id)
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
        request_id = request_id_of(request_id)
        row = conn.execute("SELECT status, expires_at, expires_at > now(), decision_digest, binding "
                           "FROM approval_requests WHERE id = %s FOR UPDATE", (request_id,)).fetchone()
        if row is None:
            raise NotApproved("no such approval request in this tenant")
        status, expires_at, live, stored_digest, seal = row
        if not live:
            raise NotApproved("the approval has expired")
        if status != "approved":
            raise NotApproved(f"the approval is {status}")
        args_hash = arguments_hash(arguments)
        fresh_digest = decision_digest(ctx, tool.tool_id, args_hash, decision.verdict, decision.level,
                                       decision.amount, decision.policy_version)
        if stored_digest is None or stored_digest != fresh_digest:
            raise NotApproved("the approval was given for a different call, context, policy or level: the "
                              "decision reached now differs from the approved one")
        current = binding(ctx, tool.tool_id, args_hash, fresh_digest, decision.policy_version, decision.level,
                          request_id, expires_at)
        if current != seal:
            raise NotApproved("the approval was given for a different call, context, policy or level")
        if conn.execute("UPDATE approval_requests SET status = 'consumed', consumed_at = now() WHERE id = %s "
                        "AND status = 'approved' AND expires_at > now()", (request_id,)).rowcount != 1:
            raise NotApproved("the approval was used meanwhile")
        return request_id
