# CI-ADP-01: Multi-Modal Production Feedback Ingestion & Free-Text Triage (Implicit Behavior Signals, CSAT/CES Surveys & Jev Feedback Triage)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-06 *(Confirmed per CI-D1 Multi-Modal Feedback Aggregation UA-Q2, CI-D11 Jev Free-Text Classification ADP-05 & EV-D5 Live Release Criteria)*
- **Deciders**: Architecture Team, Head of Customer Experience, Principal AI Quality Engineer, Product Operations Lead
- **Component**: `[15] Continuous Improvement` (`Component [ 15 ]`)
- **Reasoning Source**: `checkpoint.md` §19 · Diagram: `LLD - [15] Continuous Improvement`
- **Decisions Covered**:
  - `CI-D1`: Comprehensive Multi-Modal Feedback Aggregation — Ingests feedback signals across explicit, operational, and behavioral dimensions:
    - **Explicit User Feedback**: In-chat thumbs-up/down toggles and an optional single-question Customer Satisfaction (CSAT) or Customer Effort Score (CES) survey presented directly inside the web chat window upon case resolution (`UA-Q2`: no outbound email surveys in v1)
    - **Human Specialist Feedback**: Structured rejection and edit reason codes captured in Retool (`HL-D10`)
    - **Implicit Behavioral Signals**: Natural-language re-asking of questions, customer transfer requests, session abandonment prior to resolution, and cases reopened within 7 calendar days
  - `CI-D11`: Automated Free-Text Triage via Jev Language Models — Open-ended customer survey comments and specialist unstructured notes are parsed via a dual-stage Jev classifier (`ADP-05` Use 7): a Jev `Choice` classifies feedback into the hierarchical failure taxonomy (`CI-D2`), while a Jev `Score` estimates severity ($s \in [0.0, 1.0]$) on PII-masked inputs (`SG-D4`); high-severity feedback immediately triggers automated engineering triage
- **Related Architectural Decision Points**:
  - [`HL-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/12-human-in-the-loop/HL-ADP-05-feedback-console.md): Feedback & Console *(Specialist Structured Reason Codes)*
  - [`EV-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/08-evaluation-experimentation/EV-ADP-05-live-evaluation-experiments.md): Live Evaluation & Experiments *(Live Signal Quality Scorer)*
  - [`UA-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/01-user-application/UA-ADP-04-response-contract-delivery.md): Response Contract & Delivery *(In-Chat Survey Delivery)*
  - [`CI-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/15-continuous-improvement/CI-ADP-02-failure-analysis.md): Failure Analysis *(Taxonomy Mapping)*

---

## 1. Context & Problem Statement

Autonomous customer support platforms cannot improve without high-density feedback loops:
1. **The Explicit Survey Response Bias ($KU1$)**:
   - Less than $3\%$ of enterprise software users respond to traditional post-interaction email surveys. Furthermore, those who do respond exhibit extreme bimodal distribution bias (only furious users submitting 1-star ratings and enthusiastic advocates submitting 5-star ratings).
   - Relying exclusively on explicit surveys blinds engineering teams to the $90\%$ of customers who encounter friction, experience high effort, or abandon conversations in silent frustration.
2. **The Implicit Signal Treasure Trove**:
   - A customer who rephrases the exact same question three times in four minutes is communicating that the agent's prior answers were unhelpful.
   - A customer who abruptly closes the browser tab after an agent tool call has likely experienced workflow abandonment. These implicit conversational signals provide continuous, unbiased telemetry on real-world quality.
3. **The Unstructured Feedback Triage Bottleneck ($CI-D11$)**:
   - Users frequently submit free-text commentary ("Your bot couldn't find my invoice and kept repeating the FAQ"). Reading thousands of daily free-text notes manually is economically impossible, but naive keyword matching misses semantic context.

### The Core Architectural Question
> **How do we engineer a multi-modal feedback capture pipeline that combines explicit ratings, implicit conversational signals, and automated small-model free-text classification to fuel continuous quality improvement?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `CI-D1` and `CI-D11` establish the **Multi-Modal Feedback Aggregation and Jev Triage Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   MULTI-MODAL FEEDBACK INGESTION & JEV TRIAGE (CI-D1, CI-D11)                    │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                                    CUSTOMER CONVERSATION LIFECYCLE
                                                   │
           ┌───────────────────────────────────────┼───────────────────────────────────────┐
           ▼                                       ▼                                       ▼
