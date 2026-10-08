# CR-ADP-01: Dynamic Tri-Tier Model Routing & Predictive Complexity Cascading (Jev Difficulty Scoring, FrugalGPT Cascades & Self-Hosted Open-Weights Co-Serving)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-03 *(Confirmed per CR-D1 Tri-Tier Routing CR-Q1, CR-D2 Complexity Cascades, CR-D9 Dual-Purpose GPU Infrastructure & EV-D9 Calibration)*
- **Deciders**: Architecture Team, Principal AI Architect, Lead FinOps Engineer, Infrastructure Director
- **Component**: `[11] Cost & Resource Management` (`Component [ 11 ]`)
- **Reasoning Source**: `checkpoint.md` §15 · Diagram: `LLD - [11] Cost & Resource Management`
- **Decisions Covered**:
  - `CR-D1`: Dynamic Model Tier Selection via Jev Acuity Scoring — Every conversational turn dynamically evaluates query complexity using a lightweight Jev `Score` (TypeSafe small language model) operating on PII-masked input (`SG-D4`); routes requests across three explicit model tiers (`CR-Q1(ii)`): Tier 1 (Self-Hosted Open-Weights Llama 3.1 70B), Tier 2 (Commercial Mid-Tier API, e.g., Claude 3.5 Haiku / GPT-4o-mini), and Tier 3 (Frontier Frontier API, e.g., Claude 3.5 Sonnet / GPT-4o); routing decision boundaries are strictly calibrated per route by the evaluation harness (`EV-D9`)
  - `CR-D2`: Predictive Verification Cascading — A fail-safe escalation pipeline: if a generated response from a lower tier fails deterministic schema checks, safety screening (`SG-D6`), output promise verifications (`SG-D15`), or yields a low confidence score from Jev (`HL-D1`), the orchestration engine immediately triggers a single-step cascade rerun on the next higher model tier; limits waste by testing hypotheses cheaply before escalating
  - `CR-D9`: Dual-Role Infrastructure Optimization — Self-hosted fallback GPU pools provisioned for high-availability disaster recovery (`RP-D4`) are co-opted to serve normal, low-risk, easy turns during baseline operating conditions; guarantees steady GPU utilization, keeps model weights pre-warmed in VRAM, amortizes fixed infrastructure costs, and drastically compresses commercial frontier API token expenditures
