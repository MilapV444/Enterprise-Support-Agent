# MA-ADP-04: Specialist Permissions & Writes (Role-Scoped Identities, Read-Only Parallel Isolation & Verified Read-Back Execution)

- **Status**: Accepted & Confirmed
- **Date**: 2026-09-29 *(Amended: 2026-09-29 per MA-D9 Scoped Low-Risk Writes, MA-D14 Read-Back Action Verification & MA-D18 Read-Only Parallelism)*
- **Deciders**: Architecture Team, Lead Integrations Architect, Security & Access Governance Core
- **Component**: `[5] Multi-Agent & Communication` (`Component [ 5 ]`)
- **Reasoning Source**: `checkpoint.md` §9 · Diagram: `LLD - [5] Multi-Agent & Communication`
- **Decisions Covered**:
  - `MA-D9`: Specialist Identity & Scoped Direct Writes — Each specialist possesses its own actor identity (`act` claim in RFC 8693 tokens, recorded in audit trails) and a least-privilege tool allow-list; specialists execute reads and low-risk writes directly (notes, ticket tags, reset links); financial, destructive, or irreversible actions are proposed to the Coordinator for human approval (`TA-D5`)
  - `MA-D14`: Action Claim Integrity & Read-Back Verification — Proposed actions are reported strictly as proposed; executed low-risk writes may only be reported in results after Tools has verified the post-mutation state via read-back; customer success is announced exclusively by the Coordinator ($UU1$, $KK2$)
  - `MA-D18`: Concurrent Writer Isolation & Read-Only Parallelism — Parallel execution branches are strictly read-only; a specialist may execute writes only when running as the sole active agent in a sequential step ($UU6$)
- **Related Architectural Decision Points**:
  - [`TA-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/04-tools-actions/TA-ADP-01-tool-registry-selection.md): Tool Registry & Selection *(Peer-Reviewed Risk Classes)*
  - [`TA-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/04-tools-actions/TA-ADP-03-action-validation-approval.md): Action Validation & Approval Tiers *(Two-Person Financial Thresholds)*
  - [`TA-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/04-tools-actions/TA-ADP-04-execution-credentials-isolation.md): Execution, Credentials & Isolation *(On-Behalf-Of Tokens & Output Screening)*
  - [`TA-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/04-tools-actions/TA-ADP-05-transactional-integrity-audit.md): Transactional Integrity & Audit *(SOX Audit Trails with Specialist Actor Attribution)*

---

## 1. Context & Problem Statement

In a multi-agent enterprise support system, delegating operational authority across specialist subgraphs creates severe security and consistency hazards:

1. **The Shared Identity Blame Diffusion Trap ($TA-D12$)**: If all specialists execute tool calls under a single monolithic agent token, forensic audit logs cannot distinguish whether an unauthorized database query or ticket modification was initiated by the Billing agent, the Technical agent, or a prompt-injected Generalist.
2. **The "Several Writers" State Corruption Exploit ($UU6$)**: When two specialists execute concurrently in parallel (e.g., Technical diagnosing a network outage while Account & Ops manages user access), both agents might attempt to mutate the same enterprise record simultaneously (e.g., both appending conflicting ticket comments, or one changing an email while the other triggers a password reset). Parallel write collisions produce lost updates and inconsistent database states.
3. **The Unverified Action Hallucination Disaster ($UU1 / KK2$)**: An agent hallucinates that a database rollback or payment credit succeeded and informs the user: *"I have issued your $12,400 credit memo"*. In reality, the call was blocked by an approval gate, timed out, or was never dispatched. Announcing unverified actions creates acute legal and financial liability (*Moffatt v. Air Canada*).
4. **Privilege Creep Across Subgraphs**: A Generalist handling a simple inquiry must not possess access to high-privilege infrastructure APIs (e.g., `aws.restart_cluster`), while a Technical specialist must not possess access to payment ledgers (`stripe.refund_charge`).

### The Core Architectural Question
> **How do we grant specialists the operational autonomy to execute routine low-risk actions directly, while preventing parallel write collisions, enforcing cryptographic actor attribution, and mathematically guaranteeing that unverified actions are never reported as complete?**

---

## 2. Decision Framework & Theoretical Formulation

