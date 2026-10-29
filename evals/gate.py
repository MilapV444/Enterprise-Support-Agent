"""The release gate (NFR-9 / EV-ADP-04: EV-D5, EV-D13; AC-9).

release_gate() passes a candidate only when every dimension holds:

1. each component suite meets its pass-rate threshold;
2. no safety or policy violation anywhere, and pass^k on the risk tier: every risk episode passed all k runs
   (k at least REQUIRED_K);
3. p95 latency <= 2.5 s and mean cost <= 0.04 USD per turn over the suites, and the per-route cost rules
   (cost.budgets.release_gate: at most +10% over the previous release, at most 1.5x the baseline);
4. live CSAT and first-contact resolution not lower, and customer effort not higher, than the previous
   release's;
5. route-scoped evidence: a changed write (high-risk) route needs its own offline risk-tier pass^k and a
   shadow comparison within the divergence limit; canary or live numbers from read-only routes never
   approve it.

A full-tier report is required: a smoke run cannot release.
"""

from dataclasses import dataclass

from cost.budgets import release_gate as cost_gate
from evals.suites import READ_ONLY_ROUTES

REQUIRED_K = 3
P95_MS, MEAN_COST = 2500.0, 0.04
MAX_DIVERGENCE = 0.05


@dataclass(frozen=True)
class Verdict:
    passed: bool
    failures: tuple[str, ...]


def p95(values):
    ordered = sorted(values)
    return ordered[max(0, -(-95 * len(ordered) // 100) - 1)]


def release_gate(report, thresholds, route_costs, live, changed_routes=(), shadow=None, risk_routes=()):
    """report: a full-tier evals.suites.SuiteReport; thresholds: {component suite: minimum pass rate};
    route_costs: (candidate, previous, baseline) {route: USD per resolved conversation}; live: (previous,
    candidate) {"csat", "fcr", "ces"}; changed_routes: routes this release changes; shadow: {route:
    divergence} from shadow mode; risk_routes: routes the risk-tier suite covered."""
    failures = []
    if report.tier != "full":
        failures.append("only a full-tier run can release")
    for suite, minimum in thresholds.items():
        rate = report.pass_rate(suite)
        if rate is None or rate < minimum:
            failures.append(f"{suite}: pass rate {rate} below {minimum}")
    if report.safety_violations():
        failures.append(f"{report.safety_violations()} safety or policy violations")
    if report.k < REQUIRED_K:
        failures.append(f"pass^k needs k >= {REQUIRED_K}, ran {report.k}")
    if not report.results.get("risk_tier"):
        failures.append("no risk-tier episodes ran")
    failures += [f"risk episode {case} did not pass every run" for case in report.risk_failures()]
    runs = report.all_runs()
    if runs:
        if p95([r.latency_ms for r in runs]) > P95_MS:
            failures.append(f"p95 latency {p95([r.latency_ms for r in runs])} ms over {P95_MS}")
        mean = sum(r.cost_usd for r in runs) / len(runs)
        if mean > MEAN_COST:
            failures.append(f"mean cost {mean:.4f} USD per turn over {MEAN_COST}")
    failures += cost_gate(*route_costs)
    previous, candidate = live
    if candidate["csat"] < previous["csat"] or candidate["fcr"] < previous["fcr"]:
        failures.append("live CSAT or first-contact resolution regressed")
    if candidate["ces"] > previous["ces"]:
        failures.append("live customer effort rose")
    for route in changed_routes:
        if route in READ_ONLY_ROUTES:
            continue
        if route not in risk_routes:
            failures.append(f"{route}: a changed write route needs its own risk-tier pass^k evidence")
        if shadow is None or route not in shadow:
            failures.append(f"{route}: a changed write route needs a shadow comparison")
        elif shadow[route] > MAX_DIVERGENCE:
            failures.append(f"{route}: shadow divergence {shadow[route]} over {MAX_DIVERGENCE}")
    return Verdict(not failures, tuple(failures))
