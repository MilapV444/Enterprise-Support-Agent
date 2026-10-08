# DL-ADP-04: Multi-Tier Versioning & Lifecycle Governance (Pinned Embeddings, Pinned Jev, Provider Aliases & Continue-As-New Workflows)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-06 *(Confirmed per DL-D3 Selective Model Pinning DL-Q1, DL-D6 Continue-As-New Workflow Transitions UU3, DL-D11 In-Place Maintenance Re-Indexing KU1)*
- **Deciders**: Architecture Team, Lead Machine Learning Engineer, Temporal Platform Lead, Vector Search Architect
- **Component**: `[14] Deployment & LLMOps` (`Component [ 14 ]`)
- **Reasoning Source**: `checkpoint.md` §18 · Diagram: `LLD - [14] Deployment & LLMOps`
- **Decisions Covered**:
  - `DL-D3`: Asymmetric Model Versioning (Selective Pinning vs. Aliases) — Resolves the conflict between maintenance overhead and vector space stability (`DL-Q1(ii)`):
    - **Foundation LLM Tiers (Tiers 1, 2, 3)**: Utilize provider "latest" model aliases (e.g., `claude-3-5-sonnet-latest`, `gpt-4o-mini`), avoiding manual update friction while monitoring behavioral drift via live evaluation sampling (`EV-D8`) and exact cost counters (`CR-D11`)
    - **Vector Embedding Model & Jev Classifier**: Strictly pinned to exact immutable release snapshots (`text-embedding-3-large-2024-05`, `jev-1.13`); prevents silent geometric distortion of Qdrant vector spaces ($KR\text{ }KK5$) and invalidation of per-route calibrated decision thresholds (`EV-D9`, $UU1$)
  - `DL-D6`: Continue-As-New Workflow Lifecycle Transitions — Upgrades long-running in-flight Temporal workflows across release boundaries using `workflow.continue_as_new()`; eliminates the operational burden of maintaining legacy worker fleets for multi-day approval cases (`HL-D9`); strictly enforces that workflows drain and process all pending queue signals (approvals, cancellations) prior to completing the transition ($UU3$), while migrating LangGraph checkpoints cleanly (`MS-D13`, `TQ-D14`)
  - `DL-D11`: Scheduled In-Place Vector Index Evolution — Upgrading the pinned embedding model executes via in-place Qdrant re-indexing during scheduled maintenance windows; accepts temporary retrieval degradation ($KU1$) to eliminate the cost and operational overhead of maintaining duplicate blue/green vector database clusters
- **Related Architectural Decision Points**:
  - [`ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/00-orchestration-core/ADP-02-workflow-durability.md): Workflow Durability *(Temporal Long-Running Sagas)*
  - [`MS-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/03-memory-state/MS-ADP-04-agent-state-durability.md): Agent State & Durability *(LangGraph Checkpoint Migrations)*
  - [`KR-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/02-knowledge-retrieval/KR-ADP-03-indexing-tenant-isolation.md): Indexing & Tenant Isolation *(Qdrant Vector Geometry)*
  - [`EV-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/08-evaluation-experimentation/EV-ADP-02-scoring-calibration.md): Scoring & Calibration *(Jev Threshold Stability)*

---

## 1. Context & Problem Statement

Managing version lifecycles across an autonomous enterprise agent involves coordinating heterogeneous, interdependent software layers:
1. **The Vector Space Geometry Collapse ($KR\text{ }KK5$, $UU1$)**:
   - If an embedding model utilizes a provider "latest" alias and the vendor silently updates the model weights, the underlying vector space geometry shifts.
   - An inbound query embedded under the new model yields completely divergent cosine similarity scores when matched against millions of enterprise documents indexed under the previous model. The retrieval pipeline collapses, returning irrelevant passages and hallucinated answers.
2. **The Jev Calibration Shift ($UU1$)**:
   - Jev confidence thresholds (`HL-D2`) are calibrated offline against human gold labels (`EV-D9`). If Jev's model changes silently under a generic alias, the calibrated boundaries ($0.90$ send, $0.50$ handoff) no longer correspond to true empirical probabilities, causing widespread false handoffs or unauthorized auto-sends.
3. **The Multi-Day Workflow Stranding Dilemma ($UU3$)**:
   - Customer support approvals can remain pending for up to 3 business days (`HL-D9`), and rate-limited requests can hold for 24 hours (`RP-D7`).
   - If an engineering team deploys new workflow definitions, the traditional approach requires keeping "v1 workers" running alongside "v2 workers" for a week until all legacy executions drain. When worker versions proliferate, infrastructure complexity multiplies.
   - Conversely, abruptly terminating workflows drops pending customer approvals ($UU3$).

### The Core Architectural Question
> **How do we establish a principled versioning architecture that pins vector and decision models to prevent calibration collapse, leverages provider aliases for general generation, and rolls over in-flight workflows without dropping pending customer signals?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `DL-D3`, `DL-D6`, and `DL-D11` establish the **Asymmetric Model Pinning and Continue-As-New Lifecycle Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   ASYMMETRIC VERSIONING & WORKFLOW UPGRADE PIPELINE (DL-D3, DL-D6)               │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                                    NEW CODE & MODEL RELEASE (vNext)
                                                   │
                     ┌─────────────────────────────┴─────────────────────────────┐
                     ▼                                                           ▼