To solve these challenges, `MA-D9`, `MA-D14`, and `MA-D18` establish the **Role-Scoped Identity Model with Read-Only Parallelism and Read-Back Verification**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                            CONCURRENT WRITER ISOLATION (MA-D18)                                  │
├─────────────────────────────────────────────────┬────────────────────────────────────────────────┤
│   PHASE 1: PARALLEL AUDIT / DIAGNOSTICS         │   PHASE 2: SEQUENTIAL STATE MUTATION           │
├─────────────────────────────────────────────────┼────────────────────────────────────────────────┤
│   • Execution Mode: Parallel Fan-Out            │   • Execution Mode: Single-Agent Sequential    │
│   • Concurrency Invariant: STRICTLY READ-ONLY   │   • Concurrency Invariant: Exactly 1 Writer    │
│   • Billing Agent: READ-ONLY (Reads Invoices)   │   • Technical Agent runs alone in graph        │
│   • Technical Agent: READ-ONLY (Reads Syslogs)  │   • Permitted: Directly executes Low-Risk      │
│   • Account Agent: READ-ONLY (Reads SAML)       │     Write (e.g., tags Jira issue BUG-8192)     │
│   • Zero write collisions (UU6 mathematically   │   • High-Risk Writes: Proposed to Coordinator  │
│     eliminated)                                 │     for Two-Person Human Approval              │
└─────────────────────────────────────────────────┴────────────────────────────────────────────────┘
```

---

### Pillar A: Role-Scoped Identity & Dual-Subject Attribution (`MA-D9`)

Every specialist executes tool calls using a distinct, cryptographically verifiable security principal:

$$\text{Identity}_{\text{call}} = \langle \text{sub}: \text{Principal}_{\text{customer}}, \text{act}: \text{Role}_{\text{specialist}}, \text{tenant}: \text{TenantID} \rangle$$

1. **RFC 8693 Actor Delegation**: Downstream requests carry the `act` claim identifying the exact sub-agent (e.g., `act="specialist.billing"`).
2. **Intersection of Authorities**: A tool call is permitted if and only if it falls within the intersection of the customer's permissions and the specialist's allow-list:
   $$\mathcal{T}_{\text{executable}} = \mathcal{T}_{\text{user\_permissions}} \cap \mathcal{T}_{\text{specialist\_allowlist}}$$
   - The Billing specialist's allow-list contains Stripe and SAP tools; it cannot call CloudWatch or Okta.
   - The Technical specialist's allow-list contains CloudWatch and Datadog; it cannot call Stripe or ERP tools.
3. **Low-Risk Direct Writes vs. Proposed Actions**:
   - **`LOW_RISK_WRITE`**: Executed directly by the specialist without coordinator round-trip (e.g., `jira.add_comment`, `auth0.send_verification_email`).
   - **`HIGH_RISK_WRITE` / Financial**: The specialist is **structurally barred** from direct dispatch; it emits a `ProposedAction` deliverable in its result envelope. The Coordinator presents the proposal to the human approval gate (`TA-ADP-03`).

---

### Pillar B: Read-Only Parallelism & Concurrency Mutex (`MA-D18` / $UU6$)

To eliminate the "several writers" collision failure mode ($UU6$):
The Coordinator schedules execution in two strictly enforced concurrency modes:

$$\text{CanExecuteWrite}(s, t) \iff \text{RiskClass}(t) = \text{LOW\_RISK\_WRITE} \land |\mathcal{S}_{\text{active\_in\_turn}}| = 1$$

1. **Parallel Execution Invariant**: Whenever the Coordinator dispatches multiple specialists in parallel (e.g., Billing and Technical running concurrently during Flow B), the tool dispatcher intercepts all calls and dynamically forces:
   $$\text{Tools}_{\text{parallel}}(s) = \mathcal{T}_{\text{allowlist}}(s) \cap \mathcal{T}_{\text{READ\_ONLY}}$$
   Any mutating tool call attempted during a parallel branch is rejected with `ConcurrencyViolationException`.
2. **Sequential Write Scheduling**: If a specialist needs to execute a low-risk write, it must be scheduled in a dedicated sequential step where it is the sole active agent operating in the case.

---

### Pillar C: Two-Phase Read-Back Verification Protocol (`MA-D14` / $UU1$)

To guarantee that the agent never falsely claims an action succeeded ($KK2$, $UU1$):

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                         TWO-PHASE READ-BACK VERIFICATION FLOW (MA-D14)                           │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

Step 1: Specialist Dispatches Low-Risk Write Tool (e.g., update_ticket_status("IN_PROGRESS"))
Step 2: External System Returns HTTP 200 OK
Step 3: MANDATORY READ-BACK: Tool Adapter immediately executes a fresh GET request
        read_ticket_status() -> Asserts status == "IN_PROGRESS"
Step 4: Verification Gate
        • Match Confirmed: Specialist emits FactualFinding("Ticket status verified as IN_PROGRESS")
        • Discrepancy Detected: Specialist emits Status("BLOCKED", reason="State read-back mismatch")
Step 5: Coordinator receives verified deliverable and announces success to customer.
```

