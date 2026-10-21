"""M1-15: Cedar policies for ticket visibility, account data, production changes, blackout windows, the tenant
boundary and fail-closed writes (FR-33, NFR-22)."""

import json
from datetime import datetime, timezone
from pathlib import Path

import cedarpy
import pytest

from safety.authz.cedar import POLICY_DIR, Authorizer, User, entity, in_blackout, read_actions

SARAH = User("t_us", "sarah")
BOB = User("t_us", "bob")
SUPPORT = User("t_us", "sam", ("tenant_support",))
ADMIN = User("t_us", "ada", ("tenant_admin",))
OPS = User("t_us", "omar", ("cloud_admin",))
EU_SUPPORT = User("t_eu", "eve", ("tenant_support",))


def ticket(author="sarah", tenant="t_us"):
    return {"tenant_id": tenant, "author": entity("User", author)}


def account(owner="sarah", tenant="t_us"):
    return {"tenant_id": tenant, "owner": entity("User", owner)}


PROD = {"tenant_id": "t_us", "name": "production"}


@pytest.fixture
def authz():
    return Authorizer()


def test_policies_validate_against_the_schema_and_every_action_is_classified():
    policies = (Path(POLICY_DIR) / "support.cedar").read_text()
    schema = json.loads((Path(POLICY_DIR) / "support.cedarschema.json").read_text())
    assert cedarpy.validate_policies(policies, json.dumps(schema)).validation_passed
    assert read_actions(schema) == {"read_ticket", "read_account"}


@pytest.mark.parametrize("user, verdict", [(SARAH, "allow"), (BOB, "deny"), (SUPPORT, "allow"),
                                           (ADMIN, "allow"), (EU_SUPPORT, "deny"), (OPS, "deny")])
def test_tickets_are_visible_to_their_author_and_the_tenants_support_and_admins(authz, user, verdict):
    assert authz.check(user, "read_ticket", "Ticket", "T-1", ticket()) == verdict


@pytest.mark.parametrize("user, verdict",
                         [(SARAH, "allow"), (BOB, "deny"), (ADMIN, "allow"), (SUPPORT, "deny")])
def test_account_changes_are_for_the_owner_and_admins(authz, user, verdict):
    assert authz.check(user, "update_contact", "Account", "A-1", account()) == verdict


def test_production_changes_need_a_cloud_admin_and_a_blackout_needs_a_human(authz):
    assert authz.check(OPS, "restart_cluster", "Environment", "prod", PROD) == "allow"
    assert authz.check(SARAH, "restart_cluster", "Environment", "prod", PROD) == "deny"
    frozen = authz.check(OPS, "restart_cluster", "Environment", "prod", PROD, blackout=True)
    assert frozen == "approval_required"
    assert authz.check(SARAH, "terminate_service", "Environment", "prod", PROD, blackout=True) == "deny"
    assert authz.check(SARAH, "read_ticket", "Ticket", "T-1", ticket(), blackout=True) == "allow"


def test_nothing_crosses_tenants_even_for_admins(authz):
    assert authz.check(ADMIN, "read_account", "Account", "A-9", account("zoe", tenant="t_eu")) == "deny"
    assert authz.check(OPS, "restart_cluster", "Environment", "prod", {**PROD, "tenant_id": "t_eu"}) == "deny"


def test_anything_not_permitted_is_denied(authz):
    assert authz.check(ADMIN, "drop_database", "Environment", "prod", PROD) == "deny"
    assert authz.check(SARAH, "read_ticket", "Ticket", "T-1", {"tenant_id": "t_us"}) == "deny"  # bad shape


def flaky(clock):
    """An evaluator that works until `down` is set, then raises like an unreachable engine."""
    state = {"down": False}

    def evaluate(*args):
        if state["down"]:
            raise ConnectionError("policy engine unreachable")
        return cedarpy.is_authorized(*args)
    return Authorizer(evaluate=evaluate, clock=lambda: clock[0]), state


def test_engine_down_denies_writes_and_serves_recent_read_verdicts_only():
    clock = [1000.0]
    authz, state = flaky(clock)
    assert authz.check(SARAH, "read_ticket", "Ticket", "T-1", ticket()) == "allow"
    assert authz.check(SARAH, "update_contact", "Account", "A-1", account()) == "allow"
    state["down"] = True
    assert authz.check(SARAH, "read_ticket", "Ticket", "T-1", ticket()) == "allow"       # cached read
    assert authz.check(SARAH, "update_contact", "Account", "A-1", account()) == "deny"   # writes fail closed
    assert authz.check(SARAH, "read_account", "Account", "A-1", account()) == "deny"    # never cached
    clock[0] += 301
    assert authz.check(SARAH, "read_ticket", "Ticket", "T-1", ticket()) == "deny"       # cache expired


def test_cached_reads_are_per_principal_and_resource():
    clock = [0.0]
    authz, state = flaky(clock)
    authz.check(SARAH, "read_ticket", "Ticket", "T-1", ticket())
    state["down"] = True
    assert authz.check(BOB, "read_ticket", "Ticket", "T-1", ticket()) == "deny"
    assert authz.check(SARAH, "read_ticket", "Ticket", "T-2", ticket()) == "deny"


def test_blackout_windows_are_decided_in_code():
    windows = [{"start": "2026-11-27T00:00:00+00:00", "end": "2026-11-30T23:59:59+00:00"}]
    assert in_blackout(windows, datetime(2026, 11, 28, 12, tzinfo=timezone.utc))
    assert not in_blackout(windows, datetime(2026, 12, 1, tzinfo=timezone.utc))
    assert not in_blackout([], datetime(2026, 11, 28, tzinfo=timezone.utc))


def copy_schema(folder):
    schema = (Path(POLICY_DIR) / "support.cedarschema.json").read_text()
    (folder / "support.cedarschema.json").write_text(schema)


def test_invalid_policies_refuse_to_load(tmp_path):
    (tmp_path / "support.cedar").write_text('permit (principal, action == Action::"no_such_action", '
                                            'resource);')
    copy_schema(tmp_path)
    with pytest.raises(Exception, match="no_such_action|unrecognized|not declared|undeclared"):
        Authorizer(policy_dir=tmp_path)


def test_the_tenant_boundary_holds_even_if_a_future_permit_forgets_it(tmp_path):
    careless = 'permit (principal in Role::"tenant_support", action == Action::"read_ticket", resource);'
    real = (Path(POLICY_DIR) / "support.cedar").read_text()
    (tmp_path / "support.cedar").write_text(real + "\n" + careless)
    copy_schema(tmp_path)
    authz = Authorizer(policy_dir=tmp_path)
    assert authz.check(SUPPORT, "read_ticket", "Ticket", "T-9", ticket("zoe", tenant="t_eu")) == "deny"
