"""Tool registry and selection (FR-20 / TA-ADP-01: TA-D1, TA-D2, TA-D16).

Tools are plain typed Python functions registered in code with @registry.tool(...). The registry is frozen
when the application starts: nothing registers at run time, and no tool comes from outside (no MCP in v1).

Each tool declares a risk class (read_only < low_risk_write < high_risk_write < destructive_irreversible), the
lowest identity tier and the roles it needs, the statechart stages it may run in, and the structured output
fields other tools may take arguments from. A tool without a second engineer's review (reviewed_by) always
needs human approval, whatever risk class its author declared.

Selection, per turn:
1. code: only tools the tier, roles and current stage allow; an anonymous user gets read-only tools only;
2. Jev: if more than 5 remain, a shortlist of the 5 most relevant (one yes/no question per tool);
3. Jev: one tool from the shortlist (Gate 3, DecisionEngine.select_tool).
No relevant tool, low confidence or Jev down at any step: no tool, and the turn goes to a human.
"""

from dataclasses import dataclass, field
from enum import Enum

from channels.identity.tiers import Tier
from core.orchestrator.decisions import NUMBERS, JevUnavailable
from tools.schemas import review

SHORTLIST = 5
RELEVANT_AT = 0.50
RELEVANT = "Is this tool relevant to what the customer is asking for right now? Tool: {description}"


class Risk(str, Enum):
    READ_ONLY = "read_only"
    LOW_RISK_WRITE = "low_risk_write"
    HIGH_RISK_WRITE = "high_risk_write"
    DESTRUCTIVE_IRREVERSIBLE = "destructive_irreversible"


class RegistryFrozen(RuntimeError):
    pass


@dataclass(frozen=True)
class Tool:
    tool_id: str
    func: object
    args: type
    description: str
    risk: Risk
    stages: frozenset[str]
    min_tier: Tier = Tier.T1_VERIFIED
    roles: frozenset[str] = frozenset()
    trusted_outputs: frozenset[str] = frozenset()  # output paths other tools may take sensitive args from
    author: str = ""
    reviewed_by: str | None = None

    @property
    def mutating(self):
        return self.risk is not Risk.READ_ONLY

    @property
    def needs_approval(self):
        """True when a human must approve each call (TA-D16; approval cards are TA-ADP-03)."""
        return not self.reviewed_by or self.risk in (Risk.HIGH_RISK_WRITE, Risk.DESTRUCTIVE_IRREVERSIBLE)


@dataclass
class Selection:
    tool: Tool | None
    reason: str
    shortlist: list[str] = field(default_factory=list)


class Registry:
    def __init__(self):
        self.tools, self.frozen = {}, False

    def tool(self, tool_id, *, args, description, risk, stages, min_tier=Tier.T1_VERIFIED, roles=(),
             trusted_outputs=(), author, reviewed_by=None):
        """Register a function as a tool; refuses a schema that fails review."""
        def register(func):
            if self.frozen:
                raise RegistryFrozen(f"{tool_id}: tools are registered in code before start-up only")
            problems = review(args)
            if tool_id in self.tools:
                problems.append("tool id already registered")
            if NUMBERS.search(description):
                problems.append("description must not contain numbers or money (it is shown to Jev)")
            if not stages:
                problems.append("must name the statechart stages it may run in")
            if reviewed_by is not None and reviewed_by == author:
                problems.append("the reviewer must be a second engineer, not the author")
            if problems:
                raise ValueError(f"{tool_id}: " + "; ".join(problems))
            self.tools[tool_id] = Tool(tool_id, func, args, description, Risk(risk), frozenset(stages),
                                       Tier(min_tier), frozenset(roles), frozenset(trusted_outputs), author,
                                       reviewed_by)
            return func
        return register

    def freeze(self):
        self.frozen = True
        return self

    def permitted(self, tier, roles, stage):
        """Step 1, code only: the tools this caller may be offered in this stage."""
        tier, roles = Tier[tier] if isinstance(tier, str) else Tier(tier), set(roles)
        return [t for t in self.tools.values()
                if tier >= t.min_tier and t.roles <= roles and stage in t.stages
                and (tier > Tier.T0_ANON or not t.mutating)]

    def shortlist(self, engine, tools, masked_state):
        """Step 2: at most SHORTLIST tools Jev finds relevant, most relevant first; [] means a human."""
        if len(tools) <= SHORTLIST:
            return tools
        questions = {t.tool_id: {"type": "noul", "instructions": RELEVANT.format(description=t.description)}
                     for t in tools}
        try:
            answers = engine.ask(masked_state, questions)
        except JevUnavailable:
            return []
        relevance = {tid: (a.confidence if a.value else 1 - a.confidence) for tid, a in answers.items()}
        ranked = sorted((t for t in tools if relevance[t.tool_id] >= RELEVANT_AT),
                        key=lambda t: -relevance[t.tool_id])
        return ranked[:SHORTLIST]

    def choose(self, engine, masked_state, tier, roles, stage):
        """Steps 1-3. Selection.tool is None when the turn should go to a human."""
        permitted = self.permitted(tier, roles, stage)
        if not permitted:
            return Selection(None, "no tool is allowed here")
        shortlist = self.shortlist(engine, permitted, masked_state)
        if not shortlist:
            return Selection(None, "no tool is clearly relevant")
        picked = engine.select_tool({t.tool_id: t.description for t in shortlist}, masked_state)
        names = [t.tool_id for t in shortlist]
        if picked is None:
            return Selection(None, "no confident tool choice", names)
        return Selection(self.tools[picked], "chosen", names)
