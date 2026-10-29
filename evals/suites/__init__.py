"""Evaluation suites, their environments and cadence, shadow mode and canaries (NFR-8 / EV-ADP-03: EV-D3,
EV-D4, EV-D6, EV-D14; NFR-10 / EV-ADP-05: EV-D7, EV-D12).

- Suite: one component (triage, retrieval, memory, tool selection, delegation, screening, output checks) or
  the risk-tier end-to-end episodes; each case returns a CaseResult. run() runs the smoke tier (per commit,
  90 s budget) or the full tier (nightly and before a release, 45 min budget), and risk-tier cases k times
  each (pass^k).
- Environments: Cassette replays recorded responses for read-only integrations and never records in CI (a
  missing recording fails the case rather than reaching the network); Sandbox allows only listed hosts and
  turns every customer notification into an error, so a test cannot reach a real customer; Twin is the base
  for stateful fakes of write integrations.
- ShadowTools: a candidate on live traffic runs reads for real and records writes as proposals that are never
  executed; divergence() compares its outcomes with production's.
- canary(): only read-only routes may take canary traffic; assignment is a deterministic share by
  conversation.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field

import httpx

SMOKE_BUDGET, FULL_BUDGET = 90.0, 45 * 60.0     # seconds
COMPONENTS = ("triage", "retrieval", "memory", "tool_selection", "delegation", "screening", "output_checks")
READ_ONLY_ROUTES = frozenset({"faq", "status", "documentation"})


@dataclass(frozen=True)
class CaseResult:
    passed: bool
    failures: tuple[str, ...] = ()
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    safety_violation: bool = False


@dataclass(frozen=True)
class Case:
    id: str
    run: object                          # () -> CaseResult
    smoke: bool = False


@dataclass(frozen=True)
class Suite:
    name: str                            # a component, or "risk_tier"
    cases: tuple[Case, ...]

    def __post_init__(self):
        if self.name not in (*COMPONENTS, "risk_tier"):
            raise ValueError(f"unknown suite {self.name!r}")


@dataclass
class SuiteReport:
    tier: str
    k: int
    results: dict = field(default_factory=dict)      # suite -> {case id: [CaseResult, ...]}
    seconds: float = 0.0

    @property
    def over_budget(self):
        return self.seconds > (SMOKE_BUDGET if self.tier == "smoke" else FULL_BUDGET)

    def pass_rate(self, suite):
        runs = [r for results in self.results.get(suite, {}).values() for r in results]
        return sum(r.passed for r in runs) / len(runs) if runs else None

    def risk_failures(self):
        """Risk episodes that failed or violated safety in any of their k runs."""
        return sorted(case for case, results in self.results.get("risk_tier", {}).items()
                      if not all(r.passed and not r.safety_violation for r in results))

    def safety_violations(self):
        return sum(r.safety_violation for results in self.results.values() for runs in results.values()
                   for r in runs)

    def all_runs(self):
        return [r for results in self.results.values() for runs in results.values() for r in runs]


def run(suites, tier="full", k=3, clock=time.monotonic):
    """Run the suites at a tier; risk-tier cases run k times (pass^k), the rest once. A case that raises
    counts as failed."""
    if tier not in ("smoke", "full"):
        raise ValueError("tier is smoke or full")
    report, started = SuiteReport(tier, k), clock()
    for suite in suites:
        cases = [c for c in suite.cases if tier == "full" or c.smoke]
        repeats = k if suite.name == "risk_tier" else 1
        for case in cases:
            outcomes = []
            for _ in range(repeats):
                try:
                    outcomes.append(case.run())
                except Exception as error:  # noqa: BLE001 - a broken case is a failed case
                    outcomes.append(CaseResult(False, (f"{type(error).__name__}",)))
            report.results.setdefault(suite.name, {})[case.id] = outcomes
    report.seconds = clock() - started
    return report


# Environments -----------------------------------------------------------------------------------------------

class MissingRecording(LookupError):
    pass


class Cassette:
    """Recorded responses for read-only integrations, keyed by method, URL and body; replay only."""

    def __init__(self, recordings):
        """recordings: {key(method, url, body): (status, json body)}."""
        self.recordings, self.played = dict(recordings), []

    @staticmethod
    def key(method, url, body=b""):
        return hashlib.sha256(f"{method.upper()} {url}\n".encode() + (body or b"")).hexdigest()

    def __call__(self, request):
        key = self.key(request.method, str(request.url), request.content)
        if key not in self.recordings:
            raise MissingRecording(f"no recording for {request.method} {request.url}")
        self.played.append(key)
        status, body = self.recordings[key]
        return httpx.Response(status, json=body)


class SandboxViolation(PermissionError):
    pass


class Sandbox:
    """Test containment: outbound requests only to allowed hosts, and no customer notification at all."""

    def __init__(self, allowed_hosts, inner):
        self.allowed_hosts, self.inner = frozenset(allowed_hosts), inner

    def __call__(self, request):
        if request.url.host not in self.allowed_hosts:
            raise SandboxViolation(f"egress to {request.url.host} is not allowed in tests")
        return self.inner(request)

    @staticmethod
    def notify(*args, **kwargs):
        raise SandboxViolation("customer notifications are disabled in tests")


class Twin:
    """Base for stateful fakes of write integrations: state, and every change kept in order."""

    def __init__(self, state):
        self.state, self.changes = json.loads(json.dumps(state)), []

    def change(self, what, **detail):
        self.changes.append((what, detail))


# Shadow mode and canaries -----------------------------------------------------------------------------------

@dataclass
class ShadowTools:
    """run_read(tool_id, arguments) runs a read for real; writes become proposals and never run."""

    run_read: object
    is_write: object                     # tool_id -> bool
    proposals: list = field(default_factory=list)

    def __call__(self, tool_id, arguments):
        if self.is_write(tool_id):
            self.proposals.append((tool_id, dict(arguments)))
            return {"shadow": "proposed, not executed"}
        return self.run_read(tool_id, arguments)


def divergence(shadow, production):
    """Share of turns (by id) where the candidate's outcome differs from production's."""
    shared = set(shadow) & set(production)
    if not shared:
        raise ValueError("no turns to compare")
    return sum(shadow[t] != production[t] for t in shared) / len(shared)


def canary(route, conversation_id, percent):
    """Whether this conversation takes the candidate: read-only routes only, a stable share by id."""
    if route not in READ_ONLY_ROUTES:
        return False
    bucket = int(hashlib.sha256(conversation_id.encode()).hexdigest(), 16) % 100
    return bucket < percent
