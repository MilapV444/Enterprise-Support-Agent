# Enterprise Support Agent: Architectural Decision Checkpoint

> **Status:** ✅ ACTIVE & CHECKPOINTED (Component [ 5 ] Finalized)  
> **Component Under Review:** Component [ 5 ] — Agent Orchestration Core & Runtime  
> **Genesis Readiness:** READY FOR SCAFFOLDING (Initial Specifications Checkpointed)  
> **Reference Master Report:** [`Enterprise AI Customer Support Agent Architecture - Formatted Master Report.md`](<./Enterprise AI Customer Support Agent Architecture - Formatted Master Report.md>)  
> **Visual Whiteboard Canvas:** [`architecture.tldr`](./architecture.tldr) (Page 2: `LLD - Agent Orchestration & Planning Core`)  
> **Component Loop (thoughts.md order, excl. Orchestration):** [1/15] User & Application — ✅ MATERIALIZED (steps 1–11; page `LLD - [1] User & Application`; page-1 pointer decision pending)

---

## 1. Executive Purpose & Genesis Integration

This checkpoint document records all architectural decisions, trade-off selections, and design rationales across the enterprise agent lifecycle. 

When initializing the **Genesis** code generation agent, this file serves as the definitive source of architectural truth:
1. Every component will adhere strictly to the options chosen herein.
2. No assumptions or unilateral framework defaults will be introduced without explicit checkpointing.
3. Every decision maps directly to engineering constraints, class hierarchies, and execution contracts.

---

## 2. Component [ 5 ]: Agent Orchestration Core & Runtime

The Orchestration Core is the central cognitive control plane. It decomposes customer intent, governs state transitions, compiles context windows, dispatches tools, and recovers from runtime exceptions.

Below are the finalized **Architectural Decisions** established for Component [ 5 ]:

---

### ADP-01: Planning & Deliberative Cognition Paradigm
* **Selected Architecture:** **Option C — Hybrid Dual-Process Statechart (Deterministic FSM + Scoped ReAct)**
* **Literature Foundations:**
  * Dual-Process Theory (Stanovich & West, 2000; Kahneman, 2011)
  * Deterministic Reducer Transitions: $S_{t+1} = \text{Reducer}(S_t, \Delta_t)$
  * Localized ReAct Trajectory: $\tau_t = (o_0, r_0, a_0, \dots)$ (Yao et al., 2023)
* **Operational Rationale:**
  * Enterprise customer support cannot tolerate open-loop hallucination or non-deterministic branching on regulatory, billing, or security operations (e.g., initiating refunds, resetting credentials, tenant migrations).
  * High-risk operations follow deterministic statechart reducers with strict pre/post-condition invariants.
  * Generative ReAct and Plan-and-Solve reasoning is strictly scoped *within* bounded edge nodes for open-ended diagnostic steps and log analysis.
* **Genesis Directives:**
  * Implement `core/orchestrator/statechart.py` using `langgraph.graph.StateGraph`.
  * Define explicit state enums (`INGESTED`, `TRIAGED`, `COLLECTING_PARAMS`, `EXECUTING_SOP`, `DELIBERATING`, `AWAITING_APPROVAL`, `RESOLVED`).
  * Ensure high-risk transitions are hardcoded code edges, while open-ended tasks route through deliberative subgraphs.

---

### ADP-02: Workflow Execution & Durability Substrate
* **Selected Architecture:** **Option C — Two-Tier Hybrid (Temporal.io Outer Saga + LangGraph Inner Cognitive Loop)**
* **Literature Foundations:**
  * Distributed Saga Patterns & Compensating Transactions (Garcia-Molina & Salem, 1987)
  * Multi-tier Durable Execution (Temporal.io State Machine)
* **Operational Rationale:**
  * Contact center workflows often span multiple hours or days (e.g., awaiting customer reply, human specialist review, tier-3 engineering escalations). In-memory or simple database polling is vulnerable to node crashes and deploy restarts.
  * **Temporal.io** guarantees event-sourced execution replay, crash durability, and reliable multi-day timers for ticket lifecycles and human escalation queues.
  * **LangGraph** runs inside Temporal Activity workers, providing sub-second execution velocity for rapid, multi-turn LLM reasoning.
* **Genesis Directives:**
  * Implement `workflows/ticket_lifecycle_workflow.py` (Temporal workflow definition for ticket SLA, timeout timers, and human signals).
  * Implement `activities/cognitive_reasoning_activity.py` (LangGraph invocation wrapper with thread snapshot commits).

---

### ADP-03: Working Memory & Context Engineering Strategy
* **Selected Architecture:** **Option C — Tripartite Structured Slot Allocator**
* **Literature Foundations:**
  * Baddeley Multicomponent Working Memory Model (Baddeley, 2000)
  * Mitigating "Lost in the Middle" Attention Degradation (Liu et al., 2023)
* **Operational Rationale:**
  * Naive FIFO turn buffers suffer from the "context cliff" (dropping earliest user constraints) or token bloat.
  * Allocating explicit token budget quotas prevents prompt dilution and guarantees room for high-precision retrieval:
    - **15%**: Immutable System Persona, Role Boundaries, and Hard Safety Invariants.
    - **15%**: Customer Identity & Chronic Account Knowledge Graph (extracted facts).
    - **35%**: Grounded RAG Knowledge Chunks (ColBERT MaxSim + BM25 ranked passages).
    - **25%**: Chronological Dialogue Buffer (verbatim recent turns).
    - **10%**: Ephemeral Scratchpad / Working Memory Buffer for intermediate plan thoughts.
