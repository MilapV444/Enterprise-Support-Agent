# CR-ADP-04: Budgets & Cost Governance (Deterministic Usage Ledger, Soft-Cap Degradation & Gated FinOps Constraints)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-03 *(Confirmed per CR-D4 Monthly Soft-Cap Budgets UK2, CR-D7 Admin Showback Reports, CR-D11 Exact Usage Ledger KK3, CR-D12 Release Gate Cost Ceilings CR-Q3/Q4)*
- **Deciders**: Architecture Team, VP of Engineering, Lead FinOps Architect, Customer Success Director
- **Component**: `[11] Cost & Resource Management` (`Component [ 11 ]`)
- **Reasoning Source**: `checkpoint.md` §15 · Diagram: `LLD - [11] Cost & Resource Management`
- **Decisions Covered**:
  - `CR-D4`: Tiered Tenant Monthly Budgets & Graceful Soft-Cap — Configurable monthly financial budget per tenant (`DP-D12`); automated notifications trigger at $80\%$ threshold; reaching $100\%$ invokes a deterministic Soft Cap that degrades the agent to Knowledge-Base-Only answers (`RP-D2`) rather than abruptly shutting down service; user-facing banners and admin alerts proactively announce degraded mode ($UK2$)
  - `CR-D7`: Tenant Admin Showback & Transparency — Real-time and monthly usage and cost breakdown reporting for tenant administrators (showback model); exposes token volume, model tier distributions, and estimated costs per department/route without imposing direct automated chargebacks
  - `CR-D11`: Deterministic Ledger Source of Truth — Cost accounting derives from the exact orchestrator usage counter (`RP-D14`) multiplied by a versioned foundation model price table; reconciled monthly against upstream provider invoices and raw GPU infrastructure bills ($KK3$); decouples exact financial accounting from sampled telemetry traces (`OB-D13`)
  - `CR-D12`: Release Gate Economic Invariants — Mandates automated CI/CD release gate constraints (`EV-D5`): cost per resolved conversation per route may not increase by more than $10\%$ compared to the preceding production release (`CR-Q3(i)`), and must not exceed an absolute ceiling of $1.5\times$ the baseline first-month operational cost (`CR-Q4(i)`)
- **Related Architectural Decision Points**:
  - [`EV-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/08-evaluation-experimentation/EV-ADP-04-release-gate-approval-evidence.md): Release Gate & Approval Evidence *(Cost Invariants in CI/CD)*
  - [`RP-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/10-reliability-performance-scale/RP-ADP-01-admission-control.md): Admission Control *(RP-D14 Redis Counter & RP-D2 KB Degradation)*
  - [`OB-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/09-observability-monitoring/OB-ADP-04-token-cost-telemetry.md): Token & Cost Telemetry *(Trace Estimates vs. Exact Ledger)*
  - [`UA-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/01-user-application/UA-ADP-01-channels-api-transport.md): Channels & Transport *(Client Degraded Status Banners)*

---

## 1. Context & Problem Statement

Uncontrolled token consumption in autonomous enterprise agents creates existential margin erosion:
1. **The Silent Budget Drain**:
   - Unlike static cloud infrastructure, autonomous agents have variable marginal costs. A single enterprise tenant initiating complex multi-agent sagas or encountering adversarial prompt loops can burn thousands of dollars in commercial API fees in hours.
   - Without a deterministic financial firewall, an enterprise SaaS provider risks subsidizing runaway customer inquiries at an operating loss.
2. **The Abrupt Hard-Cap Blackout ($UK2$)**:
   - Conventional SaaS rate-limiting imposes hard cutoffs: when a monthly limit is reached, all further API calls return `HTTP 403 Forbidden` or `HTTP 429 Too Many Requests`.
   - In an enterprise customer support context, completely shutting off customer support mid-month creates catastrophic brand damage. Frustrated end-users conclude the software is completely broken rather than recognizing their company reached a contract allowance ($UK2$).
