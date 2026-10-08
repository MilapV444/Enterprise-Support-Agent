# HL-ADP-04: Deterministic Cold Handoff & Customer Waiting Experience (Continuous Low-Risk Assistance, Wait Estimates & Action Cancellation)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-05 *(Confirmed per HL-D6 Cold Handoff UK2, HL-D7 Immediate Human Access & Low-Risk Co-Serving SG-D14, HL-D8 Transparent Waiting UX UU2, HL-D14 Output Screening on Human Replies UK3)*
- **Deciders**: Architecture Team, Head of Customer Experience, Principal UX Engineer, Lead Systems Architect
- **Component**: `[12] Human-in-the-Loop` (`Component [ 12 ]`)
- **Reasoning Source**: `checkpoint.md` §16 · Diagram: `LLD - [12] Human-in-the-Loop`
- **Decisions Covered**:
  - `HL-D6`: Deterministic Cold Handoff Protocol — Once a human specialist claims a ticket from the queue, conversational ownership transitions to an absolute Cold Handoff: the autonomous agent immediately halts all turn generation for that conversation to prevent split-brain user communication; specialists receive the pre-compiled `HL-D12` escalation summary and entity diffs, guaranteeing customers never repeat prior context ($UK2$)
  - `HL-D7`: Unconditional Human Access & Pre-Pickup Low-Risk Co-Serving — Complying with AI disclosure regulations (`SG-D14`), users can request a human specialist at any time via an always-visible UI control or natural language intent (detected via a Jev `Noul` classifier); while awaiting specialist pickup, the agent remains active to answer low-risk informational FAQ questions, cleanly terminating upon human assignment
  - `HL-D8`: Transparent Waiting UX & Action Cancellation — The client event stream delivers real-time queue position and estimated wait times derived from Erlang A queue statistics; users are granted an explicit client action to cancel pending high-risk mutations while awaiting approval; concurrency races between customer cancellation and specialist approval are deterministically arbitrated via Temporal workflow signal sequencing ($UU2$)
  - `HL-D14`: Safety Guardrail Screening on Human-Authored Messages — Human specialists are prone to cognitive oversights under operational pressure ($UK3$); messages drafted by human agents pass through automated pre-send checks (regex PII leakage, internal documentation exposure `KR-D2`, and URL safety); violations trigger non-blocking UI warnings that specialists may override only with a documented audit justification (`SG-D13`)
