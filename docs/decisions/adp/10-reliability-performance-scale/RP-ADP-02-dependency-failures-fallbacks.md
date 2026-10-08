# RP-ADP-02: Dependency Failure Isolation, Fallback Cascade & Retry Budget Governance (Self-Hosted Model Fallbacks, Jev Structured Classifiers & 24-Hour Tool Holding)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-03 *(Confirmed per RP-D4 Self-Hosted LLM Fallback RP-Q3, RP-D5 Fallback Jev Classifier, RP-D7 24-Hour Tool Hold RP-Q4 & RP-D13 Single Retry Layer with Budgets KK3)*
- **Deciders**: Architecture Team, Principal Reliability Engineer, Lead AI Systems Architect, Security Infrastructure Lead
- **Component**: `[10] Reliability / Performance / Scale` (`Component [ 10 ]`)
- **Reasoning Source**: `checkpoint.md` §14 · Diagram: `LLD - [10] Reliability / Performance / Scale`
- **Decisions Covered**:
  - `RP-D4`: Frontier LLM Provider Fallback Cascade — Multi-tier model redundancy: If primary frontier provider (Anthropic Claude 3.5 Sonnet) fails or emits HTTP 429/5xx, traffic fails over to a self-hosted open-weights model deployed on dedicated regional GPUs (`RP-Q3`: Llama 3.1 70B via vLLM); if both models fail, agent degrades to non-neural Knowledge-Base snippet retrieval (`RP-Q1`); guarantees strict data residency (`DP-D10`) and zero third-party leakage
  - `RP-D5`: TypeSafe Jev Outage Fallback Classifier — If the hosted Jev decision service fails, an in-process fallback LLM classifier (Instructor/Pydantic structured output) executes the identical typed `Choice` schemas for triage and delegation using elevated, conservative confidence thresholds calibrated via `EV-D9`; security guardrails and tool gating stay fail-safe (`ADP-05`), preventing unauthorized tool execution
  - `RP-D7`: Circuit Breaker Open 24-Hour Deferred Execution — When an external tool system breaker trips (`TA-D10`), the request is held as an asynchronous Temporal workflow for up to 24 hours (`RP-Q4`); upon system recovery, the workflow resumes, re-checks authorization and fresh account facts (`MS-D18`), and delivers the answer via deferred SSE inbox delivery (`UA-D2`); if the system remains broken past 24 hours, the case routes to human supervisors; caching stale account facts rejected to maintain `MS-D6`
  - `RP-D13`: Single Retry Layer & Global Retry Budgets — Eradication of retry amplification ($KK3$): SDK-level retries disabled across all client libraries; retries permitted strictly at one designated layer per dependency (Temporal activity retry policies for tools); governed by an absolute per-turn budget ($\le 3$ retries total) and a global dependency retry budget (retries immediately suppressed if $> 10\%$ of calls to that system are retries)
- **Related Architectural Decision Points**:
  - [`ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/00-orchestration-core/ADP-04-error-recovery-replanning.md): Error Recovery & Replanning *(In-Graph Execution Self-Healing)*
  - [`ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/00-orchestration-core/ADP-05-decision-model-jev.md): Decision Model (Jev) *(Fail-Safe Contract Invariants)*
  - [`TA-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/04-tools-actions/TA-ADP-04-execution-credentials-isolation.md): Execution Credentials & Isolation *(Circuit Breaker Implementation)*
  - [`CR-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/11-cost-resource-management/CR-ADP-01-model-tier-routing.md): Model Tier Routing *(Dynamic Frontier vs. Regional Fallbacks)*

---

## 1. Context & Problem Statement

Enterprise multi-agent architectures depend on a precarious chain of external dependencies: frontier foundation model APIs, hosted decision services (Jev), external enterprise CRMs (Salesforce), billing gateways (Stripe), and internal databases.

### The Systemic Failure Modes of Distributed Dependencies
1. **The Retry Amplification Storm ($KK3$)**:
   - In uncoordinated microservice stacks, retries exist at every abstraction layer:
     $$\text{Total Calls} = N_{\text{HTTP\_Client}} \times N_{\text{LangChain}} \times N_{\text{Temporal}} \times N_{\text{ToolProxy}}$$
   - When an external billing API slows down, an initial burst of 100 customer turns amplifies into $3 \times 3 \times 5 = 45$ calls per turn, blasting the struggling dependency with $4,500$ calls. This retry storm drives a transient slow-down into a complete, catastrophic multi-hour outage.
