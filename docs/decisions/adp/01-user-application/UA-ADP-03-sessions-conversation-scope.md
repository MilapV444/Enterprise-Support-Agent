# UA-ADP-03: Sessions, Conversations & Case Scoping (Three-Level Entity Hierarchy & NIST AAL2 Timeouts)

- **Status**: Accepted & Confirmed
- **Date**: 2026-09-23 *(Confirmed: 2026-09-26 via MS-D1 Entity Alignment)*
- **Deciders**: Architecture Team, Lead Systems Architect, Data Governance Core
- **Component**: `[1] User & Application` (`Component [ 1 ]`)
- **Reasoning Source**: `checkpoint.md` §5 · Diagram: `LLD - [1] User & Application`
- **Decisions Covered**:
  - `UA-D5`: Session Scoping — Three-Level Model: Transport Session $\to$ Conversation Thread $\to$ Case Record (`MS-D1`)
  - `UA-D6`: Session Timeouts — Fixed 30-Minute Idle / 12-Hour Absolute Session Lifetime (NIST SP 800-63B AAL2)
  - `UA-Q3`: Idle-Timer Reset Policy — Any Authenticated Request (including open SSE streams) Resets the Idle Timer
- **Related Architectural Decision Points**:
  - [`MS-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#ms-adp-01--conversation--case-model): Conversation & Case Model *(Case Association & Pinned Memory)*
  - [`RP-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#rp-adp-01--admission-control): Admission Control *(Concurrent Session Limits & Stream Quotas)*
  - [`UA-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/01-user-application/UA-ADP-01-channels-api-transport.md): Channels & API Transport *(Resumable SSE Connections & Replay Logs)*

---

## 1. Context & Problem Statement

Conversational systems frequently conflate three distinct operational concepts under the vague moniker of "session":
1. **The Network / Transport Connection**: The physical HTTP/2 or SSE socket binding the browser to the API gateway.
2. **The Conversational Dialogue Thread**: The sequence of turns, clarifications, and agent reasoning traces addressing an active line of inquiry.
3. **The Business Problem / Case Record**: The persistent enterprise support entity (e.g., Zendesk ticket, Salesforce Case, Jira issue) tracking the business resolution, SLA timers, financial adjustments, and human escalations.

### The Scope Collapse Vulnerability
When systems collapse these three layers into a single entity, severe architectural failures emerge:
- **Premature State Destruction**: When a transport session times out after 30 minutes of user inactivity, naive systems delete the entire dialogue history. If the customer returns 45 minutes later, their context is lost, forcing them to repeat their problem from scratch (high Customer Effort Score).
- **Broken Object Level Authorization (BOLA / IDOR, OWASP API1:2023)**: If session and conversation identifiers are enumerable, unpartitioned, or decoupled from tenant identity, an authenticated user can swap `conversation_id` in the API URL and inspect the private dialogue of another customer or tenant ($KK4$).
- **Deadlock on Asynchronous Human Outcomes**: If an agent escalates a turn to a human supervisor (HITL) who reviews the case 4 hours later, the original transport session has expired. If delivery requires an active session, the customer never receives the approved resolution.

### The Core Architectural Question
> **What is the formal lifecycle, boundary, and relationship between a session, a conversation, and a case—and what strict inactivity and absolute timeout rules govern them across security tiers?**

---

## 2. Decision Framework & Theoretical Formulation

We structure our scoping architecture upon three theoretical pillars: **Hierarchical State Encapsulation**, **OWASP Broken Object Level Authorization (BOLA) Defense-in-Depth**, and **NIST SP 800-63B Session Management Protocols**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             SCOPING THEORETICAL PILLARS                                          │
├────────────────────────────────┬────────────────────────────────┬────────────────────────────────┤
│   Pillar A: Hierarchical State │   Pillar B: Dual-Key BOLA      │   Pillar C: NIST SP 800-63B    │
│   Decomposition Hierarchy      │   Authorization & Cryptography │   Inactivity & Absolute Caps   │
│                                │                                │                                │
│   • Transport Session S_t      │   • Non-enumerable UUIDv4      │   • T_idle ≤ 30 Minutes        │
│   • Conversation Thread C_t    │   • Composite key validation   │   • T_absolute ≤ 12 Hours      │
│   • Persistent Case Record Ω   │   • Verify(tenant ∧ principal) │   • Delivery decoupled from    │
│   • Nested lifecycles S ⊂ C ⊂ Ω│   • Zero cross-tenant leakage  │     live session (inbox model) │
└────────────────────────────────┴────────────────────────────────┴────────────────────────────────┘
```

---

### Pillar A: Hierarchical State Decomposition (Session $\to$ Conversation $\to$ Case)

To resolve the scope collapse problem, we establish a formal three-tier entity hierarchy (`MS-D1`, `UA-D5`):

$$\text{Architecture Hierarchy: } \quad \mathcal{S}_{\text{Transport Session}} \quad \subset \quad \mathcal{C}_{\text{Conversation Thread}} \quad \subset \quad \Omega_{\text{Case Record}}$$

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ CASE RECORD Ω (Multi-Day/Week Persistent Business Entity: e.g. CASE-9082)                         │
│                                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ CONVERSATION THREAD C_1 (Turn-by-turn Dialogue History: 24h - 14 Days)                   │   │
│   │                                                                                          │   │
│   │   ┌───────────────────────────────────┐        ┌───────────────────────────────────┐     │   │
│   │   │ TRANSPORT SESSION S_1             │        │ TRANSPORT SESSION S_2 (Reconnected)│     │   │
│   │   │ • Ephemeral browser window        │        │ • New browser tab / device        │     │   │
│   │   │ • 30 min idle / 12 h max          │        │ • Re-attaches to C_1 with T2 SSO  │     │   │
│   │   └───────────────────────────────────┘        └───────────────────────────────────┘     │   │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ CONVERSATION THREAD C_2 (Follow-up Turn on same Case days later)                         │   │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

1. **Transport Session ($\mathcal{S}$)**:
   - Lifespan: Minutes to hours ($\le 12\text{ hours}$).
   - Responsibility: Manages active HTTP/2 transport sockets, authentication token bindings, and in-memory rate limits.
   - Ownership: Client browser instance ↔ Gateway connection edge.
2. **Conversation Thread ($\mathcal{C}$)**:
   - Lifespan: Hours to days (persists across multiple transport sessions).
   - Responsibility: Chronological sequence of turns, Baddeley context window assembly, and LangGraph PostgreSQL state checkpoints (`MS-D8`).
   - Ownership: Agent Orchestration Core & Working Memory.
3. **Case Record ($\Omega$)**:
   - Lifespan: Days to weeks (until ticket resolution).
   - Responsibility: Legal audit record, SLA timers, Temporal distributed saga state, and CRM/ERP synchronization.
   - Ownership: Enterprise System of Record (CRM / Zendesk) & Temporal Saga Coordinator.

---

### Pillar B: Dual-Key BOLA Authorization & Cryptographic Invariants

To completely eliminate **Broken Object Level Authorization ($KK4$)**, entity access is governed by strict cryptographic non-enumerable tokens and composite validation checks.

All identifiers are generated via cryptographically secure pseudo-random number generators (CSPRNG) conforming to **UUIDv4**:

$$P(\text{UUIDv4 Collision}) \approx \frac{n^2}{2^{123}} \approx 0 \quad (\text{Non-Enumerable Space})$$

#### The Dual-Key Validation Invariant
Every request to inspect, stream, or append to a conversation $\mathcal{C}$ must satisfy:

$$\text{Authorize}(\mathcal{C}, \text{Context}) = \begin{cases}
\text{ALLOW} & \text{if } \mathcal{C}.\text{tenant\_id} == \text{Context}.\text{tenant\_id} \;\land\; \mathcal{C}.\text{principal\_id} == \text{Context}.\text{principal\_id} \\
\text{DENY} & \text{otherwise} \implies \text{Emit HTTP 404 (Masking Existence)}
\end{cases}$$

An authenticated user cannot read transcripts belonging to another user—even within the same enterprise tenant—unless they possess an explicit supervisor delegation role.

---

### Pillar C: NIST SP 800-63B Inactivity Limits & Activity Definition (`UA-D6`, `UA-Q3`)

Following **NIST Special Publication 800-63B §7.2 (AAL2 Session Management)**, enterprise sessions must enforce both idle and absolute expiration ceilings:

$$\begin{aligned}
T_{\text{idle}} &\le 30\text{ minutes} \quad &&(\text{Inactivity Timeout Ceiling}) \\
T_{\text{absolute}} &\le 12\text{ hours} \quad &&(\text{Hard Absolute Session Lifetime Ceiling})
\end{aligned}$$

#### The Activity Reset Policy (`UA-Q3 -> ii`)
What constitutes "activity" that resets the 30-minute idle timer?
- **Adopted Policy**: **Any authenticated HTTP request, including open SSE streams emitting keep-alive heartbeats, resets the 30-minute idle timer**.
- **Consequence**: An open browser tab with an active SSE connection keeps the transport session alive **up to the 12-hour absolute cap**, providing a seamless user experience without unexpected disconnects.
- **Safety Ceiling**: At $t = 12\text{ hours}$, the transport session terminates unconditionally, forcing token re-evaluation and preventing indefinite kiosk exposure ($UK5$).

---

## 3. Decision Rules & System Architecture

### Architectural Decision

1. **Three-Tier Entity Model (`UA-D5` / `MS-D1`)**:
   - Systems strictly isolate `session_id`, `conversation_id`, and `case_id`.
   - A conversation outlives the session; a returning user can authenticate and resume an existing conversation thread.
   - Multiple conversations can link to a single durable case.
2. **Fixed Timeouts (`UA-D6`)**:
   - Enforce 30-minute idle / 12-hour absolute lifetime across all identity tiers.
   - Delivery of late/deferred outcomes **must not depend on a live session**; outcomes are persisted to the conversation event log and retrieved via the user's inbox on next load (`UA-Q2`).
3. **Inclusive Activity Resets (`UA-Q3`)**:
   - Open SSE streams reset the idle timer, bounding open tabs to the 12-hour absolute cap.

---

### Concrete Genesis Implementation Contracts

#### 1. Entity Scoping Schema (`core/session/models.py`)

```python
from datetime import datetime, timedelta
from typing import Optional, List
from pydantic import BaseModel, Field

class TransportSession(BaseModel):
    session_id: str
    tenant_id: str
    principal_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity_at: datetime = Field(default_factory=datetime.utcnow)
    idle_timeout_seconds: int = 1800   # 30 Minutes (NIST AAL2)
    absolute_timeout_seconds: int = 43200  # 12 Hours (NIST AAL2)
    is_active: bool = True

    def is_expired(self, current_time: datetime) -> bool:
        idle_elapsed = (current_time - self.last_activity_at).total_seconds()
        absolute_elapsed = (current_time - self.created_at).total_seconds()
        return (idle_elapsed > self.idle_timeout_seconds) or (absolute_elapsed > self.absolute_timeout_seconds)

    def record_activity(self, current_time: datetime) -> None:
        """UA-Q3(ii): Any authenticated request or open stream resets the idle timer."""
        if not self.is_expired(current_time):
            self.last_activity_at = current_time

class ConversationScope(BaseModel):
    conversation_id: str
    tenant_id: str
    principal_id: str
    case_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_turn_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "ACTIVE"  # ACTIVE, IDLE, CLOSED

class CaseScope(BaseModel):
    case_id: str
    tenant_id: str
    external_crm_ref: Optional[str] = None
    title: str
    priority: str = "NORMAL"
    sla_due_at: Optional[datetime] = None
    is_resolved: bool = False
```

#### 2. Session Lifecycle Middleware (`core/session/middleware.py`)

```python
from datetime import datetime
from fastapi import Request, HTTPException, status
from core.session.models import TransportSession
from core.session.repository import SessionRepository

class SessionValidationMiddleware:
    def __init__(self, session_repo: SessionRepository):
        self.session_repo = session_repo

    async def validate_session(self, request: Request, session_id: str, tenant_id: str, principal_id: str) -> TransportSession:
        now = datetime.utcnow()
        session = await self.session_repo.get_session(session_id)

        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

        # Dual-Key BOLA Defense (Pillar B)
        if session.tenant_id != tenant_id or session.principal_id != principal_id:
            # Emit 404 to mask existence
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

        # Timeout Check (Pillar C)
        if session.is_expired(now):
            await self.session_repo.deactivate_session(session_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired due to inactivity or 12-hour policy. Please re-authenticate."
            )

        # Record Activity (UA-Q3: open SSE streams keep session alive)
        session.record_activity(now)
        await self.session_repo.update_activity(session_id, now)

        return session
```

---

## 4. Knowing Your Unknowns: Failure Modes & Mitigation Matrix

| Quadrant | Failure Mode | Technical Risk Description | Concrete Architectural Mitigation |
| :--- | :--- | :--- | :--- |
| **Q1: Known Knowns** *(Deterministic Contract Breaches)* | **BOLA Cross-Tenant Leak ($KK4$)** | User manipulates `conversation_id` in URL to read transcripts of other tenants. | **Dual-Key Invariant Check**: Gateway verifies `(tenant_id, principal_id)` matches token; returns 404 on mismatch. |
| **Q1: Known Knowns** *(Deterministic Contract Breaches)* | **Session Lifetime Desync ($KK3$)** | Inactivity timeout cuts session while background Temporal workflow is running. | **Scope Decoupling (`MS-D1`)**: Workflow attaches to durable `case_id`; delivery routes to user inbox independently of session. |
| **Q2: Known Unknowns** *(Probabilistic Reasoning Variance)* | **Gateway Connection Fatigue ($KU3$)** | Keeping 10,000 tabs open for 12h under `UA-Q3(ii)` exhausts Redis socket descriptors. | **Stateless SSE Ping**: Heartbeats do not hit Redis write path; in-memory lease renewal runs in local gateway RAM. |
| **Q2: Known Unknowns** *(Probabilistic Reasoning Variance)* | **Abandoned Case Sprawl** | Thousands of conversations never resolve, leaving cases in `PENDING` indefinitely. | **24-Hour Conversation Idle Closer (`MS-D5`)**: Conversations idle for 24 hours auto-close and extract persistent facts. |
| **Q3: Unknown Knowns** *(Tacit Enterprise Etiquette & Invariants)* | **Public Kiosk Exposure ($UK5$)** | A user leaves a browser open at a library kiosk; 12h session exposes history to next visitor. | **Hard 12-Hour Absolute Cap**: Sessions terminate strictly at 12 hours; high-risk actions prompt for re-authentication. |
| **Q3: Unknown Knowns** *(Tacit Enterprise Etiquette & Invariants)* | **Detached Deferred Outcome ($UK4$)** | A deferred outcome appears in the user inbox hours later without context of the question. | **Structured Turn Envelope (`UA-D7`)**: Deferred inbox items carry the originating customer query string in metadata. |
| **Q4: Unknown Unknowns** *(Emergent Cascades & Black Swans)* | **Replay Thundering Herd ($UU5$)** | Node deployment drops 5,000 12h-alive SSE connections; simultaneous reconnections crash DB. | **Jittered SSE Backoff & Rate Limits (`RP-ADP-01`)**: Reconnection algorithm applies full random jitter between 100ms and 5000ms. |
| **Q4: Unknown Unknowns** *(Emergent Cascades & Black Swans)* | **Cross-Session Context Injection** | A user starts a new session on a shared computer; browser cache injects previous user's turns. | **LocalStorage Cryptographic Wipe**: Session termination invokes client-side `indexedDB.deleteDatabase()` clearing cached turns. |

---

## 5. Closed-Loop Feedback & Telemetry Integration

1. **Session Lifetime & Inactivity Distribution**:
   - Prometheus gauges track active concurrent sessions (`active_sessions_count`, `active_sse_streams_count`).
   - Distribution histograms measure session durations ($P_{50} \approx 25\text{m}$, $P_{95} \approx 4\text{h}$, $P_{99} \approx 11.8\text{h}$).
2. **BOLA Security Violation Counter**:
   - Any attempt to access a conversation with a mismatched `tenant_id` or `principal_id` fires a critical security event (`SecurityBOLAAttemptEvent`) to the SIEM platform.

---

## 6. Genesis Implementation Directives

### Target File Manifest
1. `core/session/models.py`: Pydantic schemas for `TransportSession`, `ConversationScope`, and `CaseScope`.
2. `core/session/middleware.py`: FastAPI security middleware enforcing Dual-Key BOLA checks and 30m/12h timeouts.
3. `core/session/repository.py`: Redis/PostgreSQL storage layer for session activity leases and conversation mappings.

### Scaffolding Verification Criteria
- [ ] **Dual-Key BOLA Test**: Requesting a valid `conversation_id` with an incorrect `principal_id` token returns `HTTP 404 Not Found`.
- [ ] **Idle Timeout Invariant**: Inactive session returns `HTTP 401 Unauthorized` exactly at 30 minutes and 1 second.
- [ ] **Open SSE Reset Test**: Active SSE connection reset lease keeps session alive beyond 30 minutes, but cuts off at exactly 12 hours.

---

## 7. Consequences & Trade-offs

### Positive Consequences
- **Total Elimination of BOLA Vulnerabilities**: Multi-tenant isolation is enforced at the transport and database query levels.
- **Superior Customer Experience**: Conversations persist across browser restarts, allowing users to return without losing context.
- **NIST AAL2 Statutory Compliance**: Meets federal and enterprise security requirements for session management.
- **Resilient Deferred Delivery**: Multi-day approvals reach customers seamlessly through the conversation inbox model.

### Negative / Neutral Trade-offs & Mitigations
- **Open SSE Resource Consumption**: Keeping open SSE connections for up to 12 hours consumes gateway file descriptors.  
  *Mitigation*: Deploy lightweight async ASGI reverse proxies (Envoy / Traefik) capable of maintaining 50,000+ idle SSE sockets with minimal RAM.
- **Kiosk Exposure Window**: A shared device remains open until the 12-hour mark if the tab is left open.  
  *Mitigation*: Provide an explicit "Log Out & Clear Device" button that purges session leases immediately.

---

## 8. References

1. **NIST (2020)**. *Digital Identity Guidelines: Authentication and Lifecycle Management*. NIST Special Publication 800-63B.
2. **OWASP Foundation (2023)**. *API Security Top 10: API1 Broken Object Level Authorization*.
3. **OWASP Foundation (2021)**. *Application Security Verification Standard (ASVS) 4.0: V3 Session Management*.
4. **RFC 4122 (2005)**. *A Universally Unique IDentifier (UUID) URN Namespace*. Internet Engineering Task Force.
