# TA-ADP-05: Transactional Integrity & Audit (Temporal Compensating Sagas, Irreversible-Step Fencing & Crypto-Shredded SOX Audit)

- **Status**: Accepted & Confirmed
- **Date**: 2026-09-29 *(Amended: 2026-09-29 per TA-D8 Temporal Sagas, TA-D12 SOX Audit Snapshots, TA-D15 Crypto-Shredding, TA-D17 Compensation Fencing & TA-D18 Irreversible Step Placement)*
- **Deciders**: Architecture Team, Lead Distributed Systems Architect, Compliance & Legal Counsel
- **Component**: `[4] Tools & Actions` (`Component [ 4 ]`)
- **Reasoning Source**: `checkpoint.md` §8 · Diagram: `LLD - [4] Tools & Actions`
- **Decisions Covered**:
  - `TA-D8`: Multi-System Distributed Writes — Managed as Temporal compensating sagas; every multi-step mutation registers explicit compensation activities
  - `TA-D12`: Forensics & SOX §404 Audit Logging — Append-only audit record per tool call (actor, credential basis, arguments, gate decisions, Jev confidence, idempotency key) with mandatory before/after state captures for financial writes
  - `TA-D15`: Audit Immutability vs. GDPR Erasure via Crypto-Shredding — Personal data fields within immutable audit records are encrypted using per-user KMS keys; GDPR Article 17 erasure deletes the user key, rendering records permanently indecipherable while preserving cryptographic log integrity ($UU5$)
  - `TA-D17`: Idempotent Compensation Fencing — Compensations are registered as first-class idempotent tools; any failure during compensation execution halts automated rollback and trips immediately to a Human Specialist ($UU3$)
  - `TA-D18`: Irreversible Action Ordering & Human Gate — Operations lacking real-world undo (e.g., dispatching external emails, irreversible payment settlements) must be placed as the final step of the saga and strictly require prior human approval ($KU5$)