2. **The Fragility of Single-Vendor AI Dependencies (`RP-D5`)**:
   - If the platform relies exclusively on a single hosted decision API (such as Jev) for intent triage and tool safety gating, a minor outage at that vendor halts the entire enterprise support operation, flooding human queues with thousands of stranded cases.
3. **The Stale Cache Poisoning Hazard (Scenario 6, `MS-D6`)**:
   - When an external CRM (Salesforce) is down, naive architectures attempt to answer customer inquiries by reading historical account facts from an operational database cache.
   - However, customer subscription tiers, account balances, and credit limits change constantly. Serving a stale cached renewal date or credit balance makes a legally binding false claim that breaches `MS-D6`.

### The Core Architectural Question
> **How do we engineer a resilient dependency execution harness that guarantees zero retry amplification, fails over seamlessly to regional self-hosted models during third-party cloud outages, and preserves requests for up to 24 hours during external system downtime without serving stale account data?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `RP-D4`, `RP-D5`, `RP-D7`, and `RP-D13` establish the **Cascading Dependency Fallback and Bounded Retry Budget Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│             DEPENDENCY FALLBACK CASCADE & RETRY BUDGET PIPELINE (RP-D4, RP-D5, RP-D13)           │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                        Agent Execution Step Initiated
                                      │
            ┌─────────────────────────┴─────────────────────────┐
            ▼                                                   ▼
┌─────────────────────────────────────┐     ┌─────────────────────────────────────┐
│ FOUNDATION MODEL CALL (RP-D4)       │     │ DECISION CLASSIFIER CALL (RP-D5)    │
├─────────────────────────────────────┤     ├─────────────────────────────────────┤
│ Primary: Claude 3.5 Sonnet (SaaS)   │     │ Primary: Hosted TypeSafe Jev API    │
└──────────────────┬──────────────────┘     └──────────────────┬──────────────────┘
                   │ 429/5xx / Timeout                         │ Network Error / Timeout
                   ▼                                           ▼
┌─────────────────────────────────────┐     ┌─────────────────────────────────────┐
│ Tier 2: Regional Self-Hosted LLM    │     │ Tier 2: In-Process Fallback LLM     │
│ (vLLM Llama 3.1 70B on Local GPUs)  │     │ (Structured Instructor JSON Schema) │
│ Enforces Strict Sovereign Residency │     │ Conservative Elevated Thresholds    │
└──────────────────┬──────────────────┘     └──────────────────┬──────────────────┘
                   │ Both LLMs Down                            │ Fallback Fails
                   ▼                                           ▼
┌─────────────────────────────────────┐     ┌─────────────────────────────────────┐
│ Tier 3: Knowledge-Base Snippets     │     │ Fail-Safe Tripping (ADP-05):        │
│ Non-neural cited passage extraction │     │ Triage -> Clarify; Tool -> HITL     │
└─────────────────────────────────────┘     └─────────────────────────────────────┘

════════════════════════════════════════════════════════════════════════════════════════════════════
EXTERNAL TOOL BREAKER TRIPPED (CIRCUIT BREAKER == OPEN, RP-D7, RP-Q4)
════════════════════════════════════════════════════════════════════════════════════════════════════

   Temporal Activity Execution (TA-D11)
               │
               ▼ Breaker OPEN: Do NOT read stale CRM cache (MS-D6)!
   ┌────────────────────────────────────────────────────────────────────────┐
   │ Temporal Workflow 24-Hour Holding Queue (RP-D7, RP-Q4)                 │
   │ • Suspends saga execution; schedules 24-hour timer                     │
   │ • Polls breaker state / listens for recovery webhook                   │
   │ • Client receives: "System busy; we will notify your inbox once ready" │
   └───────────────────────────────────┬────────────────────────────────────┘
                                       │
            ┌──────────────────────────┴──────────────────────────┐
            ▼ (System Recovers ≤ 24 Hours)                        ▼ (System Stalled > 24 Hours)
