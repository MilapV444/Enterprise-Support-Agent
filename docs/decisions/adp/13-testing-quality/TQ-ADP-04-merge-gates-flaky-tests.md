# TQ-ADP-04: Merge Gate Architecture & Flaky Test Safety Invariants (Comprehensive Pre-Merge Gates & Zero-Retry Safety Invariants)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-05 *(Confirmed per TQ-D8 Selective Retries, TQ-D9 Comprehensive Pre-Merge Gates KU1, TQ-D13 Zero-Retry Safety Invariant UU1 & EV-D6 Smoke Suite)*
- **Deciders**: Architecture Team, VP of Engineering, Lead DevOps Architect, Principal Reliability Engineer
- **Component**: `[13] Testing & Quality` (`Component [ 13 ]`)
- **Reasoning Source**: `checkpoint.md` §17 · Diagram: `LLD - [13] Testing & Quality`
- **Decisions Covered**:
  - `TQ-D8`: Selective Test Retry Policy — Automated retries (up to 2 retries) are permitted exclusively for standard non-safety integration tests and transient network fakes to maintain developer delivery velocity without blocking builds on ambient CI infrastructure flakiness
  - `TQ-D9`: Comprehensive Multi-Tier Merge Gate — Mandatory pre-merge CI validation barrier for all pull requests: code cannot be merged into mainline branches without passing: (1) Unit & Property Tests (`TQ-D1`, `TQ-D2`), (2) Integration Suites, (3) Schema Contract Tests (`TQ-D5`), (4) Static RLS & Cedar Policy Linters (`TQ-D4`), and (5) the live Evaluation Smoke Suite (`EV-D6`); model inference costs incurred by the smoke suite ($KU1$) are monitored and budgeted under FinOps governance
  - `TQ-D13`: Zero-Retry Invariant for Safety & Property Tests — Directly eliminates the severe hazard of retries masking intermittent race conditions ($UU1$); automated retries are strictly forbidden for invariant tests, property-based tests (Hypothesis), Cedar policy verifications, and security injection suites; any single failure in a safety-critical test immediately halts the build and requires mandatory engineering root-cause resolution
- **Related Architectural Decision Points**:
  - [`EV-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/08-evaluation-experimentation/EV-ADP-03-suites-environment-cadence.md): Evaluation Suites & Cadence *(Smoke Suite Specification)*
  - [`DL-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/14-deployment-llmops/DL-ADP-02-release-tracks-cadence.md): Release Tracks & Cadence *(Automated CI/CD Delivery Gates)*
  - [`TQ-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/13-testing-quality/TQ-ADP-01-testing-model-driven-logic.md): Testing Model-Driven Logic *(Property-Based Invariants)*
  - [`CR-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/11-cost-resource-management/CR-ADP-04-budgets-cost-governance.md): Budgets & Cost Governance *(CI Model Burn Budgeting)*

---

## 1. Context & Problem Statement

Balancing continuous integration speed with uncompromising safety invariants presents acute operational tensions:
1. **The Flaky Test Retry Hazard ($UU1$)**:
   - Modern continuous integration pipelines frequently introduce automatic retry mechanisms (e.g., `pytest --reruns 2`) to paper over network blips and database container spin-up latencies.
   - However, concurrency bugs in autonomous agent runtimes (such as single-turn active mutex races `RP-D3`, or customer cancellation vs. human approval races `HL-D8`) are inherently non-deterministic. A concurrency race that fails 1 out of 5 test executions will reliably pass on a blind retry.
   - Allowing automated retries on safety-critical tests masks real thread-safety and distributed mutex vulnerabilities, allowing critical race conditions to reach production ($UU1$).
2. **The "Green Build Illusion"**:
   - Gating pull requests on simple unit tests and linter passes allows breaking changes to slip into staging. When behavioral changes, Cedar policies, or schema contracts drift, errors are detected only during production canary deployments.
3. **The CI Model Burn Dilemma ($KU1$)**:
   - Gating every developer commit on extensive live foundation model evaluation suites creates massive CI build delays ($>45\text{ minutes}$) and burns hundreds of dollars per merge.
   - A balanced merge gate must enforce deep safety while strictly scoping live LLM calls to a lean, cost-bounded smoke subset (`EV-D6`).

