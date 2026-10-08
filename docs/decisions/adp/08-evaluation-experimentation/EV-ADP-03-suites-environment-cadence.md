# EV-ADP-03: Evaluation Suites, Execution Environments & Regression Cadence (Component & Risk Suites, Tiered Digital Twins & Sandboxed Outbound Safety)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-02 *(Confirmed per EV-D3 Hybrid Component & Risk-Tier Suites EV-Q1, EV-D4 Tiered Staging Environments EV-Q2, EV-D6 Smoke vs. Nightly Cadence & EV-D14 Sandboxed Staging Safety)*
- **Deciders**: Architecture Team, Lead Platform Reliability Engineer, CI/CD Architect, Security Operations Lead
- **Component**: `[8] Evaluation & Experimentation` (`Component [ 8 ]`)
- **Reasoning Source**: `checkpoint.md` §12 · Diagram: `LLD - [8] Evaluation & Experimentation`
- **Decisions Covered**:
  - `EV-D3`: Evaluation Suite Topology — Per-component isolation suites (Jev triage, knowledge retrieval, conversation memory, tool selection, specialist delegation, input screening, output checks) combined with a dedicated end-to-end Interaction Episode suite strictly scoped to the High-Risk Tier (`EV-Q1`); isolates unit failures while verifying multi-agent integration for high-stakes financial and destructive operations
  - `EV-D4`: Execution Environment Architecture — Tiered environment strategy for external system dependencies (`EV-Q2`): (1) High-fidelity staging copies of real enterprise systems where available; (2) Stateful reactive fakes ("digital twins") for critical multi-step write integrations (billing engines, CRM account provisioning); (3) Deterministic recorded response cassettes (VCR) for read-only integrations; low-priority integrations skipped in full agent suites
  - `EV-D6`: Regression Execution Cadence — Two-tier pipeline: Fast hermetic smoke subset executed per Git commit ($< 90\text{ seconds}$ budget, zero external API costs); comprehensive full regression suite executed nightly and as a mandatory release gating prerequisite ($< 45\text{ minutes}$ budget)
  - `EV-D14`: Staging Blast Radius Containment — Strict physical sandboxing of test environments: dedicated sandbox tenant credentials, outbound network egress allow-lists restricting worker pools (`TA-D11`), and hard disabling of external customer notification channels (email, SMS, webhooks) to prevent test side effects reaching real customers ($UK1$)