┌──────────────────────────────────────┐              ┌──────────────────────────────────────┐
│ Resume Workflow Execution:           │              │ Escalate to Human Supervisor:        │
│ • Re-fetch live fresh facts (MS-D18) │              │ • Case routed to specialist desk     │
│ • Re-validate Cedar policy (SG-D17)  │              │ • Customer notified of delay         │
│ • Deliver via SSE Event Log (UA-D2)  │              └──────────────────────────────────────┘
└──────────────────────────────────────┘
```

---

### Pillar 1: Regional Open-Weights Model Fallback (`RP-D4`, `RP-Q3`)

To guarantee uptime during catastrophic third-party foundation model outages (Anthropic/OpenAI global service disruptions):
1. **Self-Hosted Regional GPU Cluster (`RP-Q3`)**:
   - Each sovereign region (`us-east-1`, `eu-central-1`, `DP-D10`) maintains an autonomous vLLM inference cluster hosting **Llama 3.1 70B Instruct** (quantized via AWQ/FP8 on NVIDIA A10G/L40S nodes).
2. **Zero Cross-Border Leakage**:
   - Fallback traffic remains within the sovereign geographic boundary, satisfying EU GDPR residency mandates without negotiating emergency Standard Contractual Clauses.
3. **Dedicated Evaluation Baseline (`EV-D5`)**:
   - Because open-weights models exhibit differing reasoning and verbosity characteristics compared to Claude 3.5 Sonnet, the fallback model operates under its own calibrated prompt templates and evaluated baseline thresholds (`EV-D5`).

---

### Pillar 2: TypeSafe Jev Outage Fallback Classifier (`RP-D5`)

If the hosted Jev decision API encounters downtime:
1. **In-Process Fallback Engine**:
   - The orchestrator shifts to a local fallback classifier using the `instructor` library paired with the active foundation model.
   - It issues the identical typed Pydantic `Choice` question schema used by Jev (`ADP-05`).
2. **Elevated Confidence Thresholds**:
   - To counteract the higher variance and potential instruction-drift of standard LLMs compared to fine-tuned Jev sequence classifiers, the fallback threshold is elevated by $\Delta = +0.10$ (calibrated via `EV-D9`):
     $$\tau_{\text{fallback}} = \min(0.95, \tau_{\text{jev}} + 0.10)$$
3. **Hard Fail-Safe Boundaries (`ADP-05`)**:
   - Security screening guardrails (`SG-D2`) and financial tool approval gates (`TA-D6`) **never** use the fallback classifier; they adhere strictly to `ADP-05` fail-safe rules (screening = `BLOCK`, financial writes = `REQUIRE_HUMAN_APPROVAL`).

---

### Pillar 3: 24-Hour Asynchronous Tool Holding Queue (`RP-D7`, `RP-Q4`)

When an external integration's circuit breaker transitions to `OPEN` (e.g., Salesforce API rate limits exhausted):
1. **Rejection of Stale Account Caching (`MS-D6`)**:
   - We explicitly reject serving cached account facts ($RP\text{-}F7b$). Reading a cached credit limit or renewal date risks multi-thousand-dollar customer contract disputes.
2. **Durable Temporal Workflow Suspension (`RP-Q4`)**:
   - The turn execution saga enters a suspended state within Temporal (`ADP-02`), armed with a maximum holding timeout:
     $$\tau_{\text{hold\_max}} = 24\text{ hours}$$
   - The user interface immediately emits a progress status event informing the customer:
     > *"Our billing backend is currently undergoing maintenance. We have preserved your request and will automatically deliver your updated balance to your support inbox as soon as the system recovers."*
3. **Freshness Re-Verification on Resume (`MS-D18`)**:
   - When the circuit breaker resets to `CLOSED`, the workflow wakes up, executes a fresh live read against Salesforce, re-evaluates Cedar authorization policies (`SG-D17`), and appends the resolution to the outbound event log (`UA-D2`).
   - If the breaker remains `OPEN` past 24 hours, the workflow automatically aborts and transfers the ticket to a human support agent (`Comp 13`).

---

### Pillar 4: Single Retry Layer & Global Retry Budgets (`RP-D13`, $KK3$)

To permanently extinguish **Retry Amplification Storms ($KK3$)**:
1. **Strict Single-Layer Assignment**:
   - Retries are eliminated from all HTTP clients, LangGraph agent nodes, and utility functions.
   - **Rule**: Retries are authorized exclusively within **Temporal Activity Execution Policies** (`TA-D10`).
2. **Per-Turn Retry Budget**:
   - A single customer turn is allocated a maximum of 3 total retries across all tools combined:
     $$\sum_{s \in \text{Turn}} \text{Retries}(s) \le 3$$
3. **Global Dependency Retry Budget (Google SRE Standard)**:
   - For every external dependency $D$, the gateway tracks total calls $N_{\text{total}}$ and retried calls $N_{\text{retry}}$ over a 10-minute sliding window.
   - The gateway enforces a strict retry budget ceiling:
     $$\frac{N_{\text{retry}}(D)}{N_{\text{total}}(D)} \le 0.10 \quad (10\%)$$
   - If retries exceed $10\%$, all subsequent retries to dependency $D$ fail-fast immediately without waiting, shedding load from the struggling system.

---

## 3. Data Contracts & Execution Invariants

### 3.1 Retry Budget & Fallback Configuration Contract

```python
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class DependencyHealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED_FAILOVER_ACTIVE = "degraded_failover_active"
    CIRCUIT_BREAKER_OPEN = "circuit_breaker_open"

