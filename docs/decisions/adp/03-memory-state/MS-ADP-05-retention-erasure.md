# MS-ADP-05: Memory Retention & Erasure (Fixed TTL Taxonomy, Centralized Erasure Inventory & Multi-Store GDPR Article 17 Purge)

- **Status**: Accepted & Confirmed
- **Date**: 2026-09-26 *(Amended: 2026-09-26 per MS-D10 TTL Calibrations, MS-D11 Back-Office Workflow & MS-D14 Erasure Inventory)*
- **Deciders**: Architecture Team, Data Protection Officer, Lead Persistence & Security Engineer
- **Component**: `[3] Memory & State` (`Component [ 3 ]`)
- **Reasoning Source**: `checkpoint.md` §7 · Diagram: `LLD - [3] Memory & State`
- **Decisions Covered**:
  - `MS-D10`: Retention Taxonomy & Fixed TTL Schedules — Strict categorical storage limitation aligned with GDPR Art. 5(1)(e): facts 12mo since confirmed · episodes 24mo · blobs & checkpoints case closed + 30d · summaries & pins conversation lifetime (`MS-Q3`)
  - `MS-D11`: User Control & Erasure Model — Phased governance: v1 centralized back-office administrative erasure & rectification (SLA $\le 30$ days); v2 self-service customer portal ("What the Agent Remembers")
  - `MS-D14`: Central Erasure Inventory & Multi-Store Cascade — Unified registry covering every state store (facts, summaries, pins, blobs, checkpoints, eval traces, vector indexes); keyed by composite `(principal_id, tenant_id)`; automated user offboarding cascade ($UK3$, $KK5$)
