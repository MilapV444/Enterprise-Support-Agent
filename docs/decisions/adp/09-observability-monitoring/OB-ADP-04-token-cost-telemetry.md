# OB-ADP-04: Token & Cost Telemetry Architecture (Multi-Component Attributions, Horvitz-Thompson Tail Scaling & Cardinality Defense)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-03 *(Confirmed per OB-D9 Multi-Dimensional Token Tracking & OB-D13 Tail-Sampling Cost Scaling UU1)*
- **Deciders**: Architecture Team, FinOps Lead, Principal Observability Engineer, Systems Performance Architect
- **Component**: `[9] Observability & Monitoring` (`Component [ 9 ]`)
- **Reasoning Source**: `checkpoint.md` §13 · Diagram: `LLD - [9] Observability & Monitoring`
- **Decisions Covered**:
  - `OB-D9`: Multi-Component Token & Cost Attribution — Fine-grained token consumption and financial spend tracking segmented across four orthogonal dimensions: Tenant ID, Conversation ID, Model Family, and Architectural Component (Coordinator, Specialist subgraphs, Jev decision models, LLM judges, cross-encoder rerankers); high-cardinality conversation-level metrics strictly forbidden in Prometheus to preserve time-series stability
  - `OB-D13`: Horvitz-Thompson Tail-Sampling Cost Estimator — Analytical cost estimation derived from kept trace spans scaled via inverse probability weighting (`OB-F13(a)`); mathematical formulation isolates deterministically kept anomalies (errors, slow turns, risk tiers) from the 5% uniformly sampled routine baseline, eliminating severe upward cost estimation skews ($UU1$); authoritative financial billing delegated to lightweight unsampled counters (`CR-ADP-04`)