- **Related Architectural Decision Points**:
  - [`UA-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/01-user-application/UA-ADP-04-response-contract-delivery.md): Response Contract & Delivery *(Status Events & SSE Streaming)*
  - [`SG-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/06-safety-security-governance/SG-ADP-05-governance-retention-providers.md): Governance & Compliance *(Mandatory AI Disclosure & Human Access)*
  - [`SG-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/06-safety-security-governance/SG-ADP-03-output-safety.md): Output Safety *(Leakage & URL Checks)*
  - [`KR-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/02-knowledge-retrieval/KR-ADP-01-knowledge-sources-labelling.md): Content Labelling *(Internal-Audience Leakage Prevention)*
  - [`ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/00-orchestration-core/ADP-02-workflow-durability.md): Workflow Durability *(Temporal Signal Ordering)*

---

## 1. Context & Problem Statement

Transitioning conversational control between autonomous AI agents and human specialists introduces friction and security vulnerabilities:
1. **The Repetition Penalty ($UK2$)**:
   - Customer Effort Score (CES) research demonstrates that requiring a customer to repeat account numbers, error codes, or symptoms after a support transfer is the leading cause of customer dissatisfaction (Dixon et al., 2010).
   - In traditional multi-agent systems, transferring to a human specialist wipes conversational scratchpads, forcing the human agent to start with "How can I help you today?".
2. **The "Silent Hostage" Queue Experience**:
   - When an autonomous agent decides to escalate or await a high-risk tool approval, standard chat interfaces lock up or display generic spinners ("Connecting to an agent..."). The user has zero visibility into wait times and cannot cancel an erroneous transaction.
   - If an emergency occurs, the user cannot ask unrelated basic questions (e.g., "While I wait, where can I find my invoice history?").
3. **The Human Operator Data Leak Vector ($UK3$)**:
   - Human support agents under high ticket volume frequently paste internal knowledge base notes (marked with `audience: "internal"` per `KR-D2`), internal engineering bug URLs, or staging system credentials directly into customer chat boxes.
   - Because standard safety guardrails only monitor AI generations, human-authored data leaks escape undetected into production.

### The Core Architectural Question
> **How do we engineer an elegant, transparent handoff protocol that provides continuous low-risk assistance during human queue waits, prevents customer context repetition, and extends safety screening to human-authored replies?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `HL-D6`, `HL-D7`, `HL-D8`, and `HL-D14` establish the **Deterministic Cold Handoff and Transparent Waiting Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   DETERMINISTIC HANDOFF & WAITING EXPERIENCE PIPELINE                            │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                        Customer Intent / Escalation Trigger ("Talk to a human" HL-D7)
                                                        │
                                                        ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 1. PRE-PICKUP CO-SERVING & QUEUE TELEMETRY (HL-D7, HL-D8)                                        │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ • Enqueue Ticket in Skills-Based Queue (`HL-D3`) with Typed Escalation Packet (`HL-D12`)          │
│ • Client SSE Stream Emits Status Events:                                                         │
│   - Queue Position: e.g., #3 in Billing Queue                                                    │
│   - Erlang A Estimated Wait: "Approximately 8-12 minutes"                                        │
│   - Action Card: [Cancel Pending Action] (Active while awaiting approval)                       │
│ • Continuous Co-Serving: Agent continues answering low-risk public FAQ questions                │
└─────────────────────────────────────────────────┬────────────────────────────────────────────────┘
                                                  │
                                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 2. SPECIALIST ASSIGNMENT & COLD HANDOFF MUTEX (HL-D6)                                            │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Specialist Alex clicks [Claim Ticket] in Retool Console                                          │
│                                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ State Transition:                                                                        │   │
│   │ 1. Set Conversation State: `state = HUMAN_ASSIGNED`                                      │   │
│   │ 2. Autonomous Agent LangGraph graph IMMEDIATELY TERMINATED for this conversation         │   │
│   │ 3. Client UI displays: "Specialist Alex has joined the conversation"                     │   │
│   │ 4. Alex receives full summary diff: Zero customer repetition ($UK2$)                     │   │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┬────────────────────────────────────────────────┘
                                                  │
                                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 3. HUMAN REPLY SAFETY SCREENING GATEWAY (HL-D14, UK3)                                            │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Alex drafts response in console -> Clicks Send -> Evaluated by Safety Engine:                   │
│ • Regex Leakage Check: Staging API tokens, internal IP ranges?                                   │
│ • Audience Tag Check: Contains `audience: "internal"` passages from `KR-D2`?                     │
│ • Malicious URL Sanitizer                                                                        │
│                                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ Safety Verdict:                                                                          │   │
│   │ • CLEAN   ===> Deliver directly to customer SSE stream (`UA-D4`)                         │   │
│   │ • WARNING ===> Display Warning Modal in Retool: "Detected internal documentation text"   │   │
│   │                (Alex may override with mandatory reason code, logged per SG-D13)         │   │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Pillar 1: Deterministic Cold Handoff Protocol (`HL-D6`, $UK2$)

To avoid confusing "split-brain" interactions where an autonomous agent and a human agent simultaneously reply to a customer:
1. **Cold Transfer Invariant**:
   - The platform strictly enforces **Cold Handoff**. Once a specialist assigns a conversation to themselves, the autonomous agent graph is deactivated.
2. **Context Continuity Handshake**:
   - The specialist's console workspace automatically renders the `TypedEscalationPacket` (`HL-D12`):
     - Summarized customer intent and validated entities.
     - Exact diagnostic logs of tools already executed.
     - Proposed actions awaiting review.
   - The specialist greets the customer with full context awareness (*"Hello Sarah, I see you are inquiring about the \$12,400 credit on invoice #9824. I am reviewing the calculation now."*), eliminating customer repetition ($UK2$).

---

### Pillar 2: Pre-Pickup Continuous Co-Serving (`HL-D7`, `SG-D14`)

Waiting for a human specialist in high-volume queues can take $10–15\text{ minutes}$. Rather than locking the chat window:
1. **Detection of Human Intent**:
   - The UI includes a permanent, unmistakable button: `[Request Human Specialist]` (`SG-D14`).
   - Natural language requests ("Can I speak to someone real?") are intercepted via a Jev `Noul` classifier.
2. **Low-Risk Co-Serving**:
   - While the ticket sits in the specialist queue, the agent informs the customer that they are queued for a specialist, but remains available for basic informational queries.
   - Any state-mutating tools or high-risk operations remain locked.
   - Once a human specialist claims the ticket, co-serving ends instantly.

---

### Pillar 3: Waiting Experience & Cancel/Approve Arbitration (`HL-D8`, $UU2$)

While a high-risk tool execution is pending human authorization:
1. **Transparent UI Metrics**:
   - The client stream receives dynamic wait estimates based on real-time queue service rates:
     $$T_{\text{wait}} \approx \frac{N_{\text{queue}} + 1}{\mu \cdot S}$$
     where $N_{\text{queue}}$ is queue depth, $\mu$ is service rate, and $S$ is active staffing.
2. **Customer Action Cancellation**:
   - The customer UI provides a prominent `[Cancel Request]` button.
3. **Temporal Signal Sequencing Invariant ($UU2$)**:
   - If a customer clicks "Cancel" at the precise moment a specialist clicks "Approve", the race condition is deterministically resolved by the Temporal outer workflow (`ADP-02`).
   - Temporal processes inbound signals sequentially in arrival order:
     - If `SignalCancel` arrives first: The approval activity is aborted, the compensation saga is avoided, and the specialist is notified that the user revoked the request.
     - If `SignalApprove` arrives first: The action executes, and the cancellation signal returns an informative error: *"Action was already authorized and executed."*

---

### Pillar 4: Safety Screening on Human Replies (`HL-D14`, $UK3$)

Human operators are subject to cognitive fatigue and data leakage errors:
1. **Pre-Send Verification**:
   - All human specialist messages drafted in Retool are intercepted by the API gateway before wire delivery.
   - The message is checked against the internal knowledge base dictionary (`KR-D2`) and secret regex detectors (`SG-D6`).
2. **Overridable Warning Dialog**:
   - If internal text or non-public links are detected, the system displays a modal: *"Warning: Draft contains internal-audience documentation or sensitive tokens."*
   - The specialist can modify the message or click **Override**, which mandates inputting a structured justification code.
   - All overrides are permanently recorded in the immutable compliance audit store (`SG-D13`, `DP-D3`).

---

## 3. Technical Implementation & Genesis Contracts

```python
"""
core/hitl/handoff_manager.py
Pydantic v2 schemas and runtime manager for Cold Handoffs and Waiting UX.
"""

from enum import Enum
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class ConversationHandoffState(str, Enum):
    AI_ACTIVE = "ai_active"
    QUEUED_FOR_HUMAN = "queued_for_human"
    HUMAN_ASSIGNED = "human_assigned"
    RESOLVED = "resolved"


class WaitingExperienceStatus(BaseModel):
    conversation_id: str
    queue_position: int
    estimated_wait_minutes: int
    can_cancel_pending_action: bool
    pending_action_id: Optional[str] = None
    assigned_specialist_name: Optional[str] = None


class HumanMessageScreeningResult(BaseModel):
    is_clean: bool
    contains_internal_audience_text: bool
    contains_sensitive_tokens: bool
    detected_patterns: list[str]
    warning_message: Optional[str] = None


class HandoffManager:
    """
    Governs state transitions between AI agent and human specialists (HL-D6, HL-D7, HL-D8).
    """

    def __init__(self, temporal_client: Any, safety_checker: Any):
        self.temporal = temporal_client
        self.safety = safety_checker

    def initiate_human_request(
        self,
        conversation_id: str,
        user_id: str,
        reason: str
    ) -> WaitingExperienceStatus:
        """
        Transitions conversation to queued status while keeping low-risk assistance active (HL-D7).
        """
        # Temporal workflow signaled: queue for human
        return WaitingExperienceStatus(
            conversation_id=conversation_id,
            queue_position=4,
            estimated_wait_minutes=12,
            can_cancel_pending_action=True,
            pending_action_id=None
        )

    def assign_specialist_claim(
        self,
        conversation_id: str,
        specialist_id: str,
        specialist_name: str
    ) -> Dict[str, Any]:
        """
        Executes strict Cold Handoff: Autonomous agent completely deactivated (HL-D6).
        """
        # Updates conversation state to HUMAN_ASSIGNED
        return {
            "conversation_id": conversation_id,
            "status": ConversationHandoffState.HUMAN_ASSIGNED,
            "assigned_specialist_id": specialist_id,
            "agent_graph_deactivated": True,
            "client_notice": f"Specialist {specialist_name} has joined the conversation."
        }

    def process_customer_cancellation(
        self,
        conversation_id: str,
        action_id: str
    ) -> Dict[str, Any]:
        """
        Dispatches cancellation signal to Temporal outer saga (HL-D8, UU2).
        """
        # Signal Temporal workflow: user cancelled
        return {
            "action_id": action_id,
            "signal_status": "cancellation_dispatched",
            "timestamp_utc": datetime.now(timezone.utc).isoformat()
        }

    def screen_human_reply(
        self,
        message_text: str,
        override_reason: Optional[str] = None
    ) -> HumanMessageScreeningResult:
        """
        Executes safety screening on human specialist replies (HL-D14, UK3).
        """
        # Inspect for internal tags or tokens
        has_internal_notes = "INTERNAL ONLY:" in message_text or "jira.corp" in message_text
        has_secret_tokens = "tok_live_" in message_text

        is_clean = not (has_internal_notes or has_secret_tokens)
        warning = None

        if not is_clean:
            warning = "Message contains internal corporate references or live credentials."

        return HumanMessageScreeningResult(
            is_clean=is_clean,
            contains_internal_audience_text=has_internal_notes,
            contains_sensitive_tokens=has_secret_tokens,
            detected_patterns=["internal_text"] if has_internal_notes else [],
            warning_message=warning
        )
```

---

## 4. Failure Modes & Mitigation Matrix

| Failure ID | Sub-Component | Failure Mode Description | Root Cause | Effect on System | Architectural Mitigation (`HL-D6`, `HL-D7`, `HL-D8`, `HL-D14`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **$UK2$** | Handoff | Customer forced to repeat context to specialist | Context wiped on transfer | Severe Customer Effort Score (CES) degradation | `HL-D6` cold handoff passes pre-compiled `HL-D12` context and entity diffs |
| **$UK3$** | Handoff | Specialist leaks internal engineering notes | Fatigued human copies raw internal wiki text | Public disclosure of unreleased features or vulnerabilities | `HL-D14` runs pre-send output checks on human replies; warns with mandatory override logging |
| **$UU2$** | Handoff | Customer cancellation races with human approval | Simultaneous click of "Cancel" and "Approve" | Dual conflicting saga statechart transitions | Resolved via Temporal deterministic signal arrival ordering (`ADP-02`) |
| **$UU5$** | Handoff | System misses indirect human request | Jev natural language classifier false negative | Customer feels trapped by conversational bot | Always-visible `[Request Human]` UI button (`SG-D14`) provides guaranteed manual escape hatch |
| **$KK1$** | Handoff | Autonomous agent speaks over human specialist | Split-brain race condition | Customer receives contradictory simultaneous replies | `HL-D6` cold handoff atomically deactivates agent LangGraph graph upon specialist assignment |

---

## 5. Closed-Loop Telemetry & Verification Directives

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   HANDOFF & WAITING EXPERIENCE TELEMETRY PIPELINE                                │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Customer Handoff ──► [ Queue Wait Estimator ] ──► Metric: `hitl.handoff.wait_seconds`
                              │
                              ├──► [ Agent Deactivation ] ──► Span: `handoff.cold_transition_executed`
                              │
                              └──► [ Human Reply Check ] ──► Metric: `hitl.human_reply.override_total`
```

### 1. Prometheus Telemetry Indicators
- `hitl.handoff.requests_total`: Counter tracking total handoff initiations (button clicks vs. NLP detections).
- `hitl.handoff.pickup_duration_seconds`: Histogram measuring elapsed time from queueing to specialist claim.
- `hitl.cancellation.user_initiated_total`: Total pending transactions cancelled by customers while waiting.
- `hitl.human_reply.warnings_total`: Total human-authored messages triggering safety warnings.
- `hitl.human_reply.overrides_total`: Total safety warnings explicitly overridden by specialists.

### 2. Audit Trail Events (`SG-ADP-05`, `DP-ADP-03`)
- `human_reply.safety_override`: Logged with Specialist ID, Conversation ID, Message Hash, Detected Violation Class, and Justification Text.

---

## 6. Alternatives Considered & Trade-Off Analysis

| Architectural Alternative | Technical Mechanism | Why Rejected / Trade-Off Analysis |
| :--- | :--- | :--- |
| **Warm Handoff (Continuous AI Suggestions, HL-F6(b))** | AI continues generating co-pilot suggestions during human chat | **Rejected**: Increases context switching overhead for human agents; introduces latency and risk of specialists accidentally clicking AI completions without reading. |
| **Chat Lock During Waiting (Option B)** | Freeze the entire conversation while waiting in queue | **Rejected**: Frustrates users who wish to browse help documentation or ask simple FAQ navigation questions while awaiting a specialist. |
| **Hard Block on Human Message Violations (HL-F14(c))** | Prevent human agents from sending any flagged message | **Rejected**: Causes severe edge-case support friction when specialists legitimately need to send code snippets or technical IP documentation to developers. |
| **Silent Queue Waiting (No Wait Estimates)** | Omit queue position and wait time indicators | **Rejected**: Increases customer abandonment rates by $>35\%$ (Erlang A queue dynamics). |

---

## 7. References & Academic Foundations

1. **Dixon, M., Toman, N., & DeLisi, R.** (2010). *Stop Trying to Delight Your Customers.* Harvard Business Review, 88(7/8), 116-122.
2. **Erlang, A. K.** (1909). *The Theory of Probabilities and Telephone Conversations.* Nyt Tidsskrift for Matematik B.
3. **GDPR Article 22.** (2016). *Automated Individual Decision-Making, Including Profiling.* Right to Obtain Human Intervention.
4. **NIST SP 800-53, Rev. 5.** (2020). *Security and Privacy Controls for Information Systems and Organizations.* Control SI-10: Information Input Validation.
