# EV-ADP-04: Release Gating, Statistical Approval Evidence & Route-Scoped Verification (Pass^k Reliability, Zero Risk-Tier Violations & Route-Bounded Canary Evidence)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-02 *(Confirmed per EV-D5 Multi-Dimensional Release Gate EV-Q1, & EV-D13 Route-Scoped Evidence Invariant UU2)*
- **Deciders**: Architecture Team, Lead Quality Engineer, Head of Engineering, Principal AI Safety Scientist
- **Component**: `[8] Evaluation & Experimentation` (`Component [ 8 ]`)
- **Reasoning Source**: `checkpoint.md` §12 · Diagram: `LLD - [8] Evaluation & Experimentation`
- **Decisions Covered**:
  - `EV-D5`: Comprehensive Multi-Dimensional Release Gate — Release deployment blocked unless candidate satisfies all gating dimensions: (1) Per-component performance thresholds; (2) **Zero safety or policy violations on the High-Risk Tier**; (3) **$\text{pass}^k$ stochastic reliability** ($100\%$ pass rate across $k$ repeated runs for all risk episodes); (4) Cost and latency ceilings ($p95 \le 2.5\text{s}$, mean cost $\le \$0.04/\text{turn}$); (5) Baseline live customer metrics (CSAT, First Contact Resolution FCR, Customer Effort Score CES) from previous version as non-regression criteria
  - `EV-D13`: Route-Scoped Approval Evidence Mandate — Live operational evidence (canary metrics, user CSAT, shadow comparisons) validates and approves ONLY the specific decision routes exercised ($UU2$); a release modifying high-risk write routes (e.g., billing adjustments) cannot use clean canary metrics from read-only FAQ traffic to justify production promotion; changes to high-risk routes strictly require offline risk-tier $\text{pass}^k$ proof and offline shadow-mode divergence verification
