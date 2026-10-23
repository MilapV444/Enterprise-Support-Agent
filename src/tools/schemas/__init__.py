"""Tool argument schemas: every field says whether it is sensitive (FR-21 / TA-ADP-02: TA-D3; FR-20 / TA-D2).

    class RestartCluster(BaseModel):
        cluster_id: str = arg(sensitive=True)
        environment: Literal["staging", "production"] = arg(sensitive=True)
        note: str = arg(sensitive=False, default="")

Sensitive fields (ids, amounts, environments, recipients, scopes) must come from the customer's own words or
an allow-listed structured tool output, never from model text (tools.registry.provenance). review() is the
schema gate a tool must pass to be registered:
- every field declares sensitive=True or False;
- sensitive fields have no default, so nothing silently defaults to production;
- types are primitives, enums, literals or reviewed sub-models (and lists / optionals of those): no dict,
  no Any.
"""

import types
import typing
from enum import Enum

from pydantic import BaseModel, Field
from pydantic_core import PydanticUndefined

PRIMITIVES = (str, int, float, bool)


def arg(sensitive, default=PydanticUndefined, **options):
    """A tool argument field; sensitive=True marks values that need provenance."""
    extra = {**options.pop("json_schema_extra", {}), "sensitive": sensitive}
    return Field(default, json_schema_extra=extra, **options)


def is_sensitive(info):
    return (info.json_schema_extra or {}).get("sensitive") is True


def sensitive_fields(schema):
    return {name for name, info in schema.model_fields.items() if is_sensitive(info)}


def _type_problems(annotation, where):
    origin = typing.get_origin(annotation)
    if origin is typing.Literal or annotation in PRIMITIVES:
        return []
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return []
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [f"{where}.{problem}" for problem in review(annotation)]
    if origin in (list, typing.Union, types.UnionType):
        return [problem for inner in typing.get_args(annotation) if inner is not type(None)
                for problem in _type_problems(inner, where)]
    return [f"{where}: type {annotation!r} is not allowed (primitives, enums, literals or sub-models only)"]


def review(schema):
    """Problems that keep a tool schema out of the registry; empty when it passes."""
    problems = []
    for name, info in schema.model_fields.items():
        declared = (info.json_schema_extra or {}).get("sensitive")
        if not isinstance(declared, bool):
            problems.append(f"{name}: must declare sensitive=True or sensitive=False")
        if declared is True and not info.is_required():
            problems.append(f"{name}: a sensitive argument may not have a default")
        problems += _type_problems(info.annotation, name)
    return problems