- **Related Architectural Decision Points**:
  - [`DP-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#dp-adp-05--data-retention--deletion): Data Retention & Deletion Pipelines *(Batch Sweepers & Deletion Schedulers)*
  - [`SG-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#sg-adp-05--privacy--compliance-governance): Privacy & Compliance Governance *(Legal Archive Isolation & Audit Shredding)*
  - [`MS-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/03-memory-state/MS-ADP-02-long-term-fact-model.md): Long-Term Fact Model *(Bi-Temporal Lineage & Scope Filtering)*
  - [`TA-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/04-tools-actions/TA-ADP-05-transactional-integrity-audit.md): Transactional Integrity & Audit *(Crypto-Shredding of Auditable Transactions)*

---

## 1. Context & Problem Statement

Autonomous support agents accumulate extensive data footprints across customer journeys: conversational turn transcripts, bi-temporal factual assertions, negative operational constraints, large tool output blobs, intermediate LangGraph graph checkpoints, and evaluation judge traces.

Retaining this data indefinitely or implementing uncoordinated deletion routines creates three catastrophic legal and technical vulnerabilities:

1. **The Incomplete Erasure Exposure ($KK5$)**: A customer invokes their GDPR Article 17 "Right to be Forgotten". Engineering executes `DELETE FROM users WHERE id = ...` in the primary database. However, the customer's personal data remains duplicated across Postgres pgvector embeddings, LangGraph FSM checkpoints paused in `AWAITING_APPROVAL`, rolling dialogue summaries, and sampled LLM-judge evaluation records (`KR-D11`). Regulators discover personal data in secondary stores, triggering catastrophic statutory fines up to $4\%$ of global turnover.
2. **The "Zombie Employee" Tenant Drift ($UK3$)**: An engineer leaves Acme Corp to work for a competitor. If customer memory facts are keyed solely by personal email or global user ID, their technical memory records (e.g., proprietary network topologies and architecture preferences) persist and follow the individual, or remain accessible to other users after Acme Corp offboards the account.
3. **The Transcript Legal Records Paradox (*Moffatt v. Air Canada*)**: Under common law, statements and promises made by an automated customer agent constitute legally binding corporate commitments. If an agent promises a $\$12,400$ billing waiver and the customer subsequently demands erasure of their account, completely purging the raw transcript destroys the enterprise's ability to defend itself in litigation.

### The Core Architectural Question
> **How do we enforce strict categorical storage lifetimes across all memory artifacts, coordinate comprehensive Article 17 erasures across heterogeneous distributed stores, and isolate legal defense records without leaving personal data in active agent cognitive loops?**

---

## 2. Decision Framework & Theoretical Formulation

To solve these challenges, we establish two architectural pillars: **The Categorical Retention Taxonomy** and **The Centralized Erasure Inventory DAG**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             CENTRAL ERASURE INVENTORY ARCHITECTURE (MS-D14)                      │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                │
                               GDPR Erasure / Offboarding Webhook
                                 (tenant_id, principal_id)
                                                │
                                                ▼
                             ┌──────────────────────────────────────┐
                             │     Central Erasure Coordinator      │
                             │        (core/lifecycle/purge.py)     │
                             └──────────────────────────────────────┘
                                                │
         ┌──────────────────────────────┬───────┴──────────────────────┬──────────────────────────────┐
         ▼                              ▼                              ▼                              ▼
┌──────────────────┐           ┌──────────────────┐           ┌──────────────────┐           ┌──────────────────┐
│ Store 1: Facts   │           │ Store 2: Dialogue│           │ Store 3: Blobs   │           │ Store 4: States  │
│ principal_facts  │           │ conversations,   │           │ tool_output_blobs│           │ checkpoints      │
│ pgvector records │           │ turns, pins      │           │ S3 working files │           │ LangGraph state  │
└──────────────────┘           └──────────────────┘           └──────────────────┘           └──────────────────┘
         │                              │                              │                              │
         └──────────────────────────────┼──────────────────────────────┴──────────────────────────────┘
                                        ▼
                             ┌──────────────────────────────────────┐
                             │ Store 5: Eval & Audit Traces         │
                             │ retrieval_audits (KR-D11)            │
                             │ Langfuse / OpenTelemetry Traces      │
                             └──────────────────────────────────────┘
                                        │
                                        ▼
                             ┌──────────────────────────────────────┐
                             │ Emit Signed Cryptographic Receipt    │
                             │ (PurgeAuditRecord)                   │
                             └──────────────────────────────────────┘
```

---

### Pillar A: Categorical Retention Taxonomy & Mathematical TTLs (`MS-D10`)

Under GDPR Article 5(1)(e) (Storage Limitation), personal data must not be kept longer than necessary for the explicit purposes for which it was collected. We define explicit, non-overlapping TTL bounds per memory category (`MS-Q3`):

$$\text{Memory Artifacts} = \mathcal{M}_{\text{facts}} \cup \mathcal{M}_{\text{episodes}} \cup \mathcal{M}_{\text{blobs}} \cup \mathcal{M}_{\text{checkpoints}} \cup \mathcal{M}_{\text{dialogue}}$$

| Memory Category | Storage Substrate | Mandatory TTL Bound ($\tau$) | Eviction Condition & Trigger |
| :--- | :--- | :--- | :--- |
| **Long-Term Facts ($\mathcal{M}_{\text{facts}}$)** | Postgres + pgvector (`principal_facts`) | **12 Months** since last confirmed | $(t_{\text{now}} - t_{\text{last\_confirmed}}) > 365\text{ days}$ |
| **Episodic Summaries ($\mathcal{M}_{\text{episodes}}$)** | Postgres (`case_episodes`) | **24 Months** since creation | $(t_{\text{now}} - t_{\text{created}}) > 730\text{ days}$ |
| **Working Memory Blobs ($\mathcal{M}_{\text{blobs}}$)** | Postgres / S3 (`tool_output_blobs`) | **Case Closed + 30 Days** | $\text{Case.status} \in \{\text{RESOLVED}, \text{CLOSED}\} \land (t_{\text{now}} - t_{\text{closed}}) > 30\text{ days}$ |
| **Agent State Checkpoints ($\mathcal{M}_{\text{checkpoints}}$)** | Postgres (`checkpoints`) | **Case Closed + 30 Days** | $\text{Case.status} \in \{\text{RESOLVED}, \text{CLOSED}\} \land (t_{\text{now}} - t_{\text{closed}}) > 30\text{ days}$ |
| **Rolling Summaries & Pins ($\mathcal{M}_{\text{dialogue}}$)** | Postgres (`conversations`, `pins`) | Bound to Conversation Lifetime | Dropped when parent Conversation record reaches TTL |

#### Legal Defense Transcript Carveout (GDPR Art. 17(3)(e))
Raw delivered customer messages and agent action records are classified as commercial transaction evidence under *Moffatt v. Air Canada*.
- These records are extracted from live agent stores and transferred into the **Legal Compliance Archive** (`SG-ADP-05`).
- The legal archive is encrypted using per-user crypto keys (`TA-ADP-05`).
- Active agent cognitive loops, memory stores, and vector indexes retain **zero access** to archived transcripts after an erasure event.

---

### Pillar B: Central Erasure Inventory & Multi-Store Purge Coordinator (`MS-D14`)

To guarantee zero residual personal data ($KK5$), the system implements a **Central Erasure Inventory**. Every database table, vector collection, blob bucket, and trace sink register an atomic `PurgeHandler`.

#### Mandatory Composite Scope Keying
To prevent the "zombie employee" failure ($UK3$), all long-term memory facts, conversational entities, and checkpoints are strictly keyed by a composite primary identity:
$$\mathcal{K}_{\text{identity}} = \langle \text{tenant\_id}, \text{principal\_id} \rangle$$

1. **User Offboarding Event**: When Acme Corp deactivates Sarah's account in their IdP, the SCIM offboarding webhook dispatches an immediate erasure for $\langle \text{tenant\_acme}, \text{principal\_sarah} \rangle$.
2. **Blast-Radius Guarantee**: All facts describing Acme Corp's internal infrastructure stored against Sarah are permanently shredded. If Sarah subsequently registers with an independent personal account $\langle \text{tenant\_personal}, \text{principal\_sarah} \rangle$, zero enterprise context leaks across tenant boundaries.

---

## 3. Decision Rules, Structural Invariants & Code Contracts

### Decision Invariants
1. **Invariant 1 (Unified Erasure Cascade)**: An Article 17 erasure request MUST purge records across all seven registered inventory stores within $\le 24$ hours of receipt, well within the statutory $30$-day SLA (`MS-D11`).
2. **Invariant 2 (Strict Composite Partitioning)**: Deletion queries must never execute on `principal_id` alone; every purge statement must include `WHERE tenant_id = :tenant_id AND principal_id = :principal_id`.
3. **Invariant 3 (Audit Verification Receipt)**: Every completed erasure operation must emit a cryptographically signed `PurgeAuditRecord` containing the count of deleted entities across all stores and the sha256 checksum of the request.
4. **Invariant 4 (Provider Retention Immunity)**: Under `SG-D11`, external LLM and Jev inference endpoints operate under enterprise zero-data-retention (ZDR) agreements. No customer turns or state vectors may be used for model training or persisted on vendor infrastructure.

---

### Python & Pydantic Data Contracts

```python
"""
Core contracts for Memory Lifecycle, Retention, and Erasure.
Module: core/lifecycle/erasure.py
"""

from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class ErasureTargetStore(str, Enum):
    PRINCIPAL_FACTS = "principal_facts"
    PGVECTOR_EMBEDDINGS = "pgvector_embeddings"
    CONVERSATIONS_AND_TURNS = "conversations_and_turns"
    PINNED_CONSTRAINTS = "pinned_constraints"
    TOOL_OUTPUT_BLOBS = "tool_output_blobs"
    AGENT_CHECKPOINTS = "agent_checkpoints"
    RETRIEVAL_AUDITS = "retrieval_audits"


class PurgeStoreResult(BaseModel):
    """Execution status for a single storage target in the erasure inventory."""
    store_name: ErasureTargetStore
    records_deleted: int
    success: bool
    error_message: Optional[str] = None
    execution_duration_ms: float


class ErasureRequest(BaseModel):
    """Administrative or automated user erasure request."""
    request_id: str = Field(..., description="Unique compliance ticket UUID")
    tenant_id: str = Field(..., description="Target enterprise tenant partition")
    principal_id: str = Field(..., description="Target user principal ID")
    requested_by: str = Field(..., description="Admin user ID or 'DPO_WEBHOOK'")
    reason: str = Field(default="GDPR_ARTICLE_17")
    submitted_at: datetime = Field(default_factory=datetime.utcnow)


class PurgeAuditRecord(BaseModel):
    """Cryptographically verifiable compliance receipt emitted upon purge completion."""
    request_id: str
    tenant_id: str
    principal_id: str
    completed_at: datetime = Field(default_factory=datetime.utcnow)
    store_results: List[PurgeStoreResult]
    total_records_expunged: int
    signature_sha256: str = Field(..., description="Cryptographic proof of completed cascade")
```

---

## 4. Failure Modes Matrix & Resilience Invariants

| Quadrant | Failure Scenario | Detection Mechanism | Systemic Mitigation & Recovery |
| :--- | :--- | :--- | :--- |
| **Q1: Known Knowns** | **Orphaned Secondary Store Copies ($KK5$)**: User is deleted from SQL, but their query text remains cached in `retrieval_audits` or vector embeddings. | Automated daily data residency scanner identifies orphaned `principal_id` foreign keys. | Mandatory centralized `ErasureCoordinator` invokes all seven registered store handlers in an atomic saga (`MS-D14`); failure in any store raises a P1 alert. |
| **Q2: Known Unknowns** | **Sub-optimal TTL Sizing ($KU5$)**: 12-month fact TTL causes users to lose valid, infrequent configuration preferences, forcing repeated onboarding. | User re-explanation telemetry in CSAT feedback loops. | Configurable TTL table; facts confirmed during active interactions refresh their `last_confirmed_at` timestamp, preventing active preference eviction. |
| **Q3: Unknown Knowns** | **Offboarded Employee Tenant Leak ($UK3$)**: User leaves Acme Corp; Acme infrastructure facts follow the user to their new employer. | Tenancy boundary validation alert on login from new organization domain. | All facts and memory items strictly keyed by composite `(tenant_id, principal_id)` (`MS-D14`); IdP offboarding purges the tenant-specific memory partition completely. |
| **Q4: Unknown Unknowns** | **Re-Identification via LLM Weight Memorization**: Sensitive customer data submitted during prompt execution is memorized by fine-tuned models. | Vendor security audit; data leakage probes. | Zero fine-tuning on customer dialogue; strict enterprise Zero Data Retention agreements with model providers (`SG-D11`). |

---

## 5. Closed-Loop Feedback & Verification Signals

1. **Compliance Telemetry**:
   - `Erasure_Saga_Duration_Seconds`: Emitted per erasure execution; alerts if cascade exceeds $60\text{s}$.
   - `TTL_Batch_Purge_Volume`: Monitored nightly to verify that scheduled sweeper cron jobs expunge expired checkpoints and blobs as designed.
2. **Monthly GDPR Compliance Dry-Run**:
   - Automated synthetic user lifecycle test: generates synthetic user, seeds data across all seven stores, executes `ErasureRequest`, and queries every table to assert exact zero-record residual across the enterprise footprint.

---

## 6. Genesis Implementation Directives

1. **Code Locations**:
   - Implement the central erasure coordinator in `core/lifecycle/erasure_coordinator.py`.
   - Implement storage-specific purge handlers in `core/lifecycle/handlers/`.
   - Implement scheduled TTL sweepers in `cron/retention_sweeper.py`.
   - Implement compliance audit logging in `core/lifecycle/audit_logger.py`.
2. **Nightly Sweeper Task**:
   - Execute batch SQL eviction queries nightly via Temporal Scheduled Workflows:
     ```sql
     -- Evict expired checkpoints for closed cases
     DELETE FROM checkpoints c
     USING cases k
     WHERE c.case_id = k.case_id
       AND k.status IN ('resolved', 'closed')
       AND k.closed_at < NOW() - INTERVAL '30 days';

     -- Evict stale unconfirmed facts
     DELETE FROM principal_facts
     WHERE last_confirmed_at < NOW() - INTERVAL '12 months';
     ```

---

## 7. Consequences & Trade-offs

### Positive Consequences
- **Absolute Regulatory Immunity**: Complete multi-store coverage guarantees compliance with GDPR Articles 5, 15, 16, and 17, mitigating multi-million-euro statutory exposure.
- **Controlled Database Bloat**: Routine 30-day purging of heavy working memory blobs and intermediate graph checkpoints keeps Postgres database storage lean and high-performing.
- **Tenant Security Guarantees**: Composite `(tenant_id, principal_id)` keying mathematically prevents corporate context leaks when personnel transition between enterprises.

### Negative Consequences & Trade-offs
- **Administrative Overhead in v1**: Handling GDPR erasures via back-office tickets requires dedicated support operations bandwidth until self-service portals ship in v2 (`MS-D11`).
- **Loss of Long-Term Inactive Context**: Strictly evicting facts older than 12 months requires infrequent enterprise customers to re-declare operational preferences on annual interactions.
- **Distributed Erasure Failure Surface**: Coordinating synchronous deletions across seven heterogeneous data sinks introduces transient network retry complexities during batch purges.

---

## 8. References & Cross-Disciplinary Grounding

1. **Regulation (EU) 2016/679 (GDPR)**: European Parliament and Council. Article 5 (Principles), Article 15 (Access), Article 16 (Rectification), Article 17 (Right to Erasure).
2. **Moffatt v. Air Canada (2024 BCCRT 149)**: Legal precedent establishing corporate liability for automated agent commitments and the necessity of durable legal evidence.
3. **California Consumer Privacy Act (CCPA / CPRA)**: Cal. Civ. Code § 1798.105 (Consumer Right to Delete Personal Information).
4. **Data Minimization and Storage Limitation in Distributed AI Architectures**: Cavoukian, A. (2010). *Privacy by Design: The 7 Foundational Principles*. Information and Privacy Commissioner of Ontario.