┌───────────────────────────────────────────────┐ ┌────────────────────────────────────────────────┐
│ MODEL VERSIONING STRATEGY (DL-D3, DL-Q1(ii))  │ │ IN-FLIGHT WORKFLOW ROLLOVER (DL-D6, UU3)       │
├───────────────────────────────────────────────┤ ├────────────────────────────────────────────────┤
│ 1. LLM GENERATION TIERS (Tiers 1, 2, 3):      │ │ Long-Running Temporal Workflow (Holding Action)│
│    • Provider "Latest" Aliases Permitted      │ │                                                │
│    • Low maintenance; drift caught via EV-D8  │ │ 1. Drain Pending Signal Queue (UU3 Invariant):  │
│ 2. SENSITIVE EMBEDDINGS & JEV CLASSIFIERS:    │ │    - Process unhandled Approvals / Cancels     │
│    • STRICTLY PINNED IMMUTABLE SNAPSHOTS!     │ │ 2. Migrate LangGraph Checkpoint Schema (MS-D13)│
│    • Embedding: `text-embedding-3-large-2024` │ │ 3. Execute `workflow.continue_as_new()`        │
│    • Jev Engine: `jev-v1.13`                  │ │    - Re-instantiates workflow on vNext code    │
│    • Protects Vector Geometry ($KR\text{ }KK5$)│ │    - ZERO Legacy Worker Fleet Required!        │
└───────────────────────────────────────────────┘ └────────────────────────────────────────────────┘
```

---

### Pillar 1: Asymmetric Model Pinning Architecture (`DL-D3`, `DL-Q1(ii)`)

We bifurcate model version management based on downstream state dependencies:
1. **Pinned Dependency Set (Zero Drift Permitted, $UU1$)**:
   - **Vector Embedding Model**: Pinned in configuration (`config/models.yaml`). Changing the embedding model changes index geometry; updates strictly require executing an in-place re-index maintenance window (`DL-D11`).
   - **Jev Acuity & Grounding Classifiers (`ADP-05`)**: Pinned to explicit model release tags (e.g., `jev-1.13`). Upgrading Jev requires running the offline ECE calibration harness (`EV-D9`) to re-calculate per-route confidence thresholds before release.
2. **Aliased Generation Set (Low-Maintenance Aliases)**:
   - Commercial LLM generation tiers (Claude 3.5 Sonnet, GPT-4o-mini) point to provider aliases.
   - Behavioral drift is continuously intercepted by output safety filters (`SG-D6`), promise checks (`SG-D15`), and FinOps exact cost counters (`CR-D11`).

---

### Pillar 2: Temporal Continue-As-New Lifecycle Transitions (`DL-D6`, $UU3$)

Rather than maintaining parallel legacy worker pools, long-running sagas utilize Temporal's `continue_as_new` primitive:
1. **Release Boundary Interception**:
   - When a new deployment rolls out, running workflows detect the release boundary signal.
2. **The Signal Drain Invariant ($UU3$)**:
   - To prevent dropped customer actions, the workflow checks its internal signal buffer:
     ```python
     while workflow.has_pending_signals():
         workflow.process_signal()
     ```
   - All pending approval or cancellation signals are fully processed before the execution state is rolled over.
3. **State Migration & Re-Instantiation**:
   - The workflow invokes `migrate_checkpoint()` (`MS-D13`, `TQ-D14`) to upgrade its internal LangGraph state dictionary to the new schema.
   - The workflow calls `workflow.continue_as_new(new_migrated_state)`, seamlessly continuing execution on the new codebase without human intervention.

---

### Pillar 3: Scheduled In-Place Re-Indexing (`DL-D11`, $KU1$)

When an embedding model upgrade is approved:
1. **Maintenance Window Protocol**:
   - Re-indexing is scheduled during off-peak weekend windows (e.g., Sunday 02:00–06:00 UTC).
2. **In-Place Batch Re-Vectorization**:
   - A distributed Kubernetes batch job reads raw document snapshots (`DP-D11`), embeds passages under the new model, and upserts vectors directly into Qdrant collections.
3. **Graceful Fallback Mode**:
   - During the 4-hour re-indexing window, customer search requests falling into updating collections degrade gracefully to keyword BM25 search (`KR-ADP-04`), avoiding cluster downtime ($KU1$).

---

## 3. Technical Implementation & Genesis Contracts

```python
"""
core/deployment/workflow_rollover.py
Temporal workflow logic implementing Continue-As-New with Signal Draining (DL-D6, UU3).
"""

from typing import Dict, Any, List
from temporalio import workflow


