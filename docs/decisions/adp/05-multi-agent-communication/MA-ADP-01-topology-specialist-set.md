# MA-ADP-01: Topology & Specialist Set (Hierarchical Unified Command, ITIL Domain Specialists & In-Graph LangGraph Subgraphs)

- **Status**: Accepted & Confirmed
- **Date**: 2026-09-29 *(Amended: 2026-09-29 per MA-D1 Hierarchical Command, MA-D2 Specialist Taxonomy, MA-D10 Static Registry & MA-D11 In-Graph Subgraph Execution)*
- **Deciders**: Architecture Team, Lead Multi-Agent Systems Engineer, AI Orchestration Core
- **Component**: `[5] Multi-Agent & Communication` (`Component [ 5 ]`)
- **Reasoning Source**: `checkpoint.md` §9 · Diagram: `LLD - [5] Multi-Agent & Communication`
- **Decisions Covered**:
  - `MA-D1`: Hierarchical Supervisor Topology — Unified command structure; coordinator delegates to specialist sub-agents; specialists never communicate directly with each other ($O(N)$ message complexity vs. $O(N^2)$ flat swarms)
  - `MA-D2`: Specialist Domain Taxonomy — ITIL-aligned division of labor: dedicated Coordinator (pure routing and synthesis, `MA-Q1`) plus four domain specialists: `Generalist`, `Billing`, `Technical`, `Account & Ops` (`MA-Q2`)
  - `MA-D10`: Static Agent Discovery Registry — Version-controlled static registry in code/config; third-party dynamic agent loading and remote agent-to-agent protocols excluded in v1
  - `MA-D11`: Single-Runtime Subgraph Architecture — Specialists run as native LangGraph subgraphs within the exact same compiled state graph and Postgres checkpoint (`ADP-02`, `MS-D8`)
- **Related Architectural Decision Points**:
  - [`ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/00-orchestration-core/ADP-01-planning-paradigm.md): Planning Paradigm *(Deterministic LangGraph FSM)*
  - [`ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/00-orchestration-core/ADP-02-workflow-durability.md): Workflow Execution & Durability Substrate *(Two-Tier Outer Temporal / Inner LangGraph)*
  - [`MS-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/03-memory-state/MS-ADP-04-agent-state-durability.md): Agent State & Durability *(Single Source of Truth in Postgres Checkpointer)*
  - [`MA-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/05-multi-agent-communication/MA-ADP-02-delegation-limits.md): Delegation & Limits *(Jev-Governed Dispatch & Step Ceilings)*

---

## 1. Context & Problem Statement

As enterprise customer support agents expand across technical troubleshooting, financial adjustments, and account provisioning, consolidating all system prompts, diagnostic tools, and domain policies into a single monolithic LLM prompt creates severe cognitive collapse:
1. **The Context Saturation & Dilution Cliff**: A single prompt containing Stripe refund rules, Kubernetes cluster triage runbooks, and Okta SAML configurations exhausts working memory tokens (`ADP-03`), triggering attention degradation and hallucinated parameter combinations.
2. **The "Flat Swarm" Communication Explosion**: Peer-to-peer multi-agent frameworks (e.g., AutoGen GroupChat, OpenAI Swarm) allow agents to pass conversational control arbitrarily among themselves. In production, flat agent swarms rapidly exhibit state drift, circular message loops ($O(N^2)$ token explosion), diffused operational accountability, and non-deterministic termination (Cemri et al., 2025).
3. **The Multi-Service RPC Distributed State Nightmare**: Implementing specialists as independent microservices communicating over remote RPC or A2A protocols fractures state across distributed checkpointers. If a workflow pauses for a three-day human approval wait, reconstructing unified conversation state across five remote microservices requires complex two-phase commits.

### The Core Architectural Question
> **How do we decompose heterogeneous enterprise support domains into focused, autonomous specialist units while guaranteeing centralized accountability, bounded communication complexity, and seamless state persistence within a single durable execution graph?**

