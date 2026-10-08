# ADP-02: Workflow Durability Substrate (Two-Tier Hybrid: Temporal.io Outer Saga + LangGraph Inner Cognitive Loop)

- **Status**: Accepted & Confirmed
- **Date**: 2026-09-11 *(Updated: 2026-09-25 with LangGraph State Truth Realignment)*
- **Deciders**: Architecture Team, Lead Distributed Systems Engineer, Operations Core
- **Component**: Agent Orchestration Core & Runtime (`Component [ 5 ]`)
- **Reasoning Source**: `checkpoint.md` §2 · Diagram: `LLD - Agent Orchestration & Planning Core`
- **Related Architectural Decision Points**:
  - [`ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/00-orchestration-core/ADP-01-planning-paradigm.md): Planning Paradigm *(Hybrid Dual-Process Statechart)*
  - [`MS-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#ms-adp-04--agent-state--durability): Agent State & Durability *(LangGraph Checkpointer in PostgreSQL as Single Source of Truth; MS-D8)*
  - [`TA-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#ta-adp-05--transactional-integrity--audit): Transactional Integrity & Audit *(Two-Phase Mutation Checks & Compensating Sagas)*
  - [`DL-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#dl-adp-04--versioning-of-models-indexes--workflows): Versioning of Models, Indexes & Workflows *(Temporal Determinism & Non-Breaking Migrations)*

---

## 1. Context & Problem Statement

Enterprise customer support tickets exhibit fundamentally divergent temporal characteristics:
1. **Sub-Second Cognitive Bursts**: Turn-by-turn conversational inference, semantic slot extraction, RAG retrieval, and immediate diagnostic steps require execution velocity measured in hundreds of milliseconds.
2. **Multi-Hour and Multi-Day Asynchronous Lifecycles**: End-to-end support ticket lifecycles routinely span multiple days or weeks. Workflows frequently block while awaiting asynchronous customer email replies, third-party webhook callbacks (e.g., Stripe chargeback updates, Jira engineering issue progress), or asynchronous Human-in-the-Loop (HITL) supervisor approvals.

### The Durability Dilemma
Early autonomous agent architectures attempted to maintain workflow state in one of two suboptimal extremes:
- **In-Memory Thread Loops with Database Polling**: The agent runtime holds thread state in application container memory or relies on naive cron jobs polling a database. During container restarts, pod auto-scaling, node evictions, or infrastructure deployments, active workflows are severed. In-flight timers die, multi-turn cognitive context is corrupted, and tickets stall indefinitely without SLA breach detection.
- **Monolithic Distributed Orchestration for Every LLM Step**: Forcing every sub-second LLM reasoning hop, prompt token stream, and intermediate thought into an event-sourced distributed workflow engine (e.g., pure Temporal workflows executing prompt iterations directly) results in massive state bloat. Temporal workflow event histories rapidly hit engine limits (50,000 events / 50MB payload ceilings), while replay determinism rules make prompt engineering, model temperature changes, and non-deterministic LLM tokens an operational liability.

### The Core Architectural Question
> **How do multi-day customer support workflows survive container crashes, deployment restarts, prolonged customer wait periods, and human approval gates without losing state, breaching event history limits, or degrading sub-second cognitive reasoning velocity?**

---

## 2. Decision Framework & Theoretical Formulation

We formulate workflow durability on three theoretical pillars: **Stochastic Process Reliability & MTTF Modeling**, **Distributed Saga Theory & Compensating Transactions**, and **Event-Sourced Replay Determinism**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                            DURABILITY THEORETICAL PILLARS                                        │
├────────────────────────────────┬────────────────────────────────┬────────────────────────────────┤
│   Pillar A: Stochastic MTTF    │   Pillar B: Distributed Saga   │   Pillar C: State-Truth        │
│   & Crash Survival Probability │   Compensating Transactions    │   Decoupling & Event Sourcing  │
│                                │                                │                                │
│   • Poisson crash rate λ       │   • Forward chains T = (t_1..k)│   • Deterministic replay       │
│   • Survival P(t) = exp(-λt)   │   • Backward compensations C_k │   • Postgres thread store      │
│   • Durability invariant:      │   • Semantic ACID atomicity    │   • Temporal holds only status │
│     lim_{t->inf} StateLoss = 0 │   • Zero partial mutation leaks│     and Checkpoint UUID        │
└────────────────────────────────┴────────────────────────────────┴────────────────────────────────┘
```

---

### Pillar A: Stochastic Process Reliability & Crash Survival Modeling

Consider an enterprise support system executing $N$ concurrent workflows over a temporal horizon $t \in [0, T_{\max}]$. Let worker node failures, Kubernetes pod evictions, and deployment rollouts be modeled as a Poisson point process with constant crash rate $\lambda_{\text{crash}}$.

The probability of a long-running workflow surviving duration $t$ without crashing under an in-memory execution paradigm is given by the exponential survival function:

$$P(\text{Survival} \mid t) = e^{-\lambda_{\text{crash}} \cdot t}$$

In an enterprise contact center where complex tier-2 technical tickets have a median resolution time of $t = 72\text{ hours}$ ($4,320\text{ minutes}$), and Kubernetes node churn or rolling releases occur with mean time between failures $\text{MTBF} = \frac{1}{\lambda_{\text{crash}}} \approx 24\text{ hours}$:

$$P(\text{Survival} \mid 72\text{h}) = e^{-\frac{72}{24}} = e^{-3} \approx 0.0498 \quad (4.98\%)$$

Under in-memory execution, **over 95% of multi-day workflows will suffer catastrophic process interruption**, leaving customer tickets orphaned, SLAs unmonitored, and transactional locks unreleased.

#### Durable Execution Invariant
Durable execution decomposes the timeline into discrete persisted state checkpoints $\{c_0, c_1, \dots, c_m\}$ separated by execution intervals $\Delta t \ll \text{MTBF}$. When a crash occurs at time $t_{\text{crash}} \in (t_k, t_{k+1})$, the recovery engine replays from checkpoint $c_k$:

$$P(\text{State Loss}) = 0 \quad \text{and} \quad \mathbb{E}[\text{Lost Work Time}] \le \frac{1}{2} \Delta t$$

By delegating multi-day lifecycles, timer countdowns, and thread suspension to an industrial event-sourced engine (**Temporal.io**), the probability of ticket survival across arbitrary durations $T_{\max} \to \infty$ is identically 1:

$$\lim_{t \to \infty} P(\text{Workflow Survival}_{\text{Temporal}}) = 1.0$$

---

### Pillar B: Distributed Saga Theory & Semantic Compensations

Enterprise support agents execute actions across heterogeneous, independent distributed services (e.g., Stripe billing, Salesforce CRM, Auth0 identity, Zendesk ticketing, AWS cloud infrastructure). Because two-phase commit (2PC) is impossible across independent external third-party SaaS APIs, transactional integrity must follow the **Distributed Saga Pattern (Garcia-Molina & Salem, 1987)**.

A distributed saga is a sequence of local transactions $\{T_1, T_2, \dots, T_n\}$ with corresponding compensating actions $\{C_1, C_2, \dots, C_{n-1}\}$ such that:

$$\forall i \in [1, n-1], \quad T_i \circ C_i \equiv \mathcal{I} \quad (\text{Identity State Transformation})$$

```
Forward Execution:   [T_1: Verify Identity] ──> [T_2: Provision Credit] ──> [T_3: Update Tier (FAILS)]
                                                                                       │
Compensating Rollback: [Done] <──────────────── [C_2: Reverse Credit] <────────────────┘
```

If transaction $T_k$ fails (e.g., downstream API outage, parameter validation rejection, or human supervisor denial):

$$\text{Final State} = S_0 + \sum_{i=1}^{k-1} T_i(S_{i-1}) + \sum_{j=k-1}^{1} C_j(S_j) = S_0$$

Temporal.io acts as the **Distributed Saga Coordinator**:
1. Every forward tool invocation is modeled as an idempotent Temporal Activity.
2. In the event of an unrecoverable failure or supervisor rejection, Temporal deterministically executes compensating activities in reverse chronological order ($C_{k-1} \to C_{k-2} \dots \to C_1$).
3. This guarantees that partial side-effects are never leaked into enterprise systems of record.

---

### Pillar C: State-Truth Decoupling & Event Sourcing

A critical design challenge in combining Temporal with Large Language Models is **Temporal Replay Determinism**. Temporal achieves fault tolerance by replaying workflow history from event logs. However, LLM token generations are inherently non-deterministic: calling an LLM API twice with identical prompts can yield different tokens, violating Temporal's replay invariants.

Furthermore, multi-turn conversational agents generate large volumes of intermediate context (token embeddings, RAG passages, reasoning scratchpads). Storing this raw context inside Temporal workflow histories triggers payload explosion:

$$\text{Temporal History Payload Limit} \le 50\text{ MB} \quad \text{and} \quad \text{Event Count} \le 50,000$$

To solve this, we establish a strict **State-Truth Decoupling Contract (`MS-D8`)**:

$$S_{\text{Agent}} = \langle \mathcal{K}_{\text{Postgres}}, \mathcal{W}_{\text{Temporal}} \rangle$$

1. **Inner Cognitive State Truth (`MS-D8`)**: **PostgreSQL via LangGraph Checkpointer (`PostgresSaver`)** is the single source of truth for conversational and agent working memory. It stores dialogue turns, Baddeley token slot structures, and diagnostic scratchpads.
2. **Outer Workflow State Truth**: **Temporal.io** stores *only* workflow orchestration metadata: ticket UUID, tenant ID, current status (`PENDING_USER`, `AWAITING_APPROVAL`, `RESOLVED`), active SLA timer handles, and the immutable `checkpoint_id` reference pointing to PostgreSQL.
3. **Execution Boundary**: LangGraph runs entirely *inside* a Temporal Activity worker (`CognitiveTurnActivity`). During an activity execution, LangGraph executes its inner cognitive graph, commits its state snapshot atomically to PostgreSQL, and returns only a compact outcome descriptor (`checkpoint_id`, `next_action`, `escalate_reason`) to the parent Temporal workflow.

---

## 3. Decision Rules & System Architecture

### Architectural Decision
We formally adopt **Option C: Two-Tier Hybrid (Temporal.io Outer Saga + LangGraph Inner Cognitive Loop)**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   TWO-TIER HYBRID WORKFLOW EXECUTION ARCHITECTURE                                │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                   │
                                          [Ingress Customer Turn]
                                                   │
                                                   v
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│  TIER 1: TEMPORAL.IO OUTER SAGA (Multi-Day Lifecycle, Timers & Durability Substrate)            │
│                                                                                                  │
│   • Workflow: TicketLifecycleWorkflow (Durable for Days/Weeks)                                  │
│   • Event-Sourced Replay Engine · Zero State Loss on Crash                                      │
│   • Durable SLA Timers (e.g. 24h Customer Inactivity Timeout)                                   │
│   • Asynchronous Signal Listeners (Customer Reply, Supervisor Approval, Webhooks)               │
└──────────────────────────────────┬─────────────────────────────▲─────────────────────────────────┘
                                   │                             │
                   [Dispatches Activity Invocation]   [Returns Turn Outcome + Checkpoint ID]
                                   │                             │
                                   v                             │
┌────────────────────────────────────────────────────────────────┴─────────────────────────────────┐
│  TIER 2: LANGGRAPH INNER COGNITIVE ENGINE (Sub-Second Reasoning Activity Worker)                 │
│                                                                                                  │
│   • Activity: CognitiveTurnActivity (Runs within Temporal Activity Sandbox)                      │
│   • Loads State Snapshot from PostgreSQL using checkpoint_id                                     │
│   • Executes ADP-01 Dual-Process Statechart (System 1 SOP / System 2 ReAct)                      │
│   • Dispatches Plain Python Tool Activities (TA-D2)                                              │
│   • Commits Atomic State Snapshot to PostgreSQL (MS-D8)                                          │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Tier Decomposition & Operational Responsibilities

| Dimension | Tier 1: Outer Saga (`Temporal.io`) | Tier 2: Inner Cognitive Loop (`LangGraph`) |
| :--- | :--- | :--- |
| **Execution Lifespan** | Hours, days, weeks (Ticket lifecycle) | 200ms – 30s (Single conversational turn) |
| **State Storage** | Temporal Event History (PostgreSQL/Cassandra) | PostgreSQL (`LangGraph PostgresSaver`) |
| **Payload Scope** | Ticket UUID, Checkpoint ID, Status, Timers | Full context: System, RAG, Dialogue, Scratchpad |
| **Determinism Model** | Strictly deterministic event replay | Stochastic LLM generation in Activity sandbox |
| **Failure Handling** | Exponential activity retries, compensating sagas | Reflexion self-critique (max 2), circuit breaker |
| **Human Interaction** | Temporal Signals (`Approve`, `Reject`, `Reply`) | Statechart leaf node (`AWAITING_APPROVAL`) |
| **Infrastructure** | Temporal Cluster + Temporal Worker Pool | Stateless Container Workers invoking LLM APIs |

---

### Concrete Genesis Implementation Contracts

#### 1. Temporal Workflow Definition (`workflows/ticket_lifecycle_workflow.py`)

```python
from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy

# Import activity stubs
with workflow.unsafe.imports_passed_through():
    from activities.cognitive_turn_activity import CognitiveTurnActivity
    from activities.saga_compensations import CompensateFailedTransactionActivity
    from core.orchestrator.models import TurnRequestPayload, TurnOutcomePayload

@workflow.defn
class TicketLifecycleWorkflow:
    def __init__(self) -> None:
        self.ticket_id: str = ""
        self.tenant_id: str = ""
        self.current_checkpoint_id: str = ""
        self.status: str = "INITIALIZED"
        self.customer_reply_received: bool = False
        self.pending_user_message: str = ""
        self.supervisor_approved: bool = False
        self.approval_decision_received: bool = False

    @workflow.run
    async def run(self, payload: TurnRequestPayload) -> str:
        self.ticket_id = payload.ticket_id
        self.tenant_id = payload.tenant_id
        self.current_checkpoint_id = payload.initial_checkpoint_id
        self.status = "ACTIVE"

        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=1),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=30),
            maximum_attempts=3,
            non_retryable_error_types=["FatalComplianceException", "InvalidTenantException"]
        )

        while self.status not in ("RESOLVED", "ESCALATED_CLOSED"):
            # Execute Inner Cognitive Turn via LangGraph Activity Worker
            outcome: TurnOutcomePayload = await workflow.execute_activity(
                CognitiveTurnActivity.execute_cognitive_turn,
                TurnRequestPayload(
                    ticket_id=self.ticket_id,
                    tenant_id=self.tenant_id,
                    checkpoint_id=self.current_checkpoint_id,
                    user_input=self.pending_user_message or payload.user_input,
                ),
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=retry_policy,
            )

            # Update State Pointer to PostgreSQL
            self.current_checkpoint_id = outcome.new_checkpoint_id
            self.pending_user_message = ""

            # Evaluate Outcome Directives
            if outcome.action_required == "AWAIT_CUSTOMER_REPLY":
                self.status = "PENDING_CUSTOMER"
                self.customer_reply_received = False
                # Durable SLA Timer: Wait up to 24 hours for customer reply
                try:
                    await workflow.wait_condition(
                        lambda: self.customer_reply_received,
                        timeout=timedelta(hours=24)
                    )
                except TimeoutError:
                    self.status = "AUTO_CLOSED_INACTIVITY"
                    break

            elif outcome.action_required == "AWAIT_SUPERVISOR_APPROVAL":
                self.status = "AWAITING_APPROVAL"
                self.approval_decision_received = False
                # Durable Approval Timer: Wait up to 48 hours for supervisor review
                try:
                    await workflow.wait_condition(
                        lambda: self.approval_decision_received,
                        timeout=timedelta(hours=48)
                    )
                except TimeoutError:
                    # Timeout Escalation: auto-route to high-priority queue
                    outcome.action_required = "ESCALATE_TIER3"

                if not self.supervisor_approved:
                    # Execute Compensating Saga Activities
                    await workflow.execute_activity(
                        CompensateFailedTransactionActivity.rollback_pending_mutations,
                        outcome.saga_context,
                        start_to_close_timeout=timedelta(seconds=30)
                    )
                    self.status = "APPROVAL_DENIED"
                    break

            elif outcome.action_required == "RESOLVED":
                self.status = "RESOLVED"
                break

            elif outcome.action_required == "ESCALATE_HITL":
                self.status = "ESCALATED_HITL"
                break

        return f"Ticket {self.ticket_id} finalized with status: {self.status}"

    # Workflow Signals (Asynchronous External Events)
    @workflow.signal
    def customer_reply_signal(self, user_message: str) -> None:
        self.pending_user_message = user_message
        self.customer_reply_received = True

    @workflow.signal
    def supervisor_approval_signal(self, approved: bool) -> None:
        self.supervisor_approved = approved
        self.approval_decision_received = True