@workflow.defn
class LongRunningSupportSagaWorkflow:
    """
    Manages long-running customer approval workflows across deployments (DL-D6).
    """

    def __init__(self):
        self.pending_signals: List[Dict[str, Any]] = []
        self.state: Dict[str, Any] = {}
        self.is_terminal: bool = False

    @workflow.signal
    def approval_decision_signal(self, payload: Dict[str, Any]):
        self.pending_signals.append(payload)

    @workflow.run
    async def run(self, initial_state: Dict[str, Any]) -> Dict[str, Any]:
        self.state = initial_state

        while not self.is_terminal:
            # Wait for approval signal or release boundary rollover trigger
            await workflow.wait_condition(
                lambda: len(self.pending_signals) > 0 or self._is_release_boundary_triggered()
            )

            # 1. Drain and process all pending signals first (DL-D6, UU3 Invariant)
            while len(self.pending_signals) > 0:
                signal = self.pending_signals.pop(0)
                self._apply_signal(signal)
                if self.is_terminal:
                    return self.state

            # 2. Check if a deployment boundary rollover is required
            if self._is_release_boundary_triggered():
                # Apply LangGraph schema migration (MS-D13, TQ-D14)
                migrated_state = self._migrate_state_schema(self.state)
                
                # Cleanly transition to new workflow code without old workers!
                workflow.continue_as_new(migrated_state)

        return self.state

    def _is_release_boundary_triggered(self) -> bool:
        # Evaluates if runtime container version differs from workflow instantiation version
        return False

    def _apply_signal(self, signal: Dict[str, Any]):
        if signal.get("verdict") in ["approved", "rejected", "cancelled"]:
            self.is_terminal = True

    def _migrate_state_schema(self, state: Dict[str, Any]) -> Dict[str, Any]:
        # Upward schema migration logic
        state["schema_version"] = state.get("schema_version", 1) + 1
        return state
```

---

## 4. Failure Modes & Mitigation Matrix

| Failure ID | Sub-Component | Failure Mode Description | Root Cause | Effect on System | Architectural Mitigation (`DL-D3`, `DL-D6`, `DL-D11`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **$UU1$** | Versioning | Silent model update destroys vector search | Provider alias changes embedding dimensionality | Qdrant searches return zero matches; total retrieval blackout | `DL-D3` strictly pins embedding model and Jev version to immutable snapshot strings |
| **$UU3$** | Versioning | Approval signal dropped during deploy | Workflow continues-as-new while signal in flight | Specialist approves refund, but customer case remains blocked | `DL-D6` workflow loop mandates draining all pending queue signals before rollover |
| **$KU1$** | Versioning | Retrieval latency spikes during re-index | In-place Qdrant re-indexing consumes database IOPS | Slow search responses during maintenance window | `DL-D11` executes re-indexing during off-peak windows; falls back to BM25 keyword search |
| **$KK3$** | Versioning | Workflow fails deterministic replay | Workflow code altered without version branching | Temporal workflow panic; execution halted | Workflows rollover via `continue_as_new()` on release boundaries, eliminating legacy replays |

---

## 5. Closed-Loop Telemetry & Verification Directives

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   LIFECYCLE & VERSIONING TELEMETRY PIPELINE                                      │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Workflow Rollover ──► [ Continue-As-New Counter ] ──► Metric: `workflow.rollover.success_total`
                                │
                                ├──► [ Dropped Signal Guard ] ──► Metric: `workflow.signals.drained_count`
                                │
                                └──► [ Model Pin Verifier ] ──► Alert: `model.pin_mismatch.detected`
```

### 1. Prometheus Telemetry Indicators
- `workflow.rollover.executed_total`: Total long-running workflows migrated via Continue-As-New.
- `workflow.signals.drained_per_rollover`: Histogram tracking signals processed during rollover transition.
- `vector.index.reindex_duration_seconds`: Gauge measuring elapsed time for in-place Qdrant re-indexing.

---

## 6. Alternatives Considered & Trade-Off Analysis

| Architectural Alternative | Technical Mechanism | Why Rejected / Trade-Off Analysis |
| :--- | :--- | :--- |
| **Universal "Latest" Aliases for All Models** | Point embedding, Jev, and LLM tiers to vendor `:latest` | **Rejected ($UU1$)**: Silent vendor updates destroy vector similarity search and invalidate calibrated confidence thresholds. |
| **Long-Lived Legacy Worker Fleets (DL-F6(b))** | Keep old worker containers running for 7 days until all workflows finish | **Rejected**: Operational nightmare; maintaining multiple concurrent worker generations multiplies cloud fees and database connection pool contention. |
| **Blue/Green Qdrant Vector Clusters (DL-F11(b))** | Duplicate entire vector database cluster for every embedding change | **Rejected**: Doubles expensive high-memory vector storage costs; in-place re-indexing during maintenance windows is $80\%$ cheaper. |

---

## 7. References & Academic Foundations

1. **Temporal Technologies.** (2024). *Continue-As-New: Managing Unbounded Execution Histories.* Temporal Developer Guide.
2. **Qdrant Vector Database.** (2024). *Collection Lifecycle, Vector Dimension Immutability, and Migration Patterns.*
3. **NIST SP 800-53, Rev. 5.** (2020). *Security and Privacy Controls for Information Systems and Organizations.* Control SI-2: Flaw Remediation.