* **Genesis Directives:**
  * Implement `core/context/assembler.py` with typed Pydantic slot models: `ContextEnvelope`, `SystemSlot`, `ProfileSlot`, `RAGSlot`, `DialogueSlot`, and `ScratchpadSlot`.
  * Enforce dynamic token counting with `tiktoken` and automatic compaction when budget bounds are approached.

---

### ADP-04: Metacognitive Error Recovery & Deliberative Replanning
* **Selected Architecture:** **Option C — Dual-Process Circuit Breaker (Reflexion with Max 2 Trials + HITL Tripwire)**
* **Literature Foundations:**
  * Reflexion Verbal Reinforcement (Shinn et al., 2023): $c_t = \text{LLM\_reflect}(\tau_t, S_t, \Omega)$
  * High-Reliability Organizing (HRO) & Preoccupation with Failure (Weick & Sutcliffe, 2007)
* **Operational Rationale:**
  * Pure autonomous reflection loops risk "hallucination spiraling" (the agent rationalizes errors and repeatedly retries incorrect operations).
  * Conversely, a purely rigid fallback ladder fails to recover from minor syntactic errors (e.g. malformed JSON parameters or transient HTTP 503 retries).
  * Dual-Process Circuit Breaker gives the agent **one to two trials** to self-diagnose and correct tool invocation errors via verbal critique. If the failure persists on trial 3, the circuit breaker trips immediately, packaging a diagnostic state bundle and escalating to a Human Specialist (HITL).
* **Genesis Directives:**
  * Implement `core/recovery/circuit_breaker.py` with `StepCeilingGuard(max_steps=4)` and `TrialCounter(max_reflexion=2)`.
  * Emit structured diagnostic packets (`IncidentDiagnosticPacket`) containing the full trajectory $\tau_t$ upon circuit trip.

---

## 3. Genesis Architectural Checkpoint Log

| Decision ID | Component | Title | Selected Option | Key Rationale & Constraints | Date | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **ADP-01** | Agent Runtime | Planning Paradigm | **Option C: Hybrid Dual-Process Statechart** | Deterministic LangGraph FSM for compliance/SOPs + scoped ReAct in edge nodes. | 2026-09-11 | ✅ CONFIRMED |
| **ADP-02** | Agent Runtime | Workflow Durability | **Option C: Two-Tier Hybrid (Temporal + LangGraph)** | Temporal manages multi-day ticket sagas & HITL; LangGraph runs inner cognitive turns. | 2026-09-11 | ✅ CONFIRMED |
| **ADP-03** | Agent Runtime | Context Engineering | **Option C: Tripartite Structured Slot Allocator** | Bounded token quotas: System (15%), Profile (15%), RAG (35%), Chat (25%), Scratchpad (10%). | 2026-09-11 | ✅ CONFIRMED |
| **ADP-04** | Agent Runtime | Error Recovery & Replanning | **Option C: Dual-Process Circuit Breaker** | Max 2 Reflexion critique trials; trips immediately to HITL on repeated failure. | 2026-09-11 | ✅ CONFIRMED |
| **UA-D1** | User & Application | Channels | **Web-only v1** | Channel-agnostic envelope keeps later adapters additive. | 2026-09-23 | ✅ CONFIRMED |
| **UA-D2** | User & Application | API transport | **Decoupled POST 202 + resumable SSE** | One path for live, reconnect and deferred (HITL) delivery; idempotent submit. | 2026-09-23 | ✅ CONFIRMED |
| **UA-D3** | User & Application | Identity assurance | **Tiered T0 anon → T1 OTP → T2 SSO + step-up** | Low friction for FAQs; account actions behind real identity. | 2026-09-23 | ✅ CONFIRMED |
| **UA-D4** | User & Application | Downstream identity | **RFC 8693 on-behalf-of tokens (`sub` + `act`)** | T0 gets a minimal read-only token (UA-Q1 → ii); T1/T2 normal on-behalf-of tokens. | 2026-09-23 | ✅ CONFIRMED – conditional |
| **UA-D9** | User & Application | Token validity | **User access token valid 24 h** | Outlives the 12 h session cap, which fixes KK3's expiry variant; revocation and theft window remain owned. | 2026-09-23 | ✅ CONFIRMED |
| **UA-Q2** | User & Application | Deferred delivery | **Inbox only (no email notification in v1)** | Accepted risk: users who never return miss outcomes. | 2026-09-23 | ✅ CONFIRMED |
| **UA-Q3** | User & Application | Idle-timer activity | **Any authenticated request incl. open SSE** | Open tab keeps session to the 12 h cap; accepted (KK3/UK5/UU5). | 2026-09-23 | ✅ CONFIRMED |
| **UA-D5** | User & Application | Session scoping | — | Revisit at Comp. 4 / 13. | 2026-09-23 | 🔵 OPEN |
| **UA-D6** | User & Application | Session timeouts | **Fixed 30 min idle / 12 h absolute** | NIST AAL2; delivery must not depend on a live session. | 2026-09-23 | ✅ CONFIRMED |
| **UA-D7** | User & Application | Response contract | **Typed event envelope** | Citations and action cards are first-class; channel-degradable. | 2026-09-23 | ✅ CONFIRMED |
| **UA-D8** | User & Application | Stream vs. safety gate | — | Revisit after Comp. 7 / 9; likely experiment. | 2026-09-23 | 🔵 OPEN |