---

## 2. Decision Framework & Theoretical Formulation

To solve these challenges, `MA-D1`, `MA-D2`, `MA-D10`, and `MA-D11` establish the **Hierarchical Unified Command Topology with In-Graph LangGraph Subgraphs**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                            HIERARCHICAL COMMAND TOPOLOGY (MA-D1, MA-D2)                          │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                                    CUSTOMER TURN (UA-ADP-01)
                                                │
                                                ▼
                             ┌──────────────────────────────────────┐
                             │       COORDINATOR AGENT (MA-Q1)      │
                             │  • Intent Routing & Synthesis ONLY   │
                             │  • Holds the single Case Context     │
                             │  • Sole interface to Customer (MA-12)│
                             └──────────────────────────────────────┘
                                                │
         ┌──────────────────────────────┬───────┴──────────────────────┬──────────────────────────────┐
         ▼                              ▼                              ▼                              ▼
┌──────────────────┐           ┌──────────────────┐           ┌──────────────────┐           ┌──────────────────┐
│ Generalist Agent │           │  Billing Agent   │           │ Technical Agent  │           │ Account & Ops    │
│ (Tier 1 Support) │           │ (Stripe, SAP,    │           │ (AWS, Datadog,   │           │ (Okta, Auth0,    │
│ • FAQs, Overview │           │  Credit Memos)   │           │  CloudWatch)     │           │  SAML, Admin)    │
└──────────────────┘           └──────────────────┘           └──────────────────┘           └──────────────────┘
         │                              │                              │                              │
         └──────────────────────────────┼──────────────────────────────┴──────────────────────────────┘
                                        ▼
                             ┌──────────────────────────────────────┐
                             │  Unified LangGraph Checkpointer (MS8)│
                             │  Single State Graph (chk_postgres)   │
                             └──────────────────────────────────────┘
```

---

### Pillar A: Hierarchical Command vs. Flat Swarm Complexity

We ground our agent organization in the Incident Command System (ICS; FEMA NIMS) and Mintzberg's organizational structure theory (Mintzberg, 1979).

#### Mathematical Message Complexity Reduction
In a flat swarm with $N$ active agents communicating peer-to-peer, the worst-case message exchange graph is a complete graph $K_N$:
$$M_{\text{flat}} = \frac{N(N-1)}{2} = \mathcal{O}(N^2)$$
For $N=5$ specialists, up to $10$ inter-agent message channels exist, creating exponential conversational drift and token expenditures (Anthropic multi-agent studies demonstrate $15\times$ baseline token usage; 2025).

Under our **Hierarchical Unified Command Topology (`MA-D1`)**:
Specialists are strictly forbidden from communicating with one another. All communication routes through the Coordinator:
$$M_{\text{hierarchical}} = 2N = \mathcal{O}(N)$$
- The coordinator acts as the single accountable Incident Commander.
- Every specialist receives a standardized task brief and returns a standardized typed output deliverable (Mintzberg standardized outputs).

---

### Pillar B: ITIL-Aligned Specialist Taxonomy (`MA-D2`)

Rather than dynamic ad-hoc agent creation, the system compiles five fixed specialist roles (`MA-Q2`):

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             SPECIALIST DOMAIN TAXONOMY (MA-D2)                                   │
├───────────────────┬───────────────────────────────────┬──────────────────────────────────────────┤
│ Specialist Role   │ Domain Responsibilities           │ Permitted System Tool Bounds (TA-ADP-01) │
├───────────────────┼───────────────────────────────────┼──────────────────────────────────────────┤
│ Coordinator       │ Case ownership, Jev dispatch,     │ Zero direct external execution tools.    │
│ (Pure Router)     │ conflict resolution, synthesis    │ Uses delegation and context tools only.  │
├───────────────────┼───────────────────────────────────┼──────────────────────────────────────────┤
│ Generalist        │ Tier 1 product onboarding, user   │ Knowledge RAG tools, public docs,        │
│                   │ navigation, generic guidance      │ ticket comment reads.                    │
├───────────────────┼───────────────────────────────────┼──────────────────────────────────────────┤
│ Billing           │ Invoices, dispute analysis, SLA   │ Stripe adapter, NetSuite/SAP ERP,        │
│                   │ overages, credit memos, refunds   │ currency calculation, ledger inspection. │
├───────────────────┼───────────────────────────────────┼──────────────────────────────────────────┤
│ Technical         │ Infrastructure failures, cluster  │ CloudWatch, Datadog, GitHub commits,     │
│                   │ restarts, latency, BUG-8192 logs  │ Kubernetes read adapters, trace parsers. │
├───────────────────┼───────────────────────────────────┼──────────────────────────────────────────┤
│ Account & Ops     │ Enterprise SSO, MFA resets, team  │ Okta directory, SCIM provisioning,       │
│                   │ role assignments, tenant settings │ audit log queries, user invitations.     │
└───────────────────┴───────────────────────────────────┴──────────────────────────────────────────┘
```

