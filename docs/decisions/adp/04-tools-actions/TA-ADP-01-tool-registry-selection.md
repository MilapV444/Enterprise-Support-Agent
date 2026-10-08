# TA-ADP-01: Tool Registry & Selection (Hierarchical Code-Tier Filtering, Jev-Governed Shortlisting & Peer-Reviewed Python Tooling)

- **Status**: Accepted & Confirmed
- **Date**: 2026-09-29 *(Amended: 2026-09-29 per TA-D1 Jev Shortlist, TA-D2 Native Python Engine, TA-D16 Second-Person Review & TA-Q3 HITL Fallback)*
- **Deciders**: Architecture Team, Lead Integrations Engineer, AI Safety & Tool Governance Core
- **Component**: `[4] Tools & Actions` (`Component [ 4 ]`)
- **Reasoning Source**: `checkpoint.md` §8 · Diagram: `LLD - [4] Tools & Actions`
- **Decisions Covered**:
  - `TA-D1`: Dynamic Two-Stage Tool Selection — Static code-based RBAC/tier pre-filtering $\to$ Jev `Choice` ranking shortlist ($k \le 5$) $\to$ Jev `Choice` final tool selection; low confidence ($\gamma < 0.50$) trips safely to Human Specialist (`TA-Q3`)
  - `TA-D2`: Tool Architecture & Runtime Hosting — Plain typed Python functions using Pydantic v2 schemas; hosted directly as Temporal activities across dedicated task queues (`TA-Q2`); third-party Model Context Protocol (MCP) excluded in v1 to eliminate supply-chain injection and protocol overhead
  - `TA-D16`: Governance & Peer-Reviewed Risk Classification — Author-declared risk classes (`READ_ONLY`, `LOW_RISK_WRITE`, `HIGH_RISK_WRITE`, `DESTRUCTIVE_IRREVERSIBLE`); mandatory second-engineer peer review; unreviewed external tools strictly default to `HUMAN_APPROVAL_REQUIRED` ($UK3$)
