"""M2-09a security fixes in the approval gate: authorization inputs come from trusted sources (the
conversation record, the role directory, the tool's registered rule, application state), reads are never
authorized by omission, and approvals are bound to a deterministic digest of the decision recomputed by the
gate itself. Runs against the compose Postgres with the production Cedar policies; Jev is scripted."""

import psycopg
import pytest
from pydantic import BaseModel

from data.migrate import psql
from safety.authz.cedar import Authorizer, entity
from tests.tools.validation.test_validation import (  # the database and policy_dir fixtures: conftest.py
    DB,
    REFUND,
    STATE,
    account,
    case,
    connect,
    engine,
    refund,
    verify,
)
from tools.registry import Registry
from tools.schemas import arg
from tools.validation import Decision, Verdict
from tools.validation.approvals import ApprovalGate, CallContext, NotApproved, ToolAuthorization


class InvoiceArgs(BaseModel):
    invoice_id: str = arg(sensitive=True)


class ClusterArgs(BaseModel):
    cluster_id: str = arg(sensitive=True)


def build():
    registry = Registry()
    registry.tool("billing.get_invoice", args=InvoiceArgs, description="Read an invoice", risk="read_only",
                  stages={"DELIBERATING"}, author="ana", reviewed_by="ben")(lambda a: {"id": a.invoice_id})
    registry.tool("kb.search", args=InvoiceArgs, description="Search the public help articles",
                  risk="read_only", stages={"DELIBERATING"}, author="ana", reviewed_by="ben")(lambda a: [])
    registry.tool("cloud.restart_cluster", args=ClusterArgs, description="Restart a database cluster",
                  risk="low_risk_write", stages={"EXECUTING_SOP"}, author="ana", reviewed_by="ben")(
        lambda a: {"restarted": a.cluster_id})
    return registry.freeze()


TOOLS = build().tools
INVOICE, SEARCH, RESTART = TOOLS["billing.get_invoice"], TOOLS["kb.search"], TOOLS["cloud.restart_cluster"]
RULES = {"billing.refund": ToolAuthorization("update_contact", "Account"),
         "billing.get_invoice": ToolAuthorization("read_account", "Account", id_argument="invoice_id"),
         "cloud.restart_cluster": ToolAuthorization("restart_cluster", "Environment",
                                                    id_argument="cluster_id"),
         "kb.search": ToolAuthorization(public=True)}
DIRECTORY = {}  # the trusted role directory: (tenant, principal) -> roles


@pytest.fixture(autouse=True)
def clean_directory():
    DIRECTORY.clear()


def trusted(policy_dir, **options):
    return ApprovalGate(connect, engine(), Authorizer(policy_dir=policy_dir), verify,
                        roles_of=lambda tenant, principal: DIRECTORY.get((tenant, principal), ()),
                        tool_authz=RULES, **options)


def with_resource(ctx, resource, roles=()):
    return CallContext(ctx.tenant_id, ctx.case_id, ctx.conversation_id, ctx.principal_id, ctx.handler_id,
                       roles, resource)


def invoice_resource(invoice="INV-1", owner="sarah", tenant="t_us"):
    return {"action": "read_account", "type": "Account", "id": invoice,
            "attrs": {"tenant_id": tenant, "owner": entity("User", owner)}}


def environment(cluster="db-1", tenant="t_us"):
    return {"action": "restart_cluster", "type": "Environment", "id": cluster,
            "attrs": {"tenant_id": tenant, "name": "production"}}


def verdict(gate, ctx, tool, arguments):
    return gate.validate(ctx, tool, arguments, STATE).verdict


# 1. Trusted identity ----------------------------------------------------------------------------------------

def test_a_forged_tenant_or_principal_finds_no_conversation_and_is_denied(database, policy_dir):
    gate, ctx = trusted(policy_dir), case()
    forged_tenant = CallContext("t_eu", ctx.case_id, ctx.conversation_id, "sarah", ctx.handler_id,
                                resource=account(tenant="t_eu"))
    forged_principal = CallContext(ctx.tenant_id, ctx.case_id, ctx.conversation_id, "bob", ctx.handler_id,
                                   resource=account(owner="bob"))
    assert verdict(gate, forged_tenant, REFUND, refund(20)) is Verdict.DENY
    assert verdict(gate, forged_principal, REFUND, refund(20)) is Verdict.DENY


@pytest.mark.parametrize("claimed", [("tenant_admin",), ("cloud_admin",), ("tenant_admin", "cloud_admin")])
def test_roles_the_caller_claims_grant_nothing(database, policy_dir, claimed):
    gate, ctx = trusted(policy_dir), case()
    bobs_account = with_resource(ctx, account(owner="bob"), roles=claimed)  # tenant_admin would allow this
    assert verdict(gate, bobs_account, REFUND, refund(20)) is Verdict.DENY
    production = with_resource(ctx, environment(), roles=claimed)          # cloud_admin would allow this
    assert verdict(gate, production, RESTART, ClusterArgs(cluster_id="db-1")) is Verdict.DENY