3. **The Trace Sampling Divergence ($KK3$, $UU1$)**:
   - Modern observability platforms utilize tail-based sampling (`OB-D4`) to limit telemetry storage. Using sampled OpenTelemetry traces as the source of truth for financial billing results in severe estimation errors ($>25\%$ variance).
   - Conversely, price tables frequently drift when providers introduce discounts, prompt-caching deductions, or new model revisions ($KK3$).

### The Core Architectural Question
> **How do we establish a deterministic, audit-grade FinOps governance engine that measures real-time usage with sub-cent accuracy, enforces graceful service degradation upon budget exhaustion, and prevents economic regression in automated deployment gates?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `CR-D4`, `CR-D7`, `CR-D11`, and `CR-D12` establish the **FinOps Governance and Budget Enforcement Architecture**, adhering to the FinOps Foundation lifecycle (Inform $\to$ Optimize $\to$ Operate).

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   FINOPS GOVERNANCE & BUDGET ENFORCEMENT ENGINE (CR-D4, CR-D11)                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                         Provider API Completion (LLM, Jev, Reranker, Guardrail)
                                                   │
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 1. EXACT USAGE METERING (RP-D14, CR-D11)                                                         │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Orchestrator reads exact token usage from provider response headers:                             │
│ • $\Delta_{\text{in}}$ (Input Tokens), $\Delta_{\text{cached}}$ (Cached Tokens), $\Delta_{\text{out}}$ (Output Tokens) │
│ • Atomic Redis Increment: `HINCRBY tenant:usage:{TenantID}:{Month} ...`                         │
└──────────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                   │
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 2. DETERMINISTIC FINANCIAL LEDGER (CR-D11)                                                       │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ $\text{Cost}(t) = \sum_{m} \left( \Delta_{\text{in}} \cdot P_{\text{in}}^{(m)} + \Delta_{\text{cached}} \cdot P_{\text{cached}}^{(m)} + \Delta_{\text{out}} \cdot P_{\text{out}}^{(m)} \right)$ │
│ • Price Table Version Pinned in Postgres                                                         │
│ • Monthly Reconciliation Job with Raw Provider Invoices (Fixes KK3)                              │
└──────────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                   │
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 3. BUDGET ENFORCEMENT & DEGRADATION STATE MACHINE (CR-D4, UK2)                                   │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Evaluate Cumulative Spend $S_{\text{month}}$ vs. Tenant Budget $B_{\text{tenant}}$:              │
│                                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ Budget Band:                                                                             │   │
│   │ • $S < 0.80 \cdot B$   ===> [NORMAL]: Full Agent & Specialist Functionality              │   │
│   │ • $0.80 \le S < 1.0 \cdot B$ ===> [WARNING]: Normal Execution + Email Alert to Admin       │   │
│   │ • $S \ge 1.0 \cdot B$   ===> [SOFT CAP]: Graceful Knowledge-Base-Only Mode (RP-D2)       │   │
│   │                              - User Banner: "Operating in Essential Support Mode" (UK2)  │   │
│   │                              - Tools & Specialists Bypassed; Zero External API Spend     │   │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                   │
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 4. CI/CD RELEASE GATE ECONOMIC VERIFIER (CR-D12, EV-D5, CR-Q3, CR-Q4)                            │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Pre-Deployment Regression Test across Golden Suites:                                             │
│ 1. Delta Check:  $\text{Cost}_{\text{cand}} \le 1.10 \cdot \text{Cost}_{\text{prev}}$ (≤ +10% Rise)│
│ 2. Ceiling Check: $\text{Cost}_{\text{cand}} \le 1.50 \cdot \text{Cost}_{\text{baseline}}$ (Absolute Cap)  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Pillar 1: Deterministic Cost Ledger vs. Telemetry Sampling (`CR-D11`, `RP-D14`)