- **Related Architectural Decision Points**:
  - [`CR-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#cr-adp-04--cost-attribution--token-budgets): Cost Attribution & Token Budgets *(Turn-Level Budget Enforcement)*
  - [`RP-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#rp-adp-01--admission-control--rate-limiting): Admission Control & Rate Limiting *(Tenant Quota Counters)*
  - [`OB-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/09-observability-monitoring/OB-ADP-01-instrumentation-trace-pipeline.md): Distributed Instrumentation & Trace Pipeline *(Tail-Sampling Infrastructure)*
  - [`ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/00-orchestration-core/ADP-05-decision-model-jev.md): Decision Model (Jev) *(Model Token Tracking)*

---

## 1. Context & Problem Statement

In an enterprise multi-tenant agent system, token consumption represents the primary variable operational expenditure. Gaining visibility into spend is complicated by conflicting data engineering constraints:

1. **The Prometheus High-Cardinality Meltdown**:
   - Modern monitoring backends (Prometheus, Cortex, Thanos) maintain an inverted time-series index for every unique permutation of metric labels.
   - If an engineer attempts to track per-conversation token spend by adding `conversation_id` as a label on a Prometheus counter:
     $$\text{Cardinality} = |\text{Tenants}| \times |\text{Conversations}| \times |\text{Components}| \times |\text{Models}|$$
   - With $100,000$ active conversations per week, timeseries counts explode past $10^7$, causing Prometheus memory exhaustion and cluster crashes.
2. **The Tail-Sampling Upward Cost Distortion ($UU1$)**:
   - To save storage, the trace pipeline deploys tail-based sampling (`OB-D4`), keeping $100\%$ of errors, slow turns ($> 2.5\text{s}$), and risk-tier actions, while sampling routine turns at $5\%$.
   - If FinOps analysts naively sum tokens across all stored traces and multiply by the inverse sampling rate ($20\times$), the estimated cost is catastrophically distorted. Because complex, token-heavy errors and multi-step specialist loops are over-represented in stored traces, multiplying them by $20\times$ overstates real infrastructure spend by $300–500\%$.
3. **Component Attribution Blindness**:
   - High-level billing invoices from foundation model vendors (OpenAI, Anthropic) provide an aggregate dollar amount. They fail to reveal which subsystem drove a budget overrun: was it Jev triage classification, excessive RAG context stuffing in the technical specialist, or nightly LLM judge evaluations?

### The Core Architectural Question
> **How do we engineer an accurate, component-attributed token and cost telemetry pipeline without causing Prometheus cardinality explosions, and how do we mathematically correct for tail-sampling selection bias when estimating volume from trace spans?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `OB-D9` and `OB-D13` establish the **Dual-Engine Cost Telemetry and Horvitz-Thompson Estimator Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│             TOKEN & COST TELEMETRY FLOW ARCHITECTURE (OB-D9, OB-D13)                             │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                        Model Invocation (LLM, Jev, Judge, Reranker)
                                             │
             ┌───────────────────────────────┴───────────────────────────────┐
             ▼                                                               ▼
┌─────────────────────────────────────────┐     ┌─────────────────────────────────────────┐
│ ENGINE 1: CARDINALITY-BOUNDED METRICS   │     │ ENGINE 2: TRACE-BASED FINE ATTRIBUTION │
│ (Low Cardinality, Unsampled Prometheus) │     │ (High Cardinality, OpenSearch Spans)    │
├─────────────────────────────────────────┤     ├─────────────────────────────────────────┤
│ Labels:                                 │     │ Attributes:                             │
│ • tenant_id (e.g. "ten_acme_01")        │     │ • conversation_id ("conv_9812")         │
│ • component ("billing_specialist")      │     │ • turn_id ("turn_4412")                 │
│ • model_id ("claude-3-5-sonnet")        │     │ • prompt_tokens, completion_tokens      │
│ • direction ("input" | "output")        │     │ • tail_sampling_reason (ERROR, ROUTINE) │
│ Invariant: NO conversation_id!          │     │ Invariant: Full granular payload!       │
└────────────────────┬────────────────────┘     └────────────────────┬────────────────────┘
                     │                                               │
                     ▼                                               ▼
┌─────────────────────────────────────────┐     ┌─────────────────────────────────────────┐
│ REAL-TIME BURN RATE & SPEND DASHBOARDS  │     │ HORVITZ-THOMPSON COST ESTIMATOR ENGINE  │
│ Accurate aggregate spend per tenant;    │     │ Mathematically corrects for tail-sample │
│ Real-time tenant quota rate limiting    │     │ bias to reconstruct conversation costs  │
└─────────────────────────────────────────┘     └─────────────────────────────────────────┘
```

---

### Pillar 1: Cardinality Defense & Metrics Partitioning (`OB-D9`)

To guarantee horizontal stability in Prometheus, metric label cardinality is strictly capped:
1. **Low-Cardinality Metrics Pipeline (Prometheus)**:
   - Emits an unsampled atomic counter on every model response:
     ```promql
     gen_ai_tokens_total{tenant_id="ten_01", component="billing", model="claude-3-5-sonnet", type="input"}
     ```
   - Total series count is strictly bounded:
     $$|\mathcal{M}| \le 200 \text{ Tenants} \times 8 \text{ Components} \times 5 \text{ Models} \times 2 \text{ Types} \approx 16,000 \text{ timeseries}$$
   - This footprint remains trivial for standard Prometheus instances ($< 50\text{MB}$ memory).
2. **High-Cardinality Trace Attributes (OpenSearch)**:
   - High-cardinality dimensions (`conversation_id`, `turn_id`, `case_id`) are attached exclusively as structured OpenSearch span attributes (`OB-D1`).
   - OpenSearch's distributed inverted index natively scales to billions of unique conversation IDs without time-series fragmentation.

---

### Pillar 2: Horvitz-Thompson Estimator for Tail-Sampled Traces (`OB-D13`, $UU1$)

To reconstruct granular per-conversation token spend from tail-sampled traces without incurring upward selection bias:

#### Mathematical Formulation
Let $\mathcal{T}$ be the population of all turns. The tail-sampling policy (`OB-D4`) partitions $\mathcal{T}$ into two mutually exclusive subsets:
1. **Deterministic Retention Strata ($\mathcal{T}_{\text{det}}$)**:
   Traces containing errors, escalations, slow latencies ($> 2.5\text{s}$), or risk-tier actions. Inclusion probability:
   $$\pi_i = 1.0 \quad \forall \; i \in \mathcal{T}_{\text{det}}$$
2. **Uniformly Sampled Routine Strata ($\mathcal{T}_{\text{routine}}$)**:
   Routine successful turns sampled at baseline rate $\rho = 0.05$. Inclusion probability:
   $$\pi_i = \rho = 0.05 \quad \forall \; i \in \mathcal{T}_{\text{routine}}$$

#### The Unbiased Horvitz-Thompson Spend Estimator
Let $c_i$ be the token cost of trace $i$. The unbiased estimator of total spend $\hat{C}$ across $N$ traces is:
$$\hat{C} = \sum_{i \in \text{Kept}_{\text{det}}} c_i + \frac{1}{\rho} \sum_{j \in \text{Kept}_{\text{routine}}} c_j$$
$$\hat{C} = \sum_{i \in \text{Kept}_{\text{det}}} c_i + 20 \times \sum_{j \in \text{Kept}_{\text{routine}}} c_j$$

#### Proof of Unbiasedness
$$\mathbb{E}[\hat{C}] = \sum_{i \in \mathcal{T}_{\text{det}}} \mathbb{E}[\mathbf{1}_{i}] c_i + 20 \sum_{j \in \mathcal{T}_{\text{routine}}} \mathbb{E}[\mathbf{1}_{j}] c_j$$
$$\mathbb{E}[\hat{C}] = \sum_{i \in \mathcal{T}_{\text{det}}} (1.0) c_i + 20 \sum_{j \in \mathcal{T}_{\text{routine}}} (0.05) c_j = \sum_{i \in \mathcal{T}} c_i \equiv C_{\text{true}}$$
By tagging every stored trace with its `sampling_reason` attribute (`DETERMINISTIC` vs. `PROBABILISTIC_5PCT`), the analytics engine applies the $20\times$ multiplier **strictly** to the probabilistic stratum, completely eliminating the $300\%$ over-estimation distortion ($UU1$).

---

### Pillar 3: Multi-Component Spend Breakdown (`OB-D9`)

Token expenditures are categorized across five distinct architectural phases to enable targeted FinOps engineering:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   ARCHITECTURAL TOKEN ATTRIBUTION BREAKDOWN                                      │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 1. Input Screening:     Llama Guard 3 & Prompt Guard Ingestion (Self-Hosted GPU compute)         │
│ 2. Orchestration Core:   Coordinator Intent Triage & Jev Noul/Choice calls                      │
│ 3. Specialist Runtimes:  Domain Reasoning (Billing, Technical) + Ingested Passage Tokens (RAG)   │
│ 4. Output Guardrails:    Regex Sanitizers + LLM Promise backed rewrites (SG-D15)                │
│ 5. Continuous Eval:     Nightly Sampled Cross-Family LLM Judges (GPT-4o, EV-D2)                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Data Contracts & Execution Invariants

### 3.1 Trace Token Attribution Metadata Contract

```python
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class SamplingReason(str, Enum):
    ERROR_TRIGGERED = "error_triggered"
    ESCALATION_TRIGGERED = "escalation_triggered"
    RISK_TIER_TRIGGERED = "risk_tier_triggered"
    LATENCY_SLO_TRIGGERED = "latency_slo_triggered"
    UNIFORM_PROBABILISTIC = "uniform_probabilistic"

class ComponentTokenAttribution(BaseModel):
    """
    Contract for structured token telemetry attached to trace spans (OB-D9).
    """
    tenant_id: str = Field(..., regex=r"^ten_[a-zA-Z0-9]{16}$")
    conversation_id: str = Field(..., regex=r"^conv_[a-zA-Z0-9]{16}$")
    turn_id: str = Field(..., regex=r"^turn_[a-zA-Z0-9]{16}$")
    component: str = Field(..., regex=r"^(coordinator|specialist_billing|specialist_tech|jev|judge)$")
    model_id: str = Field(..., description="e.g., 'claude-3-5-sonnet-20241022'")
    
    input_tokens: int = Field(..., ge=0)
    output_tokens: int = Field(..., ge=0)
    estimated_cost_usd: float = Field(..., ge=0.0)
    sampling_reason: SamplingReason
    sampling_weight: float = Field(default=1.0, description="1.0 for deterministic; 20.0 for uniform")
```

### 3.2 Cardinality Defense Invariant

$$\forall \text{ Metric } M \in \text{PrometheusCatalog}, \quad \text{"conversation\_id"} \notin \text{Labels}(M)$$
The CI Prometheus metric linter statically analyzes all `Counter`, `Histogram`, and `Gauge` declarations in the codebase, immediately blocking builds that define unbounded dynamic identifiers as labels.

---

## 4. Quantitative Failure Modes & Operational Risk Bounds

| Failure Mode ID | Sub-Component & Severity | Risk Classification | Empirical Trigger Condition | Detection Vector | Automated Mitigation & Architectural Enforcement |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **OB-FM-401** | Metric Cardinality (`OB-D9`)<br>**CRITICAL** | Q1 Known Known (Prometheus Crash) | Application developer logs customer email or session ID as a Prometheus counter label. | Prometheus server reports `ScrapeFailed: out of memory`; timeseries count $> 5\text{M}$. | **Static CI AST Linter**: Pre-commit hook scans all `prometheus_client` invocations and fails PRs declaring un-whitelisted label names. |
| **OB-FM-402** | Cost Estimation Distortion (`OB-D13`)<br>**HIGH** | Q1 Known Known (Estimation Error) | Analytics dashboard multiplies ALL stored traces by 20x, treating error traces as uniform ($UU1$). | Monthly FinOps audit detects $4\times$ divergence between trace cost report and AWS/OpenAI invoice. | **Horvitz-Thompson Query Filter**: Analytics dashboard SQL explicitly checks `WHERE sampling_reason = 'UNIFORM_PROBABILISTIC'` before applying $20\times$ multiplier. |
| **OB-FM-403** | Token Quota Bypass (`OB-D9`)<br>**MEDIUM** | Q2 Known Unknown (Spend Overrun) | Malicious customer issues 1,000 parallel requests, consuming $\$500$ in tokens before trace pipeline processes. | Real-time Prometheus counter `rate(gen_ai_tokens_total[1m])` spikes. | **In-Memory Rate Limiting (`RP-ADP-01`)**: Local Redis token bucket throttles tenant turn throughput based on immediate counter telemetry. |
| **OB-FM-404** | Missing Pricing Models (`OB-D9`)<br>**LOW** | Q3 Unknown Known (Tacit Convention) | Vendor introduces a new model snapshot (e.g. `claude-3-5-sonnet-v2`), but pricing lookup table is not updated. | Telemetry ingest logs `Warning: UnknownModelPricingException; cost set to 0.0`. | **Graceful Default Fallback**: Ingestion engine uses conservative highest-tier pricing rate until new model configuration is merged. |
| **OB-FM-405** | Trace Clock Skew (`OB-D9`)<br>**LOW** | Q4 Unknown Unknown (Telemetry Drift) | Host system time drift across Kubernetes nodes causes span start/end durations to calculate negative token rates. | OpenSearch ingestion pipeline drops spans with `duration_ms < 0`. | **Monotonic Clock Invariant**: All span durations calculated via `time.monotonic()` instead of wall clock `time.time()`. |

---

## 5. Closed-Loop Architectural Feedback

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   TOKEN CONSUMPTION & COST OBSERVABILITY ENGINE                                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

     Model API Response Stream
                 │
                 ▼
     ┌─────────────────────────────┐
     │ Unsampled Prometheus Metric │─────► [Metric: gen_ai_tokens_total]
     │ Counter (Low Cardinality)   │       Partitioned by {tenant, component, model}
     └─────────────┬───────────────┘
                   │
                   ▼
     ┌─────────────────────────────┐
     │ Trace Span Span Decorator   │─────► [OpenSearch Span Attributes]
     │ (Attaches Conversation ID)  │       Full granular debugging payload
     └─────────────┬───────────────┘
                   │
                   ▼
     ┌─────────────────────────────┐
     │ FinOps Analytics Engine     │
     │ (Horvitz-Thompson Adjusted) │
     └─────────────┬───────────────┘
                   │
                   ├──────────────────────────────────────────────┐
                   ▼                                              ▼
     ┌─────────────────────────────┐               ┌─────────────────────────────┐
     │ Monthly Cost Reconciliation │               │ Real-Time Spend Quota Gate  │
     │ Divergence: |Est - Act| < 5%│               │ Trips breaker if daily cap  │
     └─────────────────────────────┘               │ exceeded (CR-ADP-04)        │
                                                   └─────────────────────────────┘
```

### Telemetry & Operational SLOs
1. **Prometheus Metric Series Headroom**:
   - Total active time series across cluster: $\le 25,000$ series.
2. **Horvitz-Thompson Cost Estimation Accuracy**:
   - Monthly divergence between estimated spend $\hat{C}$ and vendor invoices: $|\hat{C} - C_{\text{actual}}| / C_{\text{actual}} \le 0.05$ (Within 5%).
3. **Token Counter Ingestion Latency**:
   - Prometheus scrape to Grafana dashboard update: $\le 15\text{ seconds}$.

---

## 6. Genesis Implementation Directive & Verification Protocol

### 6.1 Horvitz-Thompson Cost Aggregator Query Implementation

```python
from typing import List, Dict
from pydantic import BaseModel

class TraceSpanCostRecord(BaseModel):
    cost_usd: float
    sampling_reason: str  # 'ERROR_TRIGGERED', 'RISK_TIER_TRIGGERED', 'UNIFORM_PROBABILISTIC'

class HorvitzThompsonCostEstimator:
    def __init__(self, uniform_sampling_rate: float = 0.05):
        self.uniform_weight = 1.0 / uniform_sampling_rate  # 20.0

    def estimate_total_spend(self, trace_records: List[TraceSpanCostRecord]) -> Dict[str, float]:
        """
        Reconstructs unbiased population spend from tail-sampled traces.
        Applies inverse probability weighting strictly to the uniform stratum (OB-D13).
        """
        deterministic_spend = 0.0
        uniform_spend_raw = 0.0

        for r in trace_records:
            if r.sampling_reason in ("ERROR_TRIGGERED", "ESCALATION_TRIGGERED", "RISK_TIER_TRIGGERED", "LATENCY_SLO_TRIGGERED"):
                # Weight = 1.0 (Kept deterministically)
                deterministic_spend += r.cost_usd
            elif r.sampling_reason == "UNIFORM_PROBABILISTIC":
                # Weight = 20.0 (Sampled at 5%)
                uniform_spend_raw += r.cost_usd

        estimated_routine_spend = uniform_spend_raw * self.uniform_weight
        total_estimated_spend = deterministic_spend + estimated_routine_spend

        return {
            "deterministic_spend_usd": deterministic_spend,
            "estimated_routine_spend_usd": estimated_routine_spend,
            "total_estimated_spend_usd": total_estimated_spend
        }
```

### 6.2 Verification Checklist & Integration Tests

```bash
# 1. Verify Cardinality Defense in CI
pytest tests/observability/test_metrics_cardinality.py -k "test_conversation_id_not_in_labels"

# Expected Output:
# PASS: Static AST audit verifies zero occurrences of conversation_id in Prometheus label names.

# 2. Verify Horvitz-Thompson Cost Unbiasedness
pytest tests/observability/test_cost_estimation.py -k "test_horvitz_thompson_unbiased_convergence"

# Expected Output:
# PASS: Ground truth spend = $1,000.00; Horvitz-Thompson estimate = $1,004.20 (Error = 0.42%).
# PASS: Naive unweighted scaling estimate = $4,120.00 (Distortion > 300% neutralized).
```

---

## 7. Trade-Off Analysis & Rejected Alternatives

| Dimension | Selected Paradigm (`OB-D9`, `OB-D13`) | Rejected Alternative A: Full Unsampled Traces Everywhere | Rejected Alternative B: Conversation IDs in Prometheus |
| :--- | :--- | :--- | :--- |
| **Time-Series Stability** | **Bulletproof**: Metric labels strictly bounded; total series count $< 20,000$; zero Prometheus OOM risk. | **N/A**: Relates to trace storage. | **Catastrophic Failure**: Millions of ephemeral conversations crash Prometheus server memory within days. |
| **FinOps Cost Accuracy** | **High**: Horvitz-Thompson estimator provides unbiased spend approximations within $5\%$ of invoices. | **Exact**: 100% exact, but trace storage costs exceed model API expenditures. | **Exact**: But crashes monitoring infrastructure. |
| **Granular Debuggability** | **Complete**: OpenSearch span attributes preserve exact per-turn token breakdowns for kept traces. | **Complete**: Rich data, but 90% wasted on routine uneventful turns. | **Poor**: Metrics provide numbers only, without prompt context or reasoning graphs. |
| **Storage & Network Overhead** | **Minimal**: Tail sampling discards $95\%$ of routine traces; low-cardinality counters use negligible bandwidth. | **Extreme**: Storing $100\%$ of full text traces requires terabytes of NVMe SSD provisioning. | **Moderate**: High metric storage, but lacks text context. |

---

## 8. Formal References & Literature Grounding

1. **Horvitz, D. G., & Thompson, D. J. (1952).** *A Generalization of Sampling Without Replacement from a Finite Universe*. Journal of the American Statistical Association, 47(260), 663–685. *(Theoretical foundation for inverse probability weighting in tail-sampled populations).*
2. **Prometheus Authors. (2023).** *Prometheus Documentation: Metric and Label Naming Best Practices*. Cloud Native Computing Foundation. *(Design rules for avoiding cardinality explosions in distributed timeseries databases).*
3. **FinOps Foundation. (2024).** *FinOps Framework: Managing Cloud and Generative AI Costs*. Technical Whitepaper. *(Best practices for multi-tenant token attribution and model cost allocation).*
4. **Kleppmann, M. (2017).** *Designing Data-Intensive Applications*. O'Reilly Media. *(Principles of partitioning timeseries metrics from document-oriented trace search engines).*
5. **NIST. (2023).** *Artificial Intelligence Risk Management Framework (AI RMF 1.0)*. NIST. Section 3.6: Accountable and Transparent AI. *(Standards for auditing and attributing operational resource consumption in automated systems).*
