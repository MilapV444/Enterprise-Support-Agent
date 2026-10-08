# MS-ADP-04: Agent State & Durability (Postgres LangGraph Checkpointer, Two-Phase Side-Effect Idempotency & Stale-State Revalidation)

- **Status**: Accepted & Confirmed
- **Date**: 2026-09-26 *(Amended: 2026-09-26 per MS-D8 State Separation, MS-D9 Two-Phase Checkpoints, MS-D13 Schema Migrations & MS-D18 Stale Revalidation)*
- **Deciders**: Architecture Team, Lead Distributed Systems Engineer, AI Orchestration Core
- **Component**: `[3] Memory & State` (`Component [ 3 ]`)
- **Reasoning Source**: `checkpoint.md` §7 · Diagram: `LLD - [3] Memory & State`
- **Decisions Covered**:
  - `MS-D7`: Large Working Memory Tool Outputs — Externalized by-reference blob storage with inline scratchpad summaries; on-demand paging tool calls
  - `MS-D8`: Single Source of Cognitive State Truth — LangGraph Postgres Checkpointer holds complete cognitive graph state; Temporal workflow history holds only workflow status and active `checkpoint_id` (decouples Temporal history limits)
  - `MS-D9`: Checkpoint Granularity & Idempotency Fence — Checkpoints committed after every graph node and immediately before and after every side-effecting tool invocation; deterministic idempotency keys (`checkpoint_id + tool_call_id`) eliminate duplicate mutations on crash recovery ($KK1$)
  - `MS-D13`: Checkpoint Schema Versioning & Resilient Migrations — Versioned state schemas with registered forward migration transformers; unmapped legacy schemas fail safe to Human-in-the-Loop ($KK4$)
  - `MS-D18`: Stale-World Revalidation on Long Resumption — Any resumption after a wait exceeding $1$ hour ($\Delta t > 3600\text{s}$) forces an automatic re-fetch of dependent tool state and re-verifies pre-conditions before mutation ($UU3$)