Operational telemetry and financial accounting serve fundamentally different architectural objectives:
1. **The Sampling Trap**:
   - `OB-D4` utilizes tail-sampling to reduce OpenTelemetry span storage, retaining $100\%$ of errors and slow traces but dropping $80\%$ of routine requests. Deriving tenant financial billing from sampled traces ($OB-D13$) creates biased, inaccurate estimates ($UU1$).
2. **The Exact Usage Ledger (`CR-D11`)**:
   - The orchestrator directly extracts exact token counts from raw provider response headers on every invocation.
   - Usage is atomically accumulated into a dedicated, durable Redis/Postgres usage ledger partitioned by Tenant ID, Month, and Model Identifier.
3. **Monthly Invoice Reconciliation ($KK3$)**:
   - On the 1st of each calendar month, an automated reconciliation job ingests raw billing CSV exports from Anthropic, OpenAI, AWS Bedrock, and cloud GPU providers. Any divergence exceeding $2.0\%$ triggers an immediate FinOps audit alert.

---

### Pillar 2: Tiered Monthly Budgets & Graceful Soft-Cap (`CR-D4`, $UK2$)

Rather than cutting off customer communications when a tenant exhausts their contractual allowance, the system shifts into a managed **Soft-Cap State**:

#### The Three Governance Bands
1. **Nominal State ($S < 0.80 \cdot B_{\text{tenant}}$)**: Full multi-agent deliberation, external tool calling, and frontier model routing are completely enabled.
2. **Warning State ($0.80 \le S < 1.0 \cdot B_{\text{tenant}}$)**: Full service continues unimpeded. The system dispatches an automated notification to tenant administrators and displays a billing notice in the admin console (`CR-D7`).
3. **Soft-Cap Degradation State ($S \ge 1.0 \cdot B_{\text{tenant}}$)**:
   - The orchestrator shifts to **Knowledge-Base-Only Mode** (`RP-D2`).
   - All external tool executions (`TA-D1`) and specialist subgraphs (`MA-D1`) are bypassed.
   - Answers are generated purely from local retrieved documentation or served via cached snippets (`CR-D3`), reducing ongoing marginal token costs to near-zero.
   - **User Transparency Invariant ($UK2$)**: The client UI displays an informative notice: *"Your organization has reached its monthly advanced automation limit. You are currently receiving basic knowledge support."* This eliminates user confusion and preserves customer satisfaction.

---

### Pillar 3: Release Gate Economic Invariants (`CR-D12`, `EV-D5`)

To prevent code refactoring, prompt additions, or dependency updates from silently bloating production operational spend, the automated CI/CD pipeline enforces hard financial regression gates:

#### The Two-Factor Economic Gate (`CR-Q3`, `CR-Q4`)
For candidate release $V_{k}$ evaluated on the golden evaluation dataset $\mathcal{D}_{\text{eval}}$:

1. **Relative Delta Invariant (`CR-Q3(i)`)**:
   $$\text{CostPerResolvedConversation}(V_k, r) \le 1.10 \times \text{CostPerResolvedConversation}(V_{k-1}, r) \quad \forall r \in \text{Routes}$$
   Cost per resolved turn may increase by **at most 10%** across releases.
2. **Absolute Ceiling Invariant (`CR-Q4(i)`)**:
   $$\text{CostPerResolvedConversation}(V_k, r) \le 1.50 \times \text{CostPerResolvedConversation}(V_{\text{baseline}}, r) \quad \forall r \in \text{Routes}$$
   Cost may never exceed **$1.5\times$ the baseline first-month production cost** for that route.

Any candidate release violating either constraint fails automated CI verification and cannot be deployed to staging or production canary environments (`DL-ADP-02`).

---

## 3. Technical Implementation & Genesis Contracts