### The Core Architectural Question
> **How do we engineer a multi-tier CI merge gate that catches contract, policy, and behavioral regressions before merge, while preventing automated retries from masking intermittent safety race conditions?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `TQ-D8`, `TQ-D9`, and `TQ-D13` establish the **Multi-Tier Pre-Merge Gate and Zero-Retry Safety Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   PRE-MERGE GATE & SELECTIVE RETRY PIPELINE (TQ-D8, TQ-D9, TQ-D13)               │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                                    DEVELOPER PULL REQUEST SUBMISSION
                                                   │
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 1: ZERO-RETRY SAFETY & INVARIANT BARRIER (TQ-D13, UU1)                                     │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Tests tagged `@pytest.mark.safety_critical` / `@pytest.mark.invariant`:                         │
│ • Property-Based Invariant Tests (Hypothesis: Step caps, Turn Mutex, 2-Person Rule)              │
│ • Cedar Policy Authorization Tests (`SG-D8`, `HL-D4`)                                            │
│ • Static Forced RLS Linters (`TQ-D4`, `DP-KK1`)                                                  │
│ • Fixed Adversarial Injection Benchmark (`TQ-D3`, `SG-D1`)                                       │
│                                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ ZERO RETRIES ALLOWED! (`pytest --reruns 0`)                                              │   │
│   │ • ANY FAILURE ===> INSTANT BUILD TERMINATION (Build Red; Must Investigate Race Condition)│   │
│   │ • ALL PASS    ===> Proceed to Stage 2                                                    │   │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                   │
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 2: CONTRACT & INTEGRATION HARNESS (TQ-D8, TQ-D5)                                           │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Tests tagged `@pytest.mark.integration`:                                                         │
│ • Component Contract Verification (Escalation Packets, Tool Schemas, Event Envelopes)            │
│ • Database & Vector Index Integration Tests (Local Postgres & Qdrant Containers)                 │
│ • Retries Permitted for Transient Container Latencies: `pytest --reruns 2` (TQ-D8)               │
└──────────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                   │
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 3: LIVE EVALUATION SMOKE SUBSET (TQ-D9, EV-D6, KU1)                                        │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Lean live model validation (Duration < 3 minutes, Cost < $0.15):                                 │
│ • 10 Core Representative Golden Conversations across Primary Routes                              │
│ • Evaluates Live Model Output Formatting & Acuity Classification                                 │
│ • CI Pass Gate: 100% Pass Rate Required                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Pillar 1: Comprehensive Multi-Tier Merge Gate (`TQ-D9`)

No code or configuration change may merge into `main` without passing five automated verification barriers:
1. **Linter & Policy Check**: Static AST analysis verifying forced Row-Level Security (`TQ-D4`) and Cedar policy authorization assertions.
2. **Deterministic Control Suite**: Mocked LLM statechart FSM tests asserting step caps and fallback transitions (`TQ-D1`).
3. **Property-Based Invariant Suite**: Hypothesis generative runs testing concurrent mutex acquisition (`TQ-D2`).
4. **Inter-Component Contract Suite**: Pydantic schema compatibility checks across components (`TQ-D5`).
5. **Live Evaluation Smoke Suite (`EV-D6`)**: A curated 10-conversation live inference smoke test verifying prompt syntax, model API authentication, and parsing formatting.

---

### Pillar 2: The Zero-Retry Safety Invariant (`TQ-D13`, $UU1$)

To eliminate the masking of non-deterministic concurrency bugs ($UU1$):
- **Explicit Test Categorization**:
  All test files are annotated with explicit pytest markers:
  - `@pytest.mark.safety_critical`
  - `@pytest.mark.invariant`
  - `@pytest.mark.integration`
- **Execution Policy Invariant**:
  When the CI runner executes tests tagged `safety_critical` or `invariant`, the `--reruns` parameter is **strictly forced to 0**:
  ```bash
  pytest -m "safety_critical or invariant" --reruns 0
  ```
- **Consequence**: If an invariant test encounters an intermittent lock failure or race condition once in ten iterations, the build breaks immediately. Developers are forced to analyze trace logs and fix the synchronization defect rather than relying on retry masking ($UU1$ fixed).

---

### Pillar 3: FinOps Budgeting for Smoke Runs (`KU1`)

Live model calls during merge gates add latency and financial burn ($KU1$):
1. **Smoke Scoping**:
   - The merge gate smoke suite is capped at **10 short conversations** ($<15,000\text{ tokens}$ total).
   - Full regression suites (spanning hundreds of episodes) are deferred to nightly batch execution (`EV-D6`).
2. **Financial Ceiling**:
   - CI smoke runs are executed under dedicated API keys tied to the FinOps usage tracker (`CR-D11`).
   - If monthly CI smoke testing spend exceeds $\$500.00$, a FinOps budget alert triggers to inspect developer PR merge frequencies.

---

## 3. Technical Implementation & Genesis Contracts