---

## 4. Genesis Codebase Mapping (Pre-Execution Blueprint)

When Genesis is triggered, the following module scaffolding will be instantiated:

```
src/
├── core/
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   ├── statechart.py        # LangGraph StateGraph, Node reducers, hardcoded FSM edges
│   │   ├── triage.py            # Layer 0 Acuity Classifier (ESI / MTS protocol)
│   │   └── planner.py           # Layer 2 Deliberative ReAct / Plan-and-Solve engine
│   ├── context/
│   │   ├── __init__.py
│   │   ├── assembler.py         # Tripartite slot budget allocator & token packing
│   │   └── models.py            # Pydantic schemas for ContextEnvelope and Slots
│   └── recovery/
│       ├── __init__.py
│       ├── circuit_breaker.py   # Anti-loop detector, StepCeilingGuard (N<=4)
│       └── reflexion.py         # Verbal self-critique generator (max 2 trials)
├── workflows/
│   ├── ticket_saga.py           # Temporal workflow for durable ticket lifecycle & HITL
│   └── activities.py            # Temporal activities invoking LangGraph cognitive turns
└── schemas/
    ├── state.py                 # Thread state schema S_t and Delta_t reducers
    └── diagnostic.py            # IncidentDiagnosticPacket for HITL escalation
```

---

## 5. Component Loop [1/15] — User & Application

> **Loop status:** ✅ Steps 1–11 complete · Page-1 duplicate: trim-to-pointer vs. leave-both awaiting user  
> **Decision ID prefix:** `UA-` (forks `UA-F#`, decisions `UA-D#`), which keeps these IDs apart from ADP-01..04  
> **Architecture mapping:** thoughts.md Component 1 ≈ architecture tiers `[1] User Channels` + `[2] API Gateway & Identity` + `[13/14] Response Delivery → User Client` (transport part only)

### 5.1 GROUND — Raw Material (not decisions)

**From the master report (thin for this component; it mainly positions ingress):**
* End-to-end lifecycle: `[Ingress & Edge Security] → [API Gateway & Identity] → [Input Guardrails & PII Masking]` … `[Response Delivery Engine] → [User UI]`.
* "PII redaction executes at the network edge before model ingestion" (Presidio, 15–30 ms, Network Ingress & Egress), so the ingress path must leave room for a synchronous redaction hop that **Safety (Comp. 7) owns**.
* Confidence gate (≥0.90 auto-send / 0.70–0.90 co-pilot / <0.70 warm handoff): the final response is only known *after* a full-draft evaluation. This conflicts with token streaming (see UA-F8).
* GDPR Art. 22 (human review right), EU AI Act (human-oversight logging), *Moffatt v. Air Canada* (2024): agent statements are binding corporate representations, so the delivered response is a **legal record** and must be persisted exactly as rendered.
* Dixon et al. (2010) Customer Effort Score: forced channel switching and repeating information are the top effort drivers, which argues for cross-channel continuity.
* Erlang A (Garnett, Mandelbaum & Reiman, 2002): impatient customers abandon, and a perceived wait counts as abandonment risk. SLA 80/20 applies.

**From general engineering practice / standards:**
* **Identity:** OAuth 2.0 (RFC 6749), OpenID Connect Core 1.0, JWT (RFC 7519) and the JWT access-token profile (RFC 9068), Token Introspection (RFC 7662), **Token Exchange / on-behalf-of (RFC 8693)**. NIST SP 800-63B Authenticator Assurance Levels (AAL1–3) with re-authentication and inactivity limits (rev.3: AAL2 ≤12 h / ≤30 min idle). Step-up authentication for high-risk actions.
* **Sessions:** OWASP ASVS v4 §V3 (session management), OWASP API Security Top 10 (2023) **API1 BOLA**: guessable `session_id`/`conversation_id` means cross-tenant transcript leakage.
* **Transport:** WebSocket (RFC 6455), Server-Sent Events (WHATWG HTML §9.2, with `Last-Event-ID` resume), HTTP semantics (RFC 9110), Problem Details (RFC 9457), 429 + `Retry-After` (RFC 6585), IETF draft *Idempotency-Key HTTP header*.
* **Channel platform contracts:** Slack Events API requires a 200 ack within **3 s** and otherwise retries (`X-Slack-Retry-Num`), with HMAC signing-secret verification. MS Bot Framework Activity schema + Teams Adaptive Cards. Twilio `X-Twilio-Signature`. Email threading via RFC 5322 `Message-ID`/`In-Reply-To`.
* **Event envelope:** CNCF CloudEvents 1.0 (canonical, transport-agnostic event metadata).
* **Perceived latency:** Miller (1968) / Nielsen (1993): 0.1 s / 1 s / 10 s response-time limits. Past about 1 s users need progress feedback, and past 10 s they lose the task.
* **Accessibility / disclosure:** WCAG 2.2 (ARIA live regions for streamed chat). EU AI Act Art. 50(1): users must be told they are interacting with an AI system.