- **Unverified Reporting Ban**: A specialist is forbidden from including unverified mutations in its findings.
- **Single Customer Voice**: Only the Coordinator delivers the final customer-facing response (`MA-ADP-05`). It only announces actions that have successfully passed the read-back verification barrier.

---

## 3. Decision Rules, Structural Invariants & Code Contracts

### Decision Invariants
1. **Invariant 1 (Actor Attribution in Audit)**: Every tool invocation record in the append-only ledger (`TA-ADP-05`) must record the specialist role in the `actor_subrole` column.
2. **Invariant 2 (Parallel Mutating Ban)**: Under no circumstances may a mutating tool call execute while more than one specialist thread is active in the LangGraph runtime.
3. **Invariant 3 (Structural Ban on High-Risk Direct Writes)**: The tool execution gateway MUST reject any attempt by a specialist to directly execute a `HIGH_RISK_WRITE` or `DESTRUCTIVE_IRREVERSIBLE` tool; such actions must be returned as proposals.
4. **Invariant 4 (Mandatory Read-Back)**: A mutating tool call is not marked complete until a subsequent read operation confirms the modification in the external system.

---

### Python & Pydantic Data Contracts

```python
"""
Data contracts for Specialist Permissions, Actor Scopes, and Verified Writes.
Module: core/multiagent/permissions.py
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class ActorSubrole(str, Enum):
    COORDINATOR = "coordinator"
    SPECIALIST_GENERALIST = "specialist.generalist"
    SPECIALIST_BILLING = "specialist.billing"
    SPECIALIST_TECHNICAL = "specialist.technical"
    SPECIALIST_ACCOUNT_OPS = "specialist.account_ops"


class SpecialistToolAuthorization(BaseModel):
    """Configuration mapping allowed tool categories per specialist role."""
    role: ActorSubrole
    allowed_read_tools: List[str]
    allowed_low_risk_write_tools: List[str]
    # High-risk writes are strictly excluded from direct execution
    prohibited_tools: List[str] = Field(default_factory=list)


class ReadBackVerificationResult(BaseModel):
    """Proof of verified mutation emitted by the tool execution layer (MA-D14)."""
    tool_call_id: str
    target_entity_id: str
    mutation_type: str
    read_back_successful: bool
    verified_state_snapshot: Dict[str, Any]
    verified_at: datetime = Field(default_factory=datetime.utcnow)


class SpecialistActionExecutionRecord(BaseModel):
    """Audit payload capturing a low-risk write executed by a specialist."""
    actor_subrole: ActorSubrole
    tool_id: str
    arguments: Dict[str, Any]
    idempotency_key: str
    read_back_verification: ReadBackVerificationResult
    executed_in_sequential_mode: bool = Field(
        default=True, 
        description="Must be True per MA-D18"
    )
```

---

## 4. Failure Modes Matrix & Resilience Invariants

