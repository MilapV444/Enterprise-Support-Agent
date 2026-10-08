# MA-ADP-02: Delegation & Limits (Jev Multi-Label Routing, Dependency DAG Concurrency & Strict Resource Ceilings)

- **Status**: Accepted & Confirmed
- **Date**: 2026-09-29 *(Amended: 2026-09-29 per MA-D3 Jev Routing, MA-D6 Dependency Concurrency, MA-D8 Resource Limits & MA-Q4 Step Ceilings)*
- **Deciders**: Architecture Team, Lead Distributed Orchestration Architect, AI Cost & Performance Core
- **Component**: `[5] Multi-Agent & Communication` (`Component [ 5 ]`)
- **Reasoning Source**: `checkpoint.md` §9 · Diagram: `LLD - [5] Multi-Agent & Communication`
- **Decisions Covered**:
  - `MA-D3`: Delegation Decision Engine — Jev-governed dispatch: `Choice` for the lead specialist (including "Generalist") + parallel `Noul` queries per domain specialist for cross-domain inquiries; code owns dispatch flow; low confidence ($\gamma < 0.50$) trips safely to Human Specialist (HITL)
  - `MA-D6`: Execution Concurrency & Dependency Ordering — Dynamic dependency DAG: parallel execution for subtasks marked independent by the plan; sequential ordered execution for tasks with data dependencies (e.g., Billing waiting for Technical root cause)
  - `MA-D8`: Delegation Limits & Strict Resource Ceilings — Strict Depth $1$ (no nested delegation); span of control $\le 5$ specialists per turn; shared token budget; hard step ceilings: maximum $2$ steps per specialist, maximum $6$ total steps per turn across all agents (`MA-Q4`)
- **Related Architectural Decision Points**:
  - [`ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/00-orchestration-core/ADP-04-error-recovery-replanning.md): Metacognitive Error Recovery *(StepCeilingGuard & Reflexion Circuit Breakers)*
  - [`ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/00-orchestration-core/ADP-05-decision-model-jev.md): Decision Model (Jev) *(Structured Decision Engine & PII Masking)*
  - [`CR-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#cr-adp-02--token--context-economy): Token & Context Economy *(Shared Turn Token Allocations)*
  - [`MA-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/05-multi-agent-communication/MA-ADP-01-topology-specialist-set.md): Topology & Specialist Set *(Hierarchical Command Structure)*

---

## 1. Context & Problem Statement

Multi-agent autonomous systems frequently suffer from runaway resource consumption, coordination deadlocks, and unpredictable execution latency (Cemri et al., 2025). When an enterprise support request touches multiple domains (e.g., Sarah reporting a multi-region database failover accompanied by a $\$12,400$ bandwidth overage on `INV-9821`), the system must determine:
1. Which specialists need to be activated.
2. What order they should run in.
3. How many internal deliberative steps and tokens each may consume.

Under naive multi-agent implementations, three catastrophic failures occur:
1. **The Runaway Fan-Out & Token Hemorrhage ($KK2 / KK4$)**: If specialists are permitted to recursively delegate tasks to other sub-agents (Depth $\ge 2$), or if individual agents run unconstrained ReAct loops, token consumption explodes exponentially. In complex multi-agent runs, token consumption routinely exceeds $15\times$ standard conversational turns (Anthropic, 2025), blowing past cost budgets and triggering gateway timeouts.
2. **The Dependency Inversion Race Condition ($MA-D6$)**: The Billing specialist attempts to evaluate whether an invoice overage is valid before the Technical specialist has inspected syslog events to determine if the traffic was caused by an internal platform bug (`BUG-8192`). Executing Billing and Technical in parallel without dependency awareness results in Billing erroneously rejecting the dispute.
3. **Forced Misrouting on Out-of-Distribution Inquiries ($UU5$)**: When a customer asks an atypical question (e.g., inquiring about enterprise sustainability certifications), a naive classifier forced to choose between Billing, Tech, and Ops picks the "least bad" fit (e.g., Tech), leading to bizarre specialist hallucinations.

### The Core Architectural Question
> **How do we deterministically govern specialist activation, schedule parallel vs. sequential execution based on data dependencies, and enforce strict finite bounds on execution depth, steps, and tokens?**

---

## 2. Decision Framework & Theoretical Formulation