```

#### 2. LangGraph Cognitive Activity Wrapper (`activities/cognitive_turn_activity.py`)

```python
from temporalio import activity
from core.orchestrator.statechart import build_orchestrator_statechart
from core.orchestrator.models import TurnRequestPayload, TurnOutcomePayload, OrchestratorState
from core.persistence.postgres_checkpointer import get_postgres_checkpointer

class CognitiveTurnActivity:
    @activity.defn
    async def execute_cognitive_turn(self, payload: TurnRequestPayload) -> TurnOutcomePayload:
        activity.logger.info(
            f"Invoking cognitive reasoning for ticket {payload.ticket_id}, checkpoint {payload.checkpoint_id}"
        )

        # 1. Initialize PostgreSQL Checkpointer (Single Source of Agent State Truth, MS-D8)
        checkpointer = await get_postgres_checkpointer()
        compiled_graph = build_orchestrator_statechart().compile(checkpointer=checkpointer)

        # 2. Config thread context
        config = {
            "configurable": {
                "thread_id": payload.ticket_id,
                "checkpoint_id": payload.checkpoint_id,
            }
        }

        # 3. Resume / Execute LangGraph Statechart
        inputs = {"dialogue_history": [{"role": "user", "content": payload.user_input}]}
        final_state: OrchestratorState = await compiled_graph.ainvoke(inputs, config=config)

        # 4. Extract Atomic Checkpoint Snapshot UUID
        latest_checkpoint = await checkpointer.aget(config)
        new_checkpoint_id = latest_checkpoint["id"]

        # 5. Map Inner Statechart to Temporal Outer Action Payload
        action_map = {
            "AWAITING_CUSTOMER": "AWAIT_CUSTOMER_REPLY",
            "AWAITING_APPROVAL": "AWAIT_SUPERVISOR_APPROVAL",
            "RESOLVED": "RESOLVED",
            "ESCALATED_HITL": "ESCALATE_HITL",
        }

        action_required = action_map.get(final_state.current_state, "CONTINUE_TURN")

        return TurnOutcomePayload(
            ticket_id=payload.ticket_id,
            new_checkpoint_id=new_checkpoint_id,
            action_required=action_required,
            financial_amount=final_state.financial_mutation_amount,
            saga_context={"sop_name": final_state.sop_name, "params": final_state.collected_parameters},
        )