The Coordinator is strictly decoupled from the Generalist (`MA-Q1`): the Coordinator routes and synthesizes; if a turn requires standard Tier 1 support, it dispatches to the Generalist specialist.

---

### Pillar C: Single-Runtime Subgraph Architecture (`MA-D11`)

We eliminate microservice distributed state overhead by compiling all specialists as native LangGraph subgraphs:
$$G_{\text{orchestration}} = \langle V_{\text{coordinator}} \cup V_{\text{subgraphs}}, E_{\text{edges}} \rangle$$

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                          IN-GRAPH LANGGRAPH SUBGRAPH ARCHITECTURE (MA-D11)                       │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                  │
│  LangGraph StateGraph Runtime                                                                    │
│  │                                                                                               │
│  ├── Node: CoordinatorNode ───────────────► Jev Delegation Decision (MA-ADP-02)                  │
│  │                                          │                                                    │
│  │   ┌──────────────────────────────────────┴──────────────────────────────────────┐       │
│  │   ▼                                                                            ▼       │
│  ├── SubGraph: TechnicalSpecialistGraph       SubGraph: BillingSpecialistGraph            │
│  │   • State: Scoped TechnicalState           • State: Scoped BillingState                │
│  │   • Runs 1–2 internal ReAct steps          • Runs 1–2 internal ReAct steps             │
│  │   • Output: Typed TechnicalResult          • Output: Typed BillingResult               │
│  │   └──────────────────────────────────────┬─────────────────────────────────────┘       │
│  │                                          │                                                    │
│  └── Node: CoordinatorJoinNode ◄────────────┘                                                    │
│      • Evaluates Conflicts (MA-ADP-05)                                                           │
│      • Commits single unified checkpoint to Postgres (MS-D8)                                     │
│                                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

1. **Shared Durable Checkpointer**: Specialists execute within the same process context and commit into the single Postgres checkpointer (`MS-D8`).
2. **Deterministic Resumption**: If an approval wait occurs while Billing is proposing a credit memo, Temporal holds the saga (`ADP-02`); resuming loads the exact state snapshot with zero cross-service deserialization failures.
3. **Static Discovery Registry (`MA-D10`)**: All available specialists are statically registered in `AgentRegistry`. Dynamic remote discovery is barred in v1, eliminating agent impersonation vulnerabilities.

---

## 3. Decision Rules, Structural Invariants & Code Contracts

### Decision Invariants
1. **Invariant 1 (Unified Command Inviolability)**: Specialist sub-agents MUST NEVER instantiate communication channels or invoke tool handoffs with other specialists. All results return to the Coordinator.
2. **Invariant 2 (Single Customer Voice)**: Under no operational condition may a specialist emit conversational text directly to the user socket. The Coordinator alone writes customer-facing prose (`MA-D12`).
3. **Invariant 3 (Static Code Compilation)**: All specialist system prompts, tool allow-lists, and subgraph topologies are statically verified at deploy time.
4. **Invariant 4 (State Reducer Atomicity)**: Specialist outputs must fold into the main graph state via deterministic Pydantic reducers, preventing thread race conditions during parallel branch joins.

