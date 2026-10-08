# KR-ADP-05: Retrieval Evaluation (Tripartite Triangulation: Offline Golden Sets, Online Implicit Signals & Sampled LLM-Judge Auditing)

- **Status**: Accepted & Confirmed
- **Date**: 2026-09-24 *(Amended: 2026-09-24 per KR-D10/KR-D11 Retrieval Gap Redefinition & Tenant Purge Alignment)*
- **Deciders**: Architecture Team, Lead Search & Retrieval Engineer, Evaluation & LLMOps Lead
- **Component**: `[2] Knowledge & Retrieval` (`Component [ 2 ]`)
- **Reasoning Source**: `checkpoint.md` §6 · Diagram: `LLD - [2] Knowledge & Retrieval`
- **Decisions Covered**:
  - `KR-D11`: Retrieval Evaluation — Comprehensive Tripartite Layering: Offline Golden Sets + Online Implicit Telemetry Signals + Sampled LLM-Judge Production Auditing
- **Adjustments & Boundary Constraints**:
  - *KR-D10 Impact*: Because `KR-D10` unconditionally passes fixed top-$k$ parent sections without retrieval-stage abstention, the legacy `"no_evidence"` signal does not exist. Retrieval gap detection must triangulate using low reranker score distributions, customer re-asks, negative turn sentiment/thumbs, and LLM-judge context precision.
  - *Data Governance & Tenant Isolation*: Sampled LLM-judge evaluation datasets contain production tenant data. Judge evaluations must run strictly within internal execution boundaries and remain fully subject to GDPR Article 17 tenant erasure cascades (`DP-ADP-05`, `SG-ADP-05`).