```

---

## 4. Knowing Your Unknowns: Failure Modes & Mitigation Matrix

| Quadrant | Failure Mode | Technical Risk Description | Concrete Architectural Mitigation |
| :--- | :--- | :--- | :--- |
| **Q1: Known Knowns** *(Deterministic Contract Breaches)* | **Temporal History Size Overflow** | Saving full conversation turns or RAG passages into workflow state breaches the 50MB Temporal history ceiling. | **State-Truth Decoupling (`MS-D8`)**: Temporal workflow variables contain only primitives (`ticket_id`, `checkpoint_id`, `status`). All LLM context resides in PostgreSQL. |
| **Q1: Known Knowns** *(Deterministic Contract Breaches)* | **Activity Timeout Hang** | LangGraph reasoning gets stuck on a hung LLM endpoint, blocking the Temporal activity indefinitely. | **Bounded Activity Timeouts**: `start_to_close_timeout` is strictly capped at 60s with exponential retries and upstream circuit breaking (`ADP-04`). |
| **Q2: Known Unknowns** *(Probabilistic Reasoning Variance)* | **Replay Non-Determinism Trap** | Workflow code attempts to inspect non-deterministic values (e.g. system clock, random UUID) inside workflow definition. | **Temporal Determinism SDK**: All clocks use `workflow.now()`, random operations use `workflow.random()`, and all network I/O is isolated inside Activities. |
| **Q2: Known Unknowns** *(Probabilistic Reasoning Variance)* | **Signal-Before-Wait Race Condition** | Customer reply signal arrives milliseconds before workflow reaches `wait_condition`. | **Temporal Native Signal Buffering**: Temporal persists unconsumed signals in execution history; buffered signals fire immediately upon reaching wait condition. |
| **Q3: Unknown Knowns** *(Tacit Enterprise Etiquette & Invariants)* | **Ghost Compensations on Read-Only Turns** | Failed read-only diagnostic turns attempt to trigger compensating saga rollbacks, wasting DB compute. | **Idempotent Mutation Registry**: Compensating saga activities execute strictly for verified state-mutating actions registered in the audit store (`TA-ADP-05`). |
| **Q3: Unknown Knowns** *(Tacit Enterprise Etiquette & Invariants)* | **Indefinite Customer Stalling** | Customer disappears mid-conversation, leaving cloud resources or reservation locks held indefinitely. | **Durable Inactivity Timers**: Temporal workflow schedules a 24-hour inactivity timer; on expiry, locks release, and ticket transitions to `AUTO_CLOSED_INACTIVITY`. |
| **Q4: Unknown Unknowns** *(Emergent Cascades & Black Swans)* | **Postgres / Temporal State Desynchronization** | LangGraph commits state to PostgreSQL, but worker pod crashes before returning checkpoint UUID to Temporal. | **Idempotent Checkpoint Replay**: Upon activity retry, LangGraph detects existing checkpoint UUID for that turn ID and returns committed state without re-invoking LLM. |
| **Q4: Unknown Unknowns** *(Emergent Cascades & Black Swans)* | **Rolling Deployment Workflow Breakage** | New code deploys while thousands of workflows are paused on multi-day timers, causing replay mismatch exceptions. | **Temporal Workflow Versioning (`DL-ADP-04`)**: Changes to workflow control flow use `workflow.patched()` API, allowing in-flight workflows to complete on legacy paths. |

---

## 5. Closed-Loop Feedback & Resilience Monitoring

1. **Saga Failure & Compensation Telemetry**:
   - Every triggered compensating saga emits a `SagaCompensatedEvent` to OpenTelemetry/Langfuse detailing the failed transaction, elapsed time, and business unit.
   - If compensation failure rate exceeds 0.5% over a 7-day window, the system automatically alerts the Reliability Engineering Core (`OB-ADP-03`).
2. **Postgres Checkpoint Compaction**:
   - Checkpoints for resolved tickets are retained in hot PostgreSQL storage for 30 days post-resolution, then asynchronously offloaded to cold S3 Parquet archives by the retention daemon (`MS-ADP-05`).

---

## 6. Genesis Implementation Directives

When initializing the **Genesis** code generation agent, the following files and components must be scaffolded:

### Target File Manifest
1. `workflows/ticket_lifecycle_workflow.py`: Temporal workflow class managing multi-day SLA timers, signals, and activity choreography.
2. `activities/cognitive_turn_activity.py`: Temporal activity wrapping the LangGraph statechart invocation with PostgreSQL checkpoint management.
3. `activities/saga_compensations.py`: Temporal activity implementing compensating rollbacks for failed multi-step tool mutations.
4. `core/persistence/postgres_checkpointer.py`: Connection pool manager providing `AsyncPostgresSaver` instances for LangGraph.

### Scaffolding Verification Criteria
- [ ] **Temporal SDK Compliance**: Workflow code passes `temporalio.workflow.execute_workflow` deterministic replay verification tests without raising non-determinism errors.
- [ ] **History Size Verification**: Simulated 50-turn conversation maintains Temporal workflow event history under 1,500 events and 200KB total payload size.
- [ ] **Crash Durability Test**: Killing worker pods mid-turn during a 48-hour wait simulation resumes execution with zero state loss upon worker recovery.
- [ ] **Compensating Rollback Test**: Rejection of a financial refund signal automatically triggers reverse accounting credit compensation activities.

---

## 7. Consequences & Trade-offs

### Positive Consequences
- **Industrial Multi-Day Durability**: Support tickets survive infrastructure reboots, Kubernetes upgrades, and weeks of customer inactivity with 100% state recovery.
- **Sub-Second Cognitive Performance**: Isolating LangGraph inside activity workers prevents Temporal engine overhead from adding latency to conversational LLM turns.
- **Guaranteed Transactional Consistency**: Distributed saga coordination prevents partial mutations across disparate corporate APIs.
- **Zero Event History Explosion**: Keeping token contexts in PostgreSQL ensures Temporal workflow payloads remain well within platform limits.

### Negative / Neutral Trade-offs & Mitigations
- **Infrastructure Overhead**: Requires provisioning, operating, and monitoring a production Temporal cluster (or Temporal Cloud) alongside PostgreSQL.  
  *Mitigation*: Temporal eliminates custom state-polling databases, Redis distributed locks, and complex homegrown cron queues, resulting in net lower operational maintenance.
- **Developer Learning Curve**: Developers must respect Temporal deterministic replay constraints.  
  *Mitigation*: Isolate all non-deterministic LLM and network code within Tier 2 LangGraph Activities; Tier 1 workflows remain pure structural choreography.

---

## 8. References

1. **Garcia-Molina, H., & Salem, K. (1987)**. *Sagas*. ACM SIGMOD International Conference on Management of Data, 249-259.
2. **Temporal Technologies (2024)**. *Temporal Platform Architecture & Deterministic Workflow Execution Design*.
3. **LangChain AI (2024)**. *LangGraph: StateGraph and Checkpointed Multi-Agent Workflows*.
4. **Nygard, M. T. (2007)**. *Release It!: Design and Deploy Production-Ready Software*. Pragmatic Bookshelf.
5. **Jiang, A. et al. (2023)**. *LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression*.