class GlobalRetryBudgetTracker(BaseModel):
    """
    Contract tracking global retry allocations per external system (RP-D13).
    """
    dependency_name: str = Field(..., description="e.g., 'anthropic_api', 'stripe_billing'")
    window_total_calls: int = Field(default=0, ge=0)
    window_retry_calls: int = Field(default=0, ge=0)
    max_retry_ratio: float = Field(default=0.10, description="10% global retry budget ceiling")

    @property
    def retry_budget_exhausted(self) -> bool:
        if self.window_total_calls < 50:
            return False  # Minimum sample size before shedding
        return (self.window_retry_calls / self.window_total_calls) > self.max_retry_ratio

class ToolHoldingManifest(BaseModel):
    """
    Contract governing 24-hour asynchronous request preservation (RP-D7, RP-Q4).
    """
    workflow_id: str = Field(...)
    conversation_id: str = Field(...)
    system_name: str = Field(...)
    holding_started_at_utc: str = Field(...)
    max_hold_expiration_utc: str = Field(..., description="Timestamp +24 hours")
    holding_reason: str = Field(default="CIRCUIT_BREAKER_OPEN")
```

### 3.2 Single Retry Layer Invariant

$$\forall \text{ ClientLibrary } L, \quad L.\text{max\_retries} \equiv 0$$
No Python SDK client (`openai.OpenAI`, `anthropic.Anthropic`, `requests.Session`) may configure internal retries; retries are exclusively owned by Temporal's activity coordinator.

---

## 4. Quantitative Failure Modes & Operational Risk Bounds

| Failure Mode ID | Sub-Component & Severity | Risk Classification | Empirical Trigger Condition | Detection Vector | Automated Mitigation & Architectural Enforcement |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **RP-FM-201** | Retry Amplification (`RP-D13`)<br>**CRITICAL** | Q1 Known Known (Cascading Outage) | External system slow-down causes uncoordinated retries across layers, multiplying load by 15x ($KK3$). | Global retry budget monitor detects $N_{\text{retry}} / N_{\text{total}} > 0.10$. | **Global Retry Circuit Break**: Temporal worker immediately rejects subsequent retries, converting to fail-fast 24-hour holding. |
| **RP-FM-202** | Recovery Herd Stampede (`RP-D7`)<br>**HIGH** | Q4 Unknown Unknown (Thundering Herd) | External CRM recovers after 4 hours, causing 2,000 held Temporal workflows to resume simultaneously ($UU4$). | Temporal task queue execution rate spikes past CRM rate limit ($> 500\text{ req/sec}$). | **Rate-Limited Task Queue Drain (`TA-Q2`)**: Temporal worker poll rate for system $S$ strictly capped at 25 concurrent activities per second. |
| **RP-FM-203** | Fallback Accuracy Degradation (`RP-D4`)<br>**HIGH** | Q2 Known Unknown (Quality Drop) | Claude outage forces failover to Llama 3.1 70B, which exhibits lower nuance on complex billing policies ($KU2$). | Live evaluation telemetry (`EV-D8`) reports drop in judge faithfulness score. | **Conservative Fallback Prompts**: Fallback model system prompt injects stricter instruction delimiters and defaults to human co-pilot escalation. |
| **RP-FM-204** | Holding Expiration Timeout (`RP-D7`)<br>**MEDIUM** | Q2 Known Unknown (Stall) | Downstream system remains broken for 26 hours, exceeding the 24-hour Temporal holding timer ($RP\text{-}Q4$). | Temporal workflow timeout timer fires at 24 hours. | **Automatic Supervisor Transfer**: Workflow triggers activity transferring case to human emergency queue with incident context. |
| **RP-FM-205** | Regional GPU OOM (`RP-D4`)<br>**HIGH** | Q1 Known Known (Infrastructure OOM) | Sudden massive failover shifts 1,000 concurrent turns to local vLLM cluster, exhausting GPU VRAM ($KU1$). | vLLM engine emits `EngineKilledError` / CUDA out-of-memory. | **Admission Shedding to KB Snippets**: When vLLM queue depth exceeds 200, orchestrator sheds excess load directly to non-neural KB snippets. |

---

## 5. Closed-Loop Architectural Feedback

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   DEPENDENCY RESILIENCE & RETRY HEALTH ENGINE                                    │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Dependency Invocation Stream
                │
                ▼
   ┌─────────────────────────────┐
   │ Global Retry Budget Tracker │─────► [Metric: dependency_retry_ratio]
   │ (Monitors 10% Ceiling KK3)  │       Alerts if retry share > 10%
   └────────────┬────────────────┘
                │
                ▼
   ┌─────────────────────────────┐
   │ Circuit Breaker Evaluator   │─────► [Metric: circuit_breaker_state]
   │ (Tracks TA-D10 Transitions) │       0=CLOSED, 1=HALF-OPEN, 2=OPEN
   └────────────┬────────────────┘
                │
                ├──────────────────────────────────────────────┐
                ▼ (Breaker CLOSED / Normal)                    ▼ (Breaker OPEN / Failover)
   ┌─────────────────────────────┐               ┌─────────────────────────────┐
   │ Execute Primary Call        │               │ Temporal 24-Hour Queue      │
   │ (Claude 3.5 / Live API)     │               │ [Metric: held_requests_total│
   └─────────────────────────────┘               └─────────────────────────────┘
```