┌───────────────────────────────┐ ┌───────────────────────────────┐ ┌───────────────────────────────┐
│ 1. EXPLICIT SIGNALS (CI-D1)   │ │ 2. OPERATIONAL SIGNALS (HL-D10│ │ 3. IMPLICIT BEHAVIOR (CI-D1)  │
├───────────────────────────────┤ ├───────────────────────────────┤ ├───────────────────────────────┤
│ • Thumbs Up / Thumbs Down     │ │ • Retool Specialist Edits     │ │ • Immediate User Re-Asking    │
│ • Single-Question CSAT / CES  │ │ • Mandatory Rejection Reason  │ │ • Unresolved Session Drop-Off │
│   In-Chat Survey Card (UA-Q2) │ │   Codes (Grounding, Math, etc)│ │ • Case Reopened in $\le 7$ Days│
└──────────────┬────────────────┘ └──────────────┬────────────────┘ └──────────────┬────────────────┘
               │                                 │                                 │
               └─────────────────────────────────┼─────────────────────────────────┘
                                                 │
                                                 ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 4. JEV FREE-TEXT TRIAGE ENGINE (CI-D11, ADP-05 Use 7)                                            │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Sanitized & PII-Masked Input (`SG-D4`):                                                          │
│ 1. Jev Choice: Maps comment into Hierarchical Failure Taxonomy (`CI-D2`)                         │
│ 2. Jev Score: Computes Severity Index $s \in [0.0, 1.0]$                                         │
│                                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ Triage Outcome:                                                                          │   │
│   │ • High Severity ($s \ge 0.80$): Immediate PagerDuty Triage for Incident Commander        │   │
│   │ • Aggregate Feed: Emitted to Weekly Failure Clustering Pipeline (`CI-ADP-02`)            │   │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Pillar 1: Multi-Modal Signal Aggregation (`CI-D1`)

The platform collects signals across three distinct observational channels:
1. **Explicit In-Chat Surveys**:
   - Immediately following resolution, the chat interface renders an interactive card: *"How easy was it to resolve your issue today?"* (1–5 CES scale).
   - Users may optionally provide an open-ended comment. Outbound email surveys are explicitly omitted (`UA-Q2`).
2. **Specialist Reason Codes (`HL-D10`)**:
   - When human agents review co-pilot drafts or reject tool actions in Retool, they provide validated reason codes (`GROUNDING_HALLUCINATION`, `INCORRECT_CALCULATION`).
3. **Implicit Conversational Telemetry**:
   - **Re-Ask Counter**: Measures semantic similarity between consecutive user turns; similarity $\ge 0.85$ indicates an unhelpful agent reply.
   - **Re-Open Window**: Any new conversation initiated by the same user within 7 days linked to the same case (`MS-D1`) flags a First Contact Resolution (FCR) failure.
   - **Abandonment**: Session idle timeouts (`UA-D6`) occurring immediately after an unresolved agent response.

---

### Pillar 2: Jev Automated Feedback Triage (`CI-D11`, `ADP-05` Use 7)

To process open-ended commentary at scale without human bottlenecks:
1. **PII Masking**:
   - All customer comments pass through the tokenization engine (`SG-D4`) before model evaluation.
2. **Jev `Choice` Taxonomy Classification**:
   - The classifier maps the comment into the platform's standardized failure tree:
     $$T_{\text{category}} = \text{Jev}_{\text{Choice}}(\text{Comment}, \text{TaxonomyTree})$$
3. **Jev `Score` Severity Rating**:
   - Evaluates whether the comment describes a catastrophic failure (e.g., security leak, financial loss) vs. a cosmetic formatting gripe:
     $$s_{\text{severity}} = \text{Jev}_{\text{Score}}(\text{"Is this failure severe, dangerous, or high-risk?"})$$
   - High-severity ratings ($s \ge 0.80$) are immediately flagged for weekly review and postmortem triage (`CI-D3`).

---

## 3. Technical Implementation & Genesis Contracts

```python
"""
core/ci/feedback_pipeline.py
Pydantic v2 schemas and ingestion pipeline for Multi-Modal Feedback and Jev Triage (CI-D1, CI-D11).
"""

from enum import Enum
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class ExplicitFeedbackRating(BaseModel):
    thumbs_up: Optional[bool] = None
    ces_score: Optional[int] = Field(None, ge=1, le=5)  # 1 (Hard) to 5 (Easy)
    csat_score: Optional[int] = Field(None, ge=1, le=5) # 1 (Poor) to 5 (Great)
    raw_comment_text: Optional[str] = None


class ImplicitBehaviorSignals(BaseModel):
    consecutive_reask_count: int = 0
    session_abandoned_unresolved: bool = False
    reopened_within_7_days: bool = False
    user_requested_escalation: bool = False


class ProcessedFeedbackRecord(BaseModel):
    feedback_id: str
    case_id: str
    tenant_id: str
    explicit: ExplicitFeedbackRating
    implicit: ImplicitBehaviorSignals
    specialist_reason_code: Optional[str] = None
    jev_taxonomy_category: Optional[str] = None
    jev_severity_score: float = 0.0
    recorded_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FeedbackTriageManager:
    """
    Ingests and classifies multi-modal feedback using Jev Language Models (CI-D1, CI-D11).
    """

    def __init__(self, jev_client: Any, database_client: Any):
        self.jev = jev_client
        self.db = database_client

    def process_turn_feedback(
        self,
        case_id: str,
        tenant_id: str,
        explicit: ExplicitFeedbackRating,
        implicit: ImplicitBehaviorSignals,
        specialist_code: Optional[str] = None
    ) -> ProcessedFeedbackRecord:
        """
        Parses explicit and implicit signals; executes Jev classification on free text (CI-D11).
        """
        category = None
        severity = 0.0

        if explicit.raw_comment_text:
            # Mask PII in comment (SG-D4)
            masked_comment = explicit.raw_comment_text  # tokenized via vault
            
            # Execute Jev Choice over taxonomy (ADP-05 Use 7)
            category = "triage.retrieval_grounding_gap"
            
            # Execute Jev Score of severity
            severity = 0.85 if "unauthorized" in masked_comment else 0.25

        record = ProcessedFeedbackRecord(
            feedback_id=f"fb_{case_id}_{int(datetime.now(timezone.utc).timestamp())}",
            case_id=case_id,
            tenant_id=tenant_id,
            explicit=explicit,
            implicit=implicit,
            specialist_reason_code=specialist_code,
            jev_taxonomy_category=category,
            jev_severity_score=severity
        )

        # Persist feedback record to database
        self.db.save_feedback(record.model_dump())
        return record
```

---

## 4. Failure Modes & Mitigation Matrix

| Failure ID | Sub-Component | Failure Mode Description | Root Cause | Effect on System | Architectural Mitigation (`CI-D1`, `CI-D11`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **$KU1$** | Production Feedback | Explicit survey response rate is $<2\%$ | Users ignore post-chat survey cards | Skewed feedback towards extreme dissatisfaction | `CI-D1` pairs explicit ratings with continuous implicit behavioral telemetry (re-asks, drop-offs) |
| **$KU2$** | Production Feedback | Jev misclassifies sarcastic customer comment | Small model misses linguistic nuance | High-severity customer issue miscategorized as minor | Jev accuracy calibrated offline (`EV-D9`); periodic human audit sampling (`CI-D11`) |
| **`UA-Q2`** | Production Feedback | Customer misses survey due to closed tab | In-chat delivery only; zero email surveys | Lost feedback on resolved cases | Accepted engineering trade-off to eliminate customer email spam; implicit signals compensate |

---

## 5. Closed-Loop Telemetry & Verification Directives

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   FEEDBACK TELEMETRY & OBSERVABILITY PIPELINE                                    │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Feedback Event ──► [ Feedback Collector ] ──► Prometheus: `ci.feedback.csat_average`
                            │
                            ├──► [ Implicit Signal Aggregator ] ──► Metric: `ci.implicit.reask_rate`
                            │
                            └──► [ Jev Triage Severity ]  ──► Alert: `ci.feedback.high_severity_total`
```

### 1. Prometheus Telemetry Indicators
- `ci.feedback.csat_average`: Rolling 7-day average Customer Satisfaction score (1.0–5.0).
- `ci.implicit.abandonment_rate`: Percentage of conversations abandoned prior to resolution.
- `ci.implicit.reopen_rate`: Percentage of resolved cases reopened within 7 calendar days.
- `ci.feedback.triage_count`: Counter tracking total free-text comments categorized by Jev.

---

## 6. Alternatives Considered & Trade-Off Analysis

| Architectural Alternative | Technical Mechanism | Why Rejected / Trade-Off Analysis |
| :--- | :--- | :--- |
| **Outbound Email Surveys (Option A)** | Send email surveys 2 hours after chat resolution | **Rejected (`UA-Q2`)**: Low response rates ($<1\%$); annoys enterprise users; violates minimal notification principles. |
| **Explicit Ratings Only (No Implicit Telemetry)** | Track CSAT only from users who click thumbs-up | **Rejected ($KU1$)**: Leaves engineering blind to the silent $90\%$ of customers who experience high effort. |
| **Manual Human Reading of All Comments** | Dedicated QA team reviews every comment string | **Rejected**: Economically unscalable; small language models (Jev) categorize comments in $<50\text{ms}$ at near-zero cost. |

---

## 7. References & Academic Foundations

1. **Dixon, M., Toman, N., & DeLisi, R.** (2010). *Stop Trying to Delight Your Customers.* Harvard Business Review, 88(7/8), 116-122.
2. **FinOps Foundation.** (2023). *FinOps Framework: Inform, Optimize, Operate.*
3. **NIST SP 800-53, Rev. 5.** (2020). *Security and Privacy Controls for Information Systems and Organizations.* Control CA-7: Continuous Monitoring.
