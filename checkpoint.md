# Enterprise Support Agent: Architectural Decision Checkpoint

> **Status:** ✅ ACTIVE & CHECKPOINTED (Component [ 5 ] Finalized)  
> **Component Under Review:** Component [ 5 ] — Agent Orchestration Core & Runtime  
> **Genesis Readiness:** READY FOR SCAFFOLDING (Initial Specifications Checkpointed)  
> **Reference Master Report:** [`Enterprise AI Customer Support Agent Architecture - Formatted Master Report.md`](<./Enterprise AI Customer Support Agent Architecture - Formatted Master Report.md>)  
> **Visual Whiteboard Canvas:** [`architecture.tldr`](./architecture.tldr) (Page 2: `LLD - Agent Orchestration & Planning Core`)

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