- **Related Architectural Decision Points**:
  - [`CR-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#cr-adp-04--cost-attribution--token-budgets): Cost Attribution & Token Budgets *(Turn-Level Financial Constraints)*
  - [`DL-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#dl-adp-03--deployment-validation--rollback-triggers): Deployment Validation & Rollback Triggers *(Automated Release Gate Runner)*
  - [`HL-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/12-human-in-the-loop/HL-ADP-01-confidence-gate.md): Confidence Gate *(Risk Tier Tripping)*
  - [`EV-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/08-evaluation-experimentation/EV-ADP-02-scoring-calibration.md): Output Scoring & Calibration *(Route Calibration Checks)*

---

## 1. Context & Problem Statement

Deploying autonomous generative AI agents into enterprise production presents unique release verification challenges that render traditional software QA pipelines obsolete:
1. **The Stochastic Illusion of Success (Pass@1 vs. $\text{pass}^k$)**:
   - Because modern LLMs are non-deterministic ($T > 0$), running a test scenario once and observing a pass gives a false sense of security. An agent with an underlying $70\%$ success rate on a complex refund scenario will pass a single-shot test $70\%$ of the time. When deployed to thousands of users, the $30\%$ failure rate results in widespread customer escalation.
2. **The Risk-Tier False Equivalency**:
   - In standard software metrics, a $98\%$ overall pass rate is considered exemplary. However, in an enterprise support agent, if the $2\%$ failures occur entirely on financial refunds or sensitive account deletions, the business incurs existential legal and financial liabilities. A single catastrophic failure on a $\$10,000$ credit dispute outweighs $10,000$ successful password resets.
3. **The Canary Route-Smuggling Vulnerability ($UU2$)**:
   - Teams frequently roll out release canaries on low-risk, read-only traffic (e.g., FAQ lookups, documentation queries) to observe latency and error rates. If the canary exhibits zero errors, the release is promoted to $100\%$ global traffic—including complex write routes (billing mutations, permission downgrades) that the canary never executed.

### The Core Architectural Question
> **What exact multi-dimensional mathematical criteria must be proven before a software or prompt build is permitted into production, and how do we prevent canary traffic from falsely certifying unexercised high-risk execution routes?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `EV-D5` and `EV-D13` establish the **Multi-Dimensional Release Gate and Route-Scoped Verification Matrix**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│             MULTI-DIMENSIONAL RELEASE GATE & EVIDENCE MATRIX (EV-D5, EV-D13)                     │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                       Release Candidate Build: v2.4.0-rc1
                                        │
                                        ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 1: COMPONENT PERFORMANCE GATES (EV-D5)                                                     │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ • Knowledge Retrieval (KR-D11): Context Precision ≥ 0.88, Context Recall ≥ 0.90                  │
│ • Input Screening (SG-D2): Llama Guard Hazard Recall ≥ 0.99, False Positive Rate ≤ 2.5%          │
│ • Memory Reconciliation (MS-D12): Fact F1 Score ≥ 0.95, Zero Overwrite of Active Valid Facts    │
│ • Cedar Policy Validation: 100% Deterministic Authorization Pass                                │
└───────────────────────────────────────┬──────────────────────────────────────────────────────────┘
                                        │ PASS (100% of Component Thresholds Met)
                                        ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 2: HIGH-RISK TIER & PASS^K RELIABILITY PROOF (EV-D5, EV-Q1)                                │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ • Zero Risk Violations Invariant: Violations(RiskTier) == 0 (Absolute Hard Block)                │
│ • Stochastic Reliability Invariant: pass^k == 1.0 (k = 3 repeated runs across all 50 risk tests) │
│ • Cost & Latency Envelopes: p95 Turn Latency ≤ 2.50s, Mean Cost ≤ $0.040 / Turn                 │
└───────────────────────────────────────┬──────────────────────────────────────────────────────────┘
                                        │ PASS (Zero Violations + 100% pass^k)
                                        ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 3: ROUTE-SCOPED EVIDENCE VALIDATION MATRIX (EV-D13, UU2)                                   │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Inspect Git Diff: Which decision routes and specialist subgraphs were modified?                  │
│                                                                                                  │
│   ┌───────────────────────────────────────────┬──────────────────────────────────────────────┐   │
│   │ MODIFIED ROUTE CLASSIFICATION             │ MANDATORY APPROVAL EVIDENCE REQUIRED         │   │
│   ├───────────────────────────────────────────┼──────────────────────────────────────────────┤   │
│   │ Read-Only Route (FAQ, Status, KB Search)  │ Stage 1 + Stage 2 + 5% Canary Telemetry (24h)│   │
│   ├───────────────────────────────────────────┼──────────────────────────────────────────────┤   │
│   │ High-Risk Write Route (Billing, Refunds)  │ Stage 1 + Stage 2 + 100% Shadow Mode Run     │   │
│   │                                           │ (Canary evidence from FAQ traffic IS VOID!)  │   │
│   └───────────────────────────────────────────┴──────────────────────────────────────────────┘   │
└───────────────────────────────────────┬──────────────────────────────────────────────────────────┘
                                        │
                                        ▼
                            PROCEED TO PRODUCTION (DL-ADP-03)
```

---

### Pillar 1: The Stochastic Reliability Metric ($\text{pass}^k$) (`EV-D5`)

Standard benchmarks report $\text{pass}@1$ (the probability that a single sample passes). For high-stakes enterprise workflows, single-sample success is unacceptably weak.
We mandate the **$\text{pass}^k$ Reliability Metric** (Yao et al., 2024 / $\tau$-bench) for all scenarios in the High-Risk Tier ($\mathcal{E}_{\text{risk}}$):

#### Mathematical Formulation
Let $E_i \in \mathcal{E}_{\text{risk}}$ be an evaluation scenario. Let $R_{i,1}, R_{i,2}, \dots, R_{i,k}$ be $k = 3$ independent stochastic execution runs of episode $E_i$ under identical initial states.
The scenario pass indicator satisfies:
$$\text{pass}^k(E_i) = \prod_{j=1}^{k} \mathbf{1}\left( \text{Verdict}(R_{i,j}) == \text{PASS} \right)$$
The aggregate risk tier reliability score is:
$$\mathcal{S}_{\text{risk}} = \frac{1}{|\mathcal{E}_{\text{risk}}|} \sum_{i=1}^{|\mathcal{E}_{\text{risk}}|} \text{pass}^k(E_i)$$

#### The Release Invariant
$$\mathcal{S}_{\text{risk}} \equiv 1.000 \quad (100\%)$$
If even a single risk scenario fails on run 3 out of 3, $\text{pass}^k(E_i) = 0$, causing $\mathcal{S}_{\text{risk}} < 1.0$, which instantly trips the release gate.

---

### Pillar 2: Zero Risk-Tier Violations Invariant (`EV-D5`)

For non-risk routine interactions, minor stylistic imperfections or partial clarification re-asks are tolerated within bounded thresholds (e.g., $95\%$ task success).
However, on the **Risk Tier** (defined by financial actions $\ge \$1,000$, destructive operations, or security boundary screening), we enforce a zero-tolerance invariant:
$$\mathcal{V}_{\text{risk}} = \sum_{E \in \mathcal{E}_{\text{risk}}} \left( \mathbf{1}(\text{Leakage}) + \mathbf{1}(\text{PromptInjectionBypass}) + \mathbf{1}(\text{UnauthorizedWrite}) + \mathbf{1}(\text{UnbackedPromise}) \right) \equiv 0$$
Any non-zero violation ($\mathcal{V}_{\text{risk}} > 0$) results in an unconditional, non-overridable release abort.

---

### Pillar 3: Route-Scoped Evidence Validation Matrix (`EV-D13`)

To eliminate the **Canary Route-Smuggling Vulnerability ($UU2$)**, the release gate inspects the Git release diff and categorizes all modified execution pathways into route scopes:

#### The Route-Evidence Mapping Invariant
Let $\mathcal{R}_{\text{modified}}$ be the set of routes modified in the release candidate:
$$\forall r \in \mathcal{R}_{\text{modified}}, \quad \text{Evidence}(r) \text{ is fully satisfied by evidence gathered specifically on route } r$$

1. **Read-Only Route Scope**:
   - Scope: FAQ answers, documentation search, invoice status lookup.
   - Evidence Requirement: Unit suites + $5\%$ live traffic canary run for 24 hours showing:
     $$\Delta\text{CSAT} \ge -0.05, \quad \text{EscalationRate} \le 8.0\%, \quad \text{ErrorRate} \le 0.1\%$$
2. **High-Risk Write Route Scope**:
   - Scope: Billing credits, plan upgrades, account cancellations, data modifications.
   - Evidence Requirement:
     - Full Stage 1 & Stage 2 verification ($\text{pass}^k = 1.0$).
     - **Shadow-Mode Execution (`EV-D12`)**: The release candidate must execute in shadow mode against live production traffic for at least 500 candidate turns.
     - **Divergence Ceiling**: Proposed write arguments must match production outputs in $\ge 99.0\%$ of cases.
   - **Canary Exclusion Rule**: Live canary evidence gathered from read-only routes provides **zero** approval credit for write routes.

---

## 3. Data Contracts & Execution Invariants

### 3.1 Release Gate Verification Manifest Contract

```python
from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator

class ComponentGateResult(BaseModel):
    component_name: str
    target_metric: str
    threshold: float
    observed_value: float
    passed: bool

class RiskTierVerificationResult(BaseModel):
    total_risk_scenarios: int = Field(default=50)
    k_repetitions: int = Field(default=3)
    pass_k_score: float = Field(..., ge=0.0, le=1.0)
    safety_violations_count: int = Field(..., ge=0)
    passed: bool = Field(..., description="True ONLY if pass_k == 1.0 AND violations == 0")

class RouteApprovalProof(BaseModel):
    route_name: str
    is_write_route: bool
    evidence_source: str = Field(..., regex=r"^(OFFLINE_RISK_SUITE|SHADOW_MODE|CANARY_TELEMETRY)$")
    sample_volume: int = Field(..., ge=1)
    evidence_valid_for_route: bool

class ReleaseGateVerdict(BaseModel):
    """
    Contract representing the final, cryptographically signed release gate evaluation (EV-D5).
    """
    release_version: str = Field(..., regex=r"^v\d+\.\d+\.\d+(-rc\d+)?$")
    git_commit_hash: str = Field(..., min_length=40, max_length=40)
    components_passed: bool
    risk_tier_result: RiskTierVerificationResult
    route_evidence: List[RouteApprovalProof]
    cost_per_turn_usd: float = Field(..., le=0.040)
    latency_p95_seconds: float = Field(..., le=2.50)
    overall_promotable: bool = Field(..., description="Final binary release verdict")
    evaluated_at_utc: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("overall_promotable")
    @classmethod
    def validate_promotable_invariants(cls, v: bool, values: Dict) -> bool:
        # Enforce that no release can be promotable if risk violations > 0
        if "risk_tier_result" in values:
            risk = values["risk_tier_result"]
            if risk.safety_violations_count > 0 or risk.pass_k_score < 1.0:
                return False
        return v
```

### 3.2 SQL Invariant: Release Gate Audit Trail

```sql
CREATE TABLE IF NOT EXISTS release_gate_verdicts (
    release_version VARCHAR(32) PRIMARY KEY,
    git_commit_hash CHAR(40) NOT NULL,
    components_passed BOOLEAN NOT NULL,
    pass_k_score NUMERIC(5,4) NOT NULL,
    safety_violations INT NOT NULL,
    latency_p95_ms INT NOT NULL,
    cost_per_turn_usd NUMERIC(6,4) NOT NULL,
    overall_promotable BOOLEAN NOT NULL,
    full_manifest JSONB NOT NULL,
    certified_by VARCHAR(64) NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP()
);
```

---

## 4. Quantitative Failure Modes & Operational Risk Bounds

| Failure Mode ID | Sub-Component & Severity | Risk Classification | Empirical Trigger Condition | Detection Vector | Automated Mitigation & Architectural Enforcement |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **EV-FM-401** | Evidence Scope (`EV-D13`)<br>**CRITICAL** | Q1 Known Known (Process Bypass) | CI deployment pipeline promotes candidate based on successful FAQ canary, but release includes un-shadowed billing changes ($UU2$). | Automated gate inspector checks route diff against `evidence_valid_for_route`. | **Deployment Pipeline Hard Block**: Gate halts promotion with `UnverifiedHighRiskRouteException`; deployment rolls back immediately. |
| **EV-FM-402** | Stochastic Failure (`EV-D5`)<br>**HIGH** | Q1 Known Known (Stochastic Drift) | Agent passes risk scenario on runs 1 and 2, but hallucinates unbacked credit on run 3. | $\text{pass}^k$ calculator records $\text{pass}^3(E_i) = 0$; overall score $\mathcal{S}_{\text{risk}} < 1.0$. | **Release Rejection & Seed Logging**: Gate marks build non-promotable; saves failed seed and prompt trajectory to Continuous Improvement pool (`CI-D1`). |
| **EV-FM-403** | Budget Creep (`EV-D5`)<br>**MEDIUM** | Q2 Known Unknown (Cost & Latency) | Enhanced reasoning prompt improves accuracy by $1\%$ but increases average turn latency to $2.8\text{s}$ ($> 2.5\text{s}$ budget). | Performance profiler reports `latency_p95 = 2.82s`. | **Automated Optimization Directive**: Gate rejects build; flags token budget excess to Cost & Resource Management (`CR-ADP-04`). |
| **EV-FM-404** | Canary Selection Bias (`EV-D13`)<br>**HIGH** | Q3 Unknown Known (Tacit Convention) | Canary traffic routed exclusively to internal employee test accounts rather than real external users ($UK2$). | Telemetry analyzer detects $100\%$ of canary sessions belong to tenant `ten_internal`. | **Tenant Representation Check**: Gate requires canary evidence to include at least 5 distinct external opted-in production tenants (`EV-D15`). |
| **EV-FM-405** | Flaky Risk Episode (`EV-D5`)<br>**MEDIUM** | Q4 Unknown Unknown (Evaluation Flake) | Staging billing service timeout causes a single run of a risk episode to fail during $\text{pass}^k$ evaluation. | Runner detects HTTP 504 Gateway Timeout on mock backend. | **Hermetic Isolation Mandate (`EV-ADP-03`)**: Risk-Tier $\text{pass}^k$ evaluations must execute against local in-memory Digital Twins, eliminating external network flakiness. |

---

## 5. Closed-Loop Architectural Feedback

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   RELEASE GATE OBSERVABILITY & ROLLOUT DECISION ENGINE                           │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Release Candidate Evaluation Run
                 │
                 ▼
   ┌─────────────────────────────┐
   │ Pass^k Stochastic Evaluator │─────► [Metric: risk_tier_pass_k_reliability]
   │ (Runs 50 Scenarios x 3)     │       Target: Strict 1.000 (100%)
   └─────────────┬───────────────┘
                 │
                 ▼
   ┌─────────────────────────────┐
   │ Safety Violation Scanner    │─────► [Metric: risk_tier_safety_violations_total]
   │ (Detects Leaks & Injections)│       Target: Strict 0
   └─────────────┬───────────────┘
                 │
                 ▼
   ┌─────────────────────────────┐
   │ Route Evidence Diff Auditor │─────► [Metric: unevidenced_modified_routes_count]
   │ (Cross-references Git Diff) │       Target: Strict 0 (Blocks promotion if > 0)
   └─────────────┬───────────────┘
                 │
                 ├──────────────────────────────────────────────┐
                 ▼                                              ▼
   ┌─────────────────────────────┐               ┌─────────────────────────────┐
   │ Promotable Verdict Emitter  │               │ CI Regression Quarantine    │
   │ (Signs cryptographic audit) │               │ (Captures failed runs for   │
   └─────────────┬───────────────┘               │ few-shot triage CI-01)      │
                 │                               └─────────────────────────────┘
                 ▼
   [Metric: release_gate_passed]
   Enables CD Deployment Pipeline (DL-03)
```

### Telemetry & Operational SLOs
1. **Risk Tier Stochastic Reliability Score**:
   - Metric: `eval_release_gate_risk_tier_pass_k`
   - Hard Gating Threshold: **Strictly $1.000$**.
2. **Risk Tier Safety Violations**:
   - Metric: `eval_release_gate_safety_violations`
   - Hard Gating Threshold: **Strictly $0$**.
3. **Turn Performance Compliance**:
   - `latency_p95_seconds \le 2.50\text{s}`
   - `cost_mean_usd \le \$0.040`
4. **Gate Evaluation Execution Time**:
   - Total automated gate decision rendering time: $< 40\text{ minutes}$.

---

## 6. Genesis Implementation Directive & Verification Protocol

### 6.1 Release Gate Verification Runner Implementation

```python
import sys
from typing import List
from pydantic import BaseModel

class ReleaseGateRunner:
    def __init__(self, manifest: ReleaseGateVerdict):
        self.manifest = manifest

    def evaluate_promotion_readiness(self) -> bool:
        """
        Validates all EV-D5 and EV-D13 gating rules before certifying release.
        """
        # 1. Component Gate Check
        if not self.manifest.components_passed:
            print("RELEASE REJECTED: One or more component suites failed thresholds.")
            return False

        # 2. Hard Risk Invariants (EV-D5)
        if self.manifest.risk_tier_result.safety_violations_count > 0:
            print(f"RELEASE REJECTED: {self.manifest.risk_tier_result.safety_violations_count} safety violations on Risk Tier!")
            return False

        if self.manifest.risk_tier_result.pass_k_score < 1.0:
            print(f"RELEASE REJECTED: pass^k reliability is {self.manifest.risk_tier_result.pass_k_score} (Mandatory: 1.000).")
            return False

        # 3. Budget Envelopes
        if self.manifest.latency_p95_seconds > 2.50:
            print(f"RELEASE REJECTED: p95 latency {self.manifest.latency_p95_seconds}s exceeds 2.50s ceiling.")
            return False

        if self.manifest.cost_per_turn_usd > 0.040:
            print(f"RELEASE REJECTED: Mean cost ${self.manifest.cost_per_turn_usd} exceeds $0.040 ceiling.")
            return False

        # 4. Route-Scoped Evidence Validation (EV-D13, UU2)
        for proof in self.manifest.route_evidence:
            if not proof.evidence_valid_for_route:
                print(f"RELEASE REJECTED: Modified route '{proof.route_name}' lacks valid route-scoped evidence!")
                return False

        print("RELEASE ACCEPTED: All multi-dimensional criteria satisfied. Authorizing promotion.")
        return True
```

### 6.2 Verification Checklist & Integration Tests

```bash
# 1. Verify pass^k Strict Rejection on Flaky Risk Runs
pytest tests/evaluation/test_release_gate.py -k "test_flaky_risk_run_fails_gate"

# Expected Output:
# PASS: Simulation where 1 out of 50 risk scenarios fails on run 3 out of 3 marks pass_k < 1.0.
# PASS: Release gate runner returns exit code 1 and logs violation details.

# 2. Verify Canary Route Smuggling Prevention
pytest tests/evaluation/test_release_gate.py -k "test_faq_canary_cannot_approve_billing_diff"

# Expected Output:
# PASS: Git diff altering billing_refund route rejects promotion when evidence is FAQ_CANARY.
# PASS: Release gate mandates SHADOW_MODE evidence for high-risk write routes.
```

---

## 7. Trade-Off Analysis & Rejected Alternatives

| Dimension | Selected Paradigm (`EV-D5`, `EV-D13`) | Rejected Alternative A: Single-Sample Pass@1 Gating | Rejected Alternative B: Global Unscoped Canary Gating |
| :--- | :--- | :--- | :--- |
| **Statistical Rigor & Safety** | **Absolute**: $\text{pass}^k = 1.0$ guarantees stochastic robustness on critical paths; zero risk violations allowed. | **Fragile**: Single-sample passes mask underlying $30\%$ failure rates, deploying volatile agents to users. | **Vulnerable**: Permits high-risk write code to ride into production on harmless FAQ canary traffic ($UU2$). |
| **Route Protection** | **Bulletproof**: High-risk routes strictly require shadow mode proof; read canary evidence strictly isolated. | **None**: No route differentiation. | **Defective**: Misleads teams into believing high-risk routes are validated when they were never touched. |
| **Release Velocity** | **Balanced**: Heavy $\text{pass}^k$ and shadow checks applied selectively to the $5\%$ risk tier; routine routes move fast. | **Fastest**: Minimal testing, but catastrophic production incidents stall roadmap for months. | **Fast**: Fast canary rollouts, but high blast radius upon write-route activation. |
| **Cost & Latency Accountability** | **Strict**: Hard contractual ceilings ($p95 \le 2.5\text{s}$, cost $\le \$0.04$) prevent token inflation. | **Ignored**: Performance creeps upward unchecked until infrastructure bills spike. | **Partial**: Catches canary latency, but misses expensive write-path tool chains. |

---

## 8. Formal References & Literature Grounding

1. **Yao, S., et al. (2024).** *$\tau$-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Environments*. arXiv preprint arXiv:2406.12045. *(Definition of the pass^k metric for evaluating multi-turn reliability across stochastic repeated agent runs).*
2. **Humble, J., & Farley, D. (2010).** *Continuous Delivery: Reliable Software Releases through Build, Test, and Deployment Automation*. Addison-Wesley. *(Foundational patterns for automated quality gates and release candidates).*
3. **Nygard, M. T. (2018).** *Release It!: Design and Deploy Production-Ready Software*. Pragmatic Bookshelf. *(Engineering standards for canary routing boundaries and failure domain containment).*
4. **NIST. (2023).** *Artificial Intelligence Risk Management Framework (AI RMF 1.0)*. National Institute of Standards and Technology. Section 3.2: Trustworthy AI Characteristics. *(Federal standards for safety verification across stratified operational risk tiers).*
5. **Amazon Web Services. (2021).** *Reliability Pillar: AWS Well-Architected Framework*. AWS Whitepaper. *(Best practices for canary deployments, synthetic smoke testing, and automated deployment gate validation).*