```python
"""
tests/conftest.py
Pytest hooks enforcing the Zero-Retry Invariant on Safety-Critical Tests (TQ-D8, TQ-D13).
"""

import pytest


def pytest_collection_modifyitems(config, items):
    """
    Enforces that safety-critical and invariant tests cannot be executed with retries.
    """
    # Check if pytest-rerunfailures is active
    reruns_count = config.getoption("reruns", default=0)

    for item in items:
        # Detect safety-critical markers
        is_safety_critical = (
            item.get_closest_marker("safety_critical") is not None or
            item.get_closest_marker("invariant") is not None or
            item.get_closest_marker("security") is not None
        )

        if is_safety_critical and reruns_count > 0:
            # Dynamically override and strip rerun capability for safety tests (TQ-D13, UU1)
            item.add_marker(pytest.mark.flaky(reruns=0))


# ---------------------------------------------------------------------------
# SAMPLE MERGE GATE TESTS WITH ENFORCED MARKERS
# ---------------------------------------------------------------------------

@pytest.mark.safety_critical
def test_two_person_rule_cedar_invariant():
    """
    Safety Critical Test: Zero retries allowed (TQ-D13). Must fail build on any flake.
    """
    handler_id = "agent_sarah_01"
    approver_id = "agent_sarah_01"  # Same person!
    
    is_permitted = False  # Cedar evaluation asserts DENY
    assert not is_permitted, "CRITICAL: Two-Person Rule violated!"


@pytest.mark.integration
def test_temporal_database_connection():
    """
    Integration Test: Retries permitted (up to 2) for transient network timeouts (TQ-D8).
    """
    connection_successful = True
    assert connection_successful
```

---

## 4. Failure Modes & Mitigation Matrix

| Failure ID | Sub-Component | Failure Mode Description | Root Cause | Effect on System | Architectural Mitigation (`TQ-D8`, `TQ-D9`, `TQ-D13`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **$UU1$** | Regression | Retries mask non-deterministic concurrency race | Flaky test runner retries intermittent lock failure | Mutex race ships to production, causing double tool writes | `TQ-D13` strictly enforces zero retries on all safety, invariant, and security tests |
| **$KU1$** | Regression | Merge gate delays developer velocity | Smoke suite executes too many live model calls | Developers wait 45 minutes for CI completion | `TQ-D9` restricts live model calls to 10-episode smoke subset; full evals run nightly (`EV-D6`) |
| **$KK1$** | Regression | Broken Cedar policy merged into `main` | Pull request merged without policy unit verification | Unauthorized specialists approve high-value transactions | `TQ-D9` merge gate mandates 100% pass rate on Cedar policy test suites |
| **$KK2$** | Regression | Contract drift breaks live frontend | API envelope change merged without contract test | Frontend web app displays blank screens on status events | `TQ-D9` merge gate validates Pydantic schema contracts across all shared envelopes |

---

## 5. Closed-Loop Telemetry & Verification Directives

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   MERGE GATE TELEMETRY & BUILD OBSERVABILITY PIPELINE                            │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Pull Request ──► [ GitHub Actions Runner ] ──► Metric: `ci.merge_gate.duration_seconds`
                          │
                          ├──► [ Zero-Retry Failures ] ──► Alert: `ci.safety_invariant.failure`
                          │
                          └──► [ Smoke Token Meter ]  ──► FinOps Metric: `ci.smoke.token_spend`
```

### 1. CI Telemetry Indicators
- `ci.merge_gate.build_duration_seconds`: Total elapsed time from PR trigger to merge approval (Target: $\le 8\text{ minutes}$).
- `ci.safety.invariant_failures_total`: Counter tracking hard failures in zero-retry safety tests.
- `ci.smoke.model_tokens_consumed`: Real-time token consumption incurred by the live EV smoke suite.

---

## 6. Alternatives Considered & Trade-Off Analysis

| Architectural Alternative | Technical Mechanism | Why Rejected / Trade-Off Analysis |
| :--- | :--- | :--- |
| **Universal Retries Everywhere (Option A)** | Allow 2 retries on all tests including invariants | **Rejected ($UU1$)**: Conceals real distributed concurrency bugs; allows race conditions to silently leak into production. |
| **Zero Retries Everywhere (Option C)** | Disallow retries on any test across the entire codebase | **Rejected**: Degrades developer velocity; causes pull requests to fail due to transient Docker network delays and ambient cloud CI blips. |
| **Unit Tests Only for Merge Gate (Option B)** | Defer contracts, policy tests, and smoke evals to nightly runs | **Rejected**: Allows broken schemas and security policy violations to merge into `main`, breaking staging environments. |

---

## 7. References & Academic Foundations

1. **Fowler, M.** (2011). *Eradicating Non-Determinism in Tests.* martinfowler.com Engineering Articles.
2. **Beyer, B. et al.** (2016). *Site Reliability Engineering: How Google Runs Production Systems.* Chapter 23: Managing Releases.
3. **NIST SP 800-53, Rev. 5.** (2020). *Security and Privacy Controls for Information Systems and Organizations.* Control CA-7: Continuous Monitoring.