- **Related Architectural Decision Points**:
  - [`KR-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/02-knowledge-retrieval/KR-ADP-04-retrieval-ranking-pipeline.md): Retrieval & Ranking Pipeline *(First-Stage Hybrid RRF & LLM Reranker Scoring)*
  - [`EV-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#ev-adp-02--eval-framework--harness): Evaluation Framework & Harness *(Deterministic Assertions & LLM Judge Rubrics)*
  - [`EV-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#ev-adp-05--online-monitoring--telemetry): Online Monitoring & Production Telemetry *(Implicit Feedback Streams)*
  - [`CI-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#ci-adp-01--continuous-improvement-signals): Continuous Improvement Signals *(Knowledge Gap Triangulation & Documentation Deficit Logging)*

---

## 1. Context & Problem Statement

In enterprise support systems, retrieval quality directly dictates answer correctness. An agent with access to incorrect or insufficient knowledge chunks inevitably hallucinates, gives misleading instructions, or fails silently. However, evaluating retrieval in production presents three severe challenges:

1. **The Static Golden-Set Mirage ($UK5$)**: Offline evaluation suites test pre-defined, manually curated query-passage pairs. While essential for preventing regressions during code changes, static golden sets rapidly rot as software features evolve, API limits shift, and customer inquiry patterns drift. A retrieval pipeline scoring $95\%$ recall on a static test suite may fail catastrophically in production against newly released features.
2. **The Loss of the Explicit Abstain Signal ($KR-D10$)**: Under `KR-D10`, the retrieval subsystem never abstains (`no_evidence` is eliminated; fixed top-$k$ parent sections are unconditionally admitted). Consequently, the classic metric for knowledge gaps—the *no-evidence trigger rate*—is unavailable. If retrieval silently passes irrelevant documents, naive telemetry records a nominal "retrieval success," obscuring severe knowledge vacuums.
3. **The Prohibitive Cost and Privacy Exposure of Exhaustive LLM Auditing**: Running an LLM judge on $100\%$ of production retrievals to verify context relevance introduces unacceptable latency, doubles inference expenditures, and exposes raw multi-tenant customer inquiries to evaluation pipelines without strict isolation.

### The Core Architectural Question
> **How do we rigorously quantify, continuously monitor, and proactively detect retrieval degradation and knowledge base deficits across both pre-deployment pipelines and live production traffic, without an explicit retrieval abstain signal and without compromising tenant data residency?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve this challenge, `KR-D11` establishes a **Tripartite Triangulation Architecture** spanning three synchronized measurement planes:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
 theoretical triangulation: retrieval evaluation architecture                                     │
├────────────────────────────────┬────────────────────────────────┬────────────────────────────────┤
│   Layer 1: Offline Golden      │   Layer 2: Online Implicit     │   Layer 3: Sampled LLM Judge   │
│   Benchmark Harness (CI/CD)    │   Behavioral Telemetry (100%)  │   Production Auditing (1–5%)   │
│                                │                                │                                │
│   • Version-controlled dataset │   • Reranker score mass (KR-D9)│   • Context Precision (CP@k)   │
│   • Deterministic ground truth │   • User conversational re-asks│   • Context Recall (CR@k)      │
│   • NDCG@10, MRR, HitRate@k    │   • Downstream thumbs up/down  │   • Faithfulness grounding     │
│   • Masked vs. unmasked tests  │   • Citation click tracking    │   • Multi-tenant safe sandbox  │
└────────────────────────────────┴────────────────────────────────┴────────────────────────────────┘
                                                │
                                                ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   CONTINUOUS COMPOSITE RETRIEVAL DEFICIT INDEX (RDI)                             │
│       Triangulates implicit friction + low reranker confidence to flag knowledge gaps            │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Layer 1: Offline Golden Benchmark Formulations

The offline harness operates in pre-commit and nightly continuous integration workflows. Given a benchmark corpus of $N$ evaluation queries $Q = \{q_1, q_2, \dots, q_N\}$ with human-annotated binary or graded relevance judgments $R(q, d) \in \{0, 1, \dots, r_{\max}\}$ over document universe $\mathcal{D}$:

1. **Normalized Discounted Cumulative Gain ($NDCG@k$)**:
   $$\text{DCG}@k(q) = \sum_{i=1}^k \frac{2^{R(q, d_{\pi(i)})} - 1}{\log_2(i + 1)}$$
   $$\text{NDCG}@k(q) = \frac{\text{DCG}@k(q)}{\text{IDCG}@k(q)}$$
   where $\pi(i)$ is the document at rank $i$ returned by the pipeline, and $\text{IDCG}@k(q)$ is the ideal DCG obtained by an optimal descending sort of relevance labels.

2. **Mean Reciprocal Rank ($MRR$)**:
   $$\text{MRR} = \frac{1}{|Q|} \sum_{i=1}^{|Q|} \frac{1}{\min \{r : R(q_i, d_{\pi(r)}) > 0\}}$$

3. **Masking Distortion Coefficient ($\Delta_{\text{mask}}$)**:
   Per `KU4` and `UU3`, offline benchmarks explicitly execute two runs across identical queries: unmasked raw queries $\mathcal{R}_{\text{raw}}$ vs. Presidio-masked queries $\mathcal{R}_{\text{masked}}$. We enforce:
   $$\Delta_{\text{mask}} = 1 - \frac{\text{NDCG}@10(\mathcal{R}_{\text{masked}})}{\text{NDCG}@10(\mathcal{R}_{\text{raw}})} \le 0.05$$
   If token masking degrades NDCG by more than $5\%$, the PII entity masking allow-list is rejected.

---

### Layer 2: Online Implicit Behavioral Telemetry

Because `KR-D10` forces admission of top-10 chunks regardless of relevance, implicit telemetry tracks behavioral proxies for retrieval failure in real-time across $100\%$ of production requests.

We formulate the **Retrieval Confidence Mass ($\mathcal{M}_{\text{rerank}}$)**:
Let $\{s_1, s_2, \dots, s_k\}$ be the raw logit scores assigned to the top-$k$ parent sections by the LLM reranker (`KR-D9`), normalized via softmax over the candidate pool:
$$\bar{s}_i = \frac{\exp(s_i / T)}{\sum_{j=1}^M \exp(s_j / T)}$$
The top-3 mass is defined as:
$$\mathcal{M}_{\text{top3}} = \sum_{i=1}^3 \bar{s}_i$$

When $\mathcal{M}_{\text{top3}} < \tau_{\text{marginal}}$ (empirically calibrated at $\tau_{\text{marginal}} = 0.35$), the retrieval pipeline flags a **Potential Evidence Vacuum**.

To compensate for the lack of an explicit `no_evidence` branch, we construct the **Composite Retrieval Deficit Index ($RDI$)**:
$$RDI(t) = w_1 \cdot \mathbb{I}(\mathcal{M}_{\text{top3}} < \tau) + w_2 \cdot \mathbb{I}(\text{ReAsk}_{t+1}) + w_3 \cdot \mathbb{I}(\text{NegativeFeedback}_t) - w_4 \cdot \mathbb{I}(\text{CitationClicked}_t)$$
Where:
- $\mathbb{I}(\text{ReAsk}_{t+1})$ detects if turn $t+1$ rephrases the same intent due to agent confusion (detected by Jev `Noul`).
- $\mathbb{I}(\text{NegativeFeedback}_t)$ tracks user thumbs-down or agent escalation tripwires.
- Weights $w = [0.35, 0.35, 0.20, 0.10]$ produce an $RDI \in [0, 1]$. An $RDI > 0.65$ triggers a Knowledge Gap alert in `CI-ADP-01`.

---

### Layer 3: Sampled LLM-Judge Production Auditing

For deep semantic auditing, a stratified random sample of production retrievals ($\rho \in [0.01, 0.05]$, $1\%$ baseline, scaled to $5\%$ for high-risk enterprise tenants) is asynchronously evaluated using an LLM Judge (`EV-D2`).

1. **Context Precision ($CP@k$)** (RAGAS framework; Es et al., 2023):
   Quantifies whether relevant chunks are prioritized at the top of the context window to prevent "Lost in the Middle" attention degradation (`ADP-03`):
   $$CP@k = \frac{\sum_{r=1}^k (P@r \times v_r)}{\sum_{r=1}^k v_r}$$
   where $v_r \in \{0, 1\}$ is the LLM-judge binary verdict determining whether passage $d_r$ provides factual evidence required to address query $q$, and $P@r = \frac{\sum_{i=1}^r v_i}{r}$.

2. **Context Sufficiency / Recall ($CR$)**:
   The judge evaluates whether the retrieved passage set $\mathcal{D}_{\text{admitted}}$ completely covers the atomic claims required to answer query $q$:
   $$CR = \frac{|\mathcal{C}_{\text{grounded}}|}{|\mathcal{C}_{\text{required}}|}$$
   where $\mathcal{C}_{\text{required}}$ are gold semantic propositions extracted from the user turn, and $\mathcal{C}_{\text{grounded}}$ are propositions supported by $\mathcal{D}_{\text{admitted}}$.

---

## 3. Decision Rules, Structural Invariants & Code Contracts

### Decision Invariants
1. **Invariant 1 (Deterministic Layer Decoupling)**: Online production serving MUST NEVER synchronously await LLM-judge evaluation. Layer 3 auditing runs strictly out-of-band via asynchronous queue workers (`evaluation-audit-queue`).
2. **Invariant 2 (Tenant Sandbox & Privacy Containment)**: Judge evaluations MUST execute in the primary tenant boundary. No production query or retrieved ticket chunk may be dispatched to external non-enterprise LLM evaluation endpoints.
3. **Invariant 3 (GDPR Article 17 Erasure Compliance)**: All sampled retrieval traces, judge verdicts, and cached eval tuples must be tagged with `(tenant_id, principal_id)` and deleted immediately upon customer erasure invocations (`MS-D14`, `DP-ADP-05`).
4. **Invariant 4 (Reranker Schema Fallback Logging)**: Any execution triggering `KR-D12` (schema failure falling back to RRF ordering) automatically sets `reranker_fallback_flag = True` and increments the Layer 2 degradation counter.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             RETRIEVAL EVALUATION PIPELINE                                        │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                │
                                                ▼
                             ┌──────────────────────────────────────┐
                             │    Production Request & Context      │
                             │   (Standalone Query + Top-10 Chunks) │
                             └──────────────────────────────────────┘
                                                │
                       ┌────────────────────────┴────────────────────────┐
                       ▼                                                 ▼
        ┌─────────────────────────────┐                   ┌─────────────────────────────┐
        │  Layer 2: Real-time Telemetry│                   │    Sampling Filter (ρ=0.02) │
        │  - Extract Reranker Scores  │                   │    Check Tenant Sampling Rate│
        │  - Capture Re-Ask Signals   │                   └─────────────────────────────┘
        │  - Compute RDI in StatsD    │                                  │
        └─────────────────────────────┘                                  ▼
                                                          ┌─────────────────────────────┐
                                                          │ Async Evaluation Queue Worker│
                                                          │ (Internal Boundary Isolated)│
                                                          └─────────────────────────────┘
                                                                         │
                                                                         ▼
                                                          ┌─────────────────────────────┐
                                                          │   Layer 3: LLM Judge Engine  │
                                                          │   - Score Context Precision │
                                                          │   - Verify Claim Coverage   │
                                                          │   - Log to PostHog / Langfuse│
                                                          └─────────────────────────────┘
```

---

### Python & Pydantic Data Contracts

```python
"""
Core contracts for the Tripartite Retrieval Evaluation Pipeline.
Module: core/retrieval/evaluation.py
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime
from enum import Enum


class MetricType(str, Enum):
    NDCG_AT_10 = "ndcg@10"
    MRR = "mrr"
    HIT_RATE_AT_10 = "hit_rate@10"
    CONTEXT_PRECISION = "context_precision"
    CONTEXT_RECALL = "context_recall"
    RETRIEVAL_DEFICIT_INDEX = "rdi"


class RetrievalTrace(BaseModel):
    """Production retrieval event captured for online telemetry and auditing."""
    trace_id: str = Field(..., description="Unique trace identifier linked to turn execution")
    tenant_id: str = Field(..., description="Multi-tenant identifier for physical isolation")
    principal_id: str = Field(..., description="Authenticated user principal ID (for GDPR purge)")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Query details
    raw_query: str = Field(..., description="PII-masked conversational standalone query")
    extracted_identifiers: List[str] = Field(default_factory=list)
    
    # Admitted chunks (KR-D10 top-10)
    admitted_chunk_ids: List[str] = Field(..., max_items=10)
    reranker_scores: List[float] = Field(..., description="Normalized confidence scores from KR-D9")
    reranker_fallback_invoked: bool = Field(
        default=False, 
        description="True if KR-D12 schema fallback to RRF was triggered"
    )
    
    # Online telemetry proxies (Layer 2)
    user_reask_detected: bool = Field(default=False)
    negative_feedback_received: bool = Field(default=False)
    citation_clicked: bool = Field(default=False)
    computed_rdi: Optional[float] = Field(None, ge=0.0, le=1.0)


class JudgeVerdict(BaseModel):
    """Detailed LLM Judge evaluation verdict for a single retrieved passage."""
    chunk_id: str
    rank: int
    is_relevant: bool = Field(..., description="Binary indicator if chunk contains factual ground truth")
    relevance_explanation: str = Field(..., description="Chain-of-thought justification from judge rubric")


class Layer3JudgeAuditResult(BaseModel):
    """Output contract for sampled Layer 3 LLM-judge evaluation."""
    trace_id: str
    tenant_id: str
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)
    judge_model_id: str = Field(..., example="anthropic.claude-3-5-sonnet")
    
    verdicts: List[JudgeVerdict]
    context_precision_at_10: float = Field(..., ge=0.0, le=1.0)
    context_recall: float = Field(..., ge=0.0, le=1.0)
    knowledge_gap_detected: bool = Field(
        ..., 
        description="True if context_recall < 0.50, signaling documentation deficit"
    )


class OfflineBenchmarkResult(BaseModel):
    """Output of pre-commit / nightly offline golden test suite."""
    suite_id: str
    run_timestamp: datetime = Field(default_factory=datetime.utcnow)
    total_queries: int
    
    ndcg_at_10: float = Field(..., ge=0.0, le=1.0)
    mrr: float = Field(..., ge=0.0, le=1.0)
    hit_rate_at_10: float = Field(..., ge=0.0, le=1.0)
    masking_distortion_delta: float = Field(
        ..., 
        description="Delta between raw vs Presidio-masked queries (KU4)"
    )
    passed_release_threshold: bool
```

---

## 4. Failure Modes Matrix & Resilience Invariants

| Quadrant | Failure Scenario | Detection Mechanism | Systemic Mitigation & Recovery |
| :--- | :--- | :--- | :--- |
| **Q1: Known Knowns** | **Golden Set Rot ($UK5$)**: Offline benchmark passes with $98\%$ NDCG, but live users ask about newly shipped features resulting in zero retrieval relevance. | Layer 2 composite $RDI$ surges; Layer 3 LLM judge flags low Context Precision ($<0.40$). | Automated weekly golden set synthesis from resolved high-CSAT transcripts (`CI-ADP-01`); stale benchmark deprecation. |
| **Q2: Known Unknowns** | **Reranker Schema Collapse ($KR-D12$)**: LLM reranker encounters extreme context pressure and emits non-JSON rankings. | `reranker_fallback_invoked` metric alerts in Prometheus; FallbackRate counter increments. | Immediate graceful fallback to raw RRF rank ordering (`KR-D12`); eval system flags anomaly for model-tier review. |
| **Q3: Unknown Knowns** | **PII Masking Entity Distortion ($KU4 / UU3$)**: Aggressive regex/NER masking transforms technical identifiers (e.g., masking `ID-9021` as `[REDACTED]`), destroying search recall. | Offline golden set comparative run computes $\Delta_{\text{mask}} > 0.05$. | Pipeline test aborts release; updates custom entity preservation regex allow-list (`SG-D5`). |
| **Q4: Unknown Unknowns** | **Adversarial Poisoning of Judge Audit ($UU1$)**: Malicious customer prompt contains prompt injection instructing the offline/async judge to rate context precision as $1.0$. | Judge reasoning trace divergence detector; cross-validation against Layer 2 implicit signals. | LLM Judge runs behind rigorous untrusted text spotlighting with independent system prompt fencing; audit anomalies flag human review. |

---

## 5. Closed-Loop Feedback & Verification Signals

The retrieval evaluation framework acts as the primary sensory organ for system health:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                            CLOSED-LOOP CONTINUOUS IMPROVEMENT ENGINE                             │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                │
                     ┌──────────────────────────┴──────────────────────────┐
                     ▼                                                     ▼
      ┌─────────────────────────────┐                       ┌─────────────────────────────┐
      │  Live Telemetry Spikes      │                       │  Sampled Judge Gap Flag     │
      │  RDI > 0.65 across >5 turns │                       │  Context Recall < 0.50      │
      └─────────────────────────────┘                       └─────────────────────────────┘
                     │                                                     │
                     └──────────────────────────┬──────────────────────────┘
                                                │
                                                ▼
                             ┌──────────────────────────────────────┐
                             │   Continuous Improvement Dispatcher  │
                             │              (CI-ADP-01)             │
                             └──────────────────────────────────────┘
                                                │
                       ┌────────────────────────┴────────────────────────┐
                       ▼                                                 ▼
        ┌─────────────────────────────┐                   ┌─────────────────────────────┐
        │ Action A: KB Article Draft  │                   │ Action B: Query Formulation │
        │ Automated ticket to Product │                   │ Refinement / Synonym Tuning │
        │ Docs Team to fill bug docs  │                   │ Updates BM25 token filters  │
        └─────────────────────────────┘                   └─────────────────────────────┘
```

1. **Continuous Telemetry Thresholds**:
   - `RDI_p95 > 0.60` over a 15-minute rolling window triggers a P2 alert for retrieval degradation.
   - `Reranker_Fallback_Rate > 1.0%` halts automated canary deployments.
2. **Weekly Knowledge Deficit Aggregation**:
   Traces exhibiting both high $RDI$ and low LLM-judge context precision are clustered by semantic topic via HDBSCAN. Clusters containing $\ge 10$ customer turns automatically generate drafted Knowledge Centered Service (KCS) article candidates in Jira/Confluence.

---

## 6. Genesis Implementation Directives

1. **File Locations**:
   - Implement evaluation data contracts in `core/retrieval/evaluation.py`.
   - Implement the offline golden benchmark harness in `eval/retrieval/golden_runner.py`.
   - Implement the async Layer 3 judge worker in `workers/eval_judge_worker.py`.
   - Implement the telemetry calculation and $RDI$ aggregator in `core/retrieval/telemetry.py`.
2. **Database & Telemetry Integrations**:
   - Store offline benchmark artifacts in MLflow / Langfuse.
   - Emit Layer 2 metrics (`rdi`, `reranker_scores`, `fallback_rate`) via OpenTelemetry/StatsD to Prometheus.
   - Persist Layer 3 judge audits in Postgres `retrieval_audits` partitioned by `tenant_id`.
3. **Privacy & Erasure Protocol**:
   - Register `retrieval_audits` in the Central Erasure Inventory (`MS-D14`, `DP-ADP-05`).
   - Hard-delete all audit records matching `(tenant_id, principal_id)` within $\le 24$ hours of GDPR erasure webhook receipt.

---

## 7. Consequences & Trade-offs

### Positive Consequences
- **Comprehensive Deficit Visibility**: Eliminating reliance on a single metric ensures the system detects both gradual model rot (via offline benchmarks) and acute feature coverage gaps (via live $RDI$ telemetry).
- **Cost-Controlled Audit Depth**: Sampling $1\% - 5\%$ of production traffic limits LLM judge API costs while preserving high statistical confidence intervals ($p < 0.01$).
- **Deterministic Deployment Gate**: Pre-commit gating on NDCG@10 and $\Delta_{\text{mask}}$ prevents destructive embedding regressions from ever reaching staging or production.

### Negative Consequences & Trade-offs
- **Indirect Evidence Void Signal**: Because `KR-D10` eliminated explicit `no_evidence` returns, identifying unanswerable queries relies entirely on probabilistic proxies ($RDI$) rather than deterministic boolean flags.
- **Judge Inference Latency & Cost Overhead**: While sampled out-of-band, high-volume enterprise deployments processing $10^6$ queries/day still incur significant daily judge token expenses (~$20,000$ daily judge invocations at $\rho = 0.02$).
- **Tenant Data in Audit Logs**: Storing customer questions and retrieved text in audit tables creates a continuous operational burden for GDPR compliance and cryptographic lifecycle management.

---

## 8. References & Cross-Disciplinary Grounding

1. **RAGAS: Automated Evaluation of Retrieval Augmented Generation**: Es, S., James, J., Espinosa-Anke, L., & Schockaert, S. (2023). *RAGAS: Automated Evaluation of Retrieval Augmented Generation*. arXiv:2309.15217.
2. **Evaluating Information Retrieval Systems**: Manning, C. D., Raghavan, P., & Schütze, H. (2008). *Introduction to Information Retrieval*. Cambridge University Press. (Foundations of NDCG and MRR).
3. **Triangulation in Social Research**: Denzin, N. K. (1978). *The Research Act: A Theoretical Introduction to Sociological Methods*. McGraw-Hill. (Methodological grounding for tripartite metric fusion).
4. **GDPR Article 17 (Right to Erasure)**: Regulation (EU) 2016/679 of the European Parliament and of the Council.
5. **Mitigating Attention Degradation in Long Contexts**: Liu, N. F., Lin, K., Hewitt, J., Paranjape, A., Bevilacqua, M., Petroni, F., & Liang, P. (2023). *Lost in the Middle: How Language Models Use Long Contexts*. Transactions of the ACL.