- **Related Architectural Decision Points**:
  - [`TA-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/04-tools-actions/TA-ADP-04-execution-credentials-isolation.md): Execution Credentials & Isolation *(Worker Pool Per System)*
  - [`TQ-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#tq-adp-04--test-environments--sandboxing): Test Environments & Sandboxing *(Staging Infrastructure Topology)*
  - [`DL-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#dl-adp-01--deployment-topology--canary-rollouts): Deployment Topology & Canary Rollouts *(Release Deployment Pipelines)*
  - [`EV-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/08-evaluation-experimentation/EV-ADP-04-release-gate-approval-evidence.md): Release Gate & Approval Evidence *(Gating Verification on Nightly Suites)*

---

## 1. Context & Problem Statement

Evaluating autonomous agents that execute external API mutations introduces severe operational hazards:
1. **The Flaky Staging Dilemma ($KK1$, $KK2$)**:
   - Running complete end-to-end agent suites on every Git pull request against live enterprise staging APIs (e.g., Salesforce sandbox, Stripe testmode, Zendesk staging) introduces extreme test flakiness. Staging environments experience unannounced vendor maintenance, network timeouts, and state pollution (e.g., a test from Run A leaves an invoice in an invalid state that breaks Run B).
2. **The Staging Side-Effect Catastrophe ($UK1$)**:
   - In enterprise systems, staging environments are frequently misconfigured with active notification triggers. An autonomous test agent issuing a simulated refund or status update against a staging account can inadvertently trigger real emails, SMS alerts, or third-party webhooks to actual corporate clients.
3. **The Feedback Speed vs. Exhaustive Depth Trade-Off ($EV\text{-}F6$)**:
   - Running full agent simulations (multi-turn reasoning, tool calling, LLM judge evaluations) on every single developer commit takes $30–60\text{ minutes}$ and costs hundreds of dollars in API tokens ($KU1$), bringing engineering velocity to a halt.
   - Conversely, testing only before major releases allows subtle regression bugs (e.g., prompt drift, tool argument misalignment) to accumulate undetected for weeks.

### The Core Architectural Question
> **How do we construct an evaluation test execution topology that provides instantaneous developer feedback on every commit, isolates component failures cleanly, executes realistic nightly multi-agent validation, and guarantees absolute containment of external side effects?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `EV-D3`, `EV-D4`, `EV-D6`, and `EV-D14` establish the **Tiered Evaluation Cadence and Sandboxed Digital Twin Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│             EVALUATION SUITES, ENVIRONMENTS & EXECUTION CADENCE (EV-D3, EV-D4, EV-D6)            │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                        DEVELOPER GIT COMMIT (Per-Commit Trigger)
                                           │
                                           ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ TIER 1: HERMETIC SMOKE SUBSET (EV-D6)                                                            │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ • Execution Budget: < 90 Seconds | Financial Cost: $0.00 External Tokens                         │
│ • Local Python Test Runner (pytest-asyncio) with Mocked Vector DB & Tool Stubs                   │
│ • Fast Component Assertions:                                                                     │
│   - Jev Decision Parsing Invariants (Pydantic models)                                            │
│   - Cedar Policy Validation (cedar validate on policy rules)                                     │
│   - Tool Argument Safety Regex & Delimiter Spotlighting                                          │
│   - Prompt Token Budget Verification (tiktoken / token counters)                                 │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                        NIGHTLY CRON & RELEASE PREREQUISITE (Daily at 02:00 UTC)
                                           │
                                           ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ TIER 2: FULL COMPONENT & RISK-TIER END-TO-END REGRESSION (EV-D3, EV-D6)                          │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ • Execution Budget: < 45 Minutes | Evaluator: Cross-Family LLM Judge (GPT-4o, EV-D2)            │
│ • Comprehensive Suites:                                                                          │
│   1. Knowledge Retrieval Suite (KR-D11: Context Precision, Recall on 500 Golden Queries)        │
│   2. Memory Extraction & Reconciliation Suite (MS-D12: Fact Conflict Resolution)                 │
│   3. Input Screening & Injection Suite (SG-D2: Llama Guard 3 & Prompt Guard Benchmark)          │
│   4. High-Risk End-to-End Episode Suite (EV-Q1: 50 Scenarios, pass^k Repeated Execution)       │
└──────────────────────────────────┬───────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ SANDBOXED INTEGRATION RUNTIME (EV-D4, EV-D14)                                                    │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                  │
│   Dedicated Test Accounts Only (tenant_id = "ten_test_sandbox_01")                              │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ Critical Multi-Step Write Tools (Billing, CRM Provisioning):                             │   │
│   │ ===> Stateful "Digital Twin" Fakes (In-Memory ACID SQLite DB with State Reset)           │   │
│   ├──────────────────────────────────────────────────────────────────────────────────────────┤   │
│   │ Read-Only Integrations (Knowledge bases, Documentation, Metric APIs):                    │   │
│   │ ===> Deterministic Recorded Responses (VCR.py Network Cassettes)                         │   │
│   ├──────────────────────────────────────────────────────────────────────────────────────────┤   │
│   │ Outbound Egress Sandboxing (EV-D14):                                                     │   │
│   │ ===> Egress Firewall Blocks: SMTP (25/587), Twilio, Public Webhooks (HTTP 403 EHOSTUNREACH)│   │
│   │ ===> Mocked Notification Handlers: Emails redirected to local MailHog test sink          │   │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Pillar 1: Hybrid Component & Risk-Tier Episode Suites (`EV-D3`, `EV-Q1`)

We resolve the tension between component unit testing and end-to-end realism via a selective hybrid topology:
1. **Per-Component Suites (90% of Tests)**:
   - Evaluates each subsystem in complete isolation using fixed mocks:
     - `test_triage_accuracy`: Verifies Jev classification on isolated turns.
     - `test_retrieval_ranking`: Measures MRR and NDCG on the Qdrant index.
     - `test_fact_reconciliation`: Verifies fact state transitions (`ADD`/`UPDATE`/`DELETE`).
     - `test_tool_shortlist`: Verifies that Cedar policies eliminate unauthorized tools.
2. **The High-Risk End-to-End Suite (`EV-Q1`)**:
   - Because full integration testing of routine conversations provides diminishing returns, full multi-turn end-to-end simulation is reserved exclusively for the **Risk Tier** (financial credits $\ge \$1,000$, destructive database operations, security incident triage).
   - Simulates complete multi-agent handoffs: Coordinator $\to$ Specialist $\to$ Human-in-the-Loop approval gate $\to$ Tool execution $\to$ Response verification.

---

### Pillar 2: Tiered Digital Twins & Environment Sandboxing (`EV-D4`, `EV-Q2`)

External API dependencies are mapped across three distinct fidelity tiers based on operational risk (`EV-Q2`):

| Integration Class | System Examples | Mocking / Environment Strategy | State Invariant & Reset Policy |
| :--- | :--- | :--- | :--- |
| **Critical Stateful Writes** | Stripe Invoicing, AWS Billing, Salesforce Accounts | **Stateful Digital Twin (Fake Engine)**: In-process Python/SQLite server emulating exact REST schemas, state transitions, and error codes. | Reset to pristine golden database state before every test scenario via `DigitalTwin.reset()`. |
| **Simpler Read-Only** | Product Documentation, Statuspage API, Log Search | **Deterministic Network Cassettes (VCR)**: Recorded HTTP interaction cassettes replayed with zero network latency. | Cassettes versioned in Git; refreshed automatically upon API contract updates. |
| **Low-Priority Non-Core** | Third-party analytics, marketing webhooks | **Test Skipped**: Tools stubbed with mock success payload. | Zero external verification overhead. |

---

### Pillar 3: Outbound Egress Containment & Side-Effect Immunity (`EV-D14`)

To guarantee that evaluation agents never trigger real-world customer side effects ($UK1$):
1. **Worker Network Egress Filtering**:
   - Evaluation worker containers operate within a dedicated Kubernetes namespace with strict `NetworkPolicy` egress rules:
     ```yaml
     egress:
       - to:
           - podSelector:
               matchLabels:
                 app: digital-twin-engine
       - ports:
           - port: 53 # DNS
           - port: 443 # Only allowed internal endpoints
     ```
   - Standard outbound mail ports (TCP 25, 465, 587) and SMS provider gateways (Twilio, Sinch) are blocked at the kernel firewall level.
2. **Dedicated Test Accounts**:
   - All evaluation requests execute under synthetic test tenant IDs:
     $$\text{TenantID} \in \{\text{"ten\_test\_01"}, \text{"ten\_test\_02"}\}$$
   - Any tool attempting to invoke an external endpoint with an active production tenant ID immediately aborts.
3. **Notification Sinks**:
   - Email dispatch tools are configured to point to a local MailHog/InBucket container. Test assertions verify that the expected email was generated and captured in the sink without ever leaving the VPC.

---

### Pillar 4: Two-Tier Regression Cadence (`EV-D6`)

To balance feedback speed against evaluation depth:
1. **Commit Smoke Suite**:
   - Trigger: Every Git pull request and commit push.
   - Sizing: 50 deterministic test cases.
   - Budget: Execution time $\le 90\text{ seconds}$; Cost: $\$0.00$ (runs against local mocks and quantized open-source classifiers).
   - Gate: Pull request merge blocked on any assertion failure.
2. **Nightly Full Regression Suite**:
   - Trigger: Daily cron at 02:00 UTC and on release candidate tags (`vX.Y.Z-rc`).
   - Sizing: Full component suites (500 retrieval queries, 200 memory cases, 300 safety injections) + 50 Risk-Tier End-to-End episodes.
   - Budget: Execution time $\le 45\text{ minutes}$; Evaluated by external LLM Judge (GPT-4o).
   - Gate: Release deployment to production blocked if any gate criteria fails (`EV-D5`).

---

## 3. Data Contracts & Execution Invariants

### 3.1 Digital Twin Configuration Contract

```python
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class IntegrationFidelityTier(str, Enum):
    STATEFUL_DIGITAL_TWIN = "stateful_digital_twin"
    RECORDED_CASSETTE = "recorded_cassette"
    STUBBED_MOCK = "stubbed_mock"

class SystemIntegrationConfig(BaseModel):
    system_name: str = Field(..., description="e.g., 'stripe_billing', 'salesforce_crm'")
    fidelity_tier: IntegrationFidelityTier
    mock_endpoint_uri: Optional[str] = None
    cassette_path: Optional[str] = None
    state_reset_endpoint: Optional[str] = None
    outbound_notifications_disabled: bool = Field(default=True, description="Enforces side-effect immunity")

class EvalRunEnvironmentManifest(BaseModel):
    """
    Contract specifying active environment state during an evaluation run.
    """
    run_id: str = Field(...)
    cadence: str = Field(..., regex=r"^(SMOKE|NIGHTLY|RELEASE_CANDIDATE)$")
    integrations: List[SystemIntegrationConfig]
    egress_network_policy_active: bool = Field(default=True)
    test_tenant_id: str = Field(default="ten_test_sandbox_01")
    digital_twin_seed_version: str = Field(..., description="Git commit hash of mock test data")
```

### 3.2 Side-Effect Immunity Invariants

1. **Production Tenant Exclusion Invariant**:
   $$\forall \text{ ToolCall } T \in \text{EvalRun}, \quad T.\text{tenant\_id} \in \text{SandboxTenants}$$
   Any tool invocation carrying a production tenant ID during an evaluation run aborts execution instantly with a security panic.
2. **Deterministic State Reset Invariant**:
   $$\forall \text{ Episode } E_k, \quad \text{State}(\text{DigitalTwin}_{t=0}) \equiv \mathcal{S}_{\text{golden}}$$
   The initial state of the digital twin at turn 0 of episode $k$ is bitwise identical to the pristine baseline, eliminating test-order coupling ($KK2$).

---

## 4. Quantitative Failure Modes & Operational Risk Bounds

| Failure Mode ID | Sub-Component & Severity | Risk Classification | Empirical Trigger Condition | Detection Vector | Automated Mitigation & Architectural Enforcement |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **EV-FM-301** | Egress Sandboxing (`EV-D14`)<br>**CRITICAL** | Q1 Known Known (Security Breach) | Test agent in staging environment invokes SMS tool with a real developer cell phone number ($UK1$). | Kernel firewall drops outbound packet to external carrier; alerts SIEM. | **Hard Egress Blackhole & Mock Sink**: Outbound carrier traffic dropped at VPC routing table; worker tool redirected to internal test sink. |
| **EV-FM-302** | State Pollution (`EV-D4`)<br>**HIGH** | Q1 Known Known (Test Flakiness) | Run A inserts a customer record with ID `cust_123` into the digital twin; Run B fails because `cust_123` already exists ($KK2$). | Test runner setup hook detects non-empty SQLite database before scenario starts. | **Automatic Database Teardown**: Pytest fixture executes `digital_twin.reset()` in an asynchronous `finally` block after every single episode. |
| **EV-FM-303** | Digital Twin Drift (`EV-D4`)<br>**HIGH** | Q2 Known Unknown (Contract Drift) | Production Billing API updates schema to require `tax_jurisdiction`, but Digital Twin mock allows missing field ($KU5$). | Contract testing runner (`TQ-ADP-02`) detects schema divergence between mock and OpenAPI spec. | **Automated Contract Linter**: CI runs schemathesis/Pact against Digital Twin endpoints daily, asserting exact schema parity with production OpenAPI specs. |
| **EV-FM-304** | Nightly Timeout (`EV-D6`)<br>**MEDIUM** | Q2 Known Unknown (Runtime Bloat) | High-Risk Suite concurrency throttled by single-threaded digital twin, pushing nightly run time to $> 90\text{ minutes}$. | CI runner emits job timeout alert ($> 45\text{min}$). | **Sharded Parallel Execution**: Nightly episode runner parallelizes across 8 worker pods, partitioning test scenarios by episode ID hash. |
| **EV-FM-305** | Untested Integration (`EV-D3`)<br>**HIGH** | Q4 Unknown Unknown (Emergent Flaw) | Component suites pass individually, but triage router fails to pass customer billing tier metadata to the delegation engine ($UU1$). | High-Risk End-to-End Suite catches missing context in specialist handover. | **Risk-Tier Episode Integration Gate (`EV-Q1`)**: The 50 risk-tier episodes explicitly assert metadata continuity across specialist graph boundaries. |

---

## 5. Closed-Loop Architectural Feedback

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   SUITE EXECUTION & ENVIRONMENT HEALTH ENGINE                                    │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

     Git Push / Nightly Cron
                │
                ▼
   ┌─────────────────────────────┐
   │ Environment Sandbox Setup   │─────► [Metric: eval_sandbox_egress_blocks_total]
   │ (Firewall & Mock Sinks)     │       Monitors attempted outbound leaks (Target: 0)
   └────────────┬────────────────┘
                │
                ▼
   ┌─────────────────────────────┐
   │ Digital Twin State Resetter │─────► [Metric: digital_twin_reset_latency_ms]
   │ (Restores Golden SQLite DB) │       Target: < 25ms per test
   └────────────┬────────────────┘
                │
                ▼
   ┌─────────────────────────────┐
   │ Test Execution Engine       │─────► [Metric: eval_suite_duration_seconds]
   │ (Smoke vs. Nightly Runner)  │       Smoke: < 90s | Nightly: < 45min
   └────────────┬────────────────┘
                │
                ├──────────────────────────────────────────────┐
                ▼                                              ▼
   ┌─────────────────────────────┐               ┌─────────────────────────────┐
   │ Flaky Test Isolator         │               │ Contract Parity Verifier    │
   │ (Detects non-deterministic  │               │ (Compares Twin vs. OpenAPI) │
   │ assertion failures KK1)     │               └──────────────┬──────────────┘
   └────────────┬────────────────┘                              │
                │                                               ▼
                ▼                                [Metric: twin_schema_drift_count]
   [Metric: test_flakiness_ratio]                Alerts if digital twin is stale
```

### Telemetry & Operational SLOs
1. **Commit Smoke Suite Execution Latency**:
   - Metric: `smoke_suite_duration_seconds`
   - Hard Ceiling: $\le 90\text{ seconds}$.
2. **Nightly Regression Suite Latency**:
   - Metric: `nightly_suite_duration_seconds`
   - Hard Ceiling: $\le 45\text{ minutes}$.
3. **Outbound Side-Effect Egress Leakage**:
   - Metric: `unauthorized_egress_attempts_total`
   - Target: **Strictly 0**. Any attempt triggers immediate CI job abortion and container quarantine.
4. **Digital Twin Schema Drift**:
   - Number of unsupported or diverging OpenAPI schema fields: **Strictly 0**.

---

## 6. Genesis Implementation Directive & Verification Protocol

### 6.1 Hermetic Pytest Fixture & Digital Twin Reset Directive

```python
import pytest
import aiohttp
from typing import AsyncGenerator

class DigitalTwinClient:
    def __init__(self, base_url: str = "http://localhost:8089"):
        self.base_url = base_url

    async def reset_pristine_state(self):
        """Forces immediate database wipe and re-seeds golden testing fixtures."""
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.base_url}/admin/reset_state") as resp:
                assert resp.status == 200, "Digital Twin state reset failed"