```python
"""
core/cost/budget_governor.py
Pydantic v2 schemas and runtime manager for Tenant Budgets, Usage Accounting, and Release Gates.
"""

from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator


class BudgetStatus(str, Enum):
    NORMAL = "normal"          # Spend < 80%
    WARNING = "warning"        # 80% <= Spend < 100%
    SOFT_CAPPED = "soft_capped" # Spend >= 100% -> Degrade to KB-Only (RP-D2)


class TenantBudgetConfig(BaseModel):
    tenant_id: str
    monthly_budget_usd: float = Field(..., gt=0.0)
    warning_threshold_pct: float = Field(default=0.80, ge=0.5, le=0.95)
    current_month_spend_usd: float = Field(default=0.0, ge=0.0)


class ReleaseGateCostVerification(BaseModel):
    route_name: str
    previous_release_cost_usd: float
    candidate_release_cost_usd: float
    baseline_first_month_cost_usd: float

    def verify_economic_invariants(self) -> Dict[str, Any]:
        """
        Enforces CR-D12 release gate economic rules (CR-Q3, CR-Q4).
        """
        delta_ratio = self.candidate_release_cost_usd / max(self.previous_release_cost_usd, 0.001)
        ceiling_ratio = self.candidate_release_cost_usd / max(self.baseline_first_month_cost_usd, 0.001)

        delta_passed = delta_ratio <= 1.10   # Max 10% rise per release (CR-Q3(i))
        ceiling_passed = ceiling_ratio <= 1.50 # Absolute cap 1.5x baseline (CR-Q4(i))

        return {
            "passed": delta_passed and ceiling_passed,
            "delta_ratio": delta_ratio,
            "delta_passed": delta_passed,
            "ceiling_ratio": ceiling_ratio,
            "ceiling_passed": ceiling_passed,
            "failure_reason": None if (delta_passed and ceiling_passed) else "economic_invariant_violation"
        }


class BudgetGovernor:
    """
    Evaluates tenant budget consumption and enforces soft-cap degradation (CR-D4).
    """

    def __init__(self, tenant_configs: Dict[str, TenantBudgetConfig]):
        self.tenant_configs = tenant_configs

    def check_tenant_budget(self, tenant_id: str) -> BudgetStatus:
        """
        Evaluates real-time financial spend against monthly budget.
        """
        cfg = self.tenant_configs.get(tenant_id)
        if not cfg:
            return BudgetStatus.NORMAL

        ratio = cfg.current_month_spend_usd / cfg.monthly_budget_usd

        if ratio >= 1.0:
            return BudgetStatus.SOFT_CAPPED  # Triggers KB-only mode (RP-D2)
        elif ratio >= cfg.warning_threshold_pct:
            return BudgetStatus.WARNING     # Emits admin alert (CR-D4)
        return BudgetStatus.NORMAL

    def record_turn_cost(
        self,
        tenant_id: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int,
        price_in_per_m: float,
        price_out_per_m: float,
        price_cached_per_m: float
    ) -> float:
        """
        Exact deterministic cost recording based on provider pricing (CR-D11).
        """
        turn_cost = (
            (input_tokens / 1_000_000.0) * price_in_per_m +
            (output_tokens / 1_000_000.0) * price_out_per_m +
            (cached_tokens / 1_000_000.0) * price_cached_per_m
        )
        
        cfg = self.tenant_configs.get(tenant_id)
        if cfg:
            cfg.current_month_spend_usd += turn_cost

        return turn_cost
```

---

## 4. Failure Modes & Mitigation Matrix

