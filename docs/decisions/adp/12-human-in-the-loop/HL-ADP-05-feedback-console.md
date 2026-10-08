# HL-ADP-05: Specialist Feedback Capture & Regional Low-Code Console (Structured Reason Codes & Multi-Region Self-Hosted Retool)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-05 *(Confirmed per HL-D10 Structured Rejection Reason Codes, HL-D11 Self-Hosted Regional Retool Deployments HL-Q5, DP-D10 Regional Data Residency & CI-D1 Continuous Improvement Feeds)*
- **Deciders**: Architecture Team, Support Tooling Lead, Security Compliance Officer, Infrastructure Architect
- **Component**: `[12] Human-in-the-Loop` (`Component [ 12 ]`)
- **Reasoning Source**: `checkpoint.md` §16 · Diagram: `LLD - [12] Human-in-the-Loop`
- **Decisions Covered**:
  - `HL-D10`: Structured Specialist Feedback Capture — Specialists reviewing co-pilot drafts or approving high-risk actions must submit explicit structured feedback on every interaction; rejections and draft modifications strictly require selecting validated failure reason codes (e.g., `WRONG_RETRIEVAL_GROUNDING`, `INCORRECT_CALCULATION`, `POLICY_EXCLUSION_MISSED`, `UNAUTHORIZED_USER`); raw free-text feedback is categorized via Jev to feed continuous evaluation (`EV-D8`) and failure clustering (`CI-D2`)
  - `HL-D11`: Regional Self-Hosted Retool Console Infrastructure — Resolves cross-border data leakage and compliance restrictions (`HL-Q5(i)`, `DP-D10`); human specialist workspaces are instantiated via self-hosted Retool containers deployed locally within each sovereign geographic cloud region (US and EU Kubernetes clusters); consoles connect exclusively to regional PostgreSQL and Temporal backend clusters, guaranteeing that customer PII and internal enterprise data never leave the tenant's legal jurisdiction
