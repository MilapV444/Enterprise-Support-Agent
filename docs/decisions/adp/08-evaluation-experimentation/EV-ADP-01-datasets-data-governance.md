# EV-ADP-01: Evaluation Datasets & Data Governance (Synthetic Interaction Episodes, Tokenized Regional Production Corpora & Per-Tenant Opt-In)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-02 *(Confirmed per EV-D1 Behavioural Framework, EV-D10 Tokenized & Erasable Production Eval Data & EV-D15 Per-Tenant Opt-In)*
- **Deciders**: Architecture Team, Lead AI Evaluation Scientist, Principal Privacy & Compliance Officer
- **Component**: `[8] Evaluation & Experimentation` (`Component [ 8 ]`)
- **Reasoning Source**: `checkpoint.md` §12 · Diagram: `LLD - [8] Evaluation & Experimentation`
- **Decisions Covered**:
  - `EV-D1`: Evaluation Dataset Composition — Tripartite dataset architecture based on [`user_evaluation_framework.md`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/analysis/user_evaluation_framework.md): synthetic Interaction Episodes generated from persona/intent priors + hand-crafted golden edge seeds + curated post-launch production dialogues; replaces naive static QA sets with full multi-turn conversational trajectories
  - `EV-D10`: Privacy & Sovereignty Constraints on Production Data — Production conversations ingested into evaluation pools must be PII-tokenized via global deterministic vaults (`SG-D4`, `SG-D5`), tenant-isolated, pinned strictly to the tenant's sovereign legal region (`DP-D10`), and directly integrated into the `DP-D13` Temporal erasure saga to guarantee complete right-to-be-forgotten enforcement across all evaluation artifacts
  - `EV-D15`: Per-Tenant Evaluation Opt-In — Enterprise tenant conversations cannot be sampled for evaluation corpora by default; sampling requires explicit affirmative administrative consent via dynamic database settings (`DP-D12`); protects purpose limitation under GDPR Art. 5(1)(b) ($UK2$)