- **Related Architectural Decision Points**:
  - [`ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/00-orchestration-core/ADP-02-workflow-durability.md): Workflow Execution & Durability Substrate *(Two-Tier Temporal + LangGraph Topology)*
  - [`TA-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#ta-adp-04--execution-credentials--isolation): Tool Execution, Credentials & Isolation *(Tool Worker Isolation)*
  - [`TA-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#ta-adp-05--transactional-integrity--audit): Transactional Integrity & Audit *(Temporal Saga Compensations)*
  - [`DL-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#dl-adp-04--state-schema-migrations): State Schema Migrations *(Evolution of Long-Lived Paused States)*

---

## 1. Context & Problem Statement

Enterprise customer support workflows frequently span hours or days. A refund request over $\$1,000$ requires supervisor approval (`TA-ADP-03`); an infrastructure tenant migration requires awaiting off-peak maintenance windows; a complex billing audit requires a customer to locate legacy purchase orders.

In this asynchronous distributed operating environment, naive agent state storage creates severe systemic failures:

1. **The Double-Execution Financial Disaster ($KK1$)**: An agent executes an external refund API call (`stripe.refunds.create($1,240)`). The payment processor successfully debits the account, but the worker node crashes or network disconnects before the turn completes. Upon recovery, the agent re-executes the step from its last turn-level checkpoint, issuing a duplicate refund.
2. **Temporal Workflow History Exhaustion & Bloat ($MS-D8$)**: If high-frequency cognitive turns, LLM scratchpads, and large tool payloads (e.g., $40\text{KB}$ billing ledger exports) are persisted directly inside Temporal workflow event histories, the workflow rapidly breaches Temporal's $50,000$ event / $50\text{MB}$ payload history limit, forcing complex `Continue-As-New` resets and slowing replay execution.
3. **The Schema Evolution Deserialization Collapse ($KK4$)**: While an approval waits for three days in `AWAITING_APPROVAL`, engineering deploys a new agent release with an updated LangGraph state schema (e.g., renaming `user_params` to `collected_intent_parameters`). When the human approves the ticket, the deserializer crashes on the stale schema, stranding the ticket in an unrecoverable zombie state.
4. **The Stale-World Hallucination Exploit ($UU3$)**: A customer requests an account credit because their balance is $\$500$. The approval is granted three days later. During those three days, an automated batch run charged the customer's card, zeroing the balance. If the agent resumes and acts on the cached working memory without checking reality, it credits an account that no longer has an active charge.

### The Core Architectural Question
> **How do we decouple high-frequency cognitive state from workflow orchestration, guarantee absolute at-most-once execution for financial side effects, and safely resume long-paused agents across schema migrations and shifting external realities?**

---

## 2. Decision Framework & Theoretical Formulation

To solve these challenges, `MS-D8` and `MS-D9` establish the **Two-Tier State Decoupling Architecture with Two-Phase Tool Checkpointing**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                            TWO-TIER STATE ARCHITECTURE (MS-D8)                                   │
├─────────────────────────────────────────────────┬────────────────────────────────────────────────┤
│   ORCHESTRATION LAYER: TEMPORAL.IO              │   COGNITIVE STATE LAYER: LANGGRAPH POSTGRES    │
│   Durable Multi-Day Workflow Sagas              │   High-Frequency Cognitive Checkpoints         │
│                                                 │                                                │
│   • Workflow ID: wf_case_inv9821                │   • Checkpoint ID: chk_9021a_step3             │
│   • Workflow Status: RUNNING                    │   • Current FSM Node: AWAITING_APPROVAL        │
│   • Durable Timers & Escalation Signals         │   • Full Turn Trajectory & Collected Params    │
│   • Pointer: active_checkpoint_id = "chk_9021a" │   • Version Tag: schema_version = 2            │
│   • Payload Size: < 2 KB (Zero History Bloat)   │   • Persisted in Postgres 'checkpoints' table  │
└─────────────────────────────────────────────────┴────────────────────────────────────────────────┘
```

---

### Pillar A: State Truth Decoupling & Virtual Memory References

We partition the global agent runtime into three distinct persistence planes:
$$\text{Runtime State} = \langle \mathcal{W}_{\text{Temporal}}, \mathcal{C}_{\text{Postgres}}, \mathcal{B}_{\text{BlobStore}} \rangle$$

1. **Temporal Control Plane ($\mathcal{W}_{\text{Temporal}}$)**:
   Maintains the outer saga execution pointer, durable multi-day timers, human escalation queues, and compensation logs (`ADP-02`). Temporal payload size is strictly $\mathcal{O}(1)$:
   $$\mathcal{W}_{\text{Temporal}} = \left\{ \text{workflow\_id}, \text{status}, \text{active\_checkpoint\_id}, \text{created\_at} \right\}$$
2. **LangGraph Cognitive Checkpointer ($\mathcal{C}_{\text{Postgres}}$)**:
   The single authoritative source of truth for the cognitive FSM state $S_t$ (`MS-D8`). Managed by `PostgresCheckpointer`, capturing graph reducers, variable dictionaries, and scratchpad counters.
3. **Working Memory Blob Store ($\mathcal{B}_{\text{BlobStore}}$, `MS-D7`)**:
   Tool outputs exceeding $4\text{KB}$ (e.g., raw JSON ledgers, log extracts) are offloaded to Postgres `tool_output_blobs` or S3, keyed by `(case_id, turn_id, tool_call_id)`.
   The working memory scratchpad retains only a virtual memory descriptor:
   $$\text{Descriptor} = \left\{ \text{blob\_id}, \text{byte\_size}, \text{summary}: \text{"42 invoice line items totaling \$12,400"} \right\}$$
   The agent can dynamically inspect specific line items via pagination tools (`tool_inspect_blob_page`), preventing scratchpad token explosion (`ADP-03`).

---

### Pillar B: Two-Phase Checkpointing & Deterministic Idempotency Fence (`MS-D9`)

To guarantee zero duplicate side-effects ($KK1$), every mutating or financial tool invocation follows a strict two-phase atomic fence protocol:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                     TWO-PHASE IDEMPOTENCY CHECKPOINT FENCE (MS-D9)                               │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

Step 1: Commit Pre-Call Checkpoint (S_t)
        Status: PENDING_TOOL_EXECUTION
        Idempotency Key: K_idem = HMAC(checkpoint_id || tool_call_id)
           │
           ▼
Step 2: Dispatch External Mutation Tool (e.g., Stripe API, AWS IAM)
        Headers: Idempotency-Key: K_idem
           │
           ├───► [CRASH OCCURS HERE] ──► Resume loads S_t
           │                             Re-sends K_idem ──► Downstream returns cached 200 OK
           ▼
Step 3: Commit Post-Call Checkpoint (S_{t+1})
        Status: TOOL_EXECUTION_COMPLETED
        Payload: ToolResult / BlobDescriptor
```

#### Deterministic Idempotency Key Formulation
For any side-effecting action $a_k$ invoked at checkpoint $S_t$:
$$K_{\text{idem}} = \text{HMAC-SHA256}\left(\text{checkpoint\_id} \,\|\, \text{tool\_call\_id}, \mathcal{K}_{\text{tenant\_secret}}\right)$$

If a crash or container restart occurs during tool execution:
1. Worker restarts and loads checkpoint $S_t$ (pre-call state).
2. The agent re-submits the tool call carrying the exact deterministic key $K_{\text{idem}}$.
3. The downstream enterprise API recognizes $K_{\text{idem}}$, skips re-execution, and returns the cached result, strictly preventing duplicate billing or provisioning.

---

### Pillar C: Schema Versioning, Migrations & Stale Revalidation

#### Resilient Schema Migration Pipeline (`MS-D13`)
Every checkpoint record stores an explicit integer schema version:
$$S_t = \langle v, \text{Payload} \rangle, \quad v \in \mathbb{N}$$

On load:
$$S_{\text{active}} = \begin{cases}
S_t & \text{if } v = v_{\text{current}} \\
\mathcal{T}_{v \to v_{\text{current}}}(S_t) & \text{if a registered forward migration path exists} \\
\text{TripToHITL}(S_t, \text{ERR\_UNSUPPORTED\_SCHEMA}) & \text{if no migration path exists}
\end{cases}$$
An unknown schema version never crashes silently or restarts from turn 1; it safely packages state and alerts engineering.

#### Stale-World Revalidation Barrier (`MS-D18`)
When an agent wakes from a long wait (e.g., human supervisor approval or customer delay):
$$\Delta t_{\text{wait}} = t_{\text{resume}} - t_{\text{checkpoint\_committed}}$$

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   STALE-WORLD RESUMPTION REVALIDATION PROTOCOL (MS-D18)                          │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                       Agent Resumes from Wait (e.g., Human Approval)
                                                │
                                                ▼
                                    Is Δt_wait > 3600 seconds (1 hour)?
                                                │
                                ┌───────────────┴───────────────┐
                                │ YES                           │ NO
                                ▼                               ▼
                Execute Pre-Condition Re-fetch           Resume Immediately from S_t
                • Re-read account balance from CRM       (Standard fast execution)
                • Re-read cluster provisioning state
                                │
                                ▼
                Have preconditions changed?
                                │
                ┌───────────────┴───────────────┐
                │ YES                           │ NO
                ▼                               ▼
  Divergence Detected!            Pre-conditions Valid.
  • Invalidate prior approval     Execute pending approved action.
  • Route back to FSM node
  • Notify specialist of state drift
```

---

## 3. Decision Rules, Structural Invariants & Code Contracts

### Decision Invariants
1. **Invariant 1 (Checkpoint Inviolability)**: Checkpoints MUST be committed to Postgres before any external HTTP call that modifies downstream state is dispatched.
2. **Invariant 2 (Temporal History Limit Ceiling)**: Workflow activity wrappers must never return raw graph states or payloads exceeding $10\text{KB}$ to Temporal. Only the `checkpoint_id` string is returned.
3. **Invariant 3 (Mandatory Revalidation for $\Delta t > 1\text{h}$)**: If the elapsed time between approval submission and resumption exceeds $3,600$ seconds, the workflow engine MUST execute fresh read-only tools to verify external invariants before dispatching mutations.
4. **Invariant 4 (Blob Dereferencing Bounds)**: The orchestrator context assembler must never hydrate full blobs into the prompt context; blobs are paged exclusively through explicit tool invocations.

---

### Python & Pydantic Data Contracts

```python
"""
Data contracts for Agent State, Durability, and Checkpointing.
Module: core/state/durability.py
"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class CheckpointStage(str, Enum):
    NODE_COMPLETED = "node_completed"
    PRE_TOOL_EXECUTION = "pre_tool_execution"
    POST_TOOL_EXECUTION = "post_tool_execution"
    AWAITING_EXTERNAL_SIGNAL = "awaiting_signal"


class ToolOutputBlobDescriptor(BaseModel):
    """Virtual memory reference for offloaded tool outputs (MS-D7)."""
    blob_id: str = Field(..., description="UUID in blob storage")
    tool_call_id: str
    content_type: str = Field(default="application/json")
    byte_size: int
    summary: str = Field(..., description="LLM-generated semantic abstract of the blob")
    total_pages: int
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AgentStateCheckpoint(BaseModel):
    """Authoritative cognitive state snapshot persisted in Postgres (MS-D8)."""
    checkpoint_id: str = Field(..., description="Unique deterministic checkpoint UUID")
    tenant_id: str
    case_id: str
    conversation_id: str
    schema_version: int = Field(default=1, description="State schema version for migrations")
    
    stage: CheckpointStage
    current_node: str = Field(..., description="Current LangGraph FSM node name")
    
    # State payload
    channel_params: Dict[str, Any] = Field(default_factory=dict)
    collected_entities: Dict[str, Any] = Field(default_factory=dict)
    reflexion_trial_count: int = Field(default=0)
    step_count: int = Field(default=0)
    
    # Pending side effects (for two-phase fencing)
    pending_tool_call_id: Optional[str] = None
    pending_idempotency_key: Optional[str] = None
    
    blob_references: List[ToolOutputBlobDescriptor] = Field(default_factory=list)
    committed_at: datetime = Field(default_factory=datetime.utcnow)


class RevalidationCheckResult(BaseModel):
    """Output contract for resumption pre-condition verification (MS-D18)."""
    checkpoint_id: str
    elapsed_seconds: float
    revalidation_performed: bool
    state_divergence_detected: bool
    divergence_details: Optional[str] = None
    suggested_action: str = Field(
        ..., 
        description="'PROCEED' if unchanged, 'ABORT_TO_HITL' if stale invariants"
    )
```

---

## 4. Failure Modes Matrix & Resilience Invariants

| Quadrant | Failure Scenario | Detection Mechanism | Systemic Mitigation & Recovery |
| :--- | :--- | :--- | :--- |
| **Q1: Known Knowns** | **Duplicate Mutation on Crash ($KK1$)**: Worker dies immediately after issuing a $\$500$ credit; on restart, executes the refund again. | Downstream gateway rejects duplicate idempotency key or logs dual mutation. | Pre-call checkpoint commits deterministic key $K_{\text{idem}}$ before dispatch (`MS-D9`); downstream API recognizes key and safely returns cached response. |
| **Q2: Known Unknowns** | **High Checkpoint Write Saturation ($KU3$)**: Checkpointing per node and twice per mutating tool creates high Postgres TPS write load during traffic surges. | Postgres connection pool exhaustion and elevated write latency alerts in Prometheus. | Postgres checkpoint commits use asynchronous batch WAL flushing and partitioned unlogged scratch tables for ephemeral transitions (`DP-ADP-01`). |
| **Q3: Unknown Knowns** | **Schema Evolution Breakage ($KK4$)**: A three-day-old paused ticket fails to resume because code was refactored with new state variables. | Deserialization validator flags `schema_version < current_version`. | Forward schema migration functions transform legacy state dictionaries (`MS-D13`); unresolvable schemas trip safely to HITL queue. |
| **Q4: Unknown Unknowns** | **Resumption on Invalidated Realities ($UU3$)**: Specialist approves a $\$12,400$ billing adjustment four days later, but customer's subscription was canceled yesterday. | Resumption revalidation detector compares fresh CRM read with checkpoint state. | Automatic barrier (`MS-D18`): waits $>1\text{h}$ force live re-fetch; detected divergence halts mutation and alerts specialist. |

---

## 5. Closed-Loop Feedback & Verification Signals

1. **System Telemetry**:
   - `Checkpoint_Commit_Latency_p99`: Monitored via StatsD; alerts if Postgres checkpoint persistence exceeds $25\text{ms}$.
   - `Resumption_State_Divergence_Rate`: Tracks the percentage of resumptions ($>1\text{h}$) where external state diverged, quantifying the protection delivered by `MS-D18`.
   - `Blob_Page_In_Frequency`: Tracks how often agents inspect large external tool outputs via paging.
2. **Chaos Engineering Verification**:
   - Continuous chaos test worker injects random SIGKILL signals into workers during tool execution steps, asserting that zero duplicate tool calls occur across $1,000$ simulated financial mutations.

---

## 6. Genesis Implementation Directives

1. **Code Locations**:
   - Implement Postgres checkpointer in `core/state/postgres_checkpointer.py`.
   - Implement idempotency key generation and two-phase fences in `core/tools/idempotency.py`.
   - Implement schema version registry and migrations in `core/state/migrations.py`.
   - Implement resumption revalidation logic in `core/orchestrator/revalidation.py`.
   - Implement blob storage offloading in `core/memory/blobs.py`.
2. **Temporal Integration**:
   - In `workflows/ticket_lifecycle_workflow.py`, activities accept only `(tenant_id, case_id, checkpoint_id)` and return updated `checkpoint_id`.

---

## 7. Consequences & Trade-offs

### Positive Consequences
- **Absolute Mutation Safety**: Two-phase idempotency fencing mathematically eliminates duplicate execution of side-effecting financial and provisioning tools.
- **Infinite Workflow Longevity**: Keeping large cognitive graph states out of Temporal allows multi-week sagas without ever approaching event history ceilings.
- **Robustness Against Long-Wait Drift**: Enforcing live revalidation prevents agents from acting on stale approvals and invalidated commercial states.

### Negative Consequences & Trade-offs
- **Postgres IOPS Load**: Checkpointing per node and around side-effects significantly increases database write volume compared to turn-level checkpoints.
- **Resume Latency for Long Waits**: The mandatory re-validation check adds $100–300\text{ms}$ of tool fetching latency when resuming workflows that waited $>1\text{hour}$.
- **Developer Overhead for Schema Migrations**: Every structural modification to the agent state model requires authoring and testing a deterministic forward migration script.

---

## 8. References & Cross-Disciplinary Grounding

1. **Distributed Sagas & Compensating Transactions**: Garcia-Molina, H., & Salem, K. (1987). *ACM SIGMOD Record*. (Theoretical basis for two-phase durable transactions).
2. **Temporal Architecture & Event History Management**: Temporal Technologies. (2024). *Workflow Execution Limits and Continue-As-New Patterns*.
3. **MemGPT: Towards LLMs as Operating Systems**: Packer, C., et al. (2023). arXiv:2310.08560. (Virtual memory paging and by-reference blob storage design).
4. **Idempotency in Distributed Financial Systems**: RFC 7395 / Stripe Engineering. (2017). *Designing Robust Idempotent APIs with Distributed Mutexes*.