def test_roles_from_the_trusted_directory_authorize(database, policy_dir):
    gate, ctx = trusted(policy_dir), case()
    DIRECTORY[("t_us", "sarah")] = ("tenant_admin", "cloud_admin")
    assert verdict(gate, with_resource(ctx, account(owner="bob")), REFUND, refund(20)) is Verdict.ALLOW
    assert verdict(gate, with_resource(ctx, environment()), RESTART, ClusterArgs(cluster_id="db-1")) is \
        Verdict.ALLOW


# 2. Reads are never authorized by omission ----------------------------------------------------------------

@pytest.mark.parametrize("trusted_mode", [True, False])
def test_a_protected_read_without_its_resource_is_denied(database, policy_dir, trusted_mode):
    legacy = ApprovalGate(connect, engine(), Authorizer(policy_dir=policy_dir), verify)
    gate = trusted(policy_dir) if trusted_mode else legacy
    ctx = with_resource(case(), {})
    assert verdict(gate, ctx, INVOICE, InvoiceArgs(invoice_id="INV-1")) is Verdict.DENY


def test_a_protected_read_with_its_resource_is_decided_by_cedar(database, policy_dir):
    gate, ctx = trusted(policy_dir), case()
    own = with_resource(ctx, invoice_resource())
    assert verdict(gate, own, INVOICE, InvoiceArgs(invoice_id="INV-1")) is Verdict.ALLOW
    assert verdict(gate, with_resource(ctx, invoice_resource(owner="bob")), INVOICE,
                   InvoiceArgs(invoice_id="INV-1")) is Verdict.DENY


def test_only_an_explicitly_public_read_needs_no_resource(database, policy_dir):
    gate, ctx = trusted(policy_dir), case()
    assert verdict(gate, with_resource(ctx, {}), SEARCH, InvoiceArgs(invoice_id="x")) is Verdict.ALLOW
    unregistered = trusted(policy_dir)
    unregistered.tool_authz = {k: v for k, v in RULES.items() if k != "billing.get_invoice"}
    assert verdict(unregistered, with_resource(ctx, invoice_resource()), INVOICE,
                   InvoiceArgs(invoice_id="INV-1")) is Verdict.DENY  # no rule: denied, not allowed
    public_write = trusted(policy_dir)
    public_write.tool_authz = {**RULES, "cloud.restart_cluster": ToolAuthorization(public=True)}
    no_resource = with_resource(ctx, {})
    assert verdict(public_write, no_resource, RESTART, ClusterArgs(cluster_id="db-1")) is Verdict.DENY


# 3. The Cedar request is bound to what the tool does --------------------------------------------------------

@pytest.mark.parametrize("resource", [
    {**environment(), "action": "read_account"},       # a harmless action named for a production write
    {**environment(), "type": "Account"},              # the wrong resource type
    environment(cluster="db-2"),                       # another cluster than the tool's argument
    environment(tenant="t_eu"),                        # another tenant's environment
])
def test_a_resource_that_does_not_match_the_tool_is_denied(database, policy_dir, resource):
    gate, ctx = trusted(policy_dir), case()
    DIRECTORY[("t_us", "sarah")] = ("cloud_admin",)
    mismatched = with_resource(ctx, resource)
    assert verdict(gate, mismatched, RESTART, ClusterArgs(cluster_id="db-1")) is Verdict.DENY


def test_another_tenants_resource_is_refused_by_the_gate_itself_not_only_by_cedar(database, policy_dir):
    gate, ctx = trusted(policy_dir), case()
    DIRECTORY[("t_us", "sarah")] = ("cloud_admin",)
    decision = gate.validate(with_resource(ctx, environment(tenant="t_eu")), RESTART,
                             ClusterArgs(cluster_id="db-1"), STATE)
    assert decision.verdict is Verdict.DENY and "the resource belongs to another tenant" in decision.reasons


def test_a_refund_cannot_pass_as_a_read(database, policy_dir):
    gate, ctx = trusted(policy_dir), case()
    as_read = with_resource(ctx, {**account(), "action": "read_account"})
    assert verdict(gate, as_read, REFUND, refund(20)) is Verdict.DENY


def test_application_state_overrides_the_attributes_the_caller_sends(database, policy_dir):
    """The caller says Sarah owns the account; the CRM says Bob does: Cedar sees Bob."""
    def crm(tenant, kind, ident):
        return {"tenant_id": tenant, "owner": entity("User", "bob")}
    gate, ctx = trusted(policy_dir, resource_attrs=crm), case()
    assert verdict(gate, with_resource(ctx, invoice_resource(owner="sarah")), INVOICE,
                   InvoiceArgs(invoice_id="INV-1")) is Verdict.DENY


# 4 and 5. Approvals bound to the decision the gate itself reaches -------------------------------------------

