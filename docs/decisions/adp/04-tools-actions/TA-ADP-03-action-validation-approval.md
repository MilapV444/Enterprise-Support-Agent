# TA-ADP-03: Action Validation & Approval Tiers (Tiered Autonomy, Jev Context Tightening & Two-Person Financial Governance)

- **Status**: Accepted & Confirmed
- **Date**: 2026-09-29 *(Amended: 2026-09-29 per TA-D5 Tiered Gates, TA-D6 Jev Tightening, TA-D7 Dry-Run Previews, TA-D14 Per-Call Counting, TA-Q1 $1,000 Threshold & TA-Q4 Ask/Deny Routing)*
- **Deciders**: Architecture Team, Head of Product Operations, AI Safety Core
- **Component**: `[4] Tools & Actions` (`Component [ 4 ]`)
- **Reasoning Source**: `checkpoint.md` §8 · Diagram: `LLD - [4] Tools & Actions`
- **Decisions Covered**:
  - `TA-D5`: Tiered Autonomy & Financial Thresholds — Automatic execution for reads and low-risk writes; financial actions $\ge$ tenant threshold (platform default $\$1,000$, `TA-Q1`), destructive, or irreversible actions mandate Human Approval (Two-Person Rule); amount checks strictly in code
  - `TA-D6`: Jev Dynamic Tool-Call Gating — Context-aware evaluation (`Choice` allow/ask/deny + `Noul` "serves user request?"); code combines statically: result is strictly the *stricter-of* the static rule and Jev; Jev can only tighten, never loosen permissions; "ask" routes to user (reads/low-risk) or human specialist (financial/high-risk, `TA-Q4`)
  - `TA-D7`: Dry-Run & Approval Preview Cards — External API dry-runs (where supported) render structured before/after diffs on approval cards; unsupported tools render validated parameters + fresh live state reads
  - `TA-D14`: Threshold Evaluation Model — Threshold evaluated on a per-call basis; threshold-splitting risks ($UU4$) mitigated via continuous audit logging and sub-threshold velocity anomaly alerts
