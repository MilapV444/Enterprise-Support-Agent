# OB-ADP-05: Automated Failure Classification & Diagnostic Taxonomy (Deterministic Rule Engines, TypeSafe Jev Bulk Labelling & Continuous Learning Feedback)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-03 *(Confirmed per OB-D11 Two-Tier Failure Classification via Rules & Jev Choice Use #7)*
- **Deciders**: Architecture Team, Lead Machine Learning Scientist, Quality Assurance Director, Incident Commander
- **Component**: `[9] Observability & Monitoring` (`Component [ 9 ]`)
- **Reasoning Source**: `checkpoint.md` §13 · Diagram: `LLD - [9] Observability & Monitoring`
- **Decisions Covered**:
  - `OB-D11`: Two-Tier Scaled Failure Categorization — Two-phase classification architecture for failed and escalated conversational sessions: (1) Deterministic rule engine rapidly categorizes technical failures based on error codes, exception types, and decision records (`SG-D13`); (2) TypeSafe Jev `Choice` model (Use #7 bulk classification) classifies nuanced conversational failures over a standardized hierarchical failure taxonomy on PII-masked transcripts (`ADP-05-Q3`); unclassifiable low-confidence residuals routed to human QA queues; classification outputs feed Continuous Improvement (`CI-ADP-02`)
- **Related Architectural Decision Points**:
  - [`ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/00-orchestration-core/ADP-05-decision-model-jev.md): Decision Model (Jev) *(TypeSafe Jev Choice Schema & Prompt Governance)*
  - [`CI-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#ci-adp-02--failure-clustering--taxonomy): Failure Clustering & Taxonomy *(Failure Taxonomy Ownership & Clustering)*
  - [`SG-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/06-safety-security-governance/SG-ADP-02-pii-protection.md): PII Protection *(Masked Transcript Input Mandate)*
  - [`EV-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/08-evaluation-experimentation/EV-ADP-02-scoring-calibration.md): Output Scoring & Calibration *(Jev Calibration Measurement)*

---

## 1. Context & Problem Statement

In a high-scale enterprise customer support operation handling tens of thousands of conversations daily, a fraction ($3–8\%$) terminate in customer escalation, step-cap aborts, or explicit dissatisfaction. Manually reading thousands of failed transcripts to identify engineering root causes is physically impossible.

### The Categorization Bottlenecks
1. **The Cost of Naive LLM Categorization**:
   - Sending every single failed conversation transcript to a frontier foundation model (e.g., GPT-4o) with an open-ended classification prompt is expensive ($>\$0.03/\text{call}$) and prone to prompt hallucination, inventing ad-hoc category names that prevent structured clustering.
2. **The Blindness of Pure Error Codes**:
   - Technical error codes only capture infrastructure crashes (e.g., HTTP 504 Gateway Timeout or database connection dropped). They are completely blind to conversational and reasoning failures:
     - The agent retrieved stale documentation and confidently provided obsolete steps.
     - The coordinator specialist routed a billing inquiry to the technical specialist.
     - The agent engaged in repetitive circular questioning, prompting the user to angrily demand a human supervisor.
3. **The Data Privacy Boundary in Batch Analysis ($ADP-05-Q3$)**:
   - Batch offline classification pipelines frequently harvest raw transcripts. If the classifier is fed cleartext PII, batch analysis pipelines violate GDPR Article 5 purpose limitation mandates.

### The Core Architectural Question
> **How do we construct a scalable, cost-effective, two-tier failure classification pipeline that resolves 60% of technical failures via deterministic rules at zero cost, applies calibrated TypeSafe Jev models to classify conversational edge failures on masked text, and routes high-entropy residuals to human QA teams?**

---

## 2. Decision Framework & Theoretical Formulation

To solve these challenges, `OB-D11` establishes the **Two-Tier Deterministic Rules and Calibrated Jev Choice Classification Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│             TWO-TIER AUTOMATED FAILURE CLASSIFICATION PIPELINE (OB-D11)                          │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                       Failed / Escalated Turn or Concluded Case
                                          │
                                          ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ TIER 1: DETERMINISTIC RULE CLASSIFIER (Fast-Path — $0.00 Cost, Sub-Millisecond)                  │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Inspects: HTTP Codes, Exception Classes, Circuit Breaker States, Decision Records (SG-D13)       │
│                                                                                                  │
│   ┌───────────────────────────────────────────┬──────────────────────────────────────────────┐   │
│   │ SYSTEM TRIGGER CONDITION                  │ DETERMINISTIC CATEGORY ASSIGNED              │   │
│   ├───────────────────────────────────────────┼──────────────────────────────────────────────┤   │
│   │ Circuit Breaker State == OPEN             │ INFRASTRUCTURE_EXTERNAL_SYSTEM_DOWN          │   │
│   │ Cedar Authorization Decision == DENY      │ PERMISSION_AUTHORIZATION_DENIAL              │   │
│   │ Specialist Loop Steps == MAX_STEPS (6)    │ ORCHESTRATION_AGENT_LOOP_LIMIT               │   │
│   │ Turn Latency > 15.0s (Timeout)            │ INFRASTRUCTURE_TIMEOUT_ABORT                 │   │
│   │ Input Screening Status == BLOCK           │ SAFETY_ADVERSARIAL_INJECTION_BLOCKED         │   │
│   └───────────────────────────────────────────┴──────────────────────────────────────────────┘   │
└───────────────────────────────────────┬──────────────────────────────────────────────────────────┘
                                        │
                         Match Found?   ├──────────────────────────────┐ YES: Emit Verified Category
                                        │ NO (Conversational Failure)  ▼
                                        ▼                 ┌──────────────────────────────────────┐
┌───────────────────────────────────────────────────────┐ │ Persist to Continuous Improvement DB │
│ TIER 2: TYPESAFE JEV CHOICE CLASSIFIER (Use #7)       │ └──────────────────────────────────────┘
├───────────────────────────────────────────────────────┤
│ • Pre-Processing: Mask PII via Vault (ADP-05-Q3)      │
│ • Model: Quantized Jev Sequence Classifier            │
│ • Constrained Schema: Pydantic FailureCategory Enum   │
│ • Outputs: Category + Softmax Confidence Score        │
└───────────────────────────────────────┬──────────────────────────────────────────────────────────┘
                                        │
                                        ├──────────────────────────────────────────────┐
                                        ▼ (Confidence ≥ τ_class = 0.85)                ▼ (Confidence < 0.85)
┌───────────────────────────────────────────────────────┐ ┌──────────────────────────────────────────────┐
│ HIGH-CONFIDENCE CATEGORY ASSIGNED                     │ │ AMBIGUOUS RESIDUAL QUEUE                     │
│ Auto-tagged into Failure Taxonomy Catalog (CI-ADP-02) │ │ Routed to Human QA Reviewer Portal (HL-02)   │
└───────────────────────────────────────────────────────┘ └──────────────────────────────────────────────┘
```

---

### Pillar 1: Deterministic Fast-Path Rule Engine (`OB-D11`)

Approximately $55–65\%$ of failed customer support interactions stem from hard operational faults. These are resolved without invoking machine learning models:
1. **Rule Invariants**:
   - Rule 1 (`BREAKER_DOWN`): If external tool returns `CircuitBreakerOpenException` $\implies$ `INFRASTRUCTURE_EXTERNAL_SYSTEM_DOWN`.
   - Rule 2 (`AUTH_DENIED`): If Cedar policy evaluation returns `Decision::Deny` $\implies$ `PERMISSION_AUTHORIZATION_DENIAL`.
   - Rule 3 (`STEP_LIMIT`): If LangGraph graph terminates via step ceiling check (`MA-D8`) $\implies$ `ORCHESTRATION_AGENT_LOOP_LIMIT`.
   - Rule 4 (`TIMEOUT`): If client connection closes via gateway timeout $\implies$ `INFRASTRUCTURE_TIMEOUT_ABORT`.
   - Rule 5 (`SAFETY_BLOCKED`): If Llama Guard 3 returns `BLOCK` $\implies$ `SAFETY_ADVERSARIAL_INJECTION_BLOCKED`.
2. **Performance Guarantee**:
   Execution latency is $< 1\text{ms}$, consuming zero model tokens and offloading over half of all classification volume from AI inference infrastructure.

---

### Pillar 2: TypeSafe Jev Choice Classification (`OB-D11`, `ADP-05`)

Conversations that pass Tier 1 rules but end in human escalation, customer dissatisfaction, or unresolved dialogue are evaluated by TypeSafe Jev:
1. **Input PII Sanitization (`ADP-05-Q3`)**:
   - The dialogue turns are retrieved and processed through the regional Token Vault (`SG-D4`).
   - All customer names, card numbers, phone numbers, and addresses are replaced with surrogate UUID tokens before model ingress.
2. **Constrained Schema (`Choice` Question)**:
   - Jev evaluates the dialogue against a strictly typed Pydantic enum taxonomy:
     ```python
     class ConversationalFailureClass(str, Enum):
         INCORRECT_SPECIALIST_ROUTING = "incorrect_specialist_routing"
         RETRIEVAL_KNOWLEDGE_GAP = "retrieval_knowledge_gap"
         UNBACKED_PROMISE_ATTEMPT = "unbacked_promise_attempt"
         CUSTOMER_SENTIMENT_ESCALATION = "customer_sentiment_escalation"
         UNSUPPORTED_OUT_OF_SCOPE_REQUEST = "unsupported_out_of_scope_request"
         REPETITIVE_CIRCULAR_REASONING = "repetitive_circular_reasoning"
     ```
3. **Calibrated Confidence Thresholding (`EV-D9`)**:
   - Jev emits both the predicted class and an empirical confidence score $\hat{p} \in [0.0, 1.0]$.
   - If $\hat{p} \ge \tau_{\text{class}}$ ($\tau_{\text{class}} = 0.85$):
     The classification is committed automatically to the Failure Taxonomy Database.
   - If $\hat{p} < \tau_{\text{class}}$:
     The case is flagged as **High Entropy Residual** and enqueued for human QA spot-checking (`HL-ADP-02`), preventing automated clustering from being polluted by model guesses.

---

### Pillar 3: Continuous Improvement Learning Loop (`CI-ADP-02`)

The outputs of the failure classification pipeline directly drive system self-healing:
1. **Clustering & Trend Detection**:
   - Failure categories are aggregated hourly across tenants. If `RETRIEVAL_KNOWLEDGE_GAP` spikes for a specific product entity, the Knowledge module (`KR-D11`) flags the topic for immediate documentation authoring.
2. **Regression Test Synthesis**:
   - Cases categorized as `INCORRECT_SPECIALIST_ROUTING` or `REPETITIVE_CIRCULAR_REASONING` are automatically sanitized and exported to the Evaluation pool (`EV-D1`), generating new regression test seeds to prevent recurrence.

---

## 3. Data Contracts & Execution Invariants

### 3.1 Failure Classification Schema Contract

```python
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class RootCauseTier(str, Enum):
    TIER_1_DETERMINISTIC_RULE = "tier_1_deterministic_rule"
    TIER_2_JEV_CHOICE_MODEL = "tier_2_jev_choice_model"
    HUMAN_QA_OVERRIDE = "human_qa_override"

class FailureTaxonomyCategory(str, Enum):
    # Technical & Infrastructure (Tier 1)
    INFRASTRUCTURE_EXTERNAL_SYSTEM_DOWN = "infrastructure_external_system_down"
    PERMISSION_AUTHORIZATION_DENIAL = "permission_authorization_denial"
    ORCHESTRATION_AGENT_LOOP_LIMIT = "orchestration_agent_loop_limit"
    INFRASTRUCTURE_TIMEOUT_ABORT = "infrastructure_timeout_abort"
    SAFETY_ADVERSARIAL_INJECTION_BLOCKED = "safety_adversarial_injection_blocked"
    
    # Conversational & Reasoning (Tier 2 Jev)
    INCORRECT_SPECIALIST_ROUTING = "incorrect_specialist_routing"
    RETRIEVAL_KNOWLEDGE_GAP = "retrieval_knowledge_gap"
    UNBACKED_PROMISE_ATTEMPT = "unbacked_promise_attempt"
    CUSTOMER_SENTIMENT_ESCALATION = "customer_sentiment_escalation"
    UNSUPPORTED_OUT_OF_SCOPE_REQUEST = "unsupported_out_of_scope_request"
    REPETITIVE_CIRCULAR_REASONING = "repetitive_circular_reasoning"
    
    # Residual
    AMBIGUOUS_UNCLASSIFIED = "ambiguous_unclassified"

class ConversationFailureClassification(BaseModel):
    """
    Contract representing the diagnostic classification of a failed conversation (OB-D11).
    """
    conversation_id: str = Field(..., regex=r"^conv_[a-zA-Z0-9]{16}$")
    tenant_id: str = Field(..., regex=r"^ten_[a-zA-Z0-9]{16}$")
    classification_tier: RootCauseTier
    primary_category: FailureTaxonomyCategory
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    rule_identifier: Optional[str] = Field(None, description="Rule name if Tier 1")
    jev_reasoning_summary: Optional[str] = Field(None, description="Jev reasoning if Tier 2")
    requires_human_qa_review: bool = Field(default=False)
    created_at_utc: datetime = Field(default_factory=datetime.utcnow)
```

### 3.2 Classification Invariants

1. **PII Masking Invariant (`ADP-05-Q3`)**:
   $$\forall \text{ Input } X \to \text{JevClassifier}, \quad \text{DetectCleartextPII}(X) \equiv \emptyset$$
   No unmasked customer names, credit card numbers, or physical addresses may be fed into the offline batch classification model.
2. **Confidence Routing Invariant**:
   $$\text{ClassifierConfidence}(C) < 0.85 \implies \text{SetFlag}(C.\text{requires\_human\_qa\_review}, \text{TRUE})$$

---

## 4. Quantitative Failure Modes & Operational Risk Bounds

| Failure Mode ID | Sub-Component & Severity | Risk Classification | Empirical Trigger Condition | Detection Vector | Automated Mitigation & Architectural Enforcement |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **OB-FM-501** | Rule Misclassification (`OB-D11`)<br>**HIGH** | Q1 Known Known (Rule Conflict) | Two conflicting Tier 1 rules match simultaneously (e.g., both Breaker Open and Timeout present). | Rule engine emits non-deterministic category ordering. | **Strict Rule Priority Hierarchy**: Rules execute in rigid priority order: Safety > Breaker > Auth > Timeout > Step Cap. |
| **OB-FM-502** | Jev Classification Drift (`OB-D11`)<br>**HIGH** | Q2 Known Unknown (Model Drift) | Model updates cause Jev to dump $40\%$ of ambiguous cases into `UNSUPPORTED_OUT_OF_SCOPE_REQUEST` ($KU3$). | Category distribution monitor detects entropy collapse across taxonomy buckets. | **Entropy Floor Alert (`CI-ADP-02`)**: SRE alert fires if any single conversational category exceeds $60\%$ of classified volume. |
| **OB-FM-503** | Batch Token Bloat (`OB-D11`)<br>**MEDIUM** | Q2 Known Unknown (Cost Spike) | Sudden spike in failed conversations triggers thousands of parallel Jev classification requests, bloating costs. | Batch classification worker queue depth exceeds 5,000 items. | **Batch Throttling & Priority Queue**: Classification workers run as low-priority background workers capped at max 10 concurrent requests. |
| **OB-FM-504** | PII Leak to Classifier (`OB-D11`)<br>**CRITICAL** | Q3 Unknown Known (Tacit Convention) | Masking pre-processor fails on an obscure international phone format, passing cleartext to the classifier ($ADP-05-Q3$). | In-line regex assertion pre-flight check catches unmasked digit pattern. | **Pre-Classification Sanitization Linter**: Worker asserts zero phone/email regex matches; aborts classification and triggers security alert on match. |
| **OB-FM-505** | Unchecked Human Queue (`OB-D11`)<br>**LOW** | Q4 Unknown Unknown (Backlog Starvation) | Ambiguous cases enqueued for human QA sit uninspected for months, starving Continuous Improvement of labels. | QA portal queue backlog monitor exceeds 1,000 unreviewed items. | **Automated FIFO Eviction**: QA queue enforces 14-day FIFO eviction; older unreviewed items archived to cold storage. |

---

## 5. Closed-Loop Architectural Feedback

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   FAILURE CLASSIFICATION & CONTINUOUS LEARNING ENGINE                            │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Failed Conversation Stream
               │
               ▼
   ┌───────────────────────────────┐
   │ Tier 1: Deterministic Rules   │─────► [Metric: failure_tier1_rule_matches_total]
   │ (Resolved in < 1ms)           │       Target: ~60% of total failures resolved here
   └──────────────┬────────────────┘
               │
               ├──────────────────────────────────────────────┐
               ▼ (Unresolved Residuals)                       ▼ (Matches Rule)
   ┌───────────────────────────────┐              ┌───────────────────────────────┐
   │ Tier 2: TypeSafe Jev Choice   │              │ Emit Rule Category to Catalog │
   │ (Runs on PII-Masked Dialogue) │              └───────────────────────────────┘
   └──────────────┬────────────────┘
               │
               ├──────────────────────────────────────────────┐
               ▼ (Confidence ≥ 0.85)                          ▼ (Confidence < 0.85)
   ┌───────────────────────────────┐              ┌───────────────────────────────┐
   │ Emit High-Confidence Category │              │ Route to Human QA Queue       │
   │ [Metric: failure_jev_high_conf]              │ [Metric: failure_qa_fallback] │
   └──────────────┬────────────────┘              └──────────────┬────────────────┘
                  │                                              │
                  └───────────────────────┬──────────────────────┘
                                          ▼
                      ┌───────────────────────────────────────┐
                      │ Continuous Improvement Clustering     │
                      │ Generates regression tests for EV-01  │
                      └───────────────────────────────────────┘
```

### Telemetry & Operational SLOs
1. **Tier 1 Rule Resolution Ratio**:
   - Metric: `failure_classification_tier1_ratio`
   - Target: $\ge 0.50$ (At least $50\%$ resolved via zero-cost rules).
2. **Jev Classification Accuracy**:
   - Metric: `failure_classification_accuracy` (measured against human QA labels in `EV-D9`).
   - Target: $\ge 0.90$.
3. **Classification Processing Delay**:
   - Time from conversation closure to failure classification emission: $< 5\text{ minutes}$.

---

## 6. Genesis Implementation Directive & Verification Protocol

### 6.1 Two-Tier Failure Classifier Implementation

```python
from typing import Optional
from pydantic import BaseModel

class FailureClassificationService:
    def __init__(self, jev_client, pii_masker):
        self.jev_client = jev_client
        self.masker = pii_masker

    async def classify_failure(self, session_context: dict) -> ConversationFailureClassification:
        """
        Executes two-tier failure classification (OB-D11).
        """
        conv_id = session_context["conversation_id"]
        tenant_id = session_context["tenant_id"]

        # TIER 1: DETERMINISTIC RULES (Fast Path)
        if session_context.get("circuit_breaker_open"):
            return ConversationFailureClassification(
                conversation_id=conv_id,
                tenant_id=tenant_id,
                classification_tier=RootCauseTier.TIER_1_DETERMINISTIC_RULE,
                primary_category=FailureTaxonomyCategory.INFRASTRUCTURE_EXTERNAL_SYSTEM_DOWN,
                confidence_score=1.0,
                rule_identifier="RULE_BREAKER_OPEN"
            )

        if session_context.get("cedar_auth_denied"):
            return ConversationFailureClassification(
                conversation_id=conv_id,
                tenant_id=tenant_id,
                classification_tier=RootCauseTier.TIER_1_DETERMINISTIC_RULE,
                primary_category=FailureTaxonomyCategory.PERMISSION_AUTHORIZATION_DENIAL,
                confidence_score=1.0,
                rule_identifier="RULE_CEDAR_DENY"
            )

        if session_context.get("step_cap_exceeded"):
            return ConversationFailureClassification(
                conversation_id=conv_id,
                tenant_id=tenant_id,
                classification_tier=RootCauseTier.TIER_1_DETERMINISTIC_RULE,
                primary_category=FailureTaxonomyCategory.ORCHESTRATION_AGENT_LOOP_LIMIT,
                confidence_score=1.0,
                rule_identifier="RULE_STEP_CAP_EXCEEDED"
            )

        # TIER 2: TYPESAFE JEV CHOICE (Conversational Residuals)
        # 1. Mask PII before passing to Jev (ADP-05-Q3)
        masked_transcript = await self.masker.mask_text(session_context["transcript_text"])

        # 2. Invoke Jev Choice classifier
        jev_result = await self.jev_client.evaluate_choice(
            question="Analyze this customer support dialogue and select the primary root cause of failure.",
            context=masked_transcript,
            options=FailureTaxonomyCategory
        )

        requires_human = jev_result.confidence < 0.85

        return ConversationFailureClassification(
            conversation_id=conv_id,
            tenant_id=tenant_id,
            classification_tier=RootCauseTier.TIER_2_JEV_CHOICE_MODEL,
            primary_category=jev_result.chosen_option,
            confidence_score=jev_result.confidence,
            jev_reasoning_summary=jev_result.reasoning,
            requires_human_qa_review=requires_human
        )
```

### 6.2 Verification Checklist & Integration Tests

```bash
# 1. Verify Tier 1 Fast-Path Rule Prioritization
pytest tests/observability/test_failure_classification.py -k "test_tier1_rules_override_model"

# Expected Output:
# PASS: Session with circuit_breaker_open=True immediately returns INFRASTRUCTURE_EXTERNAL_SYSTEM_DOWN.
# PASS: Jev model client invocation count = 0 (Zero token expenditure).

# 2. Verify PII Masking Enforcement on Tier 2 Jev Input
pytest tests/observability/test_failure_classification.py -k "test_transcript_masked_before_jev"

# Expected Output:
# PASS: Jev client mock asserts zero raw email/credit card patterns in payload context.
# PASS: Low-confidence outputs (confidence < 0.85) correctly set requires_human_qa_review = True.
```

---

## 7. Trade-Off Analysis & Rejected Alternatives

| Dimension | Selected Paradigm (`OB-D11`) | Rejected Alternative A: Manual Human Review for All Failures | Rejected Alternative B: Unconstrained Generative LLM Triage |
| :--- | :--- | :--- | :--- |
| **Operational Scalability & Cost** | **High**: Zero cost on $60\%$ rule matches; cheap quantized Jev on remainder; humans review only ambiguous $< 10\%$. | **Unscalable**: Requires full-time QA teams reading tens of thousands of transcripts; MTTR is weeks. | **Expensive**: Costs $\$0.03$ per failure on frontier LLM models; incurs thousands in monthly token bills. |
| **Classification Consistency** | **Deterministic & Typed**: Strict Pydantic enum taxonomy guarantees stable time-series clustering. | **Inconsistent**: Different human raters classify identical failures into subjective, conflicting buckets. | **Chaotic**: Unconstrained LLMs invent hundreds of synonyms ("routing bug", "dispatch flaw", "misdirection"). |
| **Privacy & Regulatory Safety** | **Strict**: PII masked via Token Vault before Jev evaluation (`ADP-05-Q3`). | **High Risk**: Human reviewers exposed to raw unmasked customer PII. | **High Risk**: External LLM APIs ingest unmasked conversational customer histories. |
| **Engineering Integration** | **Direct**: Emits structured event payloads consumed directly by Continuous Improvement (`CI-ADP-02`). | **Disconnected**: Requires manual spreadsheet exports and engineering ticket creation. | **Disconnected**: Output requires secondary parsing pipelines to extract clean tags. |

---

## 8. Formal References & Literature Grounding

1. **Stanovich, K. E., & West, R. F. (2000).** *Individual Differences in Reasoning: Implications for the Rationality Debate?* Behavioral and Brain Sciences, 23(5), 645–665. *(Theoretical inspiration for two-tier architecture: fast deterministic heuristic system backed by slower reflective reasoning).*
2. **European Union General Data Protection Regulation (GDPR). (2016).** *Regulation (EU) 2016/679: Article 5(1)(c) (Data minimisation) & Article 25 (Data protection by design)*. *(Statutory mandate for PII tokenization prior to batch analytical processing).*
3. **Yao, S., et al. (2023).** *Tree of Thoughts: Deliberate Problem Solving with Large Language Models*. NeurIPS 2023. *(Methodology for structured, schema-constrained taxonomic evaluation).*
4. **NIST. (2023).** *Artificial Intelligence Risk Management Framework (AI RMF 1.0)*. NIST. Section 3.8: Continuous Monitoring and Anomaly Detection. *(Standards for categorizing, logging, and clustering systemic AI failure modes).*
5. **Kleppmann, M. (2017).** *Designing Data-Intensive Applications*. O'Reilly Media. *(Principles of multi-tier stream classification and dead-letter queue routing).*
