"""Argument provenance: sensitive tool arguments come from the customer or a trusted tool field, never from
model text (FR-21 / TA-ADP-02: TA-D3, TA-D13).

Every proposed argument carries where it came from:

    user        the customer's own words: the value must appear in one of their (masked) turns, exactly, as
                the same number ("$1,240" -> 1240), or at >= 0.95 similarity for a near-identical identifier
    tool_field  a scalar at an allow-listed path (the source tool's trusted_outputs) of an earlier call's
                output, and the value must be what that output holds there
    llm         written by the model: allowed for descriptive fields only
    tool_text   free text from a tool output (logs, ticket bodies): never allowed for sensitive fields

check() returns a ready call with the provenance of every sensitive argument (for the audit record), asks the
customer when a sensitive argument is missing (nothing defaults, so "restart the database" asks which
environment), and raises ProvenanceViolation when one comes from anywhere else. Ownership of the resource
(tenant boundary) is still checked by authorization (Cedar) before the call runs.
"""

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum

from pydantic import ValidationError

from tools.schemas import sensitive_fields

SIMILAR_AT = 0.95
NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
WORD = re.compile(r"[^\s,;:!?()\"']+")


class Source(str, Enum):
    USER = "user"
    TOOL_FIELD = "tool_field"
    LLM = "llm"
    TOOL_TEXT = "tool_text"


class ProvenanceViolation(PermissionError):
    pass


@dataclass(frozen=True)
class Sourced:
    """A proposed argument value and where it came from. For TOOL_FIELD, `ref` is (call_id, json path)."""

    value: object
    source: Source
    ref: tuple[str, str] | None = None


@dataclass
class Checked:
    arguments: object | None              # the validated args model, None when the customer must be asked
    provenance: dict[str, dict] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    question: str | None = None


def _normal(text):
    return str(text).casefold().strip()


def said_by_customer(value, user_turns):
    """True when the customer's own words contain this value (see the module notes)."""
    if isinstance(value, bool):
        return False  # a yes / no is a decision, not something to find in the text
    if isinstance(value, int | float):
        return any(float(n.replace(",", "")) == float(value)
                   for turn in user_turns for n in NUMBER.findall(turn))
    wanted = _normal(value)
    if not wanted:
        return False
    if any(wanted in _normal(turn) for turn in user_turns):
        return True
    return any(SequenceMatcher(None, wanted, _normal(word)).ratio() >= SIMILAR_AT
               for turn in user_turns for word in WORD.findall(turn))


def lookup(output, path):
    """The value at a dotted path of a tool output, or KeyError."""
    for part in path.split("."):
        output = output[int(part)] if isinstance(output, list) else output[part]
    return output


def from_trusted_field(value, ref, calls, registry):
    """True when `ref` points at an allow-listed scalar of an earlier call's output holding this value."""
    if not ref or ref[0] not in calls:
        return False
    tool_id, output = calls[ref[0]]
    tool = registry.tools.get(tool_id)
    if tool is None or ref[1] not in tool.trusted_outputs:
        return False
    try:
        held = lookup(output, ref[1])
    except (KeyError, IndexError, ValueError, TypeError):
        return False
    return isinstance(held, str | int | float | bool) and held == value


def check(registry, tool, proposed, user_turns, calls):
    """proposed: {field: Sourced}; user_turns: the customer's masked turns;
    calls: {call_id: (tool_id, output)} of the earlier tool calls."""
    sensitive = sensitive_fields(tool.args)
    missing = sorted(name for name in sensitive if name not in proposed or proposed[name].value in (None, ""))
    if missing:
        names = " and ".join(name.replace("_", " ") for name in missing)
        return Checked(None, missing=missing, question=f"To go ahead I need the {names}. Which should I use?")
    provenance = {}
    for name in sensitive:
        sourced = proposed[name]
        if sourced.source is Source.USER and said_by_customer(sourced.value, user_turns):
            provenance[name] = {"source": "user"}
        elif (sourced.source is Source.TOOL_FIELD
              and from_trusted_field(sourced.value, sourced.ref, calls, registry)):
            provenance[name] = {"source": "tool_field", "call_id": sourced.ref[0], "path": sourced.ref[1]}
        else:
            raise ProvenanceViolation(f"{tool.tool_id}.{name}: a sensitive argument from "
                                      f"{sourced.source.value} that does not trace to the customer or a "
                                      "trusted tool field")
    try:
        arguments = tool.args(**{name: sourced.value for name, sourced in proposed.items()})
    except ValidationError as error:
        raise ProvenanceViolation(f"{tool.tool_id}: arguments do not fit the schema: {error}") from error
    return Checked(arguments, provenance)