- **Related Architectural Decision Points**:
  - [`CI-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/15-continuous-improvement/CI-ADP-01-feedback-signals.md): Feedback Signals *(Multi-Modal Signal Aggregation)*
  - [`DP-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/07-data-persistence/DP-ADP-01-store-topology-residency.md): Store Topology & Residency *(Regional US/EU Deployments)*
  - [`EV-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/08-evaluation-experimentation/EV-ADP-05-live-evaluation-experiments.md): Live Evaluation & Experiments *(Sampled Human Correction Audits)*
  - [`CI-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/15-continuous-improvement/CI-ADP-02-failure-analysis.md): Failure Analysis *(Reason Code Taxonomy)*
  - [`DL-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/14-deployment-llmops/DL-ADP-01-environments-infrastructure.md): Environments & Infrastructure *(Regional K8s Orchestration)*

---

## 1. Context & Problem Statement

Specialist interfaces and feedback ingestion mechanisms frequently fail to balance operational speed with compliance rigor:
1. **The Data Sovereignty Violation (The SaaS Console Trap, `HL-Q5`, `DP-D10`)**:
   - Commercial SaaS helpdesk consoles (such as Retool Cloud, Zendesk, or Salesforce Service Cloud) route web traffic and operational data through central multi-tenant cloud planes (typically hosted in the US).
   - Ingesting European customer support transcripts, unmasked identities, and financial refund approvals through a US-hosted SaaS portal directly violates GDPR Chapter V (cross-border data transfers) and invalidates tenant data residency covenants (`DP-D10`).
2. **The Ambiguous Feedback Void ($HL-D10$)**:
   - In traditional support workflows, human agents either click "Reject" without comment or write unstructured free-text rants ("This is dumb", "Wrong").
   - Machine learning engineering teams cannot systematically train, calibrate (`EV-D9`), or cluster failures (`CI-D2`) from unstandardized text without expensive manual data annotation.
3. **The Low-Code Concurrency Bottleneck ($KU3$)**:
   - Rapidly building custom agent consoles in-house consumes 6 months of frontend engineering capacity. Conversely, deploying naive low-code tools can introduce severe performance degradation when 500 concurrent specialists query high-throughput operational queues simultaneously.

### The Core Architectural Question
> **How do we engineer an ergonomic, low-code specialist console that strictly respects regional data sovereignty, scales to hundreds of concurrent agents, and systematically captures high-signal structured feedback on every decision?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `HL-D10` and `HL-D11` establish the **Self-Hosted Regional Retool Console and Structured Feedback Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   REGIONAL CONSOLE & STRUCTURED FEEDBACK PIPELINE (HL-D10, HL-D11)               │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                               Specialist Browser (EU Support Center)
                                                  │
                                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ REGIONAL SOVEREIGN CONSOLE INSTANCE (EU REGION, HL-D11, HL-Q5(i), DP-D10)                        │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Self-Hosted Retool on Regional Kubernetes Cluster (`k8s-eu-central-1`)                          │
│ • Local SSO Authentication via Okta/SAML (Tier 3 Identity UA-D3)                                 │
│ • Zero Cross-Region Network Hops: Directly queries EU Postgres, Redis, and Temporal Clusters    │
└─────────────────────────────────────────────────┬────────────────────────────────────────────────┘
                                                  │
                                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ SPECIALIST ACTION & FEEDBACK CAPTURE (HL-D10)                                                    │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Specialist Reviews Draft / Proposed Action -> Submits Decision:                                 │
│                                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ 1. Decision: [ APPROVE ] or [ REJECT / EDIT ]                                            │   │
│   │ 2. Mandatory Structured Reason Code Dropdown:                                            │   │
│   │    • WRONG_RETRIEVAL_GROUNDING: Retrieved documentation does not support claim           │   │
│   │    • INCORRECT_CALCULATION: Math / refund amount mismatch                                │   │
│   │    • POLICY_EXCLUSION_MISSED: User does not meet terms of service                        │   │
│   │    • UNVERIFIED_IDENTITY: Insufficient authorization tier                                │   │
│   │ 3. Optional Free-Text Commentary (Categorized asynchronously via Jev Choice)            │   │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┬────────────────────────────────────────────────┘
                                                  │
                                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ CLOSED-LOOP LEARNING & EVALUATION DISPATCH (CI-D1, EV-D8)                                        │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ • Emits Durable Feedback Record: `hitl.feedback.captured`                                        │
│ • Ingested by Continuous Improvement Pipeline (`CI-ADP-01`) for Weekly Failure Clustering        │
│ • Evaluated by Release Gate Calibration (`EV-D9`) to measure human-agreement ECE metrics        │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Pillar 1: Regional Self-Hosted Retool Deployment (`HL-D11`, `DP-D10`)

To satisfy GDPR Article 44 and tenant data residency covenants:
1. **Isolated Infrastructure Topology**:
   - The Retool runtime is packaged as containerized Docker/Helm deployments running directly inside our regional Kubernetes clusters:
     - `retool-us-east-1`: Serves North American enterprise tenants.
     - `retool-eu-central-1`: Serves European enterprise tenants.
2. **Local Data Plane Invariance**:
   - Regional Retool instances bind strictly to VPC-internal database read replicas and Temporal frontend gRPC endpoints in the same cloud region.
   - Retool Cloud telemetry, usage pings, and external SaaS connections are completely disabled via firewall egress rules (`DL-ADP-01`).

---

### Pillar 2: Structured Feedback Taxonomy (`HL-D10`, `CI-D2`)

To convert operational rejections into actionable engineering assets:
1. **Validated Failure Reason Taxonomy**:
   - Rejections or draft modifications cannot be submitted without an explicit enum selection:
     - `GROUNDING_HALLUCINATION`: Claims fact not present in retrieved context.
     - `RETRIEVAL_IRRELEVANCE`: Knowledge search returned wrong topic documentation.
     - `NUMERIC_MISCALCULATION`: Inaccurate financial, fee, or SLA math.
     - `TONE_OR_POLICY_VIOLATION`: Response was hostile, dismissive, or breached policy.
     - `TOOL_ARGUMENT_ERROR`: Proposed mutating action contained malformed parameters.
2. **No Eval Contamination Rule (`CI-D5`)**:
   - In accordance with `CI-ADP-03`, human-edited drafts are captured as diagnostic data but are **strictly excluded** from automatic few-shot prompt injection to prevent evaluation benchmark contamination.

---

### Pillar 3: Concurrency & Performance Sizing ($KU3$)

To ensure self-hosted low-code infrastructure scales under peak incident loads:
1. **Connection Pooling & Read-Only Replicas**:
   - Retool backend containers connect to PostgreSQL through PgBouncer connection pools configured for transaction-mode pooling.
   - Queue listings and search queries target dedicated read-only database replicas (`DP-D1`), isolating live write paths from specialist UI traffic.
2. **Redis-Backed Real-Time Queue Caching**:
   - Queue positions and pending approval listings are cached in Redis clusters with sub-second invalidation, enabling 500+ specialists to refresh dashboards without placing load on primary relational tables.

---

## 3. Technical Implementation & Genesis Contracts

```python
"""
core/hitl/feedback_collector.py
Pydantic v2 schemas and Feedback Ingestion Engine for Specialist Review.
"""

from enum import Enum
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class FailureReasonTaxonomy(str, Enum):
    GROUNDING_HALLUCINATION = "grounding_hallucination"
    RETRIEVAL_IRRELEVANCE = "retrieval_irrelevance"
    NUMERIC_MISCALCULATION = "numeric_miscalculation"
    TONE_OR_POLICY_VIOLATION = "tone_or_policy_violation"
    TOOL_ARGUMENT_ERROR = "tool_argument_error"
    UNAUTHORIZED_REQUEST = "unauthorized_request"


class SpecialistFeedbackSubmission(BaseModel):
    """
    Structured feedback record captured on every human approval or rejection (HL-D10).
    """
    case_id: str
    action_or_draft_id: str
    specialist_id: str
    tenant_id: str
    geographic_region: str = Field(..., description="'us' or 'eu'")
    decision: str = Field(..., description="'approved', 'rejected', or 'edited'")
    reason_code: Optional[FailureReasonTaxonomy] = None
    original_ai_draft: Optional[str] = None
    human_edited_draft: Optional[str] = None
    free_text_commentary: Optional[str] = None
    review_latency_seconds: float = Field(..., ge=0.0)
    submitted_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FeedbackIngestionManager:
    """
    Ingests and validates specialist feedback, routing records to CI and EV pipelines.
    """

    def __init__(self, audit_store: Any, ci_event_publisher: Any):
        self.audit_store = audit_store
        self.publisher = ci_event_publisher

    def record_specialist_feedback(
        self,
        feedback: SpecialistFeedbackSubmission
    ) -> Dict[str, Any]:
        """
        Validates schema, persists in regional audit store, and emits CI events (HL-D10).
        """
        if feedback.decision in ["rejected", "edited"] and not feedback.reason_code:
            raise ValueError("Rejections and edits strictly mandate a structured reason_code.")

        # Persist feedback in append-only regional audit table (DP-D3)
        record_id = self.audit_store.insert_feedback(feedback.model_dump())

        # Publish event to Continuous Improvement pipeline (CI-D1)
        self.publisher.emit_event(
            event_type="hitl.feedback.recorded",
            payload={
                "feedback_id": record_id,
                "case_id": feedback.case_id,
                "reason_code": feedback.reason_code.value if feedback.reason_code else None,
                "region": feedback.geographic_region,
                "latency_sec": feedback.review_latency_seconds
            }
        )

        return {
            "status": "feedback_ingested",
            "feedback_id": record_id,
            "region": feedback.geographic_region
        }
```

---

## 4. Failure Modes & Mitigation Matrix

| Failure ID | Sub-Component | Failure Mode Description | Root Cause | Effect on System | Architectural Mitigation (`HL-D10`, `HL-D11`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`DP-D10`** | Console | European customer data transits US cloud | Using SaaS Retool Cloud or central US database | Violation of GDPR Chapter V cross-border transfer laws | `HL-D11` deploys self-hosted Retool containers locally in EU region reading EU backends only |
| **$KU3$** | Console | Specialist console crashes during high-traffic incident | Hundreds of agents querying unindexed Postgres tables | Specialists locked out of queues; mounting customer wait times | Retool queries hit PgBouncer connection pools and dedicated read-only database replicas |
| **$HL-D10$** | Feedback | Vague feedback prevents model improvement | Specialists skip reason codes or submit "Other" | ML engineering cannot diagnose root causes | Schema validation strictly mandates choosing from standardized `FailureReasonTaxonomy` |
| **`CI-D5`** | Feedback | Human edits pollute evaluation benchmarks | Specialists' edited drafts injected directly into test sets | Data leakage causing artificially inflated evaluation scores | `CI-D5` explicitly quarantines human-edited drafts from automated test and few-shot sets |

---

## 5. Closed-Loop Telemetry & Verification Directives

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   FEEDBACK CONSOLE TELEMETRY & OBSERVABILITY PIPELINE                            │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Specialist Decision ──► [ Feedback Collector ] ──► Metric: `hitl.specialist.decisions_total`
                                  │
                                  ├──► [ Reason Code Distribution ] ──► Prometheus: `hitl.rejection.reasons`
                                  │
                                  └──► [ Regional Health Check ] ──► Metric: `retool.cluster.health_status`
```

### 1. Prometheus Telemetry Indicators
- `hitl.specialist.decisions_total`: Counter tracking total actions approved, rejected, and edited.
- `hitl.rejection.reason_distribution`: Histogram tracking counts per `FailureReasonTaxonomy` category.
- `hitl.console.active_specialists`: Gauge tracking concurrent logged-in specialists per regional Retool cluster.
- `hitl.console.query_p95_ms`: P95 database query latency for queue dashboard loading (Target: $\le 250\text{ms}$).

### 2. Audit Trail Events (`DP-ADP-03`, `SG-ADP-05`)
- `specialist.feedback.submitted`: Captures Case ID, Specialist ID, Regional Pod, Reason Enum, and Latency.

---

## 6. Alternatives Considered & Trade-Off Analysis

| Architectural Alternative | Technical Mechanism | Why Rejected / Trade-Off Analysis |
| :--- | :--- | :--- |
| **Retool Cloud SaaS (HL-Q5(ii))** | SaaS-hosted Retool connecting to regional databases via VPN | **Rejected (`DP-D10`)**: Customer data and PII would transit Retool's centralized US infrastructure, violating EU GDPR data sovereignty. |
| **Custom Bespoke React/Next.js Console** | Build internal console from scratch in React | **Rejected**: Requires 6+ months of dedicated frontend development and ongoing maintenance for marginal operational benefit. |
| **Unstructured Free-Text Feedback Only** | Text input field for specialist rejection comments | **Rejected ($HL-D10$)**: Results in low-quality, inconsistent text that cannot be programmatically clustered or tracked in metrics. |
| **Automatic Few-Shot Prompt Insertion** | Immediately inject human-corrected responses into system prompts | **Rejected (`CI-D5`)**: Risks injecting non-standard phrasing, leaking personal identifiers, and contaminating evaluation test suites. |

---

## 7. References & Academic Foundations

1. **GDPR Chapter V (Articles 44–50).** (2016). *Transfers of Personal Data to Third Countries or International Organisations.*
2. **FinOps Foundation.** (2023). *FinOps Framework: Inform, Optimize, Operate.*
3. **Beyer, B. et al.** (2016). *Site Reliability Engineering: How Google Runs Production Systems.* O'Reilly Media. Chapter 14: Managing Incidents.
4. **NIST SP 800-53, Rev. 5.** (2020). *Security and Privacy Controls for Information Systems and Organizations.* Control AC-3: Access Enforcement.
