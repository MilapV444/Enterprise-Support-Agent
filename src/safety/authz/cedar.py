"""Cedar authorization (FR-33 / SG-ADP-04: SG-D8, SG-D9, SG-D10, SG-D17).

Policies and their schema live in policies/ (a release-gated behaviour path) and are validated against each
other on load. check() answers "allow", "deny" or "approval_required":

- default deny: anything no policy permits is refused, and nothing crosses tenants;
- a production change refused only because a blackout window is active comes back as "approval_required",
  so it is raised to a human instead of dropped; whether a blackout is active is decided in code
  (in_blackout);
- if the engine cannot answer, writes are denied at once, and reads may reuse a verdict cached within the last
  5 minutes. Writes are never cached. Which actions are reads comes from the schema's action groups.
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import cedarpy

POLICY_DIR = Path(__file__).resolve().parents[3] / "policies"
READ_CACHE_SECONDS = 300


class PolicyError(RuntimeError):
    pass


@dataclass(frozen=True)
class User:
    tenant_id: str
    id: str
    roles: tuple[str, ...] = field(default_factory=tuple)


def entity(kind, ident):
    return {"__entity": {"type": kind, "id": ident}}


def in_blackout(windows, now):
    """True when `now` (aware datetime) falls inside any {"start", "end"} ISO-8601 window."""
    return any(datetime.fromisoformat(w["start"]) <= now <= datetime.fromisoformat(w["end"]) for w in windows)


def read_actions(schema):
    """Actions that belong to the "read" action group in the schema."""
    actions = schema[""]["actions"]
    return {name for name, spec in actions.items()
            if any(parent.get("id") == "read" for parent in spec.get("memberOf", [])) and "appliesTo" in spec}


class Authorizer:
    def __init__(self, policy_dir=POLICY_DIR, evaluate=cedarpy.is_authorized, clock=time.monotonic,
                 cache_seconds=READ_CACHE_SECONDS):
        self.policies = (Path(policy_dir) / "support.cedar").read_text(encoding="utf-8")
        self.schema = json.loads((Path(policy_dir) / "support.cedarschema.json").read_text(encoding="utf-8"))
        result = cedarpy.validate_policies(self.policies, json.dumps(self.schema))
        if not result.validation_passed:
            raise PolicyError("; ".join(map(str, result.errors)))
        self.reads = read_actions(self.schema)
        self.evaluate, self.clock, self.cache_seconds, self.cache = evaluate, clock, cache_seconds, {}

    def _allowed(self, user, action, resource_type, resource_id, attrs, blackout):
        entities = [{"uid": {"type": "User", "id": user.id}, "attrs": {"tenant_id": user.tenant_id},
                     "parents": [{"type": "Role", "id": role} for role in user.roles]}]
        entities += [{"uid": {"type": "Role", "id": role}, "attrs": {}, "parents": []} for role in user.roles]
        entities.append({"uid": {"type": resource_type, "id": resource_id}, "attrs": attrs, "parents": []})
        request = {"principal": f'User::"{user.id}"', "action": f'Action::"{action}"',
                   "resource": f'{resource_type}::"{resource_id}"', "context": {"in_blackout": blackout}}
        return self.evaluate(request, self.policies, entities, json.dumps(self.schema)).allowed

    def check(self, user, action, resource_type, resource_id, attrs, blackout=False):
        """attrs: the resource's attributes; refer to users as entity("User", id)."""
        is_read = action in self.reads
        key = (user, action, resource_type, resource_id, json.dumps(attrs, sort_keys=True), blackout)
        try:
            if self._allowed(user, action, resource_type, resource_id, attrs, blackout):
                verdict = "allow"
            elif blackout and self._allowed(user, action, resource_type, resource_id, attrs, False):
                verdict = "approval_required"
            else:
                verdict = "deny"
        except Exception:  # engine unavailable: fail closed for writes, short cache for reads
            if is_read and key in self.cache and self.clock() - self.cache[key][0] <= self.cache_seconds:
                return self.cache[key][1]
            return "deny"
        if is_read:
            self.cache[key] = (self.clock(), verdict)
        return verdict