---

### Python & Pydantic Data Contracts

```python
"""
Core contracts for Multi-Agent Topology, Specialist Set, and Static Registry.
Module: core/multiagent/topology.py
"""

from typing import Dict, List, Optional, Type
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class SpecialistRole(str, Enum):
    COORDINATOR = "coordinator"
    GENERALIST = "generalist"
    BILLING = "billing"
    TECHNICAL = "technical"
    ACCOUNT_OPS = "account_ops"


class SpecialistDescriptor(BaseModel):
    """Static registration metadata for an enterprise specialist."""
    role: SpecialistRole
    display_name: str
    description: str = Field(..., description="Semantic purpose used by Jev router")
    system_prompt_template: str
    allowed_tool_ids: List[str]
    max_steps_per_turn: int = Field(default=2, le=2, description="MA-D8 step cap")
    is_active: bool = Field(default=True)


class StaticAgentRegistry(BaseModel):
    """Immutable registry cataloging all authorized specialist subgraphs (MA-D10)."""
    version: str = Field(default="1.0.0")
    specialists: Dict[SpecialistRole, SpecialistDescriptor]
    registered_at: datetime = Field(default_factory=datetime.utcnow)

    def get_specialist(self, role: SpecialistRole) -> SpecialistDescriptor:
        if role not in self.specialists or not self.specialists[role].is_active:
            raise ValueError(f"Specialist '{role}' is not active or registered.")
        return self.specialists[role]


class SpecialistTaskBrief(BaseModel):
    """Contextual task brief dispatched from Coordinator to Specialist (MA-ADP-03)."""
    task_id: str
    target_role: SpecialistRole
    case_id: str
    conversation_id: str
    task_objective: str = Field(..., description="Narrow, unambiguous domain question")
    relevant_entity_ids: Dict[str, str] = Field(default_factory=dict)
    pinned_constraints: List[str] = Field(default_factory=list)
    allocated_token_budget: int = Field(default=4000)


class SpecialistExecutionResult(BaseModel):
    """Normalized deliverable emitted by Specialist back to Coordinator."""
    task_id: str
    source_role: SpecialistRole
    status: str = Field(..., regex="^(completed|blocked|requires_clarification)$")
    findings_summary: str
    cited_evidence_ids: List[str] = Field(default_factory=list)
    proposed_actions: List[Dict[str, Any]] = Field(default_factory=list)
    steps_executed: int
    tokens_consumed: int
```

---

## 4. Failure Modes Matrix & Resilience Invariants

| Quadrant | Failure Scenario | Detection Mechanism | Systemic Mitigation & Recovery |
| :--- | :--- | :--- | :--- |
| **Q1: Known Knowns** | **Circular Delegation Loops ($KK2$)**: Agent A delegates to Agent B, which attempts to delegate back to Agent A, exhausting resources. | Depth tracker flags depth $\ge 2$ in delegation coordinator. | Architectural barrier: Depth is strictly fixed to $1$ (`MA-D8`); specialists possess zero delegation tools and can only return results. |
| **Q2: Known Unknowns** | **Specialist Domain Misalignment ($KK5$)**: A database connection issue is erroneously routed to Billing because the user mentioned their billing account ID. | Jev Router (`MA-ADP-02`) evaluates masked intent vector. | Jev evaluates structured intent; if delegation confidence $< 0.50$, the system trips to Human Specialist rather than misrouting. |
| **Q3: Unknown Knowns** | **Inconsistent Personas & Tone ($UK2$)**: Specialists emit contradictory conversational styles, confusing the enterprise customer. | Customer-facing message interceptor detects specialist socket writes. | Architectural barrier: Specialists never speak to users (`MA-D12`); Coordinator alone drafts replies using unified corporate persona (`MA-D17`). |
| **Q4: Unknown Unknowns** | **Uncovered Enterprise Domain Gap ($UU5$)**: Customer inquires about a newly launched product category not covered by Billing, Tech, or Ops. | Jev Router detects low domain fit across all specialists. | Jev `Choice` includes `"generalist"` option; if domain fit is low across specialists, Generalist handles query or escalates to HITL. |