def fabricated(verdict, level):
    return Decision("00000000-0000-0000-0000-000000000000", "billing.refund", verdict, verdict, verdict,
                    level=level, policy_version=999)


def stored(request_id):
    return psql(DB, f"SELECT level, policy_version FROM approval_requests WHERE id = '{request_id}'")[0]


def test_a_fabricated_weaker_decision_cannot_make_a_weaker_approval(database, policy_dir):
    gate, ctx = trusted(policy_dir), case()
    weak = gate.request(ctx, REFUND, refund(1240), fabricated(Verdict.ASK_USER, "customer"))
    level, version = stored(weak)
    assert level == "specialist" and int(version) != 999  # recomputed: the current requirement and policy
    with pytest.raises(NotApproved, match="needs one of"):
        gate.grant("t_us", weak, "tok-sarah")             # the customer cannot confirm a specialist approval
    gate.grant("t_us", weak, "tok-sam")                   # the request is the real, current requirement:
    gate.execute(ctx, REFUND, refund(1240), STATE, weak)  # a specialist's approval of it runs
    allowed = gate.request(ctx, REFUND, refund(5000), fabricated(Verdict.ALLOW, None))
    assert stored(allowed)[0] == "senior_specialist"


def test_a_request_for_a_call_that_is_denied_is_refused(database, policy_dir):
    gate, ctx = trusted(policy_dir), case()
    with pytest.raises(NotApproved, match="denied"):
        gate.request(with_resource(ctx, account(owner="bob")), REFUND, refund(1240),
                     fabricated(Verdict.ASK_SPECIALIST, "specialist"))


def test_an_approval_for_one_decision_cannot_run_another(database, policy_dir):
    gate, ctx = trusted(policy_dir), case()
    decision = gate.validate(ctx, REFUND, refund(1240), STATE)
    good = gate.request(ctx, REFUND, refund(1240), decision)
    gate.grant("t_us", good, "tok-sam")
    gate.execute(ctx, REFUND, refund(1240), STATE, good)   # D1 unchanged: it runs

    tampered = gate.request(ctx, REFUND, refund(1240), decision)
    gate.grant("t_us", tampered, "tok-sam")
    psql(DB, f"UPDATE approval_requests SET decision_digest = 'a-different-decision' WHERE id = '{tampered}'")
    with pytest.raises(NotApproved, match="decision reached now differs"):
        gate.execute(ctx, REFUND, refund(1240), STATE, tampered)

    old = gate.request(ctx, REFUND, refund(1240), decision)
    gate.grant("t_us", old, "tok-sam")
    psql(DB, f"UPDATE approval_requests SET decision_digest = NULL WHERE id = '{old}'")
    with pytest.raises(NotApproved, match="decision reached now differs"):  # no digest: refused
        gate.execute(ctx, REFUND, refund(1240), STATE, old)


def test_a_decision_that_changes_after_approval_is_refused(database, policy_dir):
    """Approved under Jev 'ask' (a customer confirmation); by execution Jev says 'deny'."""
    asking = ApprovalGate(connect, engine(verdict="ASK"), Authorizer(policy_dir=policy_dir), verify,
                          roles_of=lambda tenant, principal: (), tool_authz=RULES)
    ctx = case()
    decision = asking.validate(ctx, REFUND, refund(20), STATE)
    request_id = asking.request(ctx, REFUND, refund(20), decision)
    asking.grant("t_us", request_id, "tok-sarah")
    denying = ApprovalGate(connect, engine(verdict="DENY"), Authorizer(policy_dir=policy_dir), verify,
                           roles_of=lambda tenant, principal: (), tool_authz=RULES)
    with pytest.raises(NotApproved, match="denied"):
        denying.execute(ctx, REFUND, refund(20), STATE, request_id)


def test_the_digest_column_is_written_and_the_ledger_stays_one_row_per_attempt(database, policy_dir):
    gate, ctx = trusted(policy_dir), case()
    decision = gate.validate(ctx, REFUND, refund(1240), STATE)
    request_id = gate.request(ctx, REFUND, refund(1240), decision)
    digest = psql(DB, f"SELECT decision_digest IS NOT NULL FROM approval_requests WHERE id = '{request_id}'")
    assert digest == [["t"]]
    gate.grant("t_us", request_id, "tok-sam")
    gate.execute(ctx, REFUND, refund(1240), STATE, request_id)
    rows = psql(DB, f"SELECT count(*), count(DISTINCT decision_id) FROM financial_writes WHERE case_id = "
                    f"'{ctx.case_id}'")
    assert rows == [["1", "1"]]
    with psycopg.connect(f"postgresql://agent:change-me@127.0.0.1:5432/{DB}", autocommit=True) as conn, \
            pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute("INSERT INTO financial_writes (tenant_id, case_id, tool_id, decision_id, amount_usd) "
                     "SELECT tenant_id, case_id, tool_id, decision_id, 1 FROM financial_writes "
                     f"WHERE case_id = '{ctx.case_id}'")