| Failure ID | Sub-Component | Failure Mode Description | Root Cause | Effect on System | Architectural Mitigation (`CR-D4`, `CR-D7`, `CR-D11`, `CR-D12`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **$KK3$** | Cost Tracking | Price table drift vs. actual cloud invoices | Provider quietly changes model pricing or currency rates | Reported spend mismatches actual accounting | `CR-D11` executes monthly automated invoice reconciliation against provider billing exports |
| **$UK2$** | Usage Budgets | Customer perceives soft-cap as broken software | Agent silently switches to KB-only answers with no explanation | User frustration and duplicate high-priority support tickets | `CR-D4` mandates prominent UI banner informing user and admin of degraded basic support mode |
| **$UU1$** | Cost Tracking | Divergence between trace estimates and actual bills | OpenTelemetry tail-sampling drops $80\%$ of routine traces | Under-counting tenant token consumption by $>30\%$ | `CR-D11` enforces exact usage ledger derived from provider response headers (`RP-D14`) |
| **$KU1$** | Usage Budgets | Burst usage exhausts monthly budget in 2 days | Unchecked loop or automated customer script | Tenant locked in KB-only mode for remaining 28 days | `RP-D1` admission control caps tokens per minute; 80% warning alert proactively engages admin |
| **$UK3$** | Usage Budgets | Release gate blocks urgent hotfix due to cost | Security patch adds extra safety guardrail prompt tokens | Delayed deployment of critical security patch | `EV-D5` allows emergency override with VP of Engineering sign-off and documented FinOps waiver |

---

## 5. Closed-Loop Telemetry & Verification Directives

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   FINOPS TELEMETRY & GOVERNANCE DASHBOARD DIRECTIVES                             │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Exact Token Event ──► [ Atomic Redis Counter ] ──► Prometheus: `finops.tenant.spend_usd`
                                 │
                                 ├──► [ Budget Status Check ] ──► Metric: `finops.budget.state`
                                 │
                                 └──► [ CI/CD Pipeline ] ──► Gate Metric: `eval.cost_per_resolved_turn`
```

### 1. Prometheus Telemetry Indicators
- `finops.tenant.monthly_spend_usd`: Gauge tracking cumulative month-to-date financial burn.
- `finops.tenant.budget_utilization_ratio`: $\frac{S_{\text{month}}}{B_{\text{tenant}}}$ (Alert at $0.80$; Soft Cap at $1.0$).
- `finops.tenant.soft_capped_total`: Number of tenants currently operating in degraded KB-only mode.
- `finops.reconciliation.drift_ratio`: Percentage difference between ledger calculations and monthly invoices (Target: $\le 2\%$).

### 2. OpenTelemetry Attributes
- `finops.cost.turn_usd`: Exact floating-point dollar cost calculated for the turn.
- `finops.budget.status`: `"normal"` | `"warning"` | `"soft_capped"`
- `finops.tenant.id`: Authenticated tenant identifier.

---

## 6. Alternatives Considered & Trade-Off Analysis

| Architectural Alternative | Technical Mechanism | Why Rejected / Trade-Off Analysis |
| :--- | :--- | :--- |
| **Hard Budget Blackout (Option A)** | Return `HTTP 403` and terminate agent when budget reaches 100% | **Rejected ($UK2$)**: Catastrophic user experience; strands end-users during critical outages; damages SaaS provider reputation. |
| **Trace-Sampled Financial Billing (Option B)** | Compute tenant billing by scaling up sampled OpenTelemetry traces (`OB-D13`) | **Rejected ($UU1$)**: Tail-sampling selectively biases toward slow/failed traces, leading to significant billing inaccuracies and legal audit disputes. |
| **Automated Chargebacks (Option C)** | Automatically charge tenant credit card for overages | **Rejected per CR-D7**: Enterprise procurement teams require predictable fixed monthly invoices; showback reports provide transparency without billing friction. |
| **Unconstrained CI/CD Deployments (Option D)** | Deploy releases without economic release gates | **Rejected**: Allows developers to introduce verbose prompts or expensive reasoning loops that quadruple operational burn without oversight. |

---

## 7. References & Academic Foundations

1. **FinOps Foundation.** (2023). *FinOps Framework: Inform, Optimize, Operate.* Technical Specification.
2. **Beyer, B. et al.** (2016). *Site Reliability Engineering: How Google Runs Production Systems.* O'Reilly Media. Chapter 25: Data Processing Pipelines.
3. **Chen, L., Zaharia, M., & Zou, J.** (2023). *FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance.* arXiv preprint arXiv:2305.05176.
4. **NIST Special Publication 800-53, Rev. 5.** (2020). *Security and Privacy Controls for Information Systems and Organizations.* Control AU-16: Cross-Organizational Auditing.