- **Related Architectural Decision Points**:
  - [`ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/00-orchestration-core/ADP-05-decision-model-jev.md): Decision Model (Jev) *(Structured Tool Categorical Routing)*
  - [`MA-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#ma-adp-04--task-contracts--delegation): Task Contracts & Delegation *(Specialist Tool Allow-Lists)*
  - [`HL-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#hl-adp-03--intervention-tripwires--routing): Intervention Tripwires & Routing *(Low-Confidence Tool Fallback to Human)*
  - [`TA-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/04-tools-actions/TA-ADP-03-action-validation-approval.md): Action Validation & Approval Tiers *(Risk Class Enforcement)*

---

## 1. Context & Problem Statement

Modern enterprise customer support environments require integration with dozens of distinct APIs: CRM systems (Salesforce, Zendesk), cloud infrastructure (AWS CloudWatch, Kubernetes), billing engines (Stripe, SAP ERP), and internal ticketing systems.

Exposing dozens of heterogeneous tool interfaces directly to a generative LLM creates critical operational and security failures:

1. **Function-Calling Degradation & Context Clutter (Gorilla / BFCL Benchmark)**: As the number of tools presented in the prompt exceeds $15–20$, generative LLM tool-calling accuracy degrades precipitously (Patil et al., 2023). The model experiences parameter hallucination, misidentifies target functions, and exhausts token budgets on unused JSON schemas.
2. **Excessive Agency & Confused Deputy Vulnerabilities (OWASP LLM06)**: Providing open access to powerful mutating tools allows adversarial prompt injections to steer the agent toward unintended mutations. An anonymous or unverified user (Tier `T0_ANON`) inquiring about server status must never be presented with administrative restart or billing modification tools.
3. **The Protocol & Rug-Pull Hazard of Third-Party MCP Servers ($TA-D2$)**: The emerging Model Context Protocol (MCP) allows dynamic tool registration over JSON-RPC. However, in enterprise environments, third-party MCP servers introduce catastrophic supply-chain attack vectors: tool poisoning (adversaries embedding prompt injections inside tool description strings; Invariant Labs, 2025) and post-deployment description "rug pulls" where a tool's capabilities change without code review.
4. **Author Risk Misclassification ($UK3$)**: A software engineer writing an email-dispatch or cache-eviction tool marks it as "low risk" to bypass friction. In reality, the tool executes external customer-facing communications or triggers expensive cloud provisioning.

### The Core Architectural Question
> **How do we catalog, govern, and selectively expose dozens of enterprise tools on a per-turn basis without degrading LLM selection accuracy, suffering supply-chain injection, or exposing unauthorized operational capabilities?**

---

## 2. Decision Framework & Theoretical Formulation

To solve these challenges, `TA-D1`, `TA-D2`, and `TA-D16` establish the **Two-Stage Filter-and-Select Pipeline with Governed Python Tooling**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             TWO-STAGE TOOL SELECTION PIPELINE (TA-D1)                            │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

Stage 1: Code-Level RBAC & Route Filter (Deterministic, Zero LLM)
Inputs: Global Registry (N ≈ 80 Tools) + Security Context (Tenant, Role, Identity Tier T0/T1/T2)
  │
  ▼
Permitted Candidate Pool (M ≤ 15 Tools)
  │
  ▼
Stage 2: Jev Choice Shortlisting (TypeSafe Intent Model, PII-Masked)
Question: "Which candidate tools are relevant to the user's intent?"
  │
  ├─── Confidence γ < 0.50 ──► Trip to Human Specialist (HITL, TA-Q3)
  ▼ (Confidence γ ≥ 0.50)
Shortlist (k ≤ 5 Tools)
  │
  ▼
Stage 3: Jev Tool & Closed-Argument Picker (ADP-05)
Selects exact tool t* and closed-set parameters
Free-text parameters populated by Generative LLM
```

---

### Pillar A: Multi-Stage Filtering & Mathematical Selection Bounds

Let $\mathcal{T}_{\text{universe}}$ be the catalog of all enterprise tools registered in the codebase ($|\mathcal{T}_{\text{universe}}| \approx 80$). Presenting $\mathcal{T}_{\text{universe}}$ directly to the model violates token efficiency and safety invariants.

#### Step 1: Deterministic Code-Level RBAC & State Route Filtering
The code-level filter evaluates deterministic security invariants before any model is invoked:
$$\mathcal{T}_{\text{permitted}} = \left\{ t \in \mathcal{T}_{\text{universe}} \mid \text{Tier}(t) \le \text{Tier}_{\text{user}} \land \text{Role}(t) \subseteq \text{Roles}_{\text{user}} \land t \in \text{Allowed}(\text{FSM}_{\text{node}}) \right\}$$
- If the user is unverified (`T0_ANON`), all mutating tools are stripped: $\text{Mutating}(\mathcal{T}_{\text{permitted}}) = \emptyset$.
- Tools not permitted in the current LangGraph statechart node (e.g., refund tools during `TRIAGED` state) are excluded.

#### Step 2: Jev Categorical Shortlisting (`TA-D1`)
If $|\mathcal{T}_{\text{permitted}}| > 5$, Jev evaluates a parallel categorical ranking over the candidate set using the TypeSafe `skill_suggestion` pattern:
$$\mathcal{T}_{\text{shortlist}} = \text{Jev.ChoiceRanking}\left(\text{State} = \tilde{u}_{\text{turn}}, \text{Candidates} = \mathcal{T}_{\text{permitted}}, \text{TopK} = 5\right)$$
Where $\tilde{u}_{\text{turn}}$ is the PII-masked customer turn (`ADP-05-Q3`).

#### Fallback Safety Gate (`TA-Q3`)
Let $\gamma_{\text{shortlist}}$ be the minimum confidence score across the top shortlisted candidates:
$$\text{Action} = \begin{cases}
\text{ProceedToToolSelection}(\mathcal{T}_{\text{shortlist}}) & \text{if } \gamma_{\text{shortlist}} \ge 0.50 \\
\text{TripToHumanSpecialist}(\text{ERR\_AMBIGUOUS\_TOOL\_SELECTION}) & \text{if } \gamma_{\text{shortlist}} < 0.50
\end{cases}$$
If the intent is too ambiguous for Jev to reliably determine the appropriate tool category, the system never guesses; it safely escalates to a human agent (`HL-ADP-03`).

---

### Pillar B: Native Python Functions vs. MCP Decoupling (`TA-D2`)

We explicitly reject the Model Context Protocol (MCP) for internal tool execution in v1:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                               TOOL ARCHITECTURE COMPARISON (TA-D2)                               │
├─────────────────────────────────────────────────┬────────────────────────────────────────────────┤
│   REJECTED: MODEL CONTEXT PROTOCOL (MCP v1)     │   SELECTED: NATIVE PYTHON TEMPORAL ACTIVITIES  │
├─────────────────────────────────────────────────┼────────────────────────────────────────────────┤
│   • JSON-RPC protocol overhead over HTTP/SSE    │   • Zero protocol hop; direct in-process/worker│
│   • Vulnerable to Tool Poisoning (hidden prompt │   • Typed Pydantic v2 schemas statically checked│
│     injection inside tool descriptions)         │   • Immutable code repository versioning       │
│   • Dynamic runtime description "rug pulls"     │   • Static analysis prevents description drift │
│   • Third-party supply chain execution risks    │   • Dedicated worker pool per system (TA-D11)  │
└─────────────────────────────────────────────────┴────────────────────────────────────────────────┘
```

All tools are implemented as pure Python functions decorated with `@enterprise_tool`. Input and output signatures are strictly defined using Pydantic v2 classes with runtime type validation.

---

### Pillar C: Four-Tier Risk Classification & Mandatory Peer Review (`TA-D16`)

Every registered tool is bound to a formal risk class:

$$\text{RiskLattice}: \quad \text{READ\_ONLY} \prec \text{LOW\_RISK\_WRITE} \prec \text{HIGH\_RISK\_WRITE} \prec \text{DESTRUCTIVE\_IRREVERSIBLE}$$

1. **`READ_ONLY`**: Zero external mutations (e.g., `get_invoice_breakdown`, `query_cloud_monitoring`). Runs automatically.
2. **`LOW_RISK_WRITE`**: Reversible, low-impact state changes (e.g., `add_ticket_comment`, `update_contact_preference`). Runs automatically.
3. **`HIGH_RISK_WRITE`**: Financial adjustments $\ge \$1,000$, tenant configuration changes, provisioning (e.g., `apply_credit_memo`). Mandates human approval card (`TA-ADP-03`).
4. **`DESTRUCTIVE_IRREVERSIBLE`**: Permanent modifications with no automated rollback (e.g., `delete_database_cluster`, `send_external_legal_notice`). Mandates senior human sign-off; must be placed as the final step in sagas (`TA-D18`).

#### Mandatory Governance Gate
Any newly authored tool requires:
1. Primary author declaration of schema, risk class, idempotency support, and dry-run capabilities.
2. Mandatory second-engineer peer review sign-off committed in git.
3. **Safety Fallback ($UK3$)**: Any unreviewed tool running in staging/production automatically forces `HUMAN_APPROVAL_REQUIRED` regardless of the author's declared tier.

---

## 3. Decision Rules, Structural Invariants & Code Contracts

### Decision Invariants
1. **Invariant 1 (Shortlist Size Ceiling)**: The generative model context assembler must never receive more than $5$ tool definitions in a single turn.
2. **Invariant 2 (Identity Tier Enforcement)**: Anonymous users (`T0_ANON`) can never be offered mutating tools; RBAC filtering enforces this at the code layer before Jev shortlisting runs.
3. **Invariant 3 (Static Code Immutability)**: Tool definitions, parameter schemas, and descriptions are compiled into the application image. Dynamic runtime registration of unreviewed tools is strictly prohibited.
4. **Invariant 4 (Type Strictness)**: All tool input parameters must resolve to primitive types, typed Enums, or validated Pydantic sub-models. Arbitrary `dict` or `Any` parameters are rejected by pre-commit linter checks.

---

### Python & Pydantic Data Contracts

```python
"""
Core contracts for the Tool Registry, Tool Schemas, and Selection Engine.
Module: core/tools/registry.py
"""

from typing import List, Dict, Optional, Callable, Any, Type
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class ToolRiskClass(str, Enum):
    READ_ONLY = "read_only"
    LOW_RISK_WRITE = "low_risk_write"
    HIGH_RISK_WRITE = "high_risk_write"
    DESTRUCTIVE_IRREVERSIBLE = "destructive_irreversible"


class TargetSystemType(str, Enum):
    CRM = "crm"
    BILLING_ERP = "billing_erp"
    CLOUD_INFRASTRUCTURE = "cloud_infra"
    TICKETING = "ticketing"


class ToolDefinition(BaseModel):
    """Immutable specification of an enterprise tool in the registry."""
    tool_id: str = Field(..., description="Unique tool identifier, e.g., 'billing.apply_credit_memo'")
    name: str
    description: str = Field(..., description="Concise functional description for Jev ranking")
    target_system: TargetSystemType
    risk_class: ToolRiskClass
    
    # Access control
    min_identity_tier: str = Field(default="T1_VERIFIED", regex="^(T0_ANON|T1_VERIFIED|T2_SSO)$")
    required_roles: List[str] = Field(default_factory=list)
    allowed_fsm_nodes: List[str] = Field(default_factory=list)
    
    # Behavioral flags
    supports_dry_run: bool = Field(default=False)
    supports_idempotency: bool = Field(default=True)
    is_reversible: bool = Field(default=True)
    compensation_tool_id: Optional[str] = None
    
    # Governance & Peer Review
    author_id: str
    reviewer_id: Optional[str] = None
    peer_review_approved: bool = Field(default=False)
    registered_at: datetime = Field(default_factory=datetime.utcnow)


class ToolShortlistResult(BaseModel):
    """Output contract for Jev tool shortlisting."""
    candidate_tool_ids: List[str] = Field(..., max_items=5)
    confidence: float = Field(..., ge=0.0, le=1.0)
    requires_human_fallback: bool = Field(
        default=False, 
        description="True if confidence < 0.50 (TA-Q3)"
    )


class ToolSelectionDecision(BaseModel):
    """Final tool invocation proposal emitted by orchestrator."""
    tool_id: str
    risk_class: ToolRiskClass
    arguments: Dict[str, Any]
    provenance_verified: bool = Field(
        default=False, 
        description="Verified against TA-D3/TA-D13 argument safety rules"
    )
```

---

## 4. Failure Modes Matrix & Resilience Invariants

| Quadrant | Failure Scenario | Detection Mechanism | Systemic Mitigation & Recovery |
| :--- | :--- | :--- | :--- |
| **Q1: Known Knowns** | **Parameter Signature Mismatch ($KK1$)**: LLM provides a string parameter where an integer amount is required, crashing tool execution. | Pydantic v2 `ValidationError` thrown before network dispatch. | Errors normalized and passed to agent as structured feedback (`TA-D10`); closed-set parameters chosen via Jev `Choice` (`ADP-05`). |
| **Q2: Known Unknowns** | **Shortlist Recall Drop ($KU1$)**: Jev shortlisting omits the correct tool for an unusual customer query, stranding the workflow. | Turn execution monitor flags unhandled user intents. | If Jev shortlist confidence $\gamma < 0.50$, the system trips immediately to a Human Specialist (`TA-Q3`) rather than executing an erroneous tool. |
| **Q3: Unknown Knowns** | **Author Underestimates Risk ($UK3$)**: Tool developer marks an account-suspension tool as `LOW_RISK_WRITE` to bypass testing friction. | CI lint check asserts that all mutating tools require peer-review sign-off. | Mandatory dual-engineer review gate (`TA-D16`); unreviewed tools automatically require human approval in production. |
| **Q4: Unknown Unknowns** | **Adversarial Shortlist Steering ($UU1$)**: Attacker embeds prompt injection into a user query designed to force Jev to select an administrative tool. | Jev input screening detects anomalous intent shifts. | Code-level RBAC pre-filter strips all unpermitted tools before Jev ranking runs; an unauthorized user cannot steer toward tools outside their tier. |

---

## 5. Closed-Loop Feedback & Verification Signals

1. **Production Telemetry**:
   - `Tool_Shortlist_Confidence_Distribution`: Monitored per route; alerts if p10 confidence falls below $0.55$.
   - `Tool_Execution_ValidationError_Rate`: Tracks syntax errors caught by Pydantic schemas (alerts if $> 2\%$).
   - `Unreviewed_Tool_Invocation_Counter`: Increments whenever an unreviewed tool executes under the safety fallback gate.
2. **Weekly Leaderboard Verification**:
   - Run the Berkeley Function-Calling Leaderboard (BFCL) suite across registered tools in CI, asserting that two-stage selection maintains $>96\%$ accuracy across the catalog.

---

## 6. Genesis Implementation Directives

1. **Code Locations**:
   - Implement registry and data models in `core/tools/registry.py`.
   - Implement tool decorator `@enterprise_tool` in `core/tools/decorator.py`.
   - Implement the Jev shortlisting coordinator in `core/tools/selector.py`.
   - Register plain Python tool implementations in `tools/adapters/`.
2. **CI Governance Enforcer**:
   - Implement pre-commit validation script `scripts/lint_tool_registry.py` to assert that every tool definition in git contains a valid `reviewer_id` and non-empty Pydantic schemas.

---

## 7. Consequences & Trade-offs

### Positive Consequences
- **Exceptional Function Calling Reliability**: Limiting active tools to $k \le 5$ per turn eliminates LLM parameter confusion and hallucinated tool calls.
- **Supply-Chain Hardening**: Eliminating third-party MCP servers protects the enterprise against description injection attacks and protocol rug pulls.
- **Fail-Safe Autonomy**: Low-confidence tool selections gracefully trip to human specialists rather than executing unvalidated mutations.

### Negative Consequences & Trade-offs
- **Latency of Intermediate Jev Call**: Adding a Jev `Choice` shortlisting query introduces $\approx 35\text{ms}$ of latency on turns requiring tool execution.
- **Developer Review Friction**: Enforcing mandatory two-engineer sign-off for tool registration slows the onboarding velocity of new enterprise API connectors.
- **Inability to Dynamically Mount External Servers**: Excluding runtime MCP servers requires all external tools to be compiled and deployed within the native application codebase.

---

## 8. References & Cross-Disciplinary Grounding

1. **Gorilla: Large Language Model Connected with Massive APIs**: Patil, S. G., et al. (2023). arXiv:2305.15334. (Foundations of API retrieval and context degradation in large tool sets).
2. **Berkeley Function-Calling Leaderboard (BFCL)**: F-Eval Team. (2024). UC Berkeley. (Empirical evaluation of tool-calling accuracy vs. candidate pool size).
3. **OWASP Top 10 for LLM Applications (2025)**: Threat LLM06 — Excessive Agency & Confused Deputy Problem.
4. **Tool Poisoning in Context Protocols**: Invariant Labs Security Advisory. (2025). *Adversarial Instruction Insertion in Tool Descriptions*.