To solve these challenges, `MA-D3`, `MA-D6`, and `MA-D8` establish the **Jev-Governed Dispatcher with Dependency DAG Concurrency and Finite Resource Bounding**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                            DELEGATION & DEPENDENCY SCHEDULING (MA-D3, MA-D6)                     │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                                    CUSTOMER TURN (PII-Masked)
                                                │
                                                ▼
                             ┌──────────────────────────────────────┐
                             │       JEV DELEGATION GATEWAY         │
                             │  • Choice: Lead Specialist           │
                             │  • Noul: Domain Co-activation (0..4) │
                             └──────────────────────────────────────┘
                                                │
                     ┌──────────────────────────┴──────────────────────────┐
                     ▼                                                     ▼
      Independent Subtasks (e.g., Audit)                    Dependent Tasks (e.g., Overcharge)
      E = ∅ (Parallel Execution)                            E ≠ ∅ (Sequential DAG Execution)
                     │                                                     │
         ┌───────────┴───────────┐                             ┌───────────┴───────────┐
         ▼                       ▼                             ▼                       ▼
┌─────────────────┐     ┌─────────────────┐           ┌─────────────────┐     ┌─────────────────┐
│ Technical Agent │     │  Billing Agent  │           │ Technical Agent │     │  Billing Agent  │
│ (2 Steps Max)   │     │ (2 Steps Max)   │           │ (Root Cause)    │     │ (Evaluates $)   │
└─────────────────┘     └─────────────────┘           └─────────────────┘     └─────────────────┘
         │                       │                             │ (Emits finding)       │
         └───────────┬───────────┘                             └──────────────►────────┘
                     ▼                                                                 ▼
      Join Node (Sync Barrier)                                      Final Synthesis Join
```

---

### Pillar A: Jev Two-Phase Intent Delegation (`MA-D3`)

We decouple delegation into a two-phase structured evaluation over the PII-masked customer inquiry $\tilde{u}_{\text{turn}}$:

#### Phase 1: Lead Specialist Selection
Jev evaluates a categorical `Choice` query over the static registry:
$$s_{\text{lead}}, \gamma_{\text{lead}} = \text{Jev.Choice}\left(
\text{State} = \tilde{u}_{\text{turn}},
\text{Question} = \text{"Which primary specialist should take the lead on this customer inquiry?"},
\text{Options} = [\text{"generalist"}, \text{"billing"}, \text{"technical"}, \text{"account\_ops"}]
\right)$$

- **The Generalist Safety Valve ($UU5$)**: Including `"generalist"` in the options ensures that out-of-distribution or Tier-1 queries are not forced into specialized billing/technical graphs.
- **Low-Confidence Tripwire**: If $\gamma_{\text{lead}} < 0.50$, the Coordinator refuses to guess and trips immediately to Human Specialist review (`HL-ADP-03`).

#### Phase 2: Secondary Domain Co-Activation
To detect multi-domain turns, Jev evaluates parallel `Noul` checks for all remaining specialists:
$$\forall s \in \mathcal{S}_{\text{domain}} \setminus \{s_{\text{lead}}\}, \quad \mathbb{P}(\text{requires}_s) = \text{Jev.Noul}\left(
\text{State} = \tilde{u}_{\text{turn}},
\text{Question} = \text{f"Does addressing this inquiry require factual input or action from the {s} specialist?"}
\right)$$

The dispatched specialist set is formed dynamically:
$$\mathcal{S}_{\text{dispatched}} = \{s_{\text{lead}}\} \cup \left\{ s \mid \mathbb{P}(\text{requires}_s) \ge 0.80 \right\}$$

---

### Pillar B: Dependency DAG Concurrency Scheduling (`MA-D6`)

The Coordinator constructs a Directed Acyclic Graph (DAG) $G = (V, E)$ over the active specialists $\mathcal{S}_{\text{dispatched}}$:

1. **Independent Subtasks ($E = \emptyset$)**:
   Tasks sharing no data dependencies (e.g., Scenario 7: compliance audit evaluating Q2 uptime in Technical and credit history in Billing) execute **in parallel**:
   $$T_{\text{execution}} = \max_{s \in \mathcal{S}} T(s)$$
   Subgraphs run concurrently on separate asyncio threads and join at a synchronization barrier.
2. **Dependent Sequential Chains ($E \ne \emptyset$)**:
   When downstream analysis requires facts from an upstream specialist (e.g., Billing cannot evaluate whether an invoice adjustment is valid until Technical confirms whether `BUG-8192` caused the crash):
   $$T_{\text{execution}} = T(\text{Technical}) + T(\text{Billing})$$
   The Technical deliverable is injected directly into Billing's task brief (`MA-ADP-03`).

---

### Pillar C: Finite Resource Ceilings & Step Guardrails (`MA-D8`, `MA-Q4`)

To guarantee absolute bounds on runtime costs and prevent infinite loops, we enforce three hard resource bounds:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             FINITE RESOURCE CEILINGS (MA-D8, MA-Q4)                              │
├────────────────────────────────┬────────────────────────────────┬────────────────────────────────┤
│   1. Fixed Graph Depth         │   2. ICS Span of Control       │   3. Bounded Step Ceilings     │
├────────────────────────────────┼────────────────────────────────┼────────────────────────────────┤
│   • Depth = 1 STRICTLY         │   • Max 5 Specialists / Turn   │   • Max 2 Steps per Specialist │
│   • Specialists CANNOT spawn   │   • Aligned with Incident      │   • Max 6 Steps TOTAL per turn │
│     sub-specialists            │     Command System (FEMA)      │     (all agents + coordinator) │
│   • Eliminates nested runaway  │   • Prevents combinatorial     │   • Specialist gets at most    │
│     delegation chains (KK2)    │     coordination explosion     │     one internal retry         │
└────────────────────────────────┴────────────────────────────────┴────────────────────────────────┘
```

