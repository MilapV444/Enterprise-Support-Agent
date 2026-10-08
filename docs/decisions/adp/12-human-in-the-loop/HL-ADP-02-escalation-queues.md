# HL-ADP-02: Typed Escalation Architecture & Skills-Based SLA Queues (Jev Acuity Priority, Automated Aging Alerts & 72-Hour Cancellation)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-05 *(Confirmed per HL-D3 Skills-Based SLA Queues HL-Q2, HL-D9 Queue Aging & Auto-Cancellation HL-Q4, HL-D12 Typed Escalation Packet KK3)*
- **Deciders**: Architecture Team, Support Operations Director, SRE Principal, Lead Platform Architect
- **Component**: `[12] Human-in-the-Loop` (`Component [ 12 ]`)
- **Reasoning Source**: `checkpoint.md` §16 · Diagram: `LLD - [12] Human-in-the-Loop`
- **Decisions Covered**:
  - `HL-D3`: Skills-Based Queues & Dynamic SLA Escalation — Escalated cases route to domain-specific specialist queues (Billing, Technical, Account, Security) parameterized by Jev triage acuity (`ADP-05`) and customer contract tier; enforces strict SLA timers (`HL-Q2(i)`: live handoffs $\le 15\text{ min}$, action approvals $\le 1\text{ hour}$, significant decision reviews $\le 1\text{ business day}$); breaching an SLA timer automatically promotes the ticket to the senior tier queue and alerts queue managers
  - `HL-D9`: Queue Aging Alerts & 72-Hour Deterministic Cancellation — Resolves silent forgotten workflow deadlocks (`OB-UU3`); automated queue watchers trigger aging alert pages to the queue supervisor when items exceed $50\%$ of SLA; approvals remaining undecided after 3 business days ($72\text{ hours}$, `HL-Q4(i)`) are automatically cancelled by Temporal, releasing conversational mutexes and informing the customer with an explicit human-review recourse offer ($UU3$)
  - `HL-D12`: Universal Typed Escalation Packet — Unifies all human-bound escalations across the platform into a single typed Pydantic schema ($KK3$); bundles Case ID, Customer Provenance, Conversation Summary, Evidence References, Proposed Action Payload, `ADP-04` Reflexion Diagnostic Trails, and Strict SLA Deadlines, ensuring specialists receive zero-context-loss handoffs