### Telemetry & Operational SLOs
1. **Global Dependency Retry Share**:
   - Metric: `dependency_retry_ratio{system}`
   - Hard Ceiling: $\le 0.10$ ($10\%$ maximum).
2. **Frontier Failover Latency**:
   - Time to detect primary provider 5xx and switch to regional vLLM: $< 500\text{ms}$.
3. **Deferred Workflow Recovery Delay**:
   - Time from circuit breaker reset to first held workflow resume: $< 5.0\text{ seconds}$.

---

## 6. Genesis Implementation Directive & Verification Protocol

### 6.1 Global Retry Budget & Circuit-Breaker Interceptor Implementation

```python
import time
from typing import Callable, Any
from pydantic import BaseModel

class RetryBudgetExhaustedException(Exception):
    pass

class DependencyExecutionCoordinator:
    def __init__(self, system_name: str, max_retry_share: float = 0.10):
        self.system_name = system_name
        self.max_retry_share = max_retry_share
        self.total_calls = 0
        self.retry_calls = 0
        self.last_reset = time.time()

    def check_and_record_retry(self) -> bool:
        """
        Enforces global retry budget constraint (RP-D13, KK3).
        Rejects retry if retries exceed 10% of total volume over rolling window.
        """
        now = time.time()
        if now - self.last_reset > 600:  # Reset every 10 minutes
            self.total_calls = 0
            self.retry_calls = 0
            self.last_reset = now

        self.total_calls += 1
        if self.total_calls > 50:
            if (self.retry_calls / self.total_calls) > self.max_retry_share:
                # Global retry budget exhausted: Shed retries immediately
                raise RetryBudgetExhaustedException(
                    f"Global retry budget exceeded for {self.system_name}. Failing fast to protect dependency."
                )

        self.retry_calls += 1
        return True
```