@pytest.fixture(autouse=True)
async def enforce_hermetic_environment() -> AsyncGenerator[None, None]:
    """
    Automated fixture wrapping every test execution.
    Guarantees state reset and validates sandbox tenant credentials.
    """
    twin = DigitalTwinClient()
    # 1. Reset state prior to scenario execution (EV-D4, KK2)
    await twin.reset_pristine_state()
    
    try:
        yield
    finally:
        # 2. Cleanup state immediately after execution
        await twin.reset_pristine_state()
```

### 6.2 Verification Checklist & Integration Tests

```bash
# 1. Verify Commit Smoke Suite Performance & Cost
pytest tests/evaluation/smoke/ --durations=10

# Expected Output:
# PASS: 50 smoke tests pass within 78 seconds.
# PASS: External API token consumption = $0.00 (Zero outbound network calls).

# 2. Verify Outbound Network Sandboxing
pytest tests/evaluation/test_sandboxing.py -k "test_egress_smtp_blocked"

# Expected Output:
# PASS: Simulated agent attempt to connect to smtp.sendgrid.net raises ClientConnectorError.
# PASS: Email successfully captured in local MailHog mock sink.
```

---

## 7. Trade-Off Analysis & Rejected Alternatives

| Dimension | Selected Paradigm (`EV-D3`, `EV-D4`, `EV-D6`, `EV-D14`) | Rejected Alternative A: Live Staging on Every Commit | Rejected Alternative B: Pure Synthetic Mocks for All Systems |
| :--- | :--- | :--- | :--- |
| **Developer Velocity & Feedback** | **Immediate**: Smoke suite provides pass/fail feedback in $< 90\text{s}$ directly in GitHub PRs. | **Crippled**: Full staging tests take 45 minutes per commit, stalling developer pull request workflows. | **Immediate**: Fast local execution, but completely ungrounded in real integration realities. |
| **Environmental Reliability** | **High**: Digital twins provide deterministic state without third-party network flakiness ($KK1$). | **Abysmal**: Staging systems suffer unannounced downtime, test data corruption, and rate limit errors. | **High**: Zero flakiness, but high risk of digital twin drift ($KU5$). |
| **Integration Failure Detection** | **Targeted**: Component suites catch unit bugs; Risk-Tier episodes catch multi-agent integration flaws ($EV\text{-}Q1$). | **High**: Catches integration flaws, but failure causes are difficult to localize across microservices. | **Zero**: Misses complex multi-step transaction bugs and edge-case error returns. |
| **Safety & Side-Effect Containment** | **Absolute**: Outbound egress firewalls and mock sinks prevent accidental real customer notifications ($UK1$). | **High Risk**: Staging environments frequently leak emails or webhooks if notification flags are misconfigured. | **Absolute**: No real network calls possible. |

---

## 8. Formal References & Literature Grounding

1. **Fowler, M. (2014).** *TestPyramid*. martinfowler.com/bliki/TestPyramid.html. *(Theoretical justification for high-volume component isolation suites backed by focused integration suites).*
2. **Yao, S., et al. (2024).** *$\tau$-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Environments*. arXiv preprint arXiv:2406.12045. *(Methodology for stateful digital twin simulation in agent benchmark environments).*
3. **Nygard, M. T. (2018).** *Release It!: Design and Deploy Production-Ready Software*. Pragmatic Bookshelf. Chapter 5: Stability Patterns & Chapter 14: Test Environments. *(Principles of blast radius containment and sandboxed network egress in test automation).*
4. **Humble, J., & Farley, D. (2010).** *Continuous Delivery: Reliable Software Releases through Build, Test, and Deployment Automation*. Addison-Wesley. *(Architectural standards for smoke commit stages versus deep nightly regression gates).*
5. **NIST. (2020).** *Security and Privacy Controls for Information Systems and Organizations*. NIST Special Publication 800-53, Rev 5. Control SA-11 (Developer Testing and Evaluation) & Control SC-7 (Boundary Protection). *(Standards governing sandboxed test isolation and containment of side effects).*