### 5.2 DECOMPOSE

| Sub-component | Mechanic (what it does) |
| :--- | :--- |
| **Channels / UI** | Per-channel adapters (Web widget, Mobile, Slack, Teams, Email, later Voice). They verify platform signatures and translate native payloads to and from the canonical envelope. Each declares a capability descriptor (rich cards? streaming? max length?). |
| **API** | Public ingress contract: turn submission, delivery stream, attachment upload, error model (RFC 9457), idempotency keys, API versioning. |
| **Identity** | Establishes *who* (principal) and *which tenant*. Validates tokens, sets the assurance level, and mints the internal identity context that is handed downstream. |
| **Sessions** | Binds principal ↔ channel ↔ conversation thread. Covers session creation, resume, expiry, and non-enumerable IDs. Owns the *keys*, not the *content*. |
| **Request / Response** | Normalizes the inbound turn into a canonical request envelope. Accepts the final approved response envelope and renders and delivers it per channel (stream, push, or deferred). |

### 5.3 TRACE THE TRAJECTORY

**Flow A — Synchronous interactive turn (Web portal, Sarah @ acme-corp)**
1. **Channels/UI**: The widget sends the message with the OIDC access token plus a client-generated `turn_id` (idempotency).
2. **API**: Ingress validates size limits, content-type and API version, and dedupes on `Idempotency-Key`.
3. **Identity**: Verifies the JWT (signature, `exp`/`nbf` with clock-skew, `aud`, issuer), resolves `tenant_id`, `principal_id`, roles, and assurance level (AAL2 via SSO).
4. **Sessions**: Resolves or creates `session_id`, then checks that the session belongs to the principal *and* the tenant (BOLA guard). Attaches `conversation_id`.
5. **Request/Response (in)**: Builds the canonical `InboundTurnEnvelope {tenant, principal, assurance, session_id, conversation_id, turn_id, channel, channel_capabilities, content, attachment_refs, received_at}`.
   → **HANDOFF** to Safety (Comp. 7: PII masking + injection screening), then Orchestration (Comp. 2).
6. *(Out of scope: orchestration, retrieval, tools, confidence gate)*
7. **Request/Response (out)**: Receives the `OutboundResponseEnvelope` *after* the output guardrails and confidence gate have run. Renders per `channel_capabilities` and delivers over the open stream.
8. **Channels/UI**: Widget renders text, citations and action cards, and acknowledges receipt (`delivered` event).
   → **HANDOFF** to Data & Persistence (Comp. 8): the transcript *as rendered*, as a legal record.

**Flow B — Asynchronous channel + deferred delivery (Slack, or a HITL approval that resolves hours later)**
1. **Channels/UI**: The Slack adapter verifies the HMAC signature and returns **200 within 3 s** (it must not wait for the LLM).
2. **Identity**: Maps the Slack user to an enterprise principal (identity linking). An unlinked user drops to low assurance.
3. **Sessions**: The thread `ts` maps to `conversation_id`.
4. **Request/Response (in)**: Emits the same canonical envelope, so the downstream pipeline is identical to Flow A.
5. …the agent proposes `apply_credit_memo($12,400)` → Tools/HITL (Comp. 5/13) pause via a Temporal signal. **Not owned here.**
6. **Request/Response (out)**: Hours later the approved outcome arrives as an outbound event. The user is offline, so delivery goes out via the channel's **push** path (Slack `chat.postMessage` into the thread / email / web notification + inbox on next load).
7. Delivery receipt, or retry with backoff. If the preferred channel stays unreachable, fall back to email.

**Flow C — Session lifecycle (resume · step-up · channel switch · expiry)**
1. **Resume**: The browser reconnects with `Last-Event-ID`, and any missed events are replayed from the outbound log.
2. **Step-up**: A high-risk intent arrives (downstream classifies it, and Identity is *asked*). Identity issues an assurance challenge (re-auth / MFA). On success it raises the assurance level on the session, and the turn resumes.
3. **Channel switch**: Sarah continues by email. Whether this joins the same conversation depends on **UA-F5** (undecided).
4. **Expiry**: Idle / absolute timeout invalidates the session token. The conversation and case persist (owned by Memory/Data), and a new session can re-attach to them.

### 5.4 BOUNDARY

| | |
| :--- | :--- |
| **Receives (upstream)** | Raw end-user input from channel platforms (HTTP / WSS / webhooks / SMTP) + IdP tokens + platform signatures. **Downstream-return:** final, gated `OutboundResponseEnvelope` from Output Safety / Confidence Gate (Comp. 7/9/13); deferred outcome events from Orchestration workflows (Comp. 2). |
| **Hands off (downstream)** | Canonical `InboundTurnEnvelope` (identity-bound, session-bound, idempotent) → Safety (Comp. 7) → Orchestration (Comp. 2). Delivery receipts and rendered transcripts → Data & Persistence (Comp. 8), Observability (Comp. 10). |
| **Does NOT own** | PII redaction, injection/jailbreak detection, output guardrails (Comp. 7) · **Rate limiting** (Comp. 11 per thoughts.md) · Tool/action authorization and permissions (Comp. 5/7) · Conversation memory *content* and summarization (Comp. 4) · Workflow timers and durable waits (Comp. 2, Temporal) · Confidence gating (Comp. 9) · Escalation/handoff *decision* and human queues (Comp. 13, which Channels only render) · Model token generation (Comp. 2 Model Interaction) · Transcript storage (Comp. 8). |

