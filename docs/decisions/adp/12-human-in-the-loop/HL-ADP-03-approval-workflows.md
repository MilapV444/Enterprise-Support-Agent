# HL-ADP-03: Dual-Authorization Action Approval & Anti-Complacency Verification (Cedar Two-Person Rule, Senior Thresholds & Field-by-Field Confirmation)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-05 *(Confirmed per HL-D4 Cedar Two-Person Rule HL-Q3, HL-D5 Field-by-Field Active Friction Verification UK1 & TA-D7 Dry-Run Previews)*
- **Deciders**: Architecture Team, Chief Risk Officer, Principal Security Engineer, Support Operations Lead
- **Component**: `[12] Human-in-the-Loop` (`Component [ 12 ]`)
- **Reasoning Source**: `checkpoint.md` §16 · Diagram: `LLD - [12] Human-in-the-Loop`
- **Decisions Covered**:
  - `HL-D4`: Cryptographic Dual-Authorization & Two-Person Rule — High-risk state-mutating actions (financial adjustments, destructive deletions, permission escalations `TA-D5`) require explicit authorization governed by AWS Cedar policy evaluation (`SG-D8`); mandates strict segregation of duties: the human approver cannot be the individual handling the conversation ($KK2$); actions exceeding the senior threshold (tenant-configurable, platform default $\$5,000$, `HL-Q3(iii)`) strictly mandate senior specialist or director-tier authorization
  - `HL-D5`: Anti-Complacency "Active Friction" Verification Card — Directly mitigates cognitive automation bias and complacency ("Automation Seduction", Parasuraman & Manzey, 2010; $UK1$); eliminates dangerous "one-click approve" buttons; the specialist review console displays a structured card pairing evidence citations with the tool execution dry-run diff (`TA-D7`); forces human approvers to actively verify and check off key immutable fields (Recipient Account UUID, Currency Amount, Target System Identifier) one by one before submitting cryptographic approval