#### Mathematical Step Ceiling Formulation
Let $\text{Steps}(s)$ be the number of tool/reasoning iterations executed by agent $s$.
The runtime asserts:
$$\forall s \in \mathcal{S}_{\text{dispatched}}, \quad \text{Steps}(s) \le 2$$
$$\text{Steps}(\text{Coordinator}) + \sum_{s \in \mathcal{S}_{\text{dispatched}}} \text{Steps}(s) \le 6$$

If a specialist encounters a tool execution error on step 1, it executes a single Reflexion retry (`ADP-04`) on step 2. If step 2 fails, the specialist's step budget is exhausted; it transitions immediately to `status="blocked"` and returns its diagnostic payload to the Coordinator.

#### Shared Turn Token Budget
All agents within a turn share a single token budget:
$$\sum_{s \in \mathcal{S}_{\text{dispatched}}} \text{Tokens}(s) \le \mathcal{B}_{\text{turn\_shared}} \quad (\text{Default: } 16,000 \text{ tokens})$$
If cumulative token consumption reaches $90\%$ of $\mathcal{B}_{\text{turn\_shared}}$, the Coordinator terminates open ReAct loops and forces immediate join synthesis.

---

## 3. Decision Rules, Structural Invariants & Code Contracts

### Decision Invariants
1. **Invariant 1 (Depth Invariance)**: The execution graph depth is mathematically capped at $1$. Subgraphs possess no delegation endpoints.
2. **Invariant 2 (Monotonic Step Ceiling Enforcement)**: The step counter is tracked in the shared LangGraph state checkpointer. When $\text{total\_steps} = 6$, all further tool calls are blocked.
3. **Invariant 3 (Low-Confidence Failsafe)**: If Jev lead delegation confidence $\gamma_{\text{lead}} < 0.50$, automated dispatch is aborted, routing directly to Human Specialist escalation.
4. **Invariant 4 (ICS Span Bound)**: Under no operational condition may the Coordinator dispatch tasks to more than $5$ specialists in a single turn.

---

### Python & Pydantic Data Contracts

```python
"""
Data contracts for Delegation Decisions, Dependency DAGs, and Resource Ceilings.
Module: core/multiagent/delegation.py
"""

from typing import List, Dict, Optional, Set
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class DelegationExecutionMode(str, Enum):
    PARALLEL = "parallel"
    SEQUENTIAL = "sequential"


class SpecialistDispatchTarget(BaseModel):
    """Specification of an active specialist scheduled for execution."""
    role: str
    is_lead: bool = Field(default=False)
    depends_on: List[str] = Field(default_factory=list, description="Roles that must complete first")
    allocated_steps: int = Field(default=2, le=2)


class DelegationPlan(BaseModel):
    """Structured delegation schedule emitted by Coordinator."""
    case_id: str
    conversation_id: str
    execution_mode: DelegationExecutionMode
    lead_specialist: str
    active_specialists: List[SpecialistDispatchTarget] = Field(..., max_items=5)
    
    # Resource budgets
    max_turn_steps: int = Field(default=6, le=6)
    max_turn_tokens: int = Field(default=16000)
    
    # Confidence metrics
    lead_confidence: float = Field(..., ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TurnResourceLedger(BaseModel):
    """Authoritative counter tracking shared resource consumption across a turn."""
    turn_id: str
    total_steps_executed: int = Field(default=0, le=6)
    total_tokens_consumed: int = Field(default=0)
    specialist_steps: Dict[str, int] = Field(default_factory=dict)
    
    def increment_step(self, role: str) -> None:
        if self.total_steps_executed >= 6:
            raise RuntimeError("Turn step ceiling (6) exceeded.")
        current_agent_steps = self.specialist_steps.get(role, 0)
        if current_agent_steps >= 2:
            raise RuntimeError(f"Specialist '{role}' exceeded step ceiling (2).")
        self.specialist_steps[role] = current_agent_steps + 1
        self.total_steps_executed += 1
```