- **Related Architectural Decision Points**:
  - [`ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/00-orchestration-core/ADP-02-workflow-durability.md): Workflow Execution & Durability Substrate *(Temporal Saga Coordination)*
  - [`DP-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#dp-adp-03--encryption-key-management): Encryption & Key Management *(KMS Envelope Encryption)*
  - [`MS-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/03-memory-state/MS-ADP-05-retention-erasure.md): Memory Retention & Erasure *(Central Erasure Inventory Integration)*
  - [`TA-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/04-tools-actions/TA-ADP-03-action-validation-approval.md): Action Validation & Approval Tiers *(Human Approval Thresholds)*

---

## 1. Context & Problem Statement

Enterprise support operations routinely execute multi-system business transactions spanning disjoint SaaS platforms and on-premise databases. For example, processing an enterprise subscription return requires:
1. Canceling the scheduled renewal in Stripe (`billing.cancel_subscription`).
2. Re-allocating license seats in Salesforce CRM (`crm.update_seat_entitlement`).
3. Re-crediting enterprise credits in SAP ERP (`erp.post_credit_memo`).
4. Dispatching a formal legal confirmation email to the customer (`email.send_confirmation`).

In this distributed environment, naive execution triggers two fundamental architectural failures:

1. **The Partial-Execution State Inconsistency Disaster ($TA-D8$)**: If step 1 and step 2 succeed, but step 3 fails with an unrecoverable database constraint error, traditional two-phase commit (2PC) is unavailable across heterogeneous SaaS APIs. Without automated compensating transactions, the enterprise suffers data divergence: the subscription is canceled, but the customer was never credited.
2. **The "Un-Send the Email" Impossible Rollback ($KU5$)**: Certain real-world actions are physically irreversible (e.g., sending an external email, printing a physical warehouse manifest, or settling an instant wire transfer). If an agent places an irreversible action midway through a saga and a subsequent step fails, automated compensation cannot "un-send" the message.
3. **The Audit vs. GDPR Article 17 Erasure Paradox ($UU5$)**: Under Sarbanes-Oxley (SOX §404) and financial regulatory frameworks, any system modifying ledger balances must maintain an immutable, append-only forensic audit trail capturing exact before/after state snapshots. Conversely, under GDPR Article 17, a customer has the statutory right to have their personal data expunged. If before/after snapshots contain customer PII stored in an immutable WORM (Write Once, Read Many) log, the two legal mandates catastrophically conflict.

### The Core Architectural Question
> **How do we guarantee eventual consistency and safe rollback across multi-system write operations, protect irreversible actions from broken rollbacks, and maintain immutable SOX financial audit trails without violating GDPR erasure requirements?**

---

## 2. Decision Framework & Theoretical Formulation

To solve these challenges, we establish the **Compensating Saga Orchestrator with Crypto-Shredded Forensic Audit**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             COMPENSATING SAGA ARCHITECTURE (TA-D8, TA-D18)                       │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

Saga Definition: Case #402 - Enterprise Refund & License Revocation
Forward Transaction Steps: [T_1: Stripe Cancel] ──► [T_2: CRM Deallocate] ──► [T_3: Irreversible Email]
                               │                             │
                               ▼                             ▼
Compensating Undo Activities:  [C_1: Stripe Un-cancel]       [C_2: CRM Re-allocate]

Execution Trajectory:
1. T_1 Succeeds (Checkpoint committed)
2. T_2 Fails (e.g., CRM 500 Network Collapse)
3. Orchestrator Aborts Forward Flow
4. Compensation Rollback Triggers: Executes C_1 (Idempotent, TA-D17)
5. Invariant TA-D18: Irreversible Step T_3 (Email) NEVER executed! (Placed strictly last + approved)
```

---

### Pillar A: Distributed Sagas & Compensating Transactions Formulation

Grounding our transaction substrate in classic distributed systems literature (Garcia-Molina & Salem, 1987), an enterprise saga is modeled as a sequence of discrete transaction steps:
$$\mathcal{S} = \langle (T_1, C_1), (T_2, C_2), \dots, (T_{n-1}, C_{n-1}), T_n \rangle$$

Where:
- $T_i$ is a forward action activity.
- $C_i$ is its corresponding compensating action that semantically undoes $T_i$.
- $T_n$ is an irreversible terminal action ($C_n = \emptyset$).

#### Irreversible Terminal Placement Invariant (`TA-D18`)
Any tool classified as `DESTRUCTIVE_IRREVERSIBLE` or lacking a valid automated compensation ($C = \emptyset$) must satisfy:
$$\text{IsIrreversible}(T) \implies T = \text{TerminalStep}(\mathcal{S}) \land \text{HumanApprovalGranted}(T)$$
Irreversible actions can only execute after all preceding reversible steps $(T_1 \dots T_{n-1})$ have succeeded and a human specialist has explicitly approved the operation.

#### Compensation Failure Tripping Gate (`TA-D17` / $UU3$)
Compensations execute as first-class Temporal activities with deterministic idempotency keys:
$$K_{\text{comp}} = \text{HMAC-SHA256}(\text{saga\_id} \,\|\, \text{step\_id} \,\|\, \text{"COMPENSATE"}, \mathcal{K}_{\text{tenant}})$$
If a compensation $C_i$ fails after maximum configured retries ($N=3$), the saga engine **immediately halts automated rollback** and trips directly to a Human Specialist (`HL-ADP-03`). The system never loops, guesses, or attempts heuristic recovery on a failed rollback.

---

### Pillar B: SOX §404 Append-Only Audit & Forensic Snapshots (`TA-D12`)

Every executed tool call produces an immutable audit record committed to an append-only ledger:
$$\mathcal{A}_{\text{event}} = \langle \text{EventID}, \text{Timestamp}, \text{Actor}, \text{AuthBasis}, \text{ToolID}, \text{Params}, \text{GateVerdict}, \mathcal{S}_{\text{before}}, \mathcal{S}_{\text{after}} \rangle$$

For any mutating tool affecting financial or customer entitlement state, the runner captures:
1. **Pre-Mutation Snapshot ($\mathcal{S}_{\text{before}}$)**: Verified read of entity balances and metadata prior to dispatch.
2. **Post-Mutation Snapshot ($\mathcal{S}_{\text{after}}$)**: Verified read-back of entity state confirming that the change was successfully applied downstream.

---

### Pillar C: Crypto-Shredding of Immutable Financial Audits (`TA-D15` / $UU5$)

To reconcile SOX §404 immutability with GDPR Article 17 Right to Erasure, we implement **Per-User Envelope Crypto-Shredding** (NIST SP 800-57):

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                         CRYPTO-SHREDDING AUDIT RECONCILIATION (TA-D15)                           │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

Step 1: Write Tool Call Audit Event
• Non-PII Metadata (ToolID, Timestamp, GateDecision, Amount) ──► Stored as Plaintext in WORM Log
• Personal Data Fields (Customer Name, Email, Account Snapshot)
    │
    ▼ (Encrypted via User Data Encryption Key: K_user)
  Ciphertext: c = AES-256-GCM(K_user, SnapshotPII) ───────────► Stored in Immutable WORM Log

Step 2: Customer Invokes GDPR Article 17 Erasure Request
• Central Erasure Coordinator (MS-ADP-05) invokes KMS
• KMS Destroys User Key: KMS.DestroyKey(K_user)

Outcome:
• Append-Only Audit Trail remains 100% intact (Zero row deletion, zero hash-chain break)
• Financial metadata (Amount, Tool, Approver) remains forensically auditable for SOX §404
• Customer PII within c becomes mathematically unrecoverable (Information-Theoretic Security)
```

#### Cryptographic Shredding Formulation
Let $K_{\text{user}}$ be a customer-specific 256-bit AES key managed in AWS KMS / HashiCorp Vault.
Audit personal data $P$ is persisted as:
$$\mathcal{C} = \text{AES-GCM}(K_{\text{user}}, P, \text{AAD}=\text{event\_id})$$
Upon receipt of a verified GDPR Article 17 erasure webhook:
$$\text{ErasureAction}: \quad \text{KMS.DeleteKey}(K_{\text{user}})$$
Because $K_{\text{user}}$ is permanently destroyed, the probability of recovering personal data $P$ from ciphertext $\mathcal{C}$ is bounded by:
$$\mathbb{P}(\text{Recovery}) \le \frac{1}{2^{256}} \approx 0$$
This satisfies GDPR Article 17 without altering a single byte in the append-only SOX audit table.

---

## 3. Decision Rules, Structural Invariants & Code Contracts

### Decision Invariants
1. **Invariant 1 (Saga Compensation Atomicity)**: No multi-step write workflow may be deployed without registering deterministic compensation activities for all non-terminal steps.
2. **Invariant 2 (Irreversible Terminal Placement)**: Any action lacking a registered compensation activity must be placed as the final step in the saga sequence.
3. **Invariant 3 (WORM Ledger Integrity)**: The audit log table (`tool_execution_audits`) must enforce append-only permissions (`REVOKE UPDATE, DELETE ON tool_execution_audits`).
4. **Invariant 4 (Crypto-Shredding Key Lifetime)**: The per-user audit encryption keys must be registered in the Central Erasure Inventory (`MS-D14`, `MS-ADP-05`).

---

### Python & Pydantic Data Contracts

```python
"""
Data contracts for Transactional Sagas, Forensic Audits, and Crypto-Shredding.
Module: core/tools/saga_audit.py
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class SagaStepStatus(str, Enum):
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATED = "compensated"
    COMPENSATION_FAILED = "compensation_failed"


class SagaStepDefinition(BaseModel):
    """Specification of a forward step and its compensating activity."""
    step_id: str
    tool_id: str
    arguments: Dict[str, Any]
    is_irreversible: bool = Field(default=False)
    compensation_tool_id: Optional[str] = None
    compensation_arguments_generator: Optional[str] = None


class ToolAuditRecord(BaseModel):
    """Immutable forensic audit record persisted for SOX §404 compliance."""
    audit_id: str = Field(..., description="Unique deterministic audit UUID")
    tenant_id: str
    principal_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Execution context
    case_id: str
    tool_id: str
    actor_type: str = Field(..., regex="^(agent|human_specialist|system)$")
    idempotency_key: str
    credential_basis: str
    
    # Governance & Gating
    risk_class: str
    gate_verdict: str
    approver_id: Optional[str] = None
    
    # Financial state captures (Crypto-shredded PII)
    is_financial_write: bool = Field(default=False)
    non_pii_parameters: Dict[str, Any]
    encrypted_pii_payload: Optional[str] = Field(
        None, 
        description="AES-256-GCM ciphertext encrypted with per-user KMS key"
    )
    kms_key_id: Optional[str] = None
    
    # Execution outcomes
    success: bool
    error_code: Optional[str] = None
```

---

## 4. Failure Modes Matrix & Resilience Invariants

| Quadrant | Failure Scenario | Detection Mechanism | Systemic Mitigation & Recovery |
| :--- | :--- | :--- | :--- |
| **Q1: Known Knowns** | **Rollback Mid-Flight Failure ($UU3$)**: External API fails during compensation execution ($C_1$), leaving systems in a half-rolled-back state. | Temporal activity retry exhaustion alerts in Prometheus. | Engine halts automated saga rollback (`TA-D17`); locks case and trips immediately to Human Specialist with full diagnostic packet. |
| **Q2: Known Unknowns** | **Irreversible Step Rollback Impossibility ($KU5$)**: An email confirmation is dispatched before payment clears; payment fails and email cannot be undone. | Saga validator detects irreversible step placed at index $i < n$. | Static saga compiler rule (`TA-D18`): irreversible steps can only exist as the final step ($i=n$) and require human approval. |
| **Q3: Unknown Knowns** | **State Drift During Approval Delay**: A $\$12,400$ saga step is approved 4 days later; during the wait, external inventory changed. | Resumption revalidation detector (`MS-D18`) compares fresh read with checkpoint state. | Automatic barrier: waits $>1\text{h}$ force live re-fetch before executing forward saga steps. |
| **Q4: Unknown Unknowns** | **Audit Log Tampering / Legal Conflict ($UU5$)**: Regulator demands complete user erasure, but auditors demand immutable financial records. | Compliance conflict resolution protocol. | Per-user crypto-shredding (`TA-D15`): user KMS key is destroyed; audit trail remains immutable while PII becomes unrecoverable. |

---

## 5. Closed-Loop Feedback & Verification Signals

1. **System Health Metrics**:
   - `Saga_Rollback_Success_Rate`: Monitored per workflow; alerts immediately if any compensation fails ($C_i = \text{FAILED}$).
   - `Crypto_Shredding_Execution_Latency`: Emitted when user keys are destroyed, verifying complete cryptographic erasure.
   - `Financial_Audit_Capture_Latency`: Tracks write duration of pre/post snapshots to the audit ledger.
2. **Monthly Compliance Simulation**:
   - Automated compliance testing worker simulates an Article 17 erasure on a synthetic user account, then executes forensic audit queries to verify that financial ledger sums balance while all customer PII fields return undecipherable ciphertext.

---

## 6. Genesis Implementation Directives

1. **Code Locations**:
   - Implement Temporal saga workflows in `workflows/sagas/`.
   - Implement compensation activities in `workers/activities/compensations/`.
   - Implement the append-only audit repository in `core/audit/ledger.py`.
   - Implement the crypto-shredding envelope encryptor in `core/audit/crypto_shredder.py`.
2. **Database Directives**:
   - Create append-only table in Postgres `db/migrations/004_tool_audits.sql`:
     ```sql
     CREATE TABLE tool_execution_audits (
         audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
         tenant_id VARCHAR(64) NOT NULL,
         principal_id VARCHAR(128) NOT NULL,
         case_id VARCHAR(64) NOT NULL,
         tool_id VARCHAR(128) NOT NULL,
         idempotency_key VARCHAR(128) NOT NULL,
         non_pii_parameters JSONB NOT NULL,
         encrypted_pii_payload TEXT,
         kms_key_id VARCHAR(128),
         created_at TIMESTAMPTZ DEFAULT NOW()
     );
     REVOKE UPDATE, DELETE ON tool_execution_audits FROM app_user;
     ```

---

## 7. Consequences & Trade-offs

### Positive Consequences
- **Mathematical Multi-System Consistency**: Compensating Temporal sagas prevent orphaned resources and balance mismatches across third-party SaaS integrations.
- **Full Legal Harmony**: Crypto-shredding completely resolves the legal contradiction between SOX §404 append-only audit immutability and GDPR Article 17 Right to Erasure.
- **Fail-Safe Human Escalation**: Immediate halts on failed compensations protect against runaway automated recovery loops.

### Negative Consequences & Trade-offs
- **Compensation Tool Development Overhead**: Every forward-mutating tool requires engineering, testing, and maintaining an equivalent idempotent compensation activity.
- **KMS Key Management Costs**: Maintaining unique encryption keys per customer in KMS slightly increases key management operational expenditures.
- **Workflow Latency**: Capturing synchronous before/after state snapshots and executing envelope encryption adds $\approx 35\text{ms}$ to financial tool calls.

---

## 8. References & Cross-Disciplinary Grounding

1. **Sagas**: Garcia-Molina, H., & Salem, K. (1987). *ACM SIGMOD Record*. (Foundational literature on distributed compensating transaction workflows).
2. **NIST SP 800-57 Part 1 Rev. 5**: Recommendation for Key Management. (Cryptographic shredding and envelope encryption standards).
3. **Sarbanes-Oxley Act of 2002 (SOX)**: Public Law 107-204. Section 404 — Management Assessment of Internal Controls.
4. **Temporal Saga Implementation Pattern**: Temporal Technologies. (2024). *Orchestrating Distributed Sagas and Compensating Transactions*.