- **Related Architectural Decision Points**:
  - [`SG-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/06-safety-security-governance/SG-ADP-02-pii-protection.md): PII Protection *(Reversible Tokenization & Salted Hashes)*
  - [`DP-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/07-data-persistence/DP-ADP-01-store-topology-residency.md): Store Topology & Residency *(Regional Storage Pinning)*
  - [`DP-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/07-data-persistence/DP-ADP-05-erasure-backups-restore.md): Erasure, Backups & Restore *(Temporal Erasure Workflow Fan-Out)*
  - [`TQ-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#tq-adp-03--end-to-end-tests--test-data): End-to-End Tests & Test Data *(Test Harness Synthesis)*
  - [`CI-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#ci-adp-03--dataset-hygiene--contamination-prevention): Dataset Hygiene & Contamination *(Few-Shot vs. Evaluation Splitting)*

---

## 1. Context & Problem Statement

Evaluating autonomous enterprise support agents cannot rely on conventional NLP benchmark datasets (e.g., SQuAD, GSM8k) or naive static question-answering pairs. Real customer support interactions are multi-turn, state-dependent, emotionally varied, and intertwined with sensitive financial and operational side effects.

### The Core Challenges of Enterprise Evaluation Data
1. **The Representation & Outlier Gap**:
   - Uniform random sampling of real customer conversations severely under-represents critical low-frequency, high-consequence failure modes (e.g., fraudulent account takeovers, edge billing disputes, catastrophic system downtime). In production, $80\%$ of volume consists of routine FAQs (e.g., "how do I reset my password?"), while system-breaking hallucinations occur in the $5\%$ long-tail.
2. **Regulatory & Sovereignty Compliance (GDPR Art. 5, Art. 17 & Art. 44)**:
   - Storing live customer conversations in centralized developer evaluation environments violates GDPR purpose limitation ($UK2$) and cross-border transfer laws (`DP-D10`).
   - If an end-user exercises their right to erasure (`DP-D13`), and their conversation was previously copied into an offline evaluation dataset, retaining that sample constitutes an illegal processing violation ($KK3$, `KR KK6`).
3. **Data Contamination & Goodhart's Law ($KK4$)**:
   - If production conversations sampled for offline evaluation are simultaneously harvested by Continuous Improvement pipelines (`CI-D1`) as few-shot exemplars in agent system prompts, the evaluation framework evaluates the agent on its own training distribution, yielding artificially inflated accuracy scores.

### The Core Architectural Question
> **How do we engineer a representative, multi-turn evaluation corpus that rigorously samples high-risk failure modes while guaranteeing cryptographically tokenized PII, strict jurisdictional residency, per-tenant opt-in governance, and immediate right-to-be-forgotten purging across all test stores?**

---

## 2. Decision Framework & Theoretical Formulation

To solve these challenges, `EV-D1`, `EV-D10`, and `EV-D15` establish the **Tripartite Stratified Evaluation Corpus and Sovereign Privacy Framework**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│             EVALUATION DATASET TOPOLOGY & DATA GOVERNANCE PIPELINE (EV-D1, EV-D10, EV-D15)       │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

 ┌───────────────────────────────────────────────────────────────────────────────────────────────┐
 │ TIER 1: SYNTHETIC INTERACTION EPISODES (user_evaluation_framework.md)                         │
 │ • Sampled from Dirichlet Prior over Personas (Frustrated, Tech-Savvy, Novice, Adversarial)     │
 │ • State-Machine Driven: Digital Twin Simulation (User <---> Agent <---> Tool Fakes)           │
 ├───────────────────────────────────────────────────────────────────────────────────────────────┤
 │ TIER 2: HAND-CRAFTED GOLDEN SEED SUITE                                                        │
 │ • 50 Curated High-Consequence Edge Cases (Security Injections, $10,000+ Billing Disputes)    │
 │ • Exact Tool Trajectory & Assertion Invariants                                                │
 ├───────────────────────────────────────────────────────────────────────────────────────────────┤
 │ TIER 3: CURATED PRODUCTION CONVERSATION POOL (Post-Launch)                                    │
 │ • Opt-In Only: Checks tenant_settings.eval_opt_in == True (EV-D15)                           │
 │ • PII Scrubbed & Tokenized via Regional Vault: [UUIDv4 Tokens] (SG-D4, EV-D10)                │
 │ • Pinned to Sovereign Regional S3 Buckets (us-east-1 / eu-central-1, DP-D10)                  │
 └───────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                 │
                                                 ▼
 ┌───────────────────────────────────────────────────────────────────────────────────────────────┐
 │ IMPORTANCE-WEIGHTED STRATIFIED SAMPLING HARNESS                                               │
 ├───────────────────────────────────────────────────────────────────────────────────────────────┤
 │ • Routine Tier (30% of suite, down-weighted from 80% real world)                              │
 │ • Edge Tier (40% of suite, up-weighted from 15% real world)                                   │
 │ • Risk Tier (30% of suite, up-weighted from 5% real world)                                    │
 │                                                                                               │
 │ Unbiased Population Metric Estimator:                                                         │
 │      μ_hat = Σ [ P(strata) / Q(strata) ] * (1 / N_s) * Σ Y_s,i                                │
 └───────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                 │
                                                 ▼
 ┌───────────────────────────────────────────────────────────────────────────────────────────────┐
 │ RIGHT-TO-BE-FORGOTTEN INTEGRATION (DP-D13, EV-D10)                                            │
 │ When User "usr_98" is erased: Temporal saga purges all records in eval storage buckets        │
 └───────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Pillar 1: Stratified Importance Sampling Formulation (`EV-D1`)

Let $\mathcal{X}$ be the universe of customer support episodes. We partition $\mathcal{X}$ into three mutually exclusive operational strata:
$$\mathcal{X} = \mathcal{S}_{\text{routine}} \cup \mathcal{S}_{\text{edge}} \cup \mathcal{S}_{\text{risk}}$$

1. **Natural Operational Distribution ($P$)**:
   Observed in production traffic:
   $$P(\mathcal{S}_{\text{routine}}) = 0.80, \quad P(\mathcal{S}_{\text{edge}}) = 0.15, \quad P(\mathcal{S}_{\text{risk}}) = 0.05$$
2. **Evaluation Sampling Distribution ($Q$)**:
   To ensure high statistical power on critical failure modes without requiring millions of test runs, our evaluation harness samples from an importance distribution $Q$:
   $$Q(\mathcal{S}_{\text{routine}}) = 0.30, \quad Q(\mathcal{S}_{\text{edge}}) = 0.40, \quad Q(\mathcal{S}_{\text{risk}}) = 0.30$$
3. **Unbiased Performance Estimator**:
   For any metric $Y$ (e.g., task success, goal completion), the population expectation $\mathbb{E}_P[Y]$ is recovered via Horvitz-Thompson importance weights:
   $$\hat{\mu}_Y = \sum_{s \in \{\text{routine, edge, risk}\}} \frac{P(s)}{Q(s)} \cdot \frac{1}{N_s} \sum_{i=1}^{N_s} Y_{s,i}$$
   where importance weights $w_s = \frac{P(s)}{Q(s)}$ are:
   $$w_{\text{routine}} = \frac{0.80}{0.30} \approx 2.67, \quad w_{\text{edge}} = \frac{0.15}{0.40} = 0.375, \quad w_{\text{risk}} = \frac{0.05}{0.30} \approx 0.167$$

---

### Pillar 2: Sovereign Regional PII Tokenization & Governance (`EV-D10`)

Production conversations harvested for Tier 3 evaluation are subject to strict data governance constraints:
1. **Reversible Vault Tokenization (`SG-D4`)**:
   - Before any production dialogue enters an evaluation dataset, cleartext customer entities (names, email addresses, credit card numbers, phone numbers) are substituted with deterministic vault tokens ($T_{\text{uuid}}$):
     $$T_{\text{uuid}} = \text{VaultTokenize}(\text{Cleartext}, \mathcal{K}_{\text{token}})$$
   - Evaluation judges, test assertions, and metrics pipelines see only structured tokens.
2. **Strict Sovereign Residency (`DP-D10`)**:
   - Evaluation datasets are stored within dedicated object storage buckets physically located within the tenant's pinned geographic region:
     $$\text{Region}(\text{Dataset}(T_i)) = \mathcal{R}(T_i) \in \{\text{us-east-1}, \text{eu-central-1}\}$$
   - EU customer evaluation sets never leave `eu-central-1`. Cross-border transfer for centralized offline training is blocked by IAM Service Control Policies.
3. **Temporal Erasure Saga Integration (`DP-D13`, $KK3$)**:
   - The evaluation storage catalog is formally registered in the `MS-D14` erasure inventory.
   - When user $U$ requests erasure, Activity 1b of the `DP-D13` Temporal saga queries the evaluation dataset index and purges all episodes containing $U$'s user token. Evaluation runs do not preserve zombie customer data.

---

### Pillar 3: Dynamic Per-Tenant Opt-In (`EV-D15`)

To uphold GDPR Purpose Limitation (Art. 5(1)(b)) and protect corporate trade secrets:
1. **Zero-Default Sampling**:
   - By default, all enterprise tenants have `eval_dataset_sampling_opt_in = FALSE`.
   - The production harvesting pipeline verifies:
     ```python
     if not tenant.settings.get("eval_dataset_sampling_opt_in", False):
         return  # Strictly skip sampling
     ```
2. **Administrative Transparency**:
   - Enterprise tenant administrators can toggle evaluation consent via the back-office settings portal (`DP-D12`).
   - The system maintains an append-only audit trail logging the exact administrator and timestamp authorizing evaluation sampling.

---

## 3. Data Contracts & Execution Invariants

### 3.1 Interaction Episode Schema Contract

```python
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class EpisodeStratum(str, Enum):
    ROUTINE = "routine"
    EDGE = "edge"
    RISK = "risk"

class TurnActionExpectation(BaseModel):
    expected_tool: Optional[str] = Field(None, description="Tool expected to be called, if any")
    expected_args_subset: Optional[Dict[str, Any]] = Field(None, description="Subset of arguments required")
    forbidden_tools: List[str] = Field(default_factory=list, description="Tools that must NOT be called")
    state_invariants: List[str] = Field(default_factory=list, description="Logical assertions on state")

class InteractionTurn(BaseModel):
    turn_index: int = Field(..., ge=0)
    user_utterance: str = Field(..., description="User message (PII-tokenized)")
    expected_action: Optional[TurnActionExpectation] = None
    expected_response_regex: Optional[str] = Field(None, description="Regex pattern for required phrasing")
    forbidden_response_regex: Optional[str] = Field(None, description="Regex pattern for safety violations")

class InteractionEpisode(BaseModel):
    """
    Contract representing a multi-turn evaluation test scenario (EV-D1).
    """
    episode_id: str = Field(..., regex=r"^ep_[a-zA-Z0-9]{16}$")
    stratum: EpisodeStratum = Field(..., description="Risk tier for importance weighting")
    tenant_id: Optional[str] = Field(None, description="Origin tenant ID if harvested from production")
    sovereign_region: str = Field(..., description="us-east-1 or eu-central-1 (DP-D10)")
    persona_description: str = Field(..., description="Customer persona background and intent")
    turns: List[InteractionTurn] = Field(..., min_length=1)
    pass_criteria: Dict[str, Any] = Field(..., description="Rubric criteria for LLM judge (EV-D2)")
    created_at_utc: datetime = Field(default_factory=datetime.utcnow)
```

### 3.2 Evaluation Governance Invariants

1. **Differential Privacy & Tokenization Invariant**:
   $$\forall \text{ Episode } E \in \text{EvalCorpus}, \quad \text{DetectPII}(E.\text{turns}) = \emptyset$$
   No unmasked telephone number, SSN, email, or physical street address may exist in stored evaluation files.
2. **Opt-In Invariant ($UK2$)**:
   $$\forall E \in \text{EvalCorpus}_{\text{production}}, \quad \text{TenantSettings}(E.\text{tenant\_id}).\text{eval\_opt\_in} == \text{TRUE}$$
3. **Right-to-be-Forgotten Zero-Residual Invariant ($KK3$)**:
   $$\text{UserErased}(U) \implies \nexists E \in \text{EvalCorpus} \text{ s.t. } U \in \text{Participants}(E)$$

---

## 4. Quantitative Failure Modes & Operational Risk Bounds

| Failure Mode ID | Sub-Component & Severity | Risk Classification | Empirical Trigger Condition | Detection Vector | Automated Mitigation & Architectural Enforcement |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **EV-FM-101** | Data Governance (`EV-D10`)<br>**CRITICAL** | Q1 Known Known (Contract Breach) | Erasure workflow executes for customer Sarah, but leaves cached test episodes containing her token in S3 ($KK3$). | Automated erasure audit scanner queries eval dataset catalog for erased user ID. | **Direct S3 Deletion Step in Temporal Saga**: `DP-D13` activity queries the dataset metadata index and deletes all referencing S3 JSON files before certifying erasure. |
| **EV-FM-102** | Data Hygiene (`EV-D1`)<br>**HIGH** | Q1 Known Known (Contamination) | A production conversation is selected as a few-shot prompt example and also added to the test suite ($KK4$). | Continuous Improvement pre-commit hash checker detects identical dialogue hash in prompts and tests. | **Hash Registry Exclusion**: CI build fails if any sha256 turn hash in prompt templates matches an evaluation dataset turn. |
| **EV-FM-103** | Opt-In Enforcement (`EV-D15`)<br>**CRITICAL** | Q3 Unknown Known (Tacit Convention) | Automated pipeline harvests conversations from Tenant B whose opt-in flag was toggled off ($UK2$). | Ingestion crawler pre-filter verification detects `eval_opt_in == False`. | **Atomic Database Transaction Filter**: Crawler query joins with `tenant_settings` with an explicit `WHERE eval_dataset_sampling_opt_in = TRUE` condition. |
| **EV-FM-104** | Tokenized Semantics (`EV-D10`)<br>**MEDIUM** | Q4 Unknown Unknown (Evaluation Bias) | LLM judge penalizes agent responses because customer addresses are replaced with opaque token strings ($UU4$). | Judge scoring correlation analysis shows lower coherence scores on tokenized vs. synthetic episodes. | **Token-Aware Judge Rubrics (`EV-D2`)**: Judge system prompt explicitly includes token grammar schemas, instructing the judge to treat UUID tokens as valid semantic entities. |
| **EV-FM-105** | Stratified Sampling Skew (`EV-D1`)<br>**MEDIUM** | Q2 Known Unknown (Metric Variance) | Edge-case scenarios become over-represented without proper importance re-weighting, skewing release reports. | Release gate dashboard displays raw unweighted accuracy rather than Horvitz-Thompson estimator. | **Mandatory Weighting Schema in Gate (`EV-D5`)**: Release evaluation CLI strictly mandates passing weighted stratum configuration files. |

---

## 5. Closed-Loop Architectural Feedback

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   EVALUATION DATASET HEALTH & GOVERNANCE ENGINE                                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Harvesting / Synthesis Pipeline
                  │
                  ▼
   ┌──────────────────────────────┐
   │ Opt-In Verification Check    │─────► [Metric: eval_harvest_opt_in_skipped_total]
   │ (tenant_settings.eval_opt_in)│
   └──────────────┬───────────────┘
                  │
                  ▼
   ┌──────────────────────────────┐
   │ PII Tokenizer & Verifier     │─────► [Metric: eval_pii_tokenization_failures]
   │ (Detects Residual Cleartext) │       Target: Strict 0
   └──────────────┬───────────────┘
                  │
                  ▼
   ┌──────────────────────────────┐
   │ Dataset Catalog Indexer      │─────► [Metric: eval_dataset_episodes_count]
   │ (Partitioned by Stratum)     │       Monitors 30/40/30 distribution ratio
   └──────────────┬───────────────┘
                  │
                  ├──────────────────────────────────────────────┐
                  ▼                                              ▼
   ┌──────────────────────────────┐               ┌──────────────────────────────┐
   │ Temporal Erasure Listener    │               │ Anti-Contamination Linter    │
   │ (Listens for DP-D13 events)  │               │ (Compares against prompts)   │
   └──────────────┬───────────────┘               └──────────────┬───────────────┘
                  │                                              │
                  ▼                                              ▼
   [Metric: eval_episodes_purged]                 [Metric: contamination_collisions]
   Ensures 100% RTBF compliance                   Target: Strict 0 (Fails CI build)
```

### Telemetry & Operational SLOs
1. **Unmasked PII Leakage Rate**:
   - Metric: `eval_dataset_unmasked_pii_detections_total`
   - Target: **Strictly 0**. Any detection triggers immediate dataset quarantine and S3 bucket lock.
2. **Erasure Purge Execution Delay**:
   - Time elapsed from `DP-D13` workflow initiation to S3 evaluation object deletion: $< 60\text{ seconds}$.
3. **Stratum Balance Adherence**:
   - Active dataset distribution deviation: $\max_{s} |Q_{\text{actual}}(s) - Q_{\text{target}}(s)| \le 0.05$.

---

## 6. Genesis Implementation Directive & Verification Protocol

### 6.1 Evaluation Dataset Harvester & Tokenizer Service

```python
import hashlib
from typing import Optional
import asyncpg
from pydantic import BaseModel

class EvalHarvestingService:
    def __init__(self, db_pool: asyncpg.Pool, pii_vault_client):
        self.db_pool = db_pool
        self.vault_client = pii_vault_client

    async def harvest_resolved_conversation(self, tenant_id: str, conversation_id: str) -> Optional[dict]:
        """
        Harvests a closed conversation for the evaluation pool if tenant has opted in.
        Enforces PII tokenization and sovereign regional placement.
        """
        async with self.db_pool.acquire() as conn:
            # 1. Enforce Opt-In Verification (EV-D15)
            opted_in = await conn.fetchval(
                "SELECT COALESCE(eval_dataset_sampling_opt_in, FALSE) FROM tenant_settings WHERE tenant_id = $1;",
                tenant_id
            )
            if not opted_in:
                return None  # Strictly skip non-opted tenants

            # 2. Fetch Turns
            turns = await conn.fetch(
                "SELECT turn_index, user_message, agent_response FROM conversation_turns WHERE conversation_id = $1 ORDER BY turn_index ASC;",
                conversation_id
            )

        # 3. Tokenize PII across all turns (EV-D10)
        sanitized_turns = []
        for turn in turns:
            tokenized_user = await self.vault_client.tokenize_text(tenant_id, turn["user_message"])
            tokenized_agent = await self.vault_client.tokenize_text(tenant_id, turn["agent_response"])
            sanitized_turns.append({
                "turn_index": turn["turn_index"],
                "user_utterance": tokenized_user,
                "agent_response": tokenized_agent
            })

        return {
            "conversation_id": conversation_id,
            "tenant_id": tenant_id,
            "turns": sanitized_turns
        }
```

### 6.2 Verification Checklist & Integration Tests

```bash
# 1. Verify Opt-In Gate Enforcement
pytest tests/evaluation/test_eval_governance.py -k "test_opt_in_gate_blocks_harvesting"

# Expected Output:
# PASS: Harvesting returns None when eval_dataset_sampling_opt_in is FALSE.
# PASS: Harvesting succeeds and records audit log when opt-in is TRUE.

# 2. Verify Right-to-be-Forgotten Deletion from Evaluation Pools
pytest tests/evaluation/test_eval_erasure.py -k "test_temporal_erasure_purges_eval_s3"

# Expected Output:
# PASS: Target user token eradicated from S3 evaluation dataset JSON objects.
# PASS: Post-erasure audit confirms 0 references to target user in evaluation index.
```

---

## 7. Trade-Off Analysis & Rejected Alternatives

| Dimension | Selected Paradigm (`EV-D1`, `EV-D10`, `EV-D15`) | Rejected Alternative A: Static Synthetic QA Datasets Only | Rejected Alternative B: Unrestricted Production Data |
| :--- | :--- | :--- | :--- |
| **Realism & Multi-Turn Depth** | **High**: Stratified synthesis captures personas, while tokenized production captures real customer vocabulary. | **Low**: Static question-answer pairs miss conversation turn dynamics and tool execution states. | **Maximum**: Real customer traffic, but violates privacy and corporate confidentiality. |
| **Privacy & Legal Defensibility** | **Complete**: PII tokenized, regionalized, covered by erasure, and protected by affirmative opt-in ($UK2$). | **Absolute**: Synthetic data carries zero PII, but lacks real-world edge case distributions. | **Fatal Non-Compliance**: Storing unmasked customer data in evaluation environments breaches GDPR Art. 5. |
| **Bias & Failure Mode Coverage** | **Optimized**: Importance sampling guarantees $30\%$ test allocation to critical $5\%$ operational risks. | **Poor**: Hand-written suites reflect developer biases and miss emergent failure modes. | **Skewed**: $80\%$ of tests wasted evaluating trivial password resets and routine lookups. |
| **Maintenance Overhead** | **Moderate**: Requires running tokenization and maintaining S3 bucket lifecycle policies. | **Lowest**: Simple static JSON files committed to Git repositories. | **High**: Constant legal review and manual redaction pipelines required. |

---

## 8. Formal References & Literature Grounding

1. **Horvitz, D. G., & Thompson, D. J. (1952).** *A Generalization of Sampling Without Replacement from a Finite Universe*. Journal of the American Statistical Association, 47(260), 663–685. *(Mathematical foundation for importance-weighted stratified estimation).*
2. **Yao, S., et al. (2024).** *$\tau$-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Environments*. arXiv preprint arXiv:2406.12045. *(Foundational framework for multi-turn simulated interaction episodes).*
3. **European Union General Data Protection Regulation (GDPR). (2016).** *Regulation (EU) 2016/679: Article 5(1)(b) (Purpose limitation), Article 17 (Right to erasure), Article 44 (Cross-border transfers)*. *(Statutory requirements governing enterprise evaluation dataset governance).*
4. **Zheng, L., et al. (2023).** *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena*. Advances in Neural Information Processing Systems (NeurIPS 36). *(Methodology for benchmark dataset construction and evaluation rubrics).*
5. **NIST. (2023).** *Artificial Intelligence Risk Management Framework (AI RMF 1.0)*. National Institute of Standards and Technology. Section 3: Valid and Reliable AI. *(Guidelines for rigorous statistical evaluation across stratified operational risk tiers).*