### 5.5 SURFACE THE FORKS (undecided; awaiting user)

| Fork | Sub-component | Tension | Options | Status |
| :--- | :--- | :--- | :--- | :--- |
| **UA-F1** | Channels/UI | Build vs. buy channel adapters | (a) In-house adapters behind the canonical envelope · (b) Omnichannel platform (Bot Framework / Twilio Conversations) · (c) Web-only MVP, adapters later | ✅ (c) — see UA-D1 |
| **UA-F2** | API | Coupling of submit and delivery | (a) POST returns SSE stream per turn · (b) Persistent bidirectional WebSocket · (c) Decoupled: `POST /turns` → 202 + `turn_id`; a separate subscribable event stream (SSE, resumable) serves both live and deferred delivery | ✅ (c) — see UA-D2 |
| **UA-F3** | Identity | Who may talk to the agent | (a) Authenticated only (SSO/OIDC) · (b) Anonymous allowed for FAQ-only · (c) Tiered assurance: anonymous → verified (OTP) → authenticated, with step-up gating by action risk | ✅ (c) — see UA-D3 |
| **UA-F4** | Identity | What identity is propagated downstream | (a) Forward the user's token as-is · (b) Agent service account + user claims as context (confused-deputy risk) · (c) RFC 8693 token exchange: short-lived, audience-scoped on-behalf-of tokens carrying both `sub` (user) and `act` (agent) | ✅ (c) conditional — see UA-D4 |
| **UA-F5** | Sessions | Session ≠ conversation ≠ case? | (a) Channel-bound sessions, each its own conversation · (b) One cross-channel conversation per principal · (c) Three-level model: transport *session* → *conversation* thread → durable *case* ID; channels link to a case | 🔵 OPEN — see UA-D5 |
| **UA-F6** | Sessions | Timeout policy | (a) Fixed idle/absolute (e.g. 30 min / 12 h, per NIST AAL2) · (b) Per-channel (web short, Slack/email long-lived) · (c) Tied to assurance level + tenant config | ✅ (a) — see UA-D6 |
| **UA-F7** | Request/Response | Response contract | (a) Markdown text stream · (b) Typed event envelope (`text_delta`, `citation`, `action_card`, `status`, `handoff`, `final`) that each adapter degrades to its capabilities | ✅ (b) — see UA-D7 |
| **UA-F8** | Request/Response | **Streaming latency vs. output safety gate** | (a) Buffer the full answer until the gate passes (safe, TTFT = full generation + gate) · (b) Stream raw tokens and retract on failure (fast, but unsafe text was already seen) · (c) Stream immediate `status` events ("Checking your invoice…") while the answer is buffered, then send the gated answer · (d) Sentence-chunked streaming through an incremental guard | 🔵 OPEN — see UA-D8 |

### 5.6 RESOLVE — Step 6 (user decisions, 2026-09-23)