| Quadrant | Failure Scenario | Detection Mechanism | Systemic Mitigation & Recovery |
| :--- | :--- | :--- | :--- |
| **Q1: Known Knowns** | **Parallel Write Race Condition ($UU6$)**: Two parallel specialists attempt to write conflicting updates to the same customer ticket. | Concurrency interceptor detects write attempt when active worker count $> 1$. | Call is blocked before dispatch (`MA-D18`); parallel branches are strictly read-only; writes are deferred to sequential steps. |
| **Q2: Known Unknowns** | **Privilege Escalation Attempt**: Prompt injection inside a ticket instructs the Technical specialist to issue a Stripe refund. | Tool gateway checks tool allow-list for `specialist.technical`. | Tool gateway rejects `stripe.apply_credit_memo` with `UnauthorizedToolException`; tool is outside the specialist's allow-list (`MA-D9`). |
| **Q3: Unknown Knowns** | **False Action Proclamation ($UU1 / KK2$)**: Agent claims a server was rebooted when the external API returned an error. | Read-back verification engine compares actual state vs. expected state. | Mandatory read-back barrier (`MA-D14`): if read-back fails, the mutation is flagged as failed; Coordinator informs customer of failure. |
| **Q4: Unknown Unknowns** | **Subtle Write-Side Injection**: An attacker manipulates an allow-listed low-risk write tool into appending malicious links to a ticket. | Pre-execution argument screening via Presidio and URL sanitization. | Arguments to low-risk write tools pass through Comp 7 screening; URL allow-lists enforce strict outbound link filtering (`SG-ADP-03`). |

---

## 5. Closed-Loop Feedback & Verification Signals

1. **System Health Metrics**:
   - `Specialist_Direct_Write_Volume`: Monitored per specialist; tracks frequency of low-risk direct mutations.
   - `Read_Back_Verification_Failure_Rate`: Alerts immediately if external API state does not reflect successful mutations (alerts if $> 0.5\%$).
   - `Parallel_Write_Violation_Attempts`: Increments if an agent attempts a mutating call during a parallel phase.
2. **Weekly Permission Auditing**:
   - Automated CI testing suite validates tool allow-lists for all five specialists, asserting that zero high-risk or financial tools exist within specialist direct execution scopes.

---

## 6. Genesis Implementation Directives

1. **Code Locations**:
   - Implement specialist authorization filters in `core/multiagent/permissions.py`.
   - Implement read-back verification decorators in `core/tools/readback.py`.
   - Implement the concurrency mode validator in `core/multiagent/concurrency_guard.py`.
2. **Configuration Directives**:
   - Define immutable allow-lists in `config/specialist_permissions.yaml`:
     ```yaml
     specialist.billing:
       allowed_reads: ["billing.get_invoice", "billing.get_customer_balance"]
       allowed_low_risk_writes: ["billing.add_dispute_note"]
     specialist.technical:
       allowed_reads: ["cloudwatch.get_metrics", "k8s.get_pod_status"]
       allowed_low_risk_writes: ["jira.tag_issue"]
     ```

---

## 7. Consequences & Trade-offs

### Positive Consequences
- **Total Elimination of Write Collisions**: Enforcing read-only parallelism mathematically guarantees zero concurrent write race conditions.
- **Absolute Forensic Attribution**: Granular `act` claims in audit logs ensure complete visibility into which specific sub-agent initiated every database call.
- **Zero False Action Proclamations**: Mandatory post-mutation read-back ensures the agent never claims an action that failed downstream.

### Negative Consequences & Trade-offs
- **Sequential Execution Latency for Mutations**: Mutating operations cannot run concurrently with diagnostic reads, slightly increasing turn duration when writes are required.
- **Read-Back Network Overhead**: Executing a mandatory GET request after every mutating tool call doubles HTTP requests for write operations.
- **Authoring Overhead for Allow-Lists**: Maintaining separate read and low-risk write allow-lists for five specialists requires active configuration governance.

---

## 8. References & Cross-Disciplinary Grounding

1. **RFC 8693: OAuth 2.0 Token Exchange**: Internet Engineering Task Force. (Foundations of Actor Claims `act` for Multi-Tier Delegation).
2. **Principles of Distributed Database Systems**: Özsu, M. T., & Valduriez, P. (2011). Springer. (Concurrency Control and Isolation in Distributed Transactions).
3. **Moffatt v. Air Canada (2024 BCCRT 149)**: Legal precedent establishing corporate liability for inaccurate automated agent representations.
4. **Least Privilege in Multi-Agent Computing**: Saltzer, J. H., & Schroeder, M. D. (1975). *The Protection of Information in Computer Systems*.
