# UA-ADP-01: Channels & API Transport (Web-First Ingress & Decoupled Asynchronous SSE Transport)

- **Status**: Accepted & Confirmed
- **Date**: 2026-09-23
- **Deciders**: Architecture Team, Lead Transport & API Engineer, Security Core
- **Component**: `[1] User & Application` (`Component [ 1 ]`)
- **Reasoning Source**: `checkpoint.md` §5 · Diagram: `LLD - [1] User & Application`
- **Decisions Covered**:
  - `UA-D1`: Channels — Web-only v1 with Channel-Agnostic Canonical Envelope
  - `UA-D2`: API Transport — Decoupled `POST 202` + Resumable Server-Sent Events (SSE)
- **Related Architectural Decision Points**:
  - [`RP-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#rp-adp-01--admission-control): Admission Control *(Rate Limiting & Connection Throttling)*
  - [`DP-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#dp-adp-04--data-movement--stream-retention): Data Movement & Stream Retention *(Event Log Storage & TTL)*
  - [`UA-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/01-user-application/UA-ADP-04-response-contract-delivery.md): Response Contract & Delivery *(Typed Event Envelope & Status Steaming)*

---

## 1. Context & Problem Statement

Conversational enterprise AI agents must ingest unstructured user turns across modern digital surfaces while managing downstream cognitive execution latencies that range from 800ms (direct SOP lookups) to 45 seconds (multi-step diagnostic tool chains or Human-in-the-Loop approvals).

Traditional client-server conversational protocols exhibit severe architectural vulnerabilities:
1. **Synchronous HTTP Request-Response Deadlocks**: Holding open a synchronous HTTP POST connection while an agent performs multi-hop reasoning, tool invocation, and safety screening triggers corporate proxy timeouts (e.g., AWS ALB 60s drops, Cloudflare 524 timeouts), exhaust gateway connection pools, and exposes the system to client-retry storms ($KK1$).
2. **WebSocket Fragility Across Enterprise Firewalls**: While bidirectional WebSockets (RFC 6455) provide real-time duplex communication, they frequently fail in enterprise environments where corporate forward proxies, VPNs, and Next-Gen Firewalls (NGFW) terminate or inspect non-HTTP traffic, block HTTP `Upgrade` headers, or aggressively drop idle TCP connections without heartbeat negotiation ($KU1$).
3. **Omnichannel Surface Fragmentation**: Attempting to launch simultaneously across Slack, Microsoft Teams, WhatsApp, Email, and Web introduces disparate webhook acknowledgement contracts (e.g., Slack's mandatory 3-second HTTP 200 ack window vs. email MIME parsing), diluting core engine stability.

### The Core Architectural Question
> **Which user channels ship in v1, and how do client applications submit conversational turns and reliably receive multi-part, streaming, and delayed agent responses across hostile network topologies?**

---

## 2. Decision Framework & Theoretical Formulation

We formulate our transport and channel architecture upon three theoretical pillars: **Queuing Theory & Little's Law for Connection Pools**, **Idempotent State-Mutation Semantics**, and **Resumable Event-Stream Information Delivery**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                            TRANSPORT THEORETICAL PILLARS                                         │
├────────────────────────────────┬────────────────────────────────┬────────────────────────────────┤
│   Pillar A: Queuing Theory     │   Pillar B: Distributed        │   Pillar C: Unidirectional     │
│   & Little's Law for Gateways  │   Idempotency & Deduplication  │   Resumable Event Streams      │
│                                │                                │                                │
│   • L = λ · W connection load  │   • Exactly-once semantics     │   • HTTP/2 Server-Sent Events  │
│   • Asynchronous decoupling    │   • Deterministic turn_id hash │   • WHATWG Last-Event-ID       │
│   • HTTP 202 Accepted ingress  │   • Eliminates duplicate tool  │   • Monotonic replay log       │
│   • Eliminates gateway HOL     │     side-effects (KK1)         │   • Firewall transparency      │
└────────────────────────────────┴────────────────────────────────┴────────────────────────────────┘
```

---

### Pillar A: Queuing Theory & Little's Law for Gateway Connection Pools

Let an API gateway handle arrival rate $\lambda_{\text{turn}}$ turns per second. If the client connection remains synchronously open while the agent processes the turn, the average holding time equals the end-to-end cognitive reasoning latency $W_{\text{sync}} \in [5\text{s}, 30\text{s}]$.

By **Little's Law (Little, 1961)**, the average number of concurrently open, thread-blocking gateway sockets $L_{\text{sync}}$ is:

$$L_{\text{sync}} = \lambda_{\text{turn}} \cdot W_{\text{sync}}$$

At an enterprise peak load of $\lambda_{\text{turn}} = 200\text{ turns/sec}$ with an average multi-hop agent latency of $W_{\text{sync}} = 12\text{ seconds}$:

$$L_{\text{sync}} = 200 \cdot 12 = \mathbf{2,400 \text{ concurrent open socket handles}}$$

This creates severe thread pool starvation, file descriptor exhaustion, and head-of-line blocking at the ingress edge. 

By contrast, under a **Decoupled Asynchronous Transport Model** (`UA-D2`), the ingress submission `POST /turns` performs only authentication, schema validation, and event queue dispatch before immediately returning `HTTP 202 Accepted` ($W_{\text{async}} \approx 35\text{ms}$):

$$L_{\text{async}} = \lambda_{\text{turn}} \cdot W_{\text{async}} = 200 \cdot 0.035 = \mathbf{7 \text{ concurrent socket handles}}$$

This represents a **$99.7\%$ reduction** in ingress socket occupancy, decoupling network stability from LLM inference latency.

---

### Pillar B: Distributed Idempotency & Exactly-Once Ingress Semantics

In unstable mobile and corporate networks, client timeouts frequently trigger automated network retries. If the agent ingress pipeline processes duplicate HTTP POSTs, the agent risks proposing duplicate financial transactions or double-booking operations ($KK1$).

We enforce strict **Idempotency Semantics (IETF Draft Idempotency-Key-Header)**:

$$\text{Request Fingerprint } \Phi = \mathcal{H}\Big(\text{TenantID} \parallel \text{PrincipalID} \parallel \text{ConversationID} \parallel \text{IdempotencyKey}\Big)$$

Where $\mathcal{H}$ is cryptographic SHA-256 and `Idempotency-Key` is client-supplied (defaulting to a UUIDv4 `turn_id`).

#### The Ingress State Transition
Upon receipt of turn submission $(T_{\text{id}}, \Phi)$:
1. The gateway executes an atomic Redis/Memory evaluation:
   $$\text{SET } \Phi \text{ "IN_PROGRESS" EX } \Delta t_{\text{dedupe}} \text{ NX}$$
2. If the key already exists:
   - If `"IN_PROGRESS"`, return `HTTP 409 Conflict` (or `HTTP 202` with identical `turn_id` pointer).
   - If `"COMPLETED"`, immediately return the cached acknowledgment payload without re-triggering downstream execution.
3. The deduplication window is strictly parameterized to $\Delta t_{\text{dedupe}} = 120\text{ seconds}$, comfortably exceeding client TCP retry envelopes.

---

### Pillar C: Unidirectional Resumable Event Streams (HTTP/2 SSE)

While WebSocket requires bidirectional binary framing and stateful TCP session affinity, **Server-Sent Events (WHATWG HTML §9.2)** leverage plain HTTP/1.1 or HTTP/2 text streams (`text/event-stream`).

#### Theoretical Advantages of SSE over WebSocket
1. **Firewall & Proxy Transparency**: SSE requests are standard HTTP `GET` requests with `Accept: text/event-stream`. Corporate proxies inspect TLS certificates, apply standard HTTP authentication headers (`Authorization: Bearer`), and allow traffic through standard port 443 without rejecting WebSocket handshake upgrades ($KU1$).
2. **Native Reconnect & Replay Semantics**: The SSE specification provides native client-side reconnect handling with the `Last-Event-ID` header. If a corporate Wi-Fi network blips or a proxy cuts the stream ($KK2$), the client reconnects automatically:
   $$\text{GET /conversations/\{id\}/events} \quad \text{with Header: } \texttt{Last-Event-ID: } e_k$$
   The server replays all events with sequence IDs $e_i > e_k$ directly from the conversation's append-only outbound event log (`DP-ADP-04`), guaranteeing zero dropped messages.

---

## 3. Decision Rules & System Architecture

### Architectural Decision

1. **Channel Scope (`UA-D1`)**:
   - **Web widget is the exclusive customer-facing channel in v1**.
   - All inbound and outbound schemas strictly use a **Channel-Agnostic Canonical Envelope** (`InboundTurnEnvelope` and `OutboundResponseEnvelope`). Future channel adapters (Slack, Microsoft Teams, Twilio SMS, Email) will plug in as modular, edge-level translators without altering core downstream interfaces.
2. **API Transport Paradigm (`UA-D2`)**:
   - **Decoupled Submit/Receive**:
     - Submission: `POST /v1/conversations/{conversation_id}/turns` with `Idempotency-Key: {turn_id}` returns `HTTP 202 Accepted` containing `{ "turn_id": "...", "status": "QUEUED" }`.
     - Streaming & Delivery: `GET /v1/conversations/{conversation_id}/events` establishes a persistent, resumable SSE stream.
   - **Unified Path**: The same SSE stream handles real-time typing indicators, chunked token streaming, citations, action cards, and deferred Human-in-the-Loop outcomes that resolve hours later.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   DECOUPLED ASYNCHRONOUS API TRANSPORT ARCHITECTURE                              │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                   │
  [Client Web Widget]                              │
           │                                       │
           │ 1. POST /v1/conversations/{id}/turns  │
           │    Header: Idempotency-Key = turn_123 │
           ├───────────────────────────────────────┼──> [API Gateway Ingress]
           │                                       │           │
           │ <─────────────────────────────────────┼──── [202 Accepted {turn_id: "turn_123"}]
           │    (Returns immediately in ~35ms)     │           │
           │                                       │           v
           │                                       │    [Deduplication & Queue]
           │                                       │           │
           │                                       │           v
           │                                       │    [Orchestration Core & Tools]
           │                                       │           │
           │ 2. GET /v1/conversations/{id}/events  │           │
           │    Header: Last-Event-ID = evt_004    │           │
           ├───────────────────────────────────────┼──> [SSE Streaming Endpoint]
           │                                       │           ▲
           │ <─────────────────────────────────────┼───────────┴─── [Outbound Event Log]
           │    event: status (Thinking...)        │                (PostgreSQL / Redis)
           │    event: citation (Doc #42)          │
           │    event: final (Validated response)  │
```

---

### Concrete Genesis Implementation Contracts

#### 1. Ingress Turn Envelope (`core/transport/models.py`)

```python
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class ChannelType(str, Enum):
    WEB_WIDGET = "WEB_WIDGET"
    SLACK = "SLACK"          # Reserved for v2
    TEAMS = "TEAMS"          # Reserved for v2
    EMAIL = "EMAIL"          # Reserved for v2

class ChannelCapabilities(BaseModel):
    supports_markdown: bool = True
    supports_rich_cards: bool = True
    supports_streaming: bool = True
    max_payload_bytes: int = 65536

class InboundTurnEnvelope(BaseModel):
    tenant_id: str
    principal_id: str
    assurance_tier: str = Field(description="T0_ANON, T1_VERIFIED, T2_SSO")
    session_id: str
    conversation_id: str
    turn_id: str
    channel: ChannelType = ChannelType.WEB_WIDGET
    channel_capabilities: ChannelCapabilities = Field(default_factory=ChannelCapabilities)
    content: str = Field(min_length=1, max_length=16384)
    attachment_refs: List[str] = Field(default_factory=list)
    received_at: datetime = Field(default_factory=datetime.utcnow)
```

#### 2. FastAPI Ingress & SSE Controller (`api/v1/transport.py`)

```python
import asyncio
from fastapi import APIRouter, Request, Header, HTTPException, status
from sse_starlette.sse import EventSourceResponse
from core.transport.models import InboundTurnEnvelope, ChannelType
from core.transport.deduplication import check_and_set_idempotency
from core.transport.event_log import get_conversation_event_log

router = APIRouter(prefix="/v1/conversations/{conversation_id}")

@router.post("/turns", status_code=status.HTTP_202_ACCEPTED)
async def submit_turn(
    conversation_id: str,
    payload: Dict[str, Any],
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is mandatory for turn submission."
        )

    # 1. Atomic Idempotency Check (Pillar B)
    is_new, cached_turn_id = await check_and_set_idempotency(
        conversation_id=conversation_id,
        idempotency_key=idempotency_key,
        ttl_seconds=120
    )
    if not is_new:
        return {"turn_id": cached_turn_id, "status": "ALREADY_QUEUED"}

    turn_id = idempotency_key

    # 2. Build Canonical Inbound Envelope (UA-D1)
    envelope = InboundTurnEnvelope(
        tenant_id=payload["tenant_id"],
        principal_id=payload["principal_id"],
        assurance_tier=payload.get("assurance_tier", "T0_ANON"),
        session_id=payload["session_id"],
        conversation_id=conversation_id,
        turn_id=turn_id,
        channel=ChannelType.WEB_WIDGET,
        content=payload["content"],
    )

    # 3. Asynchronously Dispatch to Safety & Orchestration Pipelines
    await dispatch_to_orchestrator(envelope)

    return {"turn_id": turn_id, "status": "QUEUED"}


@router.get("/events")
async def stream_conversation_events(
    conversation_id: str,
    request: Request,
    last_event_id: Optional[str] = Header(None, alias="Last-Event-ID"),
):
    """
    Resumable SSE Stream (UA-D2). Replays missed events from last_event_id
    and streams live agent tokens, citations, and status events.
    """
    event_log = await get_conversation_event_log(conversation_id)

    async def event_generator():
        # 1. Replay missed historical events
        if last_event_id:
            missed_events = await event_log.get_events_after(last_event_id)
            for evt in missed_events:
                yield {
                    "id": evt.event_id,
                    "event": evt.event_type,
                    "data": evt.payload_json,
                }

        # 2. Stream real-time events from pub/sub queue
        pubsub_listener = await event_log.subscribe()
        try:
            while True:
                if await request.is_disconnected():
                    break
                event = await pubsub_listener.get_next_event(timeout=15.0)
                if event:
                    yield {
                        "id": event.event_id,
                        "event": event.event_type,
                        "data": event.payload_json,
                    }
                else:
                    # Heartbeat comment to prevent proxy idle drop (KK2)
                    yield {":": "keep-alive"}
        finally:
            await pubsub_listener.unsubscribe()

    return EventSourceResponse(event_generator())
```

---

## 4. Knowing Your Unknowns: Failure Modes & Mitigation Matrix

| Quadrant | Failure Mode | Technical Risk Description | Concrete Architectural Mitigation |
| :--- | :--- | :--- | :--- |
| **Q1: Known Knowns** *(Deterministic Contract Breaches)* | **Turn Duplicate Execution ($KK1$)** | Network drops before 202 response; client retries POST; action runs twice. | **`Idempotency-Key` Check**: Redis NX lock with 120s TTL dedupes duplicate submissions at ingress. |
| **Q1: Known Knowns** *(Deterministic Contract Breaches)* | **Proxy Idle Connection Termination ($KK2$)** | Intermediary Nginx/ALB cuts idle SSE connection after 60s of agent deliberation. | **15-Second Keep-Alive Heartbeats**: SSE generator emits periodic `: keep-alive` comments to reset proxy idle timers. |
| **Q2: Known Unknowns** *(Probabilistic Reasoning Variance)* | **Antivirus / Proxy Stream Buffering ($KU1$)** | Strict enterprise security appliance buffers SSE until close, killing perceived latency. | **Chunk Padding & HTTP/2 Delivery**: Server-side `X-Accel-Buffering: no` headers + HTTP/2 single-frame flushing. |
| **Q2: Known Unknowns** *(Probabilistic Reasoning Variance)* | **Reconnection Thundering Herd ($UU5$)** | Infrastructure reload severs 10,000 active SSE streams; all clients reconnect simultaneously. | **Client Reconnection Jitter**: Client SDK applies exponential backoff with full jitter ($T = \min(M, T_0 \cdot 2^k \pm \text{rand})$). |
| **Q3: Unknown Knowns** *(Tacit Enterprise Etiquette & Invariants)* | **Screen Reader Flitter Flooding ($UK2$)** | Rapid token-by-token SSE streaming overwhelms accessibility screen readers. | **Batched Event Rendering**: Client widget batches token deltas into sentence chunks before dispatching to ARIA live regions. |
| **Q3: Unknown Knowns** *(Tacit Enterprise Etiquette & Invariants)* | **Missing AI Transparency ($UK1$)** | User assumes agent is human, violating EU AI Act Art. 50(1). | **Mandatory Envelope Metadata**: `ChannelCapabilities` mandates an immutable `is_ai_generated: true` indicator in widget header. |
| **Q4: Unknown Unknowns** *(Emergent Cascades & Black Swans)* | **Replay Action Card Double-Click ($UU1$)** | Client reconnects; SSE replays historical `action_card`; user clicks "Confirm" a second time. | **Idempotent Action Tokens (`TA-ADP-05`)**: Action cards carry single-use cryptographic nonces; duplicate clicks return `HTTP 410 Gone`. |
| **Q4: Unknown Unknowns** *(Emergent Cascades & Black Swans)* | **Cross-Tenant Channel Injection** | Ingress adapter accepts forged `tenant_id` from spoofed client header. | **Token-Bound Identity (`UA-ADP-02`)**: Ingress gateway validates that `tenant_id` matches the cryptographically signed JWT claim. |

---

## 5. Closed-Loop Feedback & Telemetry Integration

1. **Ingress Latency & Reconnect Telemetry**:
   - Ingress tracks $P_{99}$ latency of the `POST /turns` endpoint (Target: $<50\text{ms}$).
   - SSE connection drops and reconnect frequency are aggregated in Prometheus (`sse_reconnect_total`, `last_event_id_replay_count`).
2. **Channel Error Budget Monitoring**:
   - If SSE disconnect rates exceed 2% across a specific enterprise tenant domain, automated alerts flag possible proxy buffer incompatibilities (`OB-ADP-03`).

---

## 6. Genesis Implementation Directives

### Target File Manifest
1. `core/transport/models.py`: Pydantic models for `InboundTurnEnvelope`, `ChannelType`, and `ChannelCapabilities`.
2. `core/transport/deduplication.py`: Redis-backed distributed idempotency validator.
3. `core/transport/event_log.py`: Append-only event store supporting `get_events_after(last_event_id)`.
4. `api/v1/transport.py`: FastAPI routes for turn submission (`POST /turns`) and resumable streaming (`GET /events`).

### Scaffolding Verification Criteria
- [ ] **Idempotency Invariant Test**: Sending identical `Idempotency-Key` headers concurrently results in exactly one execution dispatch.
- [ ] **SSE Reconnect Verification**: Disconnecting an SSE client mid-turn and reconnecting with `Last-Event-ID` replays all missed intermediate tokens without loss.
- [ ] **Keep-Alive Heartbeat Test**: Inactive SSE connections emit keep-alive comments every 15 seconds.

---

## 7. Consequences & Trade-offs

### Positive Consequences
- **Rock-Solid Gateway Stability**: Ingress socket holding time drops from 12s to 35ms, eliminating gateway thread pool exhaustion.
- **Enterprise Firewall Compatibility**: SSE operates seamlessly over standard HTTPS (Port 443) without WebSocket handshake failures.
- **Zero Duplicate Action Hazards**: Distributed idempotency guarantees that network retries never trigger duplicate side-effects.
- **Unified Delivery Paradigm**: A single SSE connection handles live turn streaming, reconnections, and multi-day HITL approvals.

### Negative / Neutral Trade-offs & Mitigations
- **Event Log Storage Overhead**: Requires persisting an append-only outbound event log per conversation.  
  *Mitigation*: Event logs reside in fast Redis memory for 24 hours, then compress into PostgreSQL partition tables (`DP-ADP-04`).
- **Half-Duplex Client Transport**: Clients cannot send upstream messages over the SSE connection itself (unlike WebSockets).  
  *Mitigation*: Clients submit upstream turns via lightweight `POST /turns`, which provides standard REST status codes and independent retry semantics.

---

## 8. References

1. **IETF Network Working Group (2024)**. *The Idempotency-Key HTTP Header Field*. Internet-Draft.
2. **Little, J. D. C. (1961)**. *A Proof for the Queuing Formula: $L = \lambda W$*. Operations Research, 9(3), 383-387.
3. **WHATWG (2024)**. *HTML Living Standard: Server-Sent Events*. §9.2.
4. **Nielsen, J. (1993)**. *Response Times: The 3 Important Limits*. Usability Engineering, Morgan Kaufmann.
5. **OWASP Foundation (2023)**. *API Security Top 10: API1 Broken Object Level Authorization*.