| ID | Sub-component | Decision | Status | Reasoning captured |
| :--- | :--- | :--- | :--- | :--- |
| **UA-D1** | Channels/UI | **Web widget is the only channel in v1.** The canonical envelope stays channel-agnostic, so Slack/Teams/Email adapters can be added later without changing downstream contracts. | ✅ CONFIRMED | Smallest surface for v1: one set of signature/ack contracts and one renderer. Flow B's Slack leg (3 s ack, identity linking) is **out of v1 scope**. Flow B's *deferred delivery* leg still applies to web (HITL resolves while the user is offline). |
| **UA-D2** | API | **Decoupled submit/receive.** `POST /v1/conversations/{id}/turns` (Idempotency-Key = `turn_id`) → `202 {turn_id}`. `GET /v1/conversations/{id}/events` is a resumable SSE stream (`Last-Event-ID` replay from the outbound event log). | ✅ CONFIRMED | One delivery path serves live answers, reconnects and HITL-resolved answers that arrive hours later (Flow B/C). Client retries of the POST are deduplicated. SSE runs over plain HTTP/2 and passes corporate proxies more reliably than WebSocket. Consequence: server-side outbound event log per conversation (storage owned by Comp. 8). |
| **UA-D3** | Identity | **Tiered assurance:** `T0 anonymous` → `T1 verified` (one-time code to email/phone on file) → `T2 authenticated` (enterprise SSO/OIDC). A higher tier is required (step-up) when downstream classifies an intent/action as needing it. | ✅ CONFIRMED | Lets FAQ-type traffic be served without login friction (CES) while keeping account actions behind real identity. Identity *issues* the step-up challenge. *Which* actions need which tier is a policy owned by Safety/Tools (Comp. 7/5); Identity only enforces the tier. |
| **UA-D4** | Identity | **RFC 8693 token exchange:** short-lived, audience-scoped on-behalf-of tokens with `sub` = user, `act` = agent. **Tier rule (UA-Q1 → ii):** T0 anonymous gets a minimal token with `sub` = anonymous session ID and a read-only audience only. T1/T2 get normal on-behalf-of tokens scoped to their tier. | ✅ CONFIRMED – conditional (rule stated) | Every downstream call carries a token that names both the principal and the agent, including anonymous traffic, so audit is uniform. **Which tools sit in the T0 read-only audience is owned by Tools/Safety (Comp. 5/7)**; Identity only mints the token. |
| **UA-D5** | Sessions | Session / conversation / case scoping | 🔵 OPEN | **Deferred on purpose. Revisit during Comp. 4 (Memory & State) and Comp. 13 (Human-in-the-Loop)**, which key their data on this. **What it blocks until then:** Flow C step 3 (channel switch, though with web-only v1 this is moot); where a deferred answer lands after the session expires (**UA-Q2**); the `conversation_id` lifetime. **v1 working assumption for tracing only (not a decision):** one web `conversation_id` per chat thread, independent of session lifetime. |
| **UA-D6** | Sessions | **Fixed timeouts: 30 min idle / 12 h absolute** (NIST 800-63B AAL2), same for every tier. | ✅ CONFIRMED | Simple and standards-aligned. **Consequence:** a HITL outcome can arrive after the session has expired, so delivery must not depend on a live session and the answer must be persisted to the conversation (ties to UA-D2's event log and UA-D5). What counts as "activity" is still open (**UA-Q3**). |
| **UA-D7** | Request/Response | **Typed event envelope:** `status`, `text_delta`, `citation`, `action_card`, `handoff`, `final`, `error`, each with `event_id` (monotonic per conversation), `turn_id`, `type`, `payload`. The web renderer maps each type to a component. Future adapters degrade by type. | ✅ CONFIRMED | Citations and action cards (e.g. approval status of the $12,400 credit memo) are first-class, not parsed out of markdown. Pairs naturally with UA-D2 (SSE `event:` field = `type`, `id:` = `event_id`). |
| **UA-D8** | Request/Response | Streaming vs. output-safety gate | 🔵 OPEN | **Deferred on purpose. Revisit after Comp. 7 (Safety) and Comp. 9 (Evaluation)**, which determine the gate's actual latency and whether an incremental guard exists. Option (d) needs a streaming-capable guard, and (a) is only acceptable if gate + generation fit the ~10 s attention limit. **What it blocks until then:** whether `text_delta` events are emitted before `final`. UA-D7 already carries both, so the contract survives either outcome. Candidate for a Step-7 experiment when revisited. |

**Follow-up answers (user, 2026-09-23):**
* **UA-Q1 → (ii)** Minimal read-only T0 token (`sub` = anonymous session). Folded into UA-D4.
* **UA-Q2 → (i)** Inbox only. A deferred outcome is persisted to the conversation and shown on the next visit/login. No outbound email notification in v1. Accepted trade-off: users who never return never see the outcome (see grid KU4). Works because HITL-worthy actions require step-up to T1/T2, so the inbox is always keyed to a returning, identifiable principal.
* **UA-Q3 → (ii)** Any authenticated request, including an open SSE stream, resets the 30-min idle timer. Consequence: an open tab keeps the session alive up to the 12 h absolute cap (see grid KK3, UK5, UU5).

**Follow-up questions as originally asked:**
* **UA-Q1** (D3 × D4): T0 anonymous has no user token. What can the agent do on its behalf? Options: (i) no delegated token, so public/read-only knowledge only and every tool call requires step-up · (ii) a T0 token with `sub` = anonymous session and a tiny read-only audience.
* **UA-Q2** (D1 × D2 × D6): the user is offline or the session has expired when a HITL outcome arrives. Web-only v1 means no Slack/email channel. Options: (i) inbox only: the event is persisted and shown on the next visit/login · (ii) inbox + an outbound email *notification* (a link, not a conversation channel).
* **UA-Q3** (D2 × D6): what resets the 30-min idle timer? Options: (i) only user-originated turns (SSE heartbeats and agent events do not) · (ii) any authenticated request including an open SSE stream.

### 5.7 EXPERIMENT CHECK — Step 7

No fork was marked for experiment. Per the loop, UA-D1/D2/D3/D6/D7 stand as the finalized approach, and UA-D4 stands subject to UA-Q1. UA-D5 and UA-D8 are OPEN (not experiments). UA-D8 is flagged as a likely experiment candidate when it is revisited.

### 5.8 FAILURE MODES — Step 8 (Known/Unknown grid, scoped to this component's sub-components)

Quadrant definitions follow [`failure_modes_matrix.md`](./failure_modes_matrix.md). Entries already in the whole-system matrix are **pointed to, not restated**: 15 MB paste vs. body limit, JWT clock-skew, Okta introspection latency, vague prompt, cheerful tone during an outage.

**Q1 — KNOWN KNOWNS (explicit contract breaches)**
| ID | Sub-comp | Failure |
| :--- | :--- | :--- |
| KK1 | API | The client retries `POST /turns` after a network blip, so the same turn is processed twice (duplicate tool proposal). |
| KK2 | API / Req-Resp | A proxy/LB idle timeout (e.g. Nginx 60 s) cuts the SSE stream mid-answer, and events are missed. |
| KK3 | Identity | The access token expires while the long-lived SSE stream stays open. The token was only validated at connect, so events keep flowing to a no-longer-authenticated client. **Made more likely by UA-Q3(ii).** |
| KK4 | Sessions | BOLA: the user swaps `conversation_id` in the URL/stream path and reads another principal's or tenant's transcript. |
| KK5 | Identity | T1 one-time code brute-forced or replayed (no attempt limit/TTL), or sent to a stale email/phone on file. |
| KK6 | Identity | An on-behalf-of token outlives logout or session expiry, and in-flight work keeps acting with it. |

**Q2 — KNOWN UNKNOWNS (we know to ask; magnitude unknown)**
| ID | Sub-comp | Failure |
| :--- | :--- | :--- |
| KU1 | Channels/UI | Corporate proxies/AV that buffer `text/event-stream` until close, so the answer arrives all at once or never. Unknown share of enterprise users are affected. |
| KU2 | Identity | Drop-off at step-up (T0→T1/T2): how many abandon at the one-time-code/SSO prompt (Erlang A abandonment)? |
| KU3 | Sessions / API | Capacity: concurrent open SSE connections (multi-tab, 12 h lifetime under UA-Q3(ii)) and replay-log retention size. |
| KU4 | Req-Resp | Inbox-only (UA-Q2(i)): what share of users never return to see a deferred HITL outcome and re-contact instead (FCR hit)? |
| KU5 | Req-Resp | Perceived latency while UA-D8 is OPEN. It depends on gate latency that Comp. 7/9 will set. |

**Q3 — UNKNOWN KNOWNS (tacit conventions no one wrote down)**
| ID | Sub-comp | Failure |
| :--- | :--- | :--- |
| UK1 | Channels/UI | The widget never tells users they are talking to an AI (EU AI Act Art. 50). Everyone assumes it, but it's in no spec. |
| UK2 | Channels/UI | Token-by-token updates flood screen readers via an ARIA live region (WCAG 2.2). |
| UK3 | Identity | An anonymous user *claims* an identity ("my account is 4471…") and the agent treats claimed as verified. Human agents know to verify before disclosing. |
| UK4 | Req-Resp | A deferred inbox item ("Approved: $12,400") appears hours later with no restatement of what was asked. |
| UK5 | Sessions | Shared/kiosk device: an open tab keeps the session alive for 12 h (UA-Q3(ii)), and the next person sees the conversation. |

**Q4 — UNKNOWN UNKNOWNS (emergent from combining decisions)**
| ID | Sub-comp | Failure |
| :--- | :--- | :--- |
| UU1 | Req-Resp × Sessions | SSE replay (UA-D2) re-sends an `action_card` (UA-D7). A re-rendered "Confirm" button is clicked a second time, causing a double confirmation. |
| UU2 | Identity | Over time the T0 read-only audience (UA-Q1(ii)) gains a "harmless" lookup (order status by number), and anonymous scrapers enumerate it. |
| UU3 | Identity × Sessions | Mid-conversation step-up T0→T2: earlier anonymous turns (possibly typed by someone else on a shared device) now sit in context with T2 authority. The reverse also happens: the session expires while in-flight work holds a T2 token. |
| UU4 | Channels/UI | The renderer is an exfiltration sink: model-produced citation URLs or markdown images leak data via URL parameters. |
| UU5 | API / Sessions | Deploy/restart drops every 12 h-alive stream at once, and all clients reconnect with `Last-Event-ID`, causing a replay storm on the event log. |

### 5.9 DESIGN AGAINST THE FAILURE MODES — Step 9

Legend: **FIXES** = the decision removes the failure · **MITIGATES** = reduces likelihood or impact, with residual risk · **WORSENS** = the decision increases exposure · **OWNED RISK** = no decision addresses it yet (logged, not solved).

| Grid ID | Addressed by | Effect | Residual / owner |
| :--- | :--- | :--- | :--- |
| KK1 | UA-D2 (`Idempotency-Key` = `turn_id`) | **FIXES** at ingress | Dedupe window must exceed the client retry window (parameter, not a fork). |
| KK2 | UA-D2 (resumable SSE, `Last-Event-ID` replay) | **FIXES** data loss · **MITIGATES** UX (reconnect gap still visible) | Needs heartbeat comments shorter than proxy idle timeout (implementation). |
| KK3 | UA-D9 (24 h token > 12 h session cap) · UA-Q3(ii) **WORSENS** | **FIXES** expiry variant · **OWNED RISK** revocation variant + 24 h theft window | Server must enforce session expiry and revocation on the open stream independently of the token. |
| KK4 | Trajectory step A4 ownership check (baseline design, not a fork) | **MITIGATES** | Final ID/ownership model depends on **UA-D5 (OPEN)**. Owned until D5 resolves. |
| KK5 | UA-D3 introduces T1 | **OWNED RISK** | Attempt limits / code TTL: rate limiting is Comp. 11; code policy is Comp. 7. |
| KK6 | UA-D4 (short-lived tokens) | **MITIGATES** (bounded by TTL) | Revocation on logout/expiry is not decided. **Owned.** |
| KU1 | UA-D2 (SSE over HTTP/2 is more proxy-friendly than WS) | **MITIGATES** | No fallback (long-poll) decided. **Owned.** Measure in Comp. 10. |
| KU2 | UA-D3 (FAQs need no login) | **MITIGATES** friction overall | Step-up abandonment unmeasured. **Owned**, metric for Comp. 9/10. |
| KU3 | — (UA-Q3(ii) **WORSENS**) | **OWNED RISK** | Capacity planning → Comp. 11. Replay-log retention → Comp. 8. |
| KU4 | UA-Q2(i) introduces it | **OWNED RISK (explicitly accepted trade-off)** | Revisit if re-contact rate on deferred outcomes is high. |
| KU5 | UA-D8 OPEN | **OWNED RISK** until D8 is revisited after Comp. 7/9 | UA-D7 keeps the contract stable either way. |
| UK1 | — | **OWNED RISK** | Cheap fix (disclosure banner); belongs in the web UI spec. |
| UK2 | UA-D7 (typed `text_delta` lets the renderer batch per sentence) | **MITIGATES** only if the renderer does it | **Owned** (implementation). |
| UK3 | UA-D4 + UA-Q1(ii) (T0 token is read-only, so a claimed identity unlocks no account tools) | **FIXES** for actions · **MITIGATES** for disclosure | Whether read-only T0 tools can *reveal* account data is set by the T0 audience contents (Comp. 5/7). |
| UK4 | UA-D7 (events carry `turn_id`) | **MITIGATES** (renderer can link back) | Restating the original question in the item is not decided. **Owned** (small). |
| UK5 | UA-D6 12 h cap bounds it · UA-Q3(ii) **WORSENS** it | **OWNED RISK (accepted trade-off)** | Explicit consequence of Q3(ii). |
| UU1 | — (UA-D2 × UA-D7 **create** it) | **OWNED RISK** | Real fix is action idempotency at Tools (report: HMAC idempotency key per action) → Comp. 5. The renderer should also mark replayed cards as already-actioned. |
| UU2 | UA-Q1(ii) creates the surface | **OWNED RISK** | Governance of the T0 audience → Comp. 7 Tool Permissions. |
| UU3 | — | **OWNED RISK** | Assurance-level tagging per turn. Revisit with UA-D5. |
| UU4 | UA-D7 (structured citation payloads, not raw HTML/markdown) | **MITIGATES** | Renderer must not auto-load remote images or unlisted URLs. Output safety → Comp. 7. |
| UU5 | — (UA-D2 × UA-Q3(ii) **create** it) | **OWNED RISK** | Reconnect jitter/backoff + replay caps → Comp. 11. |

**Summary:** 3 FIXES (KK1, KK2 data loss, UK3 actions) · 7 MITIGATES · 11 OWNED RISKS (2 explicitly accepted trade-offs: KU4, UK5). **KK3 is the only owned risk inside this component's own scope that has no downstream owner.** It is flagged as a candidate new fork.

**UA-F9 / UA-D9 — Token validity (user decision, 2026-09-23): user access tokens are valid for 24 h.** ✅ CONFIRMED
* Scope as understood: the *user's* access/session credential. The on-behalf-of tokens from UA-D4 stay short-lived (unchanged).
* **Effect on KK3:** the 24 h token outlives the 12 h absolute session cap (UA-D6), so a token can no longer expire in the middle of a live session. The **expiry variant of KK3 is FIXED**.
* **Residual (still OWNED):** the *revocation* variant. After logout in another tab or an account disable, an already-open stream keeps flowing unless the server re-checks.
* **New exposure (logged, not argued):** the token can outlive its session by up to 12 h, so the server must enforce session expiry on the stream on its own rather than infer it from the token. A stolen token is also usable for up to 24 h (a wider window than typical short-lived access tokens with refresh).
* Updated KK3 row in 5.9: **FIXES (expiry) · OWNED RISK (revocation, 24 h theft window).**

### 5.10 DEFINITION OF DONE — Step 10 check

| Criterion | Met? |
| :--- | :--- |
| Every sub-component has a Step-6 status | ✅ Channels/UI D1 · API D2 · Identity D3, D4 · Sessions D5 (OPEN), D6 · Request/Response D7, D8 (OPEN) |
| Trajectory traced start to finish | ✅ Flows A, B, C (§5.3). Flow B's Slack leg is out of v1 scope per D1 |
| Boundary explicit | ✅ §5.4 |
| Failure grid exists + Step 9 run | ✅ §5.8, §5.9 |
| Logged with reasoning | ✅ This section + decision table rows |

### 5.11 MATERIALIZE — Step 11

* Page **`LLD - [1] User & Application`** (`page:lld_user_app`) added to [`architecture.tldr`](./architecture.tldr) by [`generate_lld_user_app.py`](./generate_lld_user_app.py). The script only replaces its own page, and re-running it is safe.
* Contents: boundary strip (receives / hands off / not owned) · Flow A (inbound row ①–⑤ → not-owned core → outbound row ⑦–⑨) · Flow B (deferred delivery) · Flow C (resume, step-up, expiry, channel switch) · 5 sub-component cards (mechanic + status) · failure grid with step-9 effects · decision-log summary.
* **Shallower duplicate on page 1:** nodes `[1] User Channels & Ingress` (lists Web · Mobile · Slack · Teams · Email), `[2] API Gateway & Identity`, and `[13] Response Delivery Engine` ("SSE / WebSocket Streaming") partly contradict UA-D1/UA-D2. Trim-to-pointer vs. leave-both: ⏳ **awaiting user**.