- **Related Architectural Decision Points**:
  - [`ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/00-orchestration-core/ADP-05-decision-model-jev.md): Decision Model (Jev) *(Structured Classifier Execution)*
  - [`RP-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/10-reliability-performance-scale/RP-ADP-02-dependency-failures-fallbacks.md): Dependency Failures & Fallbacks *(Self-Hosted LLM Fallback Pool)*
  - [`CR-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/11-cost-resource-management/CR-ADP-02-token-context-economy.md): Token & Context Economy *(Turn Token Budgets with Cascade Margin)*
  - [`EV-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/08-evaluation-experimentation/EV-ADP-02-scoring-calibration.md): Scoring & Calibration *(Expected Calibration Error on Jev Cutoffs)*
  - [`DL-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/14-deployment-llmops/DL-ADP-04-versioning-models-indexes-workflows.md): Model Versioning *(Pinned Weights vs. Provider Aliases)*

---

## 1. Context & Problem Statement

Modern enterprise customer support workflows exhibit extreme variance in cognitive difficulty:
1. **The Homogeneous Routing Trap**:
   - Routing 100% of conversational turns through frontier foundation models (e.g., Claude 3.5 Sonnet at $3.00 / \$15.00$ per million tokens) guarantees high answer quality but results in catastrophic cost inefficiency. Over $65\%$ of enterprise support inquiries are routine FAQ queries, greeting acknowledgments, status checks, or deterministic navigation questions that do not require multi-step deliberative reasoning.
   - Conversely, statically binding workflows to a single budget model leads to severe cognitive failure on multi-variable diagnostic troubleshooting, complex refund calculations, or multi-system sagas.
2. **The Idle GPU Sunk-Cost Dilemma (`RP-D4`, `CR-D9`)**:
   - High-reliability multi-region architectures require warm standby inference infrastructure (e.g., dual NVIDIA H100/A100 clusters running open-weights models in US and EU regions) to satisfy disaster recovery and provider-outage survival SLAs.
   - Leaving standby GPU clusters idle waiting for commercial API outages incurs massive monthly cloud spend with zero operational yield.
3. **The Risk of Premature Down-Routing ($KK2$, $UU3$)**:
   - Injudicious routing to a low-tier model can produce subtly ungrounded responses or hallucinated parameters. If the system lacks an automatic, self-correcting escalation cascade, the user receives an erroneous answer or the turn must be escalated to an expensive human agent. Furthermore, if a cascade step exhausts the turn token budget, the conversation terminates abruptly ($UU3$).

### The Core Architectural Question
> **How do we engineer a dynamic model routing architecture that accurately predicts query difficulty on PII-masked inputs, dispatches tasks across three distinct cognitive tiers, dynamically cascades upward upon verification failure, and fully amortizes dedicated DR GPU capacity?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `CR-D1`, `CR-D2`, and `CR-D9` establish the **Tri-Tier Complexity Routing and Cascade Framework**, grounded in the *FrugalGPT* cascade framework (Chen et al., 2023) and *RouteLLM* preference scoring (Ong et al., 2024).

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   TRI-TIER MODEL ROUTING & PREDICTIVE CASCADE (CR-D1, CR-D2, CR-D9)              │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                       Inbound User Turn (PII-Tokenized via SG-D4, Sanitized via SG-D1)
                                                      │
                                                      ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ JEV COMPLEXITY ROUTER (CR-D1, ADP-05 Use 1)                                                      │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Evaluates: Query Length, Entity Multiplicity, Tool Invocation Probability, Acuity Score         │
│ Output: Complexity Score $s \in [0.0, 1.0]$, Calibrated via EV-D9                                │
└────────────────────────────────────┬─────────────────────────────────────────────────────────────┘
                                     │
           ┌─────────────────────────┼─────────────────────────┐
           ▼ Low ($s < \theta_1$)     ▼ Mid ($\theta_1 \le s < \theta_2$) ▼ High ($s \ge \theta_2$)
┌───────────────────────┐ ┌───────────────────────┐ ┌───────────────────────┐
│ TIER 1: SELF-HOSTED   │ │ TIER 2: MID-TIER API  │ │ TIER 3: FRONTIER API  │
│ OPEN-WEIGHTS (CR-D9)  │ │ (CR-Q1)               │ │ (CR-Q1)               │
├───────────────────────┤ ├───────────────────────┤ ├───────────────────────┤
│ • Llama 3.1 70B vLLM  │ │ • Claude 3.5 Haiku    │ │ • Claude 3.5 Sonnet   │
│ • Local Regional GPU  │ │ • GPT-4o-mini         │ │ • GPT-4o              │
│ • Zero API Marginal $ │ │ • Moderate API Cost   │ │ • Premium API Cost    │
│ • Serves Easy Turns   │ │ • Standard Reasoning │ │ • Complex Sagas/Diag  │
└───────────┬───────────┘ └───────────┬───────────┘ └───────────┬───────────┘
            │                         │                         │
            ▼                         ▼                         ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ POST-GENERATION VERIFICATION GATEWAY (CR-D2, SG-D6, SG-D15, HL-D1)                               │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 1. Schema Validation: Structured Pydantic tool call arguments parsed cleanly?                    │
│ 2. Grounding & Hallucination: Jev Noul Claims Supported ≥ 0.90?                                  │
│ 3. Output Safety: Regex Leakage & Rule-Based Promise Checks Passed?                              │
│                                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ Verification Passed?                                                                     │   │
│   │ • YES ===> Deliver to Client / Execute Action                                            │   │
│   │ • NO  ===> CASCADE ESCALATION (CR-D2): Rerun step on Tier + 1 (Tier 1 → Tier 2 → Tier 3) │   │
│   │            (Budget reservation guarantees room for exactly 1 cascade step CR-D5, UU3)    │   │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Pillar 1: Mathematical Formulation of Tri-Tier Routing (`CR-D1`)

Let a turn context be $X = (x_{\text{sys}}, x_{\text{dialogue}}, x_{\text{kb}}, x_{\text{tools}})$, tokenized and sanitized of PII under `SG-D4`.
The Jev classifier computes a scalar difficulty assessment:
$$s = f_{\text{Jev}}(X) \in [0.0, 1.0]$$

Routing decisions follow an optimal cost-risk decision partition parameterized by cutoffs $\theta_1, \theta_2$:
$$\text{Tier}(s) = \begin{cases} 
\mathcal{T}_1 \text{ (Self-Hosted Llama 3.1 70B)} & \text{if } s < \theta_1 \\
\mathcal{T}_2 \text{ (Commercial Mid-Tier API)} & \text{if } \theta_1 \le s < \theta_2 \\
\mathcal{T}_3 \text{ (Commercial Frontier API)} & \text{if } s \ge \theta_2
\end{cases}$$

#### Calibration Formulation (`EV-D9`)
Cutoffs $\Theta = \{\theta_1, \theta_2\}$ are optimized offline across evaluation sets $\mathcal{D}_{\text{eval}}$ to minimize expected cost subject to a strict quality degradation constraint $\epsilon$:
$$\min_{\Theta} \mathbb{E}_{X \sim \mathcal{D}} \left[ \text{Cost}(X, \text{Tier}(f_{\text{Jev}}(X))) \right] \quad \text{s.t.} \quad \text{Pass}^k(\text{Tier}(f_{\text{Jev}}(X))) \ge \text{Pass}^k(\mathcal{T}_3) - \epsilon$$

Where:
- $\text{Pass}^k$ denotes task success under Yao et al. (2024) $\tau$-bench criteria.
- $\epsilon = 0.015$ (maximum allowable quality drop of $1.5\%$).
- Cutoffs are recalibrated per route prior to every gated release (`EV-D9`).

---

### Pillar 2: Predictive Verification Cascades (`CR-D2`)

In accordance with Chen et al. (2023) (*FrugalGPT*), cascading executes a sequence of model invocations with early exit:
1. Generate candidate response $\hat{Y} \sim \mathcal{T}_i(X)$.
2. Evaluate deterministic and probabilistic verification functions:
   $$\mathcal{V}(\hat{Y}, X) = \mathbb{I}\left( \text{Schema}(\hat{Y}) \land \text{Safety}(\hat{Y}) \land \text{Promise}(\hat{Y}) \land (f_{\text{Jev}}^{\text{ground}}(\hat{Y}, X) \ge \tau_{\text{conf}}) \right)$$
3. If $\mathcal{V}(\hat{Y}, X) = 1$, accept and emit $\hat{Y}$.
4. If $\mathcal{V}(\hat{Y}, X) = 0$, escalate:
   $$i \leftarrow \min(i + 1, 3)$$
   Rerun generation $\hat{Y}' \sim \mathcal{T}_{i}(X)$.

#### Token Budget Invariant ($UU3$, `CR-D5`)
To avoid truncating replies mid-way ($KK1$) during cascade execution, the route turn token budget $B_{\text{turn}}$ must satisfy:
$$B_{\text{turn}} \ge \text{Tokens}(\text{Prompt}) + \text{MaxTokens}_{\mathcal{T}_i} + \text{MaxTokens}_{\mathcal{T}_{i+1}}$$
Every turn budget strictly provisions sufficient headroom for exactly **one cascade re-execution step**. If Tier 3 also fails verification, the conversation is handed off to Human-in-the-Loop (`HL-D1`, `HL-D2`).

---

### Pillar 3: Dual-Purpose GPU Sizing & Amortization (`CR-D9`, `RP-D4`)

The dedicated regional GPU cluster (provisioned for disaster recovery under `RP-D4`) operates as an active worker pool during steady-state operations:
1. **Steady-State Co-Serving**: Serves all Tier 1 requests ($s < \theta_1$), absorbing approximately $45–60\%$ of total conversation volume.
2. **GPU Health & Warm Cache**: Continuous baseline traffic ensures model weights stay resident in VRAM, eliminating cold-start latencies and driver page-in delays during external provider outages.
3. **Disaster Recovery Preemption**: If commercial APIs degrade or fail (`RP-D4`), admission control immediately drops Tier 2/Tier 3 routing and shifts all traffic to Tier 1, preempting non-essential batch workloads and degrading gracefully to knowledge-base-only modes if capacity limits are breached.

---

## 3. Technical Implementation & Genesis Contracts

```python
"""
core/cost/model_router.py
Pydantic v2 schemas and routing engine for Tri-Tier Model Selection & Cascading.
"""

from enum import Enum
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, field_validator


class ModelTier(str, Enum):
    TIER_1_LOCAL = "tier_1_local"        # Self-Hosted Open-Weights (Llama 3.1 70B vLLM)
    TIER_2_MID = "tier_2_mid"            # Commercial Mid-Tier (Claude 3.5 Haiku / GPT-4o-mini)
    TIER_3_FRONTIER = "tier_3_frontier"  # Commercial Frontier (Claude 3.5 Sonnet / GPT-4o)


class ModelTierConfig(BaseModel):
    tier: ModelTier
    model_identifier: str
    cost_per_m_in: float
    cost_per_m_out: float
    max_output_tokens: int
    timeout_seconds: float


class RouteThresholds(BaseModel):
    route_name: str
    theta_1_low: float = Field(default=0.35, ge=0.0, le=1.0)
    theta_2_high: float = Field(default=0.75, ge=0.0, le=1.0)

    @field_validator("theta_2_high")
    @classmethod
    def validate_cutoffs(cls, v: float, info: Any) -> float:
        theta_1 = info.data.get("theta_1_low", 0.35)
        if v <= theta_1:
            raise ValueError(f"theta_2_high ({v}) must be strictly greater than theta_1_low ({theta_1})")
        return v


class JevRoutingVerdict(BaseModel):
    complexity_score: float = Field(ge=0.0, le=1.0)
    assigned_tier: ModelTier
    route_name: str
    features_detected: List[str]
    cascade_eligible: bool = True


class VerificationResult(BaseModel):
    passed: bool
    schema_valid: bool
    safety_passed: bool
    promise_backed: bool
    confidence_score: float
    failure_reason: Optional[str] = None


class ModelRouter:
    """
    Executes Jev Acuity Scoring, Model Tier Selection, and Cascade Escalations.
    """

    def __init__(
        self,
        thresholds: Dict[str, RouteThresholds],
        tier_configs: Dict[ModelTier, ModelTierConfig]
    ):
        self.thresholds = thresholds
        self.tier_configs = tier_configs

    def route_turn(self, route_name: str, complexity_score: float) -> JevRoutingVerdict:
        """
        Determines initial model tier based on calibrated route thresholds (CR-D1).
        """
        thresh = self.thresholds.get(route_name, RouteThresholds(route_name="default"))
        
        if complexity_score < thresh.theta_1_low:
            tier = ModelTier.TIER_1_LOCAL
        elif complexity_score < thresh.theta_2_high:
            tier = ModelTier.TIER_2_MID
        else:
            tier = ModelTier.TIER_3_FRONTIER

        return JevRoutingVerdict(
            complexity_score=complexity_score,
            assigned_tier=tier,
            route_name=route_name,
            features_detected=["calibrated_eval_boundary"],
            cascade_eligible=(tier != ModelTier.TIER_3_FRONTIER)
        )

    def escalate_tier(self, current_tier: ModelTier) -> Optional[ModelTier]:
        """
        Determines the next escalation tier for FrugalGPT cascades (CR-D2).
        """
        if current_tier == ModelTier.TIER_1_LOCAL:
            return ModelTier.TIER_2_MID
        elif current_tier == ModelTier.TIER_2_MID:
            return ModelTier.TIER_3_FRONTIER
        return None  # Tier 3 cannot cascade further -> Escalate to HITL
```

---

## 4. Failure Modes & Mitigation Matrix

| Failure ID | Sub-Component | Failure Mode Description | Root Cause | Effect on System | Architectural Mitigation (`CR-D1`, `CR-D2`, `CR-D9`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **$KK1$** | Token Management | Output clipped mid-way during generation | Hard token ceiling imposed mid-sentence | Unusable truncated text sent to user | `CR-D5` replaces arbitrary clipping with a structured wrap-up node or graceful HITL handoff |
| **$KK2$** | Model Selection | Cheap model fails multi-step reasoning | Down-routing based on underestimated complexity | Hallucinated arguments or malformed tool schemas | `CR-D2` cascade immediately intercepts verification failure and re-executes on higher tier |
| **$KK3$** | Cost Tracking | Price table drift vs. cloud invoices | Upstream provider silently updates token rates | Inaccurate showback reports | `CR-D11` enforces monthly automated reconciliation between counter store and raw invoices |
| **$KU1$** | Model Selection | Distributional drift in Jev difficulty scores | Customer query patterns evolve over time | Over-routing to Tier 3 or under-routing to Tier 1 | `EV-D9` recalibrates Jev cutoffs per route prior to every release; monitored via `CI-D9` |
| **$KU2$** | Cost Optimization | Sub-optimal GPU saturation on Tier 1 | Insufficient easy-turn traffic volume | Wasted dedicated GPU budget | Dynamic threshold shifting adjusts $\theta_1$ upwards to capture more traffic on local cluster |
| **$UK1$** | Model Selection | Prompt gaming by adversarial customers | User prefixes prompt with "This is very complex" | False routing to Tier 3 frontier model | `CR-D1` executes Jev routing exclusively on structured features and masked text, ignoring user meta-prompts |
| **$UU3$** | Usage Budgets | Cascade step exhausts turn token budget | Rerunning turn on Tier 2/3 consumes remaining tokens | Abrupt termination or mid-cascade failure | `CR-D5` mandates that all route token budgets provision headroom for exactly one cascade step |
| **$UU4$** | Model Selection | Repeated cascade looping across tiers | Model repeatedly fails non-fixable tool validation | Extreme turn latency and multiplied token spend | Cascade is strictly capped at **one escalation step** per turn; persistent failure triggers HITL |

---

## 5. Closed-Loop Telemetry & Verification Directives

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   CLOSED-LOOP ROUTING & FINOPS TELEMETRY PIPELINE (OB-D13, EV-D9)                 │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Model Invocations ──► [ OpenTelemetry GenAI Spans ] ──► [ Tail-Sampling Collector ]
                                     │                                    │
                                     ▼                                    ▼
                         [ Direct Redis Usage Counter ]          [ Jaeger / OpenSearch ]
                         (RP-D14: Exact Token Sums)              (Trace Analysis & Debug)
                                     │                                    │
                                     ▼                                    ▼
                         [ Monthly FinOps Reconciler ]           [ ECE Calibration Engine ]
                         (CR-D11: Price Table Sync)              (EV-D9: Route Cutoff $\Theta$)
```

### 1. OpenTelemetry Semantic Conventions
Every LLM call emits the standard `gen_ai.*` attributes:
- `gen_ai.system`: `"vllm"` | `"anthropic"` | `"openai"`
- `gen_ai.request.model`: e.g., `"llama-3.1-70b-instruct"`, `"claude-3-5-sonnet-20241022"`
- `gen_ai.cost.tier`: `"tier_1_local"` | `"tier_2_mid"` | `"tier_3_frontier"`
- `gen_ai.cascade.escalated`: `boolean`
- `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` (from provider headers)

### 2. Operational Metrics & Alerts
- `cost.routing.tier_distribution`: Histogram of turns routed to Tier 1 / Tier 2 / Tier 3 (Target: $\ge 45\%$ Tier 1, $\le 20\%$ Tier 3).
- `cost.cascade.escalation_rate`: Rate of turns triggering a cascade rerun (Target: $\le 8\%$). If escalation rate exceeds $15\%$, fire `AlertCostCascadeAnomaly`.
- `cost.tier1.gpu_utilization`: P99 compute utilization on regional DR fallback pools (Target: $60–80\%$).

---

## 6. Alternatives Considered & Trade-Off Analysis

| Architectural Alternative | Technical Mechanism | Why Rejected / Trade-Off Analysis |
| :--- | :--- | :--- |
| **Single Frontier Model (Option A)** | Route 100% of turns to Claude 3.5 Sonnet / GPT-4o | **Rejected ($KK2$ avoided, but extreme cost)**: Quadruples enterprise operating expenses; wastes high-cost frontier tokens on basic navigational greetings and FAQ lookups. |
| **Static Route-Based Binding (Option B)** | Hardcode models to predefined routes in YAML config | **Rejected**: Fragile and brittle. A "billing" route may contain a trivial invoice download (Tier 1) or a multi-dispute complex financial adjustment (Tier 3). Static routing cannot handle intra-route variance. |
| **Two-Tier System (Local + Frontier, CR-Q1(i))** | Eliminate mid-tier; use only local Llama and frontier Sonnet | **Rejected per CR-Q1(ii)**: Created an abrupt cost cliff. Mid-tier models (Claude 3.5 Haiku) solve $80\%$ of moderate tool-calling tasks at $1/10\text{th}$ the price of frontier models. |
| **Cascades on Read-Only Routes Only (CR-F2(c))** | Disallow cascading on state-mutating tool routes | **Rejected**: Tool-calling steps are precisely where cheap models fail structured schema checks; cascading ensures robust tool execution without burdening human specialists. |

---

## 7. References & Academic Foundations

1. **Chen, L., Zaharia, M., & Zou, J.** (2023). *FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance.* arXiv preprint arXiv:2305.05176.
2. **Ong, D. et al.** (2024). *RouteLLM: Learning to Route LLMs with Preference Data.* LMSYS Org Technical Report.
3. **Yao, S. et al.** (2024). *$\tau$-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Environments.* arXiv preprint arXiv:2406.12045.
4. **Stanovich, K. E., & West, R. F.** (2000). *Advancing the rationality debate.* Behavioral and Brain Sciences, 23(5), 701-717.
5. **NIST Special Publication 800-53, Revision 5.** (2020). *Security and Privacy Controls for Information Systems and Organizations.* Resource Allocation (SC-6) and Fault Tolerance (CP-2).