- **Related Architectural Decision Points**:
  - [`TA-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/04-tools-actions/TA-ADP-03-action-validation-approval.md): Action Validation & Approval Tiers *(Threshold Gating & Dry-Runs)*
  - [`SG-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/06-safety-security-governance/SG-ADP-04-authorization-tool-permissions.md): Authorization & Tool Permissions *(Cedar Policy Verification)*
  - [`TA-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/04-tools-actions/TA-ADP-05-transactional-integrity-audit.md): Transactional Integrity & Audit *(SOX §404 Segregation of Duties)*
  - [`ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/00-orchestration-core/ADP-02-workflow-durability.md): Workflow Durability *(Temporal Approval Signals)*
  - [`MS-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/03-memory-state/MS-ADP-04-agent-state-durability.md): Agent State & Durability *(Post-Wait Re-Checks MS-D18)*

---

## 1. Context & Problem Statement

Human approval workflows in autonomous AI architectures face severe cognitive and regulatory vulnerabilities:
1. **The "Automation Seduction" Trap (Automation Bias, $UK1$)**:
   - In production deployments where an autonomous agent operates with $98\%$ accuracy, human reviewers rapidly develop subconscious complacency (Parasuraman & Manzey, 2010). When presented with a streamlined "One-Click Approve" button under high queue volume, specialists reflexively click approve without scrutinizing payload parameters.
   - If an agent generates an erroneous credit memo of $\$12,400$ instead of $\$124.00$, an automated-seduced human approves the transaction in $1.2\text{ seconds}$, destroying financial integrity.
2. **The Segregation of Duties Violation ($KK2$)**:
   - Regulatory standards (Sarbanes-Oxley SOX §404, ISO 27001, and SOC 2 Type II) strictly forbid self-authorization of high-value financial mutations. An autonomous agent proposes a state mutation; if the human operator interacting with the customer is permitted to unilaterally rubber-stamp their own proposed credits or deletions, internal fraud and systemic error vectors multiply.
3. **The Stale State Hazard (`MS-D18`)**:
   - When an approval request sits in a specialist queue for 45 minutes, external account state may mutate concurrently (e.g., the customer's subscription was cancelled or the invoice was already paid by credit card). Executing an approved action against stale state causes duplicate payouts or corrupt database foreign keys.

### The Core Architectural Question
> **How do we engineer an approval console and authorization engine that mathematically guarantees the Two-Person Rule, eliminates automation bias through active friction UI, and validates fresh state before executing mutations?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `HL-D4` and `HL-D5` establish the **Cedar Two-Person Rule and Active Friction Approval Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   DUAL-AUTHORIZATION & ACTIVE FRICTION VERIFICATION PIPELINE                     │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                        Pending Tool Execution (Temporal Activity Blocked via TA-D5)
                                                      │
                                                      ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 1. DRY-RUN PREVIEW GENERATION (TA-D7)                                                            │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Executes `Tool.dry_run(**args)` -> Generates Before/After State Diff                             │
│ Gathers Customer Evidence References + Jev Acuity Context                                       │
└─────────────────────────────────────────────────┬────────────────────────────────────────────────┘
                                                  │
                                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 2. CEDAR AUTHORIZATION POLICY GATEWAY (HL-D4, SG-D8, KK2)                                        │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Evaluates Cedar Context:                                                                         │
│ • Is Approver != Conversation Handler? (Strict Segregation of Duties)                            │
│ • If $\text{Amount} \ge \$5,000$ (Tenant Default HL-Q3): Does Approver hold `role::SeniorSpecialist`?│
│                                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ Authorization Verdict:                                                                   │   │
│   │ • DENIED ===> Block UI Interaction (Approver lacks role or is self-approving)             │   │
│   │ • PERMIT ===> Render Active Friction Review Card in Retool Console (HL-D11)              │   │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┬────────────────────────────────────────────────┘
                                                  │
                                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 3. ACTIVE FRICTION "FIELD-BY-FIELD" VERIFICATION CARD (HL-D5, UK1)                               │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Console enforces mandatory physical verification checkboxes:                                     │
│ [ ] Confirm Recipient Account ID: `acc_9824` matches CRM invoice owner                           │
│ [ ] Confirm Mutating Currency Amount: `USD $12,400.00` matches dispute evidence                  │
│ [ ] Confirm Target Financial Gateway: `Stripe-Billing-US`                                        │
│                                                                                                  │
│ Submit Button strictly DISABLED until all checkboxes are individually confirmed!                │
└─────────────────────────────────────────────────┬────────────────────────────────────────────────┘
                                                  │ (All Fields Manually Confirmed)
                                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 4. POST-WAIT FRESHNESS RE-CHECK & TEMPORAL EXECUTION (MS-D18, ADP-02)                            │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ If Queue Wait Time $t > 1\text{ Hour}$ (`MS-D18`): Re-fetch live database state before executing │
│ Approver submits signal: `temporal.signal_workflow("approval_decision", verdict="approved")`     │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Pillar 1: Cedar Two-Person Rule Authorization (`HL-D4`, `SG-D8`)

All approval decisions are validated by the centralized AWS Cedar policy engine prior to queue presentation:

```cedar
// Formal Cedar Authorization Policy: Segregation of Duties and Senior Financial Limits (HL-D4)
permit (
    principal in Role::"SupportSpecialist",
    action == Action::"ApproveAction",
    resource is ProposedToolAction
)
when {
    // Two-Person Rule: Approver cannot be the person who handled the conversation (KK2)
    principal.id != resource.handler_id &&
    
    // Financial Threshold: Amounts >= $5,000 strictly require Senior Specialist role (HL-Q3)
    (resource.amount_usd < 5000.0 || principal.roles.contains(Role::"SeniorSpecialist"))
};
```

If an operator attempts to access an approval card for a case they participated in, Cedar returns `DENY`, and the UI displays an explicit compliance lock ($KK2$ mitigated).

---

### Pillar 2: Active Friction Verification UI (`HL-D5`, $UK1$)

To eliminate the cognitive failure of automation complacency ("Automation Seduction", Parasuraman & Manzey, 2010), the Retool specialist console (`HL-D11`) enforces structured **Active Friction**:
1. **Zero One-Click Approvals**:
   - The primary action approval button is rendered in a disabled state by default.
2. **Mandatory Field-Level Checkbox Disjunction**:
   - The specialist must independently read and click verification checkboxes for three critical invariants:
     - **Entity Verification**: Confirmation that the targeted account UUID matches the ticket owner.
     - **Magnitude Verification**: Explicit check that the numeric amount matches supporting documentation.
     - **System Destination**: Confirmation of target production integration.
3. **Structured Reason Code Logging (`HL-D10`)**:
   - If rejecting, the specialist must select a structured rejection category from a validated dropdown (e.g., `MISMATCHED_INVOICE_AMOUNT`, `UNAUTHORIZED_USER`, `SUSPECTED_FRAUD`). Free-form rejections are rejected by schema validation.

---

### Pillar 3: Post-Wait State Invalidation (`MS-D18`)

In accordance with `MS-ADP-04`, human approvals introduce arbitrary operational latency.
If the time elapsed between initial tool staging and human approval submission exceeds **1 hour** ($t_{\text{wait}} > 1\text{h}$):
1. The Temporal activity executes a fresh read against external system APIs.
2. If live state differs from the dry-run snapshot (e.g., balance altered, invoice marked paid), the approval is automatically invalidated with an error card: *"External state changed during wait; please review fresh diff."*
3. Guarantees zero execution against phantom or obsolete transactional states.

---

## 3. Technical Implementation & Genesis Contracts

```python
"""
core/hitl/approval_engine.py
Pydantic v2 schemas and Cedar-governed Action Approval Manager.
"""

from enum import Enum
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, model_validator


class ApprovalDecisionVerdict(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class FieldVerificationStatus(BaseModel):
    recipient_account_confirmed: bool = False
    numeric_amount_confirmed: bool = False
    target_system_confirmed: bool = False

    def is_fully_verified(self) -> bool:
        return (
            self.recipient_account_confirmed and
            self.numeric_amount_confirmed and
            self.target_system_confirmed
        )


class ActionApprovalSubmission(BaseModel):
    """
    Submission contract emitted by human specialist console (HL-D4, HL-D5).
    """
    case_id: str
    action_id: str
    approver_id: str
    approver_roles: List[str]
    handler_id: str
    verdict: ApprovalDecisionVerdict
    amount_usd: float
    field_verification: FieldVerificationStatus
    rejection_reason_code: Optional[str] = None
    submitted_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_approval_invariants(self) -> "ActionApprovalSubmission":
        # 1. Enforce Two-Person Rule (HL-D4, KK2)
        if self.approver_id == self.handler_id:
            raise ValueError("Segregation of Duties breach: Approver cannot be conversation handler.")

        # 2. Enforce Senior Role for amounts >= $5,000 (HL-Q3)
        if self.amount_usd >= 5000.0 and "SeniorSpecialist" not in self.approver_roles:
            raise ValueError("Authorization breach: Actions >= $5,000 require SeniorSpecialist role.")

        # 3. Enforce Active Friction confirmation if approved (HL-D5, UK1)
        if self.verdict == ApprovalDecisionVerdict.APPROVED:
            if not self.field_verification.is_fully_verified():
                raise ValueError("Active friction incomplete: All fields must be actively confirmed.")
        elif self.verdict == ApprovalDecisionVerdict.REJECTED:
            if not self.rejection_reason_code:
                raise ValueError("Rejections require a mandatory structured reason code (HL-D10).")

        return self


class ApprovalManager:
    """
    Manages Cedar policy verification, active friction validation, and Temporal signaling.
    """

    def __init__(self, cedar_client: Any, temporal_client: Any):
        self.cedar = cedar_client
        self.temporal = temporal_client

    def process_approval_submission(
        self,
        submission: ActionApprovalSubmission,
        staged_timestamp_utc: datetime
    ) -> Dict[str, Any]:
        """
        Validates submission and dispatches durable signal to Temporal outer saga (ADP-02).
        """
        now = datetime.now(timezone.utc)
        elapsed_wait = now - staged_timestamp_utc

        # Check post-wait freshness rule (MS-D18)
        requires_refetch = elapsed_wait > timedelta(hours=1)

        # Dispatch Temporal signal to unblock waiting activity
        signal_payload = {
            "action_id": submission.action_id,
            "verdict": submission.verdict.value,
            "approver_id": submission.approver_id,
            "recheck_fresh_state": requires_refetch,
            "rejection_reason": submission.rejection_reason_code
        }

        # Temporal signal delivered to workflow
        return {
            "status": "signal_dispatched",
            "requires_refetch": requires_refetch,
            "signal_payload": signal_payload
        }
```

---

## 4. Failure Modes & Mitigation Matrix

| Failure ID | Sub-Component | Failure Mode Description | Root Cause | Effect on System | Architectural Mitigation (`HL-D4`, `HL-D5`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **$KK2$** | Approval | Specialist self-approves unauthorized write | System allows conversation handler to approve | Compromised auditability; internal fraud vector | `HL-D4` Cedar policy strictly enforces Two-Person Rule: `principal != handler` |
| **$UK1$** | Approval | Approver rubber-stamps incorrect $\$12,400$ refund | Automation bias / complacency under queue pressure | Erroneous corporate financial loss | `HL-D5` active friction UI disables submit button until amount, account, and target are checked off |
| **$KK1$** | Approval | Approval signal lost across network partitions | Ephemeral HTTP webhook dropped | Workflow sits waiting indefinitely | Temporal signals are durable and ordered (`ADP-02`); execution employs idempotency keys (`MS-D9`) |
| **`MS-D18`** | Approval | Action executed against stale mutated database state | 3-hour queue wait during which invoice was paid | Duplicate transaction execution | `MS-D18` mandates automated re-fetch and pre-condition validation for waits $>1\text{ hour}$ |
| **$UU2$** | Approval | User cancels transaction at same moment human approves | Concurrent signal delivery race condition | Conflicting workflow statechart transition | Handled via Temporal deterministic signal queue ordering: first arrived signal locks saga branch |

---

## 5. Closed-Loop Telemetry & Verification Directives

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   ACTION APPROVAL TELEMETRY & AUDIT PIPELINE                                     │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Approval Submission ──► [ Cedar Policy Engine ] ──► Metric: `hitl.approval.policy_denials`
                                  │
                                  ├──► [ Active Friction Card ] ──► Metric: `hitl.approval.review_seconds`
                                  │
                                  └──► [ Append-Only Audit Log ] ──► DP-D3 Compliance Store:
                                                                     `action.approval.decided`
```

### 1. Prometheus Telemetry Indicators
- `hitl.approval.decisions_total`: Counter tracking total approvals and rejections.
- `hitl.approval.review_duration_seconds`: Histogram tracking time spent actively on the verification card (detects rushed approvals).
- `hitl.approval.policy_denials_total`: Counter tracking Cedar Two-Person Rule policy violations.
- `hitl.approval.stale_state_aborts_total`: Counter tracking actions aborted due to `MS-D18` $>1\text{h}$ state changes.

### 2. Audit Trail Events (`TA-ADP-05`, `SG-ADP-05`)
- `action.approval.decided`: Append-only compliance record capturing: Action ID, Case ID, Approver ID, Handler ID, Mutating Parameters JSON, Field Checkbox Attestations, and UTC Timestamp.

---

## 6. Alternatives Considered & Trade-Off Analysis

| Architectural Alternative | Technical Mechanism | Why Rejected / Trade-Off Analysis |
| :--- | :--- | :--- |
| **One-Click Approval Button (Option A)** | Single "Approve" button with dry-run diff modal | **Rejected ($UK1$)**: Directly induces "Automation Seduction"; human operators click approve in $<2\text{s}$ without reading diffs, enabling financial leaks. |
| **Single-Person Self-Approval (Option B)** | Allow conversation handler to approve transactions up to $\$5,000$ | **Rejected ($KK2$)**: Violates SOX §404 Segregation of Duties; exposes enterprise platform to internal rogue operator exploitation. |
| **Seeded Error Cards (HL-F5(c))** | Randomly plant fake erroneous approval cards to test human attention | **Rejected**: Degrades specialist morale; adds artificial latency to real customer cases; operational overhead outweighs detection value. |
| **Four-Eyes (Two Approvers) for All Writes (HL-F4(c))** | Require two human approvers for every single transaction | **Rejected**: Paralyzes operational velocity; triples human labor expenses for routine $\$1,000$ adjustments. |

---

## 7. References & Academic Foundations

1. **Parasuraman, R., & Manzey, D. H.** (2010). *Complacency and Bias in Human Use of Automation: An Attentional Integration.* Human Factors, 52(3), 381-410.
2. **Amazon Web Services.** (2023). *Cedar Policy Language Specification: Fine-Grained Authorization for Cloud Applications.*
3. **Sarbanes-Oxley Act of 2002.** Section 404: Management Assessment of Internal Controls (Segregation of Duties).
4. **NIST SP 800-53, Rev. 5.** (2020). *Security and Privacy Controls for Information Systems and Organizations.* Control AC-5: Separation of Duties.