---

## 4. Failure Modes Matrix & Resilience Invariants

| Quadrant | Failure Scenario | Detection Mechanism | Systemic Mitigation & Recovery |
| :--- | :--- | :--- | :--- |
| **Q1: Known Knowns** | **Turn Step Ceiling Exhaustion ($KK4$)**: Specialists attempt complex diagnostic loops, consuming all 6 steps before finding a solution. | `TurnResourceLedger` hits `total_steps_executed == 6`. | Execution halts; Coordinator packages partial findings into an `IncidentDiagnosticPacket` and trips to Human Specialist (`ADP-04`). |
| **Q2: Known Unknowns** | **Jev Delegation Recall Anomaly ($KK5$)**: A subtle billing question with technical jargon routes solely to Technical, omitting Billing. | Specialist flags missing domain capabilities in task return. | If Technical returns `status="blocked"`, Coordinator re-evaluates delegation or escalates to human specialist. |
| **Q3: Unknown Knowns** | **Parallel Latency Skew ($KU3$)**: In a parallel audit, Technical finishes in $800\text{ms}$ while Billing takes $6.5\text{s}$, stalling the customer turn. | Task timeout watchdog triggers per-specialist. | Hard per-specialist execution timeout ($5.0\text{s}$); if exceeded, specialist is canceled and tagged as `status="timed_out"`. |
| **Q4: Unknown Unknowns** | **Combinatorial Dependency Deadlock**: Two specialists declare mutual data dependencies in an ad-hoc plan. | DAG compiler cycles detector evaluates `depends_on` graph. | Static DAG validation: dependencies must form a strict topological sort; cyclic dependency plans are rejected, defaulting to sequential execution. |

---

## 5. Closed-Loop Feedback & Verification Signals

1. **Production Health Metrics**:
   - `Delegation_Lead_Confidence_p10`: Alerts if 10th-percentile lead delegation confidence falls below $0.60$.
   - `Multi_Agent_Turn_Token_Consumption`: Monitored per route; alerts if average tokens per turn exceed $12,000$.
   - `Step_Ceiling_Trip_Rate`: Tracks percentage of turns hitting the 6-step cap.
2. **Weekly Delegation Accuracy Benchmark**:
   - Evaluate the Jev delegation router against $300$ golden multi-domain customer transcripts, asserting $>97\%$ accuracy in selecting the correct lead specialist and co-activated domains.

---

## 6. Genesis Implementation Directives

1. **Code Locations**:
   - Implement Jev delegation queries in `core/multiagent/delegation_router.py`.
   - Implement the DAG concurrency scheduler in `core/multiagent/scheduler.py`.
   - Implement the shared resource ledger in `core/multiagent/resource_ledger.py`.
2. **LangGraph Reducer Integration**:
   - Integrate `TurnResourceLedger` into the global `CaseState` Pydantic model in `core/orchestrator/statechart.py`, ensuring step increments are committed atomically.

---

## 7. Consequences & Trade-offs

### Positive Consequences
- **Deterministic Cost Governance**: Hard ceilings of 2 steps per specialist and 6 steps per turn mathematically eliminate runaway token loops.
- **Race-Free Dependency Execution**: Constructing explicit dependency DAGs ensures downstream specialists receive verified facts before drawing conclusions.
- **Fail-Safe Ambiguity Routing**: Bounding Jev delegation with $\gamma \ge 0.50$ thresholds protects users from being routed to hallucinated specialist contexts.

### Negative Consequences & Trade-offs
- **Truncated Deliberation on Complex Edge Cases**: Capping specialists at 2 steps limits deep autonomous troubleshooting, intentionally shifting edge-case complexity to human specialists.
- **Sequential Execution Latency**: Dependent tasks execute in series, resulting in $3–6\text{s}$ turn latencies for cross-domain cases.
- **Coordinator Scheduling Overhead**: Generating Jev delegation queries and constructing dependency DAGs adds $\approx 60\text{ms}$ to turn initialization.

---

## 8. References & Cross-Disciplinary Grounding

1. **Building Effective Agents**: Anthropic Research. (2024). (Foundations of Orchestrator-Worker concurrency and token consumption trade-offs).
2. **Scheduling Algorithms for Parallel Task Graphs**: Kwok, Y. K., & Ahmad, I. (1999). *ACM Computing Surveys*. (Theoretical models for DAG-based topological execution).
3. **FEMA Emergency Management Institute**: *National Incident Management System (NIMS) Incident Command System (ICS)*. (Span of control bounds: 3–7, optimal 5).
4. **Reflexion: Language Agents with Verbal Reinforcement Learning**: Shinn, N., et al. (2023). NeurIPS. (Step ceilings and trial bounding).