### 6.2 Verification Checklist & Integration Tests

```bash
# 1. Verify Global Retry Budget Protection Against Amplification
pytest tests/reliability/test_retry_budgets.py -k "test_retry_budget_blocks_storm"

# Expected Output:
# PASS: 50 consecutive dependency failures permit exactly 5 retries (10% ceiling).
# PASS: 6th retry attempt raises RetryBudgetExhaustedException immediately without network call.

# 2. Verify 24-Hour Tool Holding Without Stale Cache
pytest tests/reliability/test_tool_holding.py -k "test_breaker_open_holds_and_resumes"

# Expected Output:
# PASS: When CRM breaker is OPEN, request is held in Temporal without accessing cached facts.
# PASS: Workflow resumes when breaker resets, re-fetching live fresh facts from CRM.
```

---

## 7. Trade-Off Analysis & Rejected Alternatives

| Dimension | Selected Paradigm (`RP-D4`, `RP-D5`, `RP-D7`, `RP-D13`) | Rejected Alternative A: Stale Account Fact Caching | Rejected Alternative B: Multi-Layer Unconstrained Retries |
| :--- | :--- | :--- | :--- |
| **Data Integrity & Legal Compliance** | **Absolute**: Holds requests for up to 24h; never serves stale account facts (`MS-D6`). | **Catastrophic Risk**: Serves expired billing data; makes false contractual promises to customers. | **N/A**: Relates to retry mechanics. |
| **Dependency Protection** | **Bulletproof**: Single retry layer + 10% global budget prevents cascading outages ($KK3$). | **N/A**: Relates to cache semantics. | **Fatal Amplification**: Multiple retry loops multiply load by $45\times$, crushing struggling backends. |
| **Uptime Under Cloud Outages** | **Guaranteed**: Regional self-hosted open-weights models maintain service during SaaS outages (`RP-Q3`). | **Fragile**: Single SaaS provider outage halts entire global business. | **Fragile**: Retries uselessly against dead SaaS endpoint. |
| **Infrastructure Cost** | **Moderate**: Requires running standby regional GPU clusters (vLLM nodes, $KU1$). | **Lowest**: Uses existing database cache, but at existential legal risk. | **Expensive**: Multiplies API token spend by $300\%$ during network blips. |

---

## 8. Formal References & Literature Grounding

1. **Beyer, B., Jones, C., Petoff, J., & Murphy, N. R. (2016).** *Site Reliability Engineering: How Google Runs Production Systems*. O'Reilly Media. Chapter 22: Addressing Cascading Failures (The danger of unconstrained retries and the mathematics of retry budgets). *(Foundational theoretical basis for single-layer retry budgets).*
2. **Nygard, M. T. (2018).** *Release It!: Design and Deploy Production-Ready Software*. Pragmatic Bookshelf. Chapter 5: Stability Patterns (Circuit Breakers, Timeouts, and Bulkheads). *(Standards governing failure state isolation and fail-fast architectures).*
3. **Kwon, W., et al. (2023).** *Efficient Memory Management for Large Language Model Serving with PagedAttention*. Proceedings of the 29th ACM Symposium on Operating Systems Principles (SOSP 2023). *(Technical architecture for high-throughput regional open-weights vLLM serving).*
4. **Temporal Technologies. (2023).** *Temporal Workflow Execution Model: Long-Running Stateful Sagas and Timers*. Whitepaper. *(Mechanisms for durable 24-hour state holding and asynchronous event waking).*
5. **NIST. (2020).** *Security and Privacy Controls for Information Systems and Organizations*. NIST SP 800-53, Rev 5. Control CP-2 (Contingency Plan) & Control SC-5 (Denial of Service Protection). *(Standards governing fault tolerance and contingency operations in mission-critical applications).*