- **Related Architectural Decision Points**:
  - [`ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/00-orchestration-core/ADP-04-error-recovery-replanning.md): Error Recovery & Replanning *(Diagnostic Packet Generation)*
  - [`ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/00-orchestration-core/ADP-02-workflow-durability.md): Workflow Durability *(Temporal Timers & Approval Signals)*
  - [`OB-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/09-observability-monitoring/OB-ADP-03-service-levels-alerting.md): Service Levels & Alerting *(Queue Aging & Burn-Rate Paging)*
  - [`UA-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/01-user-application/UA-ADP-04-response-contract-delivery.md): Response Contract & Delivery *(Deferred Inbox Delivery)*
  - [`SG-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/06-safety-security-governance/SG-ADP-05-governance-retention-providers.md): Governance & Compliance *(Significant Decision Review Rights)*

---

## 1. Context & Problem Statement

Work dispatched to human support specialists in autonomous systems frequently suffers from operational fragmentation:
1. **The Context Amnesia Deficit ($KK3$)**:
   - In traditional multi-tier helpdesks, an escalation passes a bare customer message to a human agent without execution history. The customer is forced to re-explain their problem, re-state account identifiers, and re-attempt failed diagnostic steps.
   - Context repetition is the single largest driver of customer dissatisfaction and Customer Effort Score (CES) degradation (Dixon et al., 2010).
2. **The Forgotten Workflow Black Hole (`OB-UU3`)**:
   - When an autonomous workflow requires human authorization for a high-value transaction (`TA-D5`) or complex troubleshooting, the outer Temporal saga sleeps waiting for an external callback signal (`ADP-02`).
   - If the task is routed to an unmonitored or unindexed queue, it sits in execution limbo for days or weeks with zero visibility. The customer's conversation remains locked (`RP-D3`), preventing further interaction.
3. **The Silent Rejection Hazard ($UU3$)**:
   - If an approval times out or is dropped by an overloaded team, simply aborting the workflow without notifying the user creates a silent refusal. Under GDPR Article 22 and consumer protection regulations (`SG-D14`), automated rejections of refunds or account requests require explicit disclosure and accessible human review.

### The Core Architectural Question
> **How do we construct an auditable, skills-based queueing infrastructure that guarantees zero context loss, enforces bounded SLA response timers, and proactively resolves stranded approvals through automated lifecycle cancellation?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `HL-D3`, `HL-D9`, and `HL-D12` establish the **Typed Escalation and Skills-Based SLA Queueing Architecture**, governed by Erlang A queueing models (incorporating customer abandonment dynamics).

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   TYPED ESCALATION & SKILLS-BASED SLA QUEUE PIPELINE (HL-D3, HL-D9, HL-D12)       │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                        Escalation Trigger (Confidence Gate, Tool Approval, Reflexion Limit)
                                                        │
                                                        ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 1. TYPED ESCALATION PACKET COMPILATION (HL-D12, KK3)                                             │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Compiles Universal Envelope:                                                                     │
│ • Case & Conversation ID                      • Verified Identity & Tenant Metadata              │
│ • Rolling Summary + Pinned Entities           • Evidence Citations & Tool Output Diffs           │
│ • Proposed Action (Dry-Run Preview TA-D7)     • Reflexion Diagnostic Trace (`ADP-04`)             │
└─────────────────────────────────────────────────┬────────────────────────────────────────────────┘
                                                  │
                                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 2. SKILLS-BASED DISPATCH & SLA TIMER INITIALIZATION (HL-D3, HL-Q2)                               │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Jev Triage Acuity (`ADP-05`) + Domain Classifier (Billing / Tech / Account)                      │
│                                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ Queue Type & SLA Targets (HL-Q2(i)):                                                     │   │
│   │ • Live Customer Handoff:       SLA = 15 Minutes                                          │   │
│   │ • High-Risk Action Approval:   SLA = 1 Hour                                              │   │
│   │ • Significant Decision Review: SLA = 1 Business Day                                      │   │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┬────────────────────────────────────────────────┘
                                                  │
                                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 3. TEMPORAL WORKFLOW WATCHER & AGING ENGINE (HL-D9, OB-UU3)                                      │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Temporal Outer Saga Monitors Queue Elapsed Time $t_{\text{elapsed}}$:                            │
│                                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ Lifecycle State Transitions:                                                             │   │
│   │ • $t \ge 0.50 \cdot \text{SLA}$ ===> Warning Alert emitted to Queue Lead                  │   │
│   │ • $t \ge 1.00 \cdot \text{SLA}$ ===> PROMOTE TO SENIOR QUEUE (HL-D3) + PagerDuty Page    │   │
│   │ • $t \ge 72\text{ Hours}$       ===> AUTO-CANCEL WORKFLOW (HL-D9, HL-Q4(i)):             │   │
│   │                                      - Release Conversation Concurrency Mutex            │   │
│   │                                      - Send "Undecided" Notice to User with Review Offer │   │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Pillar 1: Universal Typed Escalation Packet (`HL-D12`, $KK3$)

To guarantee zero context amnesia across human transfers, all escalation origins compile a strictly typed Pydantic record:
- **Case Provenance**: Customer UUID, authenticated identity tier (`UA-D3`), tenant tier, and contact channel.
- **Cognitive Context**: Rolling summary of the dialogue (`MS-D1`), verbatim last 3 turns, and active CRM fact pins (`MS-D2`).
- **Evidence Bundle**: Citations to retrieved knowledge passages and raw outputs from diagnostic tool reads (`KR-D16`, `TA-D9`).
- **Diagnostic Trace (`ADP-04`)**: Statechart execution history, Reflexion self-critiques, and root-cause hypotheses.
- **Proposed Action Contract**: Dry-run JSON payload (`TA-D7`) specifying external system destination, mutating arguments, and compensation signatures (`TA-D17`).

---

### Pillar 2: Skills-Based Dispatch & SLA Targets (`HL-D3`, `HL-Q2`)

Cases are dispatched to specialized worker pools rather than a single monolithic inbox:
1. **Queue Taxonomy**:
   - `queue_billing`: Financial disputes, refund approvals, subscription downgrades.
   - `queue_technical`: API integration failures, bug diagnostics, log analysis.
   - `queue_account`: Credential resets, organization role changes, deletion requests.
   - `queue_senior`: Escalated high-value transactions ($\ge \$5,000$, `HL-D4`) and SLA-breached tickets.
2. **Deterministic SLA Timers (`HL-Q2(i)`)**:
   - **Live Conversational Handoffs**: $15\text{ minutes}$ (customer actively waiting in chat session).
   - **Action Approvals**: $1\text{ hour}$ (background workflow waiting on transaction authorization).
   - **Significant Decision Reviews**: $1\text{ business day}$ (regulatory adverse decision appeals, `SG-D14`).
3. **Breach Promotion**:
   - If a queue item exceeds its SLA target, the dispatch engine automatically promotes the ticket priority and transfers ownership to the senior specialist queue.

---

### Pillar 3: Aging Alerts & 72-Hour Auto-Cancellation (`HL-D9`, $UU3$)

To eliminate stranded workflows in Temporal (`OB-UU3`), the platform implements active lifecycle termination:
1. **Aging Alerts**:
   - If an item sits unassigned for $>50\%$ of its SLA window, an alert is dispatched to the team lead via Slack/PagerDuty.
2. **The 72-Hour Cancellation Rule (`HL-Q4(i)`)**:
   - If an action approval remains undecided after 3 business days ($72\text{ hours}$), the Temporal saga executes a deterministic cancellation branch:
     - Cancels the pending activity and releases the conversation concurrency lock (`RP-D3`).
     - Emits an append-only audit record: `action.approval.auto_cancelled`.
     - Dispatches a structured notification to the customer's inbox (`UA-D2`): *"Your requested transaction could not be authorized within our standard review window. Please reply to re-open or request immediate specialist assistance."* ($UU3$ mitigated).

---

## 3. Technical Implementation & Genesis Contracts

```python
"""
core/hitl/escalation_queue.py
Pydantic v2 schemas and Queue Management Engine for Typed Escalations and SLAs.
"""

from enum import Enum
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class EscalationReasonCode(str, Enum):
    CONFIDENCE_GATE_LOW = "confidence_gate_low"
    ACTION_APPROVAL_REQUIRED = "action_approval_required"
    REFLEXION_LIMIT_EXCEEDED = "reflexion_limit_exceeded"
    USER_REQUESTED_HUMAN = "user_requested_human"
    SIGNIFICANT_DECISION_REVIEW = "significant_decision_review"
    SYSTEM_DEPENDENCY_HELD = "system_dependency_held"


class EscalationQueueType(str, Enum):
    BILLING = "queue_billing"
    TECHNICAL = "queue_technical"
    ACCOUNT = "queue_account"
    SENIOR = "queue_senior"


class TypedEscalationPacket(BaseModel):
    """
    Universal context payload passed to human specialist console (HL-D12, KK3).
    """
    case_id: str
    conversation_id: str
    tenant_id: str
    user_id: str
    reason_code: EscalationReasonCode
    assigned_queue: EscalationQueueType
    conversation_summary: str
    last_user_utterance: str
    evidence_citation_urls: List[str]
    proposed_action_payload: Optional[Dict[str, Any]] = None
    diagnostic_trace_summary: Optional[str] = None
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sla_deadline_utc: datetime
    is_senior_promoted: bool = False


class EscalationQueueManager:
    """
    Manages queue dispatching, SLA tracking, and 72-hour auto-cancellation (HL-D3, HL-D9).
    """

    SLA_WINDOWS = {
        EscalationReasonCode.USER_REQUESTED_HUMAN: timedelta(minutes=15),
        EscalationReasonCode.CONFIDENCE_GATE_LOW: timedelta(minutes=15),
        EscalationReasonCode.ACTION_APPROVAL_REQUIRED: timedelta(hours=1),
        EscalationReasonCode.REFLEXION_LIMIT_EXCEEDED: timedelta(hours=1),
        EscalationReasonCode.SIGNIFICANT_DECISION_REVIEW: timedelta(days=1),
        EscalationReasonCode.SYSTEM_DEPENDENCY_HELD: timedelta(days=1),
    }

    CANCELLATION_TIMEOUT = timedelta(days=3)  # 72 Hours (HL-Q4(i))

    def create_escalation_packet(
        self,
        case_id: str,
        conversation_id: str,
        tenant_id: str,
        user_id: str,
        reason: EscalationReasonCode,
        domain: str,
        summary: str,
        last_turn: str,
        citations: List[str],
        action_payload: Optional[Dict[str, Any]] = None
    ) -> TypedEscalationPacket:
        """
        Constructs typed packet and calculates SLA deadlines (HL-D3, HL-D12).
        """
        now = datetime.now(timezone.utc)
        sla_delta = self.SLA_WINDOWS.get(reason, timedelta(hours=1))
        deadline = now + sla_delta

        # Determine queue by domain
        if domain == "billing":
            queue = EscalationQueueType.BILLING
        elif domain == "technical":
            queue = EscalationQueueType.TECHNICAL
        elif domain == "account":
            queue = EscalationQueueType.ACCOUNT
        else:
            queue = EscalationQueueType.TECHNICAL

        return TypedEscalationPacket(
            case_id=case_id,
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            user_id=user_id,
            reason_code=reason,
            assigned_queue=queue,
            conversation_summary=summary,
            last_user_utterance=last_turn,
            evidence_citation_urls=citations,
            proposed_action_payload=action_payload,
            sla_deadline_utc=deadline
        )

    def evaluate_item_aging(self, packet: TypedEscalationPacket) -> Dict[str, Any]:
        """
        Evaluates SLA breaches and 72-hour cancellations (HL-D9).
        """
        now = datetime.now(timezone.utc)
        age = now - packet.created_at_utc

        if age >= self.CANCELLATION_TIMEOUT:
            # 72-hour auto-cancellation triggered (HL-D9)
            return {
                "action": "auto_cancel",
                "reason": "undecided_approval_72h_timeout",
                "notify_user": True,
                "release_mutex": True
            }

        if now > packet.sla_deadline_utc and not packet.is_senior_promoted:
            # SLA breached: Promote to senior queue (HL-D3)
            packet.assigned_queue = EscalationQueueType.SENIOR
            packet.is_senior_promoted = True
            return {
                "action": "promote_to_senior",
                "alert_lead": True
            }

        return {"action": "maintain_queue"}
```

---

## 4. Failure Modes & Mitigation Matrix

| Failure ID | Sub-Component | Failure Mode Description | Root Cause | Effect on System | Architectural Mitigation (`HL-D3`, `HL-D9`, `HL-D12`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **$KK3$** | Escalation | Specialist receives ticket without evidence | Untyped ad-hoc escalation payload | Specialist asks customer to repeat information, degrading CES | `HL-D12` mandates Typed Escalation Packet with summary, citations, and tool diffs |
| **`OB-UU3`** | Escalation | Approval sits unobserved in queue indefinitely | Temporal saga waiting on signal without queue visibility | Customer locked out of conversation; transaction stalled | `HL-D9` enforces automated queue aging watchers and 72-hour hard lifecycle cancellation |
| **$UU3$** | Escalation | Auto-cancelled approval interpreted as silent refusal | Timeout aborts refund approval without customer notification | Regulatory non-compliance with GDPR Art. 22 / consumer rules | `HL-D9` notifies customer of undecided status with explicit link to request manual human appeal |
| **$KU2$** | Escalation | High queue backlog causes mass SLA breaches | Influx of difficult turns exceeds specialist roster | Delayed response times and SLA penalties | `HL-D3` promotes breached tickets to Senior queue; alerts queue supervisor for surge roster activation |
| **$UK1$** | Escalation | Customer double-escalates via secondary channel | User creates parallel ticket while chat approval waits | Split ticket state across multiple human specialists | `MS-D1` case linkage maps multiple conversations to one unified case ID; suppresses duplicate tickets |

---

## 5. Closed-Loop Telemetry & Verification Directives

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   ESCALATION QUEUE TELEMETRY & OBSERVABILITY PIPELINE                            │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Escalation Event ──► [ Queue Dispatcher ] ──► Prometheus: `hitl.queue.depth`
                              │
                              ├──► [ SLA Breach Watcher ] ──► Metric: `hitl.queue.sla_breach_total`
                              │
                              └──► [ 72h Cancellation Job ] ──► Metric: `hitl.approval.auto_cancelled`
```

### 1. Prometheus Telemetry Indicators
- `hitl.queue.depth`: Gauge tracking active items per queue (`billing`, `technical`, `account`, `senior`).
- `hitl.queue.sla_breach_total`: Counter tracking tickets exceeding SLA deadlines.
- `hitl.queue.wait_duration_seconds`: Histogram tracking elapsed time from escalation to specialist pickup.
- `hitl.approval.auto_cancelled_total`: Total workflows aborted due to 72-hour timeout.

### 2. OpenTelemetry Attributes
- `escalation.reason_code`: `"action_approval_required"` | `"user_requested_human"`
- `escalation.queue_type`: `"queue_billing"` | `"queue_senior"`
- `escalation.sla_deadline`: ISO-8601 UTC timestamp string.

---

## 6. Alternatives Considered & Trade-Off Analysis

| Architectural Alternative | Technical Mechanism | Why Rejected / Trade-Off Analysis |
| :--- | :--- | :--- |
| **Monolithic FIFO Queue (Option A)** | Single queue for all escalations, handled first-in first-out | **Rejected**: Inefficient; forces technical network engineers to review billing invoices and generalists to handle complex code bugs. |
| **Infinite Workflow Waiting (Option B)** | Allow Temporal workflows to sleep indefinitely until approved | **Rejected (`OB-UU3`)**: Generates phantom cases and locks conversational statecharts for months when tickets are abandoned by human staff. |
| **Immediate Approval Cancellation (24h, HL-Q4(ii))** | Cancel undecided approvals after 24 hours | **Rejected**: Too aggressive for weekend or holiday coverage; causes legitimate customer refund requests to fail prematurely. |
| **Untyped Slack Escalation Webhooks (Option C)** | Post markdown messages to Slack channels for human triage | **Rejected ($KK3$)**: Unstructured; loses execution context and prevents deterministic SLA tracking and role-based authorization. |

---

## 7. References & Academic Foundations

1. **Dixon, M., Toman, N., & DeLisi, R.** (2010). *Stop Trying to Delight Your Customers.* Harvard Business Review, 88(7/8), 116-122.
2. **Beyer, B. et al.** (2016). *Site Reliability Engineering: How Google Runs Production Systems.* O'Reilly Media. Chapter 28: Managing Critical State.
3. **Erlang, A. K.** (1909). *The Theory of Probabilities and Telephone Conversations.* Nyt Tidsskrift for Matematik B.
4. **GDPR Article 22.** (2016). *Automated Individual Decision-Making, Including Profiling.* Right to Human Intervention.
