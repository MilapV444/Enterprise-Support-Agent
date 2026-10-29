"""M5-05: contract tests for the formats components share (NFR-25 / TQ-ADP-05; TQ-ADP-02 TQ-D4's contract
tests).

Each shared format's schema is pinned in tests/contracts/snapshots/. A change fails here with what changed,
split into breaking changes (a field or option removed, a type changed, a field newly required: a reader on
the previous release breaks) and additive ones. Change a format deliberately: update its consumers, and for
the thread state bump SCHEMA_VERSION with a migration (test_checkpoints.py), then regenerate the snapshots
with UPDATE_CONTRACTS=1.
"""

import json
import os
import typing
from enum import Enum
from pathlib import Path

import pytest
from pydantic import BaseModel

from agents.contracts import Blocker, Brief, Result, Status
from agents.merge import Claim
from agents.topology import Role
from channels.api.envelope import EventType, InboundTurn, TurnRequest
from hitl.approval import RejectReason, Submission
from hitl.queues import Domain, Packet, Reason
from schemas import thread_state
from schemas.diagnostic import IncidentDiagnosticPacket
from schemas.thread_state import Stage, Step, ThreadState, Triage
from tools.registry import Risk

SNAPSHOTS = Path(__file__).with_name("snapshots")
FORMATS = {"InboundTurn": InboundTurn, "TurnRequest": TurnRequest, "EventType": EventType,
           "ThreadState": ThreadState, "Stage": Stage, "Triage": Triage, "Step": Step,
           "Brief": Brief, "Result": Result, "Status": Status, "Blocker": Blocker, "Role": Role,
           "Claim": Claim,
           "Packet": Packet, "Reason": Reason, "Domain": Domain, "Submission": Submission,
           "RejectReason": RejectReason, "IncidentDiagnosticPacket": IncidentDiagnosticPacket, "Risk": Risk}


def schema(fmt):
    if isinstance(fmt, type) and issubclass(fmt, Enum):
        return {"enum": sorted(member.value for member in fmt)}
    if isinstance(fmt, type) and issubclass(fmt, BaseModel):
        return fmt.model_json_schema()
    hints = typing.get_type_hints(fmt, include_extras=True)             # a TypedDict: the checkpoint's keys
    return {"schema_version": thread_state.SCHEMA_VERSION,
            "properties": {key: {"type": repr(hint)} for key, hint in sorted(hints.items())}}


def properties(spec):
    """{dotted field: (type description, required)} through nested $defs."""
    defs, out = spec.get("$defs", {}), {}

    def walk(node, prefix):
        required = set(node.get("required", []))
        for key, field in node.get("properties", {}).items():
            ref = field.get("$ref") or next((a["$ref"] for a in field.get("anyOf", []) if "$ref" in a), None)
            kind = {k: field[k] for k in ("type", "anyOf", "enum", "const", "items") if k in field}
            out[prefix + key] = (json.dumps(kind, sort_keys=True), key in required)
            if ref and prefix.count(".") < 3:
                walk(defs.get(ref.rsplit("/", 1)[-1], {}), f"{prefix}{key}.")
    walk(spec, "")
    for name, definition in defs.items():
        if "enum" in definition:
            out[f"$defs.{name}"] = (json.dumps(sorted(definition["enum"])), True)
    if "enum" in spec:
        out["enum"] = (json.dumps(spec["enum"]), True)
    return out


def changes(old, new):
    """(breaking, additive) between two snapshots."""
    before, after = properties(old), properties(new)
    breaking, additive = [], []
    for key, (kind, required) in before.items():
        if key not in after:
            breaking.append(f"{key} removed")
        elif after[key][0] != kind:
            values = (json.loads(kind), json.loads(after[key][0]))
            if all(isinstance(v, list) for v in values) and set(values[0]) <= set(values[1]):
                additive.append(f"{key} gained {sorted(set(values[1]) - set(values[0]))}")
            else:
                breaking.append(f"{key} changed type")
        elif after[key][1] and not required:
            breaking.append(f"{key} is now required")
    for key, (_, required) in after.items():
        if key not in before:
            (breaking if required else additive).append(f"{key} added{' as required' if required else ''}")
    if old.get("schema_version") != new.get("schema_version"):
        additive.append(f"schema_version {old.get('schema_version')} -> {new.get('schema_version')}")
    return breaking, additive


@pytest.mark.parametrize("name", FORMATS)
def test_a_shared_format_changes_only_on_purpose(name):
    path, current = SNAPSHOTS / f"{name}.json", schema(FORMATS[name])
    if os.environ.get("UPDATE_CONTRACTS") == "1":
        SNAPSHOTS.mkdir(exist_ok=True)
        path.write_text(json.dumps(current, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    pinned = json.loads(path.read_text(encoding="utf-8"))
    if current != pinned:
        breaking, additive = changes(pinned, current)
        pytest.fail(f"{name} changed. Breaking: {breaking or 'none'}. Additive: {additive or 'none'}. Update "
                    "its consumers (and, for ThreadState, SCHEMA_VERSION and a migration), then regenerate "
                    "with UPDATE_CONTRACTS=1.")


def test_the_thread_state_cannot_change_without_a_new_schema_version():
    pinned = json.loads((SNAPSHOTS / "ThreadState.json").read_text(encoding="utf-8"))
    current = schema(ThreadState)
    if current["properties"] != pinned["properties"]:
        assert current["schema_version"] > pinned["schema_version"], "bump SCHEMA_VERSION and add a migration"


def test_the_comparison_tells_breaking_from_additive_changes():
    old = {"properties": {"a": {"type": "string"}, "b": {"type": "integer"}}, "required": ["a"],
           "$defs": {"Kind": {"enum": ["x", "y"]}}}
    new = {"properties": {"a": {"type": "integer"}, "c": {"type": "string"}, "d": {"type": "string"}},
           "required": ["a", "d"], "$defs": {"Kind": {"enum": ["x", "y", "z"]}}}
    breaking, additive = changes(old, new)
    assert sorted(breaking) == ["a changed type", "b removed", "d added as required"]
    assert sorted(additive) == ["$defs.Kind gained ['z']", "c added"]
    assert changes({"enum": ["a", "b"]}, {"enum": ["a"]})[0] == ["enum changed type"]