---

## 5. Closed-Loop Feedback & Verification Signals

1. **System Health Telemetry**:
   - `Specialist_Invocation_Distribution`: Tracks invocation rates across Billing, Technical, Ops, and Generalist.
   - `SubGraph_Execution_Duration_p95`: Monitored per specialist; alerts if any specialist takes $> 4.0\text{s}$ to execute internal turns.
   - `Blocked_Task_Rate`: Tracks how frequently specialists return `status="blocked"`, signaling missing tools or ambiguous briefs.
2. **Multi-Agent Evaluation Harness (MAST Suite)**:
   - Run the Multi-Agent Systems Test (MAST; Cemri et al., 2025) in CI, asserting that zero inter-agent misalignment or specification crashes occur across $200$ synthetic cross-domain test trajectories.

---

## 6. Genesis Implementation Directives

1. **Code Locations**:
   - Implement topology definitions and registry in `core/multiagent/topology.py`.
   - Implement the Coordinator LangGraph node in `core/multiagent/coordinator.py`.
   - Implement specialist subgraphs in `core/multiagent/specialists/` (`billing.py`, `technical.py`, `account_ops.py`, `generalist.py`).
   - Register static descriptors in `config/agent_registry.yaml`.
2. **LangGraph StateGraph Integration**:
   - In `core/orchestrator/statechart.py`, register specialist subgraphs:
     ```python
     workflow = StateGraph(CaseState)
     workflow.add_node("coordinator", coordinator_node)
     workflow.add_node("technical_specialist", technical_subgraph)
     workflow.add_node("billing_specialist", billing_subgraph)
     workflow.add_conditional_edges("coordinator", route_delegation)
     ```

---

## 7. Consequences & Trade-offs

### Positive Consequences
- **Bounded Message Complexity**: Strict hierarchical command eliminates $O(N^2)$ chatter and conversational looping, capping communication at $2N$.
- **Unified Transactional Durability**: Executing specialists as in-graph subgraphs preserves single-checkpoint consistency in Postgres without distributed RPC overhead.
- **Pristine Role Isolation**: Enforcing least-privilege tool subsets prevents cross-domain tool leakage (e.g., Billing agents cannot reboot cloud servers).

### Negative Consequences & Trade-offs
- **Token Overhead vs. Single-Agent Architecture**: Running multi-specialist turns incurs $\approx 3\times$ higher token usage than single-agent execution due to task briefs and coordinator synthesis.
- **Static Extensibility Constraint**: Adding a new specialist requires a code release and graph recompilation rather than dynamic runtime registration.
- **Coordinator Bottleneck**: All cross-domain analysis must funnel through the Coordinator node, introducing a single point of cognitive synthesis.

---

## 8. References & Cross-Disciplinary Grounding

1. **The Structuring of Organizations**: Mintzberg, H. (1979). Prentice Hall. (Foundations of Direct Supervision and Standardized Deliverables in Hierarchies).
2. **National Incident Management System (NIMS) - Incident Command System**: Federal Emergency Management Agency (FEMA). (Principles of Unified Command and Span of Control).
3. **Why Do Multi-Agent LLM Systems Fail? An Empirical Study of Failure Modes**: Cemri, M., et al. (2025). arXiv:2502.12345. (MAST Benchmark on inter-agent misalignment).
4. **Building Effective Agents**: Anthropic Research. (2024). (Engineering trade-offs between monolithic agents and orchestrator-worker swarms).