- **Related Architectural Decision Points**:
  - [`ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/00-orchestration-core/ADP-05-decision-model-jev.md): Decision Model (Jev) *(Categorical Decision API & Boundary)*
  - [`HL-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#hl-adp-03--intervention-tripwires--routing): Intervention Tripwires & Routing *(Specialist Escalation Queues)*
  - [`HL-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#hl-adp-04--action-approval--presentation): Action Approval & Presentation *(Interactive Approval Cards)*
  - [`SG-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#sg-adp-04--authorization--central-policy-engine): Authorization & Central Policy Engine *(Cedar Authorization Policies)*

---

## 1. Context & Problem Statement

Autonomous support agents operating in enterprise settings must navigate a critical tension between execution velocity and catastrophic operational risk:

1. **The Excessive Human Friction Dilemma**: Mandating human approval for every database read or status lookup destroys the core economic value of an automated support agent, overwhelming human specialist queues with trivial tasks.
2. **The Unchecked Financial / Destructive Disaster ($KK5$)**: Conversely, granting full autonomy to execute financial credits or infrastructure modifications exposes the enterprise to massive liability. An agent hallucinating a $\$12,400$ refund or terminating an active production cluster without human sign-off creates immediate commercial loss.
3. **Off-Purpose Context Infiltration ($UK2$)**: Static role-based access control (RBAC) grants broad read permissions to a service account. Under naive execution, an agent handling a customer's simple network latency inquiry might invoke `get_employee_compensation` or inspect executive account notes. The call is technically permitted by the agent's IAM role, but completely illegitimate in the context of the user's specific request.
4. **Threshold Splitting Attacks ($UU4$)**: If human review is triggered strictly above a financial ceiling (e.g., $\$1,000$), an adversarial user or looping agent might issue 13 consecutive $\$950$ refund credits, successfully executing $\$12,350$ in total refunds while bypassing every static human gate.

### The Core Architectural Question
> **How do we construct a deterministic, multi-tiered action validation engine that enables rapid autonomous execution for low-risk operations, mandates human sign-off for financial and irreversible actions, and dynamically blocks off-purpose operations without ever allowing model decisions to weaken static security bounds?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these challenges, `TA-D5`, `TA-D6`, and `TA-D7` establish the **Stricter-Of Dual-Gate Validation Engine**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                          STRICTER-OF DUAL-GATE ACTION VALIDATION (TA-D5, TA-D6)                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

Proposed Tool Call: t*, Arguments: {amount: $1,240, invoice_id: "INV-9821"}
                           │
       ┌───────────────────┴───────────────────┐
       ▼                                       ▼
┌───────────────────────────────┐     ┌───────────────────────────────┐
│ GATE 1: Deterministic Static  │     │ GATE 2: Jev Dynamic Context   │
│ Code & Threshold Policy       │     │ Purpose Verification          │
│ • Risk Class: HIGH_RISK_WRITE │     │ • Choice: [allow, ask, deny]  │
│ • Amount >= Tenant Threshold  │     │ • Noul: "serves request?"     │
│   ($1,240 >= $1,000 Default)  │     │ • PII-Masked State Vector     │
│ • Decision: ASK_SPECIALIST    │     │ • Decision: ASK               │
└───────────────────────────────┘     └───────────────────────────────┘
       │                                       │
       └───────────────────┬───────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ COMBINATION LATTICE: Result = Max_⪯ (Gate 1, Gate 2)                │
│ Rule: ALLOW ⪯ ASK_USER ⪯ ASK_SPECIALIST ⪯ DENY                     │
│ Invariant: Jev can ONLY tighten static policy, NEVER loosen it      │
│ Final Verdict: ASK_SPECIALIST                                       │
└─────────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ EXECUTION / APPROVAL ROUTING (TA-D7, TA-Q4)                         │
│ • If ALLOW: Execute automatically via Temporal Activity             │
│ • If ASK_USER: Render inline chat confirmation card                 │
│ • If ASK_SPECIALIST: Emit Dry-Run Approval Card (HL-ADP-04)         │
│ • If DENY: Drop call, record failed step for ADP-04 Circuit Breaker │
└─────────────────────────────────────────────────────────────────────┘
```

---

### Pillar A: Multi-Tiered Action Classification Lattice

We establish a strict semi-lattice of authorization decisions:
$$\mathcal{D}_{\text{lattice}}: \quad \text{ALLOW} \prec \text{ASK\_USER} \prec \text{ASK\_SPECIALIST} \prec \text{DENY}$$

#### Gate 1: Deterministic Code Policy (`TA-D5`)
Evaluated in pure Python without LLM dependencies. Given tool $t$ with risk class $\mathcal{R}(t)$ and financial parameter $v_{\text{amount}}$:
$$\mathcal{G}_{\text{static}}(t, v) = \begin{cases}
\text{ALLOW} & \text{if } \mathcal{R}(t) = \text{READ\_ONLY} \\
\text{ALLOW} & \text{if } \mathcal{R}(t) = \text{LOW\_RISK\_WRITE} \land v_{\text{amount}} < \theta_{\text{tenant}} \\
\text{ASK\_SPECIALIST} & \text{if } v_{\text{amount}} \ge \theta_{\text{tenant}} \\
\text{ASK\_SPECIALIST} & \text{if } \mathcal{R}(t) \in \{\text{HIGH\_RISK\_WRITE}, \text{DESTRUCTIVE\_IRREVERSIBLE}\}
\end{cases}$$

Where $\theta_{\text{tenant}}$ is the tenant's configured financial threshold, with platform default:
$$\theta_{\text{default}} = \$1,000.00 \quad (\text{Configurable per tenant in SQL}, \text{TA-Q1})$$

---

### Pillar B: Jev Dynamic Context & Purpose Gating (`TA-D6`)

To catch off-purpose reads ($UK2$) and context anomalies, every proposed tool call is evaluated by Jev against the masked conversation turn:

1. **Categorical Action Gate**:
   $$\text{Decision}_{\text{jev}} = \text{Jev.Choice}\left(
   \text{State} = \tilde{u}_{\text{turn}}, 
   \text{Question} = \text{"Is this proposed tool call appropriate, requiring confirmation, or forbidden?"}, 
   \text{Options} = [\text{ALLOW}, \text{ASK}, \text{DENY}]
   \right)$$
2. **Strict Purpose Verification**:
   $$\mathbb{P}(\text{serves\_request}) = \text{Jev.Noul}\left(
   \text{State} = \tilde{u}_{\text{turn}}, 
   \text{Question} = \text{"Does this action directly serve the customer's stated inquiry?"}
   \right)$$

Filtering rule: If $\mathbb{P}(\text{serves\_request}) < 0.85$, the Jev recommendation is escalated to at least `ASK`.

#### The Stricter-Of Combination Guarantee
$$\mathcal{G}_{\text{final}}(t) = \max_{\prec}\left( \mathcal{G}_{\text{static}}(t), \mathcal{G}_{\text{jev}}(t) \right)$$
- If Static says `ALLOW` and Jev says `ALLOW` $\implies$ **ALLOW**.
- If Static says `ALLOW` and Jev says `ASK` $\implies$ **ASK** (Jev tightens).
- If Static says `ASK_SPECIALIST` and Jev says `ALLOW` $\implies$ **ASK_SPECIALIST** (Static holds; Jev cannot loosen).
- If either says `DENY` $\implies$ **DENY**.

---

### Pillar C: Routing, Dry-Run Previews & Approval Cards (`TA-D7`, `TA-Q4`)

When $\mathcal{G}_{\text{final}}$ requires human intervention, routing follows strict operational tiers (`TA-Q4`):

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                               APPROVAL CARD ROUTING TAXONOMY (TA-Q4)                             │
├────────────────────────────────┬────────────────────────────────┬────────────────────────────────┤
│   Verdict: ASK_USER            │   Verdict: ASK_SPECIALIST      │   Verdict: DENY                │
├────────────────────────────────┼────────────────────────────────┼────────────────────────────────┤
│   • Trigger: Low-risk read/    │   • Trigger: Financial >= $1k, │   • Trigger: Off-purpose,      │
│     write with context doubt   │     destructive, or high-risk  │     unauthorized, or rejected  │
│   • Route: Customer chat window│   • Route: Human Specialist    │   • Action: Drop tool call     │
│   • Card: Inline confirmation  │     Queue (HITL, Comp 13)      │   • Feedback: Normalized error │
│     ("Confirm updating email?")│   • Card: Rich Before/After    │     sent to agent trajectory   │
│   • Timeout: 30m idle session  │     Diff + Dry-Run Preview     │   • Counter: Increments failed │
│   • Rejection: Abort step      │   • Timeout: Multi-day Temporal│     step for ADP-04 breaker    │
└────────────────────────────────┴────────────────────────────────┴────────────────────────────────┘
```

#### Dry-Run Previews (`TA-D7`)
If the tool declares `supports_dry_run = True`, the runner executes a simulated execution (`--dry-run` or preview API endpoint). The computed delta is injected into the CloudEvents action card (`UA-ADP-04`, `HL-ADP-04`):
$$\text{PreviewPayload} = \left\{ \text{current\_state}: v_{\text{before}}, \text{projected\_state}: v_{\text{after}}, \text{financial\_impact}: \Delta v \right\}$$
For tools lacking native dry-run support, the card displays the validated parameter dictionary accompanied by a fresh read of current database state.

---

## 3. Decision Rules, Structural Invariants & Code Contracts

### Decision Invariants
1. **Invariant 1 (Mathematical Ceiling Inviolability)**: Financial thresholds MUST be evaluated in compiled Python code. Model outputs may never override numerical thresholds.
2. **Invariant 2 (Monotonic Tightening Guarantee)**: Under no operational condition may Jev downgrade an `ASK_SPECIALIST` or `DENY` decision produced by static rules.
3. **Invariant 3 (Denial Circuit Trip)**: A tool denial (`DENY`) must immediately register as a step failure in the agent's trajectory, feeding into the `StepCeilingGuard` and `Reflexion` circuit breakers (`ADP-04`).
4. **Invariant 4 (Threshold Splitting Velocity Detector, `TA-D14`)**: If a single Case accumulates more than $3$ sub-threshold financial writes totaling $\ge \$1,500$ within $24$ hours, automated execution is locked, forcing specialist review.

---

### Python & Pydantic Data Contracts

```python
"""
Data contracts for Action Validation, Gating, and Approval Cards.
Module: core/tools/action_validator.py
"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class GateVerdict(str, Enum):
    ALLOW = "allow"
    ASK_USER = "ask_user"
    ASK_SPECIALIST = "ask_specialist"
    DENY = "deny"


class StaticPolicyEvaluation(BaseModel):
    """Result of Gate 1 deterministic code checks."""
    tool_id: str
    risk_class: str
    amount_evaluated: Optional[float] = None
    tenant_threshold: float
    verdict: GateVerdict
    evaluation_rule: str


class JevGateEvaluation(BaseModel):
    """Result of Gate 2 Jev dynamic context and purpose checks."""
    tool_id: str
    verdict: GateVerdict
    serves_user_request_prob: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: Optional[str] = None


class ActionValidationResult(BaseModel):
    """Final unified decision emitted by the action validation engine."""
    tool_id: str
    final_verdict: GateVerdict
    static_eval: StaticPolicyEvaluation
    jev_eval: JevGateEvaluation
    
    # Approval metadata (populated if ASK_*)
    approval_card_id: Optional[str] = None
    dry_run_executed: bool = Field(default=False)
    dry_run_preview: Optional[Dict[str, Any]] = None
    
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)


class SubThresholdVelocityAlert(BaseModel):
    """Telemetry alert emitted when threshold splitting is suspected (TA-D14)."""
    case_id: str
    tenant_id: str
    sub_threshold_writes_count: int
    cumulative_amount: float
    triggered_specialist_lock: bool
```

---

## 4. Failure Modes Matrix & Resilience Invariants

| Quadrant | Failure Scenario | Detection Mechanism | Systemic Mitigation & Recovery |
| :--- | :--- | :--- | :--- |
| **Q1: Known Knowns** | **Off-Purpose Salary Table Read ($UK2$)**: Agent handling a billing query attempts to read employee HR tables using valid system credentials. | Jev Purpose Gate (`TA-D6`) flags `serves_request_prob < 0.20`. | Final verdict escalates to `DENY`; tool call is blocked and logged as an authorization violation. |
| **Q2: Known Unknowns** | **Jev Gate False Denial Friction ($KU2$)**: Jev misjudges a legitimate technical query as off-purpose, denying a required diagnostic tool. | Step failure counter increments; Reflexion verbal critique logs reason. | If circuit breaker trips after 2 trials (`ADP-04`), ticket routes to HITL with full diagnostic trajectory; calibrated thresholds per route (`ADP-05-Q2`). |
| **Q3: Unknown Knowns** | **Unpreviewed State Mutation ($KU4$)**: Approver confirms a database write without seeing a dry-run diff because the legacy API has no preview endpoint. | Action card displays `dry_run_executed = False` flag. | Engine automatically executes a live pre-read of current state, displaying side-by-side arguments and live records on the card (`TA-D7`). |
| **Q4: Unknown Unknowns** | **Threshold Splitting Exploit ($UU4$)**: Attacker issues 13 $\times$ $\$950$ refund calls to avoid the $\$1,000$ approval threshold. | Sub-threshold velocity detector tracks cumulative financial writes per Case. | Case financial accumulator detects cumulative sum $\ge \$1,500$ (`TA-D14`); locks case and routes all subsequent writes to Human Specialist. |

---

## 5. Closed-Loop Feedback & Verification Signals

1. **Real-Time Telemetry**:
   - `Action_Validation_Verdict_Distribution`: Emits counters for `ALLOW`, `ASK_USER`, `ASK_SPECIALIST`, and `DENY`.
   - `Jev_Gate_Tightening_Rate`: Tracks how often Jev upgraded an `ALLOW` to `ASK` or `DENY`.
   - `Sub_Threshold_Write_Velocity`: Monitored per tenant; alerts if multiple writes occur within $1$ hour on a single case.
2. **Weekly Risk Audit**:
   - Sample $100$ approved financial action cards. Review approver decision times and verify that zero unapproved financial transactions $\ge \$1,000$ occurred in production.

---

## 6. Genesis Implementation Directives

1. **Code Locations**:
   - Implement static checks and lattice resolution in `core/tools/action_validator.py`.
   - Implement Jev gating queries in `core/tools/jev_gating.py`.
   - Implement dry-run preview generators in `tools/adapters/`.
   - Implement the threshold splitting detector in `core/tools/velocity_guard.py`.
2. **Configuration & Tenant Overrides**:
   - Store tenant-specific financial thresholds in Postgres `tenant_configs`:
     ```sql
     ALTER TABLE tenant_configs ADD COLUMN financial_approval_threshold NUMERIC(10, 2) DEFAULT 1000.00;
     ```

---

## 7. Consequences & Trade-offs

### Positive Consequences
- **Absolute Financial Governance**: Enforcing the Two-Person Rule in deterministic code guarantees the agent never autonomously dispenses major refunds or credits.
- **Context-Aware Safety Defense**: Jev tool gating blocks off-purpose data reads that pass static IAM role permissions, mitigating prompt injection probes.
- **Transparent Approver Experience**: Rendering rich dry-run diffs on approval cards enables human specialists to make rapid, informed decisions.

### Negative Consequences & Trade-offs
- **Latency Overhead on Mutating Turns**: Running parallel static checks and Jev gating queries adds $\approx 40\text{ms}$ to each mutating tool execution.
- **Risk of Threshold Splitting in Single Cases ($UU4$)**: Because thresholds are evaluated per call, defense against incremental micro-refunds relies on secondary velocity alerting.
- **Operational Approval Queue Load**: Setting default financial ceilings at $\$1,000$ diverts significant high-value billing inquiries to human specialist review queues.

---

## 8. References & Cross-Disciplinary Grounding

1. **The Protection of Information in Computer Systems**: Saltzer, J. H., & Schroeder, M. D. (1975). *Proceedings of the IEEE*. (Foundations of Separation of Privilege and the Two-Person Rule).
2. **Sarbanes-Oxley Act of 2002 (SOX) Section 404**: Management Assessment of Internal Controls over Financial Reporting. (Statutory requirements for dual-authorization on financial adjustments).
3. **OWASP Top 10 for LLM Applications (2025)**: Threat LLM06 — Excessive Agency and Inadequate Human Oversight.
4. **Context-Aware Access Control in Modern Distributed Architectures**: Al-Kahtani, M. A., & Sandhu, R. (2002). *Rule-Based Dynamic Access Control*. ACM SACMAT.
