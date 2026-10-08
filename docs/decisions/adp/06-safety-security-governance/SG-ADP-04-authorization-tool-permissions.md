# SG-ADP-04: Authorization & Tool Permissions (Central AWS Cedar Policy Engine, Role-Scoped Ticket Visibility & Blackout Fail-Closed Controls)

- **Status**: Accepted & Confirmed
- **Date**: 2026-09-30 *(Amended: 2026-09-30 per SG-D8 AWS Cedar Engine, SG-D9 Author/Admin Ticket Scoping, SG-D10 Blackout Windows, SG-D17 Outage Caching & SG-Q1 Engine Selection)*
- **Deciders**: Architecture Team, Lead Security & IAM Architect, Principal Compliance Engineer
- **Component**: `[6] Safety, Security & Governance` (`Component [ 6 ]`)
- **Reasoning Source**: `checkpoint.md` §10 · Diagram: `LLD - [6] Safety, Security & Governance`
- **Decisions Covered**:
  - `SG-D8`: Central Policy Architecture — Externalized, versioned, testable authorization powered by AWS Cedar (`SG-Q1`); unified policy evaluation across Tools (agent-side checks, `TA-D4`), Knowledge (document access), and Memory
  - `SG-D9`: Within-Tenant Ticket Retrieval Privacy — Tickets are retrievable strictly by their original author or users possessing explicit tenant support/admin roles; resolves within-tenant privacy exposure (`KR-UK3`)
  - `SG-D10`: Tenant Blackout Windows & Change Freezes — Tenant-configurable blackout windows; destructive or production-affecting actions attempted inside blackout windows strictly mandate human approval (`TA-UK4`)
  - `SG-D17`: Policy Engine Outage & Fail-Closed Resilience — If the Cedar policy engine is unreachable: mutating writes fail closed immediately; read-only operations reuse cached authorization verdicts for a short TTL (default 5 minutes, $UU5$)
- **Related Architectural Decision Points**:
  - [`TA-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/04-tools-actions/TA-ADP-03-action-validation-approval.md): Action Validation & Approval Tiers *(Two-Person Human Gates)*
  - [`TA-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/04-tools-actions/TA-ADP-04-execution-credentials-isolation.md): Execution, Credentials & Isolation *(Agent-Side Service Account Verification)*
  - [`KR-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/02-knowledge-retrieval/KR-ADP-03-indexing-tenant-isolation.md): Indexing & Tenant Isolation *(Copied ACLs & Live OBO Filtering)*
  - [`HL-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#hl-adp-03--intervention-tripwires--routing): Intervention Tripwires & Routing *(Specialist Routing on Policy Denial)*

---

## 1. Context & Problem Statement

Autonomous enterprise support agents operate with extensive technical reach: querying historical ticket transcripts, reading infrastructure ledgers, and triggering operational cloud actions.

In heterogeneous enterprise architectures, managing authorization via fragmented, ad-hoc Python conditional statements creates critical security failures:
1. **The Confused Deputy Service-Account Escalation ($TA-D4$, $KK6$)**: In legacy systems lacking RFC 8693 On-Behalf-Of tokens, the agent connects using a shared service account. If the agent fails to verify whether the requesting user actually owns the target entity before dispatching SQL or API calls, an authenticated customer can inspect or mutate another customer's infrastructure.
2. **Within-Tenant Ticket Snooping ($KR-UK3$)**: When raw support tickets are indexed into a tenant's private collection (`KR-D1`), naive retrieval allows any employee at Acme Corp to retrieve sensitive tickets filed by their colleagues (e.g., executive compensation inquiries, pending layoffs, or internal whistleblowing reports).
3. **Change Freeze Violations During Peak Operations ($TA-UK4$)**: Enterprise tenants maintain strict blackout windows (e.g., Black Friday sales, end-of-quarter financial close, or scheduled maintenance). If an agent autonomously restarts a database cluster during a customer's peak revenue window because an automated diagnostic SOP recommended it, the operational impact is devastating.
4. **The Policy Engine Availability Dilemma ($UU5$)**: If an external authorization engine experiences an outage, a naive system faces a fatal dilemma: failing open creates immediate security vulnerabilities, while failing closed completely halts benign conversational support.

### The Core Architectural Question
> **How do we externalize, test, and enforce unified fine-grained authorization across tools, historical tickets, and memory, while enforcing tenant blackout freezes and maintaining conversational availability during authorization service degradation?**

---

## 2. Decision Framework & Theoretical Formulation

To solve these challenges, `SG-D8`, `SG-D9`, `SG-D10`, and `SG-D17` establish the **Centralized AWS Cedar Authorization Engine with Asymmetric Outage Caching**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                            CENTRAL CEDAR AUTHORIZATION TOPOLOGY (SG-D8)                          │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

Request Context: Principal (Sarah, Roles: [cloud_admin]), Action, Resource, Time
                                                │
                                                ▼
                             ┌──────────────────────────────────────┐
                             │     AWS Cedar Policy Engine (SG-Q1)  │
                             │  • Formally Verifiable ABAC Policies │
                             │  • Default Deny Architecture         │
                             │  • Sub-5ms In-Memory Evaluation      │
                             └──────────────────────────────────────┘
                                                │
         ┌──────────────────────────────┼──────────────────────────────┐
         ▼                              ▼                              ▼
┌──────────────────┐           ┌──────────────────┐           ┌──────────────────┐
│ Knowledge Access │           │ Tool Execution   │           │ Blackout Freeze  │
│ (SG-D9)          │           │ (TA-D4)          │           │ (SG-D10)         │
│ Permit if author │           │ Permit if user   │           │ Forbid mutations │
│ or support admin │           │ owns resource ID │           │ during window    │
└──────────────────┘           └──────────────────┘           └──────────────────┘
                                                │
                       ┌────────────────────────┴────────────────────────┐
                       ▼                                                 ▼
        ┌─────────────────────────────┐                   ┌─────────────────────────────┐
        │ VERDICT: ALLOW              │                   │ VERDICT: DENY               │
        │ Proceed with execution      │                   │ Mutating: Abort Turn        │
        │ Commit audit record         │                   │ Blackout: Force Human Card  │
        └─────────────────────────────┘                   └─────────────────────────────┘
```

---

### Pillar A: Attribute-Based Access Control via AWS Cedar (`SG-D8`, `SG-Q1`)

We select **AWS Cedar** over OPA/Rego (`SG-Q1`) as our central enterprise authorization engine. Cedar provides:
- Formally verified policy analysis (automated reasoning via SMT solvers).
- Native typing and role hierarchy semantics.
- Sub-millisecond evaluation latency in Rust/C bindings.

#### The Default-Deny Semantic Formulation
Authorization evaluates against an explicit policy lattice:
$$\text{IsPermitted}(p, a, r, c) = \begin{cases}
\text{ALLOW} & \text{if } \exists P \in \mathcal{P}_{\text{permit}} \text{ s.t. } P(p, a, r, c) \land \nexists F \in \mathcal{P}_{\text{forbid}} \text{ s.t. } F(p, a, r, c) \\
\text{DENY} & \text{otherwise (Strict Default Deny)}
\end{cases}$$

#### Representative Cedar Policy for Agent-Side Checks (`TA-D4`)
```cedar
// Permit cloud administrators to restart clusters within their own tenant
permit (
    principal in Role::"cloud_admin",
    action == Action::"restart_cluster",
    resource in Environment::"production"
)
when {
    principal.tenant_id == resource.tenant_id &&
    resource.owner_id == principal.id
};
```

---

### Pillar B: Within-Tenant Ticket Retrieval Isolation (`SG-D9` / `KR-UK3`)

To eliminate colleague ticket snooping while preserving collaborative support:
1. **Metadata Ingestion Tagging**: Every resolved ticket chunk ingested into Qdrant (`KR-D1`, `KR-D4`) is tagged with:
   $$\text{ChunkMetadata} = \langle \text{tenant\_id}, \text{author\_principal\_id}, \text{is\_internal\_sensitive} \rangle$$
2. **Cedar Retrieval Filtering Rule**:
   A user $\pi$ is permitted to retrieve ticket $T$ if and only if:
   $$\text{CanRetrieveTicket}(\pi, T) \iff (\pi = T.\text{author\_principal\_id}) \lor (\text{"tenant\_support"} \in \text{Roles}(\pi)) \lor (\text{"tenant\_admin"} \in \text{Roles}(\pi))$$
3. Standard employees querying the knowledge base retrieve public documentation, operational runbooks, and their own past tickets; tickets authored by colleagues are stripped from the retrieval candidate pool.

---

### Pillar C: Tenant Blackout Windows & Change Freezes (`SG-D10` / `TA-UK4`)

To protect customer production stability during high-stakes operational periods:
1. **Blackout Window Specification**: Tenants configure scheduled change freezes in their configuration profile:
   $$\mathcal{W}_{\text{freeze}} = \left\{ [t_{\text{start}}, t_{\text{end}}] \mid \text{Timezone: } \text{TZ}_{\text{tenant}}, \text{Scope: } \text{"production"} \right\}$$
2. **Cedar Forbid Override**: Cedar evaluates an explicit `forbid` policy:
   ```cedar
   // Forbid autonomous production mutations during active blackout windows
   forbid (
       principal,
       action in [Action::"restart_cluster", Action::"apply_migration", Action::"terminate_service"],
       resource in Environment::"production"
   )
   when {
       context.current_time >= context.blackout_start &&
       context.current_time <= context.blackout_end
   };
   ```
3. **Approval Elevation**: When an autonomous SOP triggers an action forbidden by a blackout window, the action is **not dropped**; instead, it is elevated to `HUMAN_APPROVAL_REQUIRED` (`TA-ADP-03`), presenting an emergency override card to the customer's on-call engineering lead.

---

### Pillar D: Asymmetric Outage Caching Resilience (`SG-D17` / $UU5$)

To ensure high availability without compromising security during authorization service degradation:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                            ASYMMETRIC POLICY OUTAGE CACHING (SG-D17)                             │
├─────────────────────────────────────────────────┬────────────────────────────────────────────────┤
│   MUTATING OPERATIONS (Writes, Financial)       │   NON-MUTATING OPERATIONS (Reads, Docs)        │
├─────────────────────────────────────────────────┼────────────────────────────────────────────────┤
│   • Caching: STRICTLY BANNED (TTL = 0s)         │   • Caching: Short Cache Permitted (TTL = 300s)│
│   • Engine Down Behavior: FAIL CLOSED           │   • Engine Down Behavior: SERVE FROM CACHE     │
│   • Result: Action Aborted with 503             │   • Result: Customer continues reading FAQs    │
│   • Invariant: Zero unauthorized mutations      │   • Invariant: High conversational uptime      │
└─────────────────────────────────────────────────┴────────────────────────────────────────────────┘
```

- **Mutating Operations**: Require live synchronous Cedar evaluation. If Cedar is unreachable, the call fails closed immediately.
- **Read-Only Operations**: Cedar authorization verdicts are cached in Redis for up to $300$ seconds. If Cedar is down, reads proceed against cached credentials.

---

## 3. Decision Rules, Structural Invariants & Code Contracts

### Decision Invariants
1. **Invariant 1 (Default-Deny Inviolability)**: The absence of an explicit Cedar permit policy MUST result in an immediate authorization denial.
2. **Invariant 2 (Zero Mutating Cache Tolerance)**: Mutating tool invocations must never utilize cached authorization verdicts.
3. **Invariant 3 (Blackout Window Precedence)**: A blackout `forbid` policy overrides all existing `permit` policies, forcing human approval for production modifications.
4. **Invariant 4 (Tenant Boundary Partitioning)**: All Cedar authorization queries must include `tenant_id` assertions, preventing cross-tenant policy evaluation leaks.

---

### Python & Pydantic Data Contracts

```python
"""
Data contracts for Cedar Authorization, Ticket Visibility, and Blackout Policies.
Module: core/safety/authorization.py
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class AuthorizationVerdict(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRES_OVERRIDE_APPROVAL = "requires_override_approval"


class AuthorizationContext(BaseModel):
    """Contextual parameters passed into Cedar policy engine."""
    tenant_id: str
    principal_id: str
    principal_roles: List[str]
    current_timestamp: datetime = Field(default_factory=datetime.utcnow)
    target_environment: str = Field(default="production")
    is_blackout_active: bool = Field(default=False)


class CedarPolicyEvaluationRequest(BaseModel):
    """Execution packet sent to the Cedar policy runtime."""
    principal: str = Field(..., example="User::\"sarah_9021\"")
    action: str = Field(..., example="Action::\"restart_cluster\"")
    resource: str = Field(..., example="Cluster::\"prod-db-1\"")
    context: AuthorizationContext


class AuthorizationDecision(BaseModel):
    """Authoritative decision emitted by the authorization engine."""
    verdict: AuthorizationVerdict
    decision_reason: str
    determining_policy_ids: List[str]
    served_from_cache: bool = Field(default=False)
    evaluation_duration_ms: float
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)


class TenantBlackoutSchedule(BaseModel):
    """Configuration model for customer maintenance freezes (SG-D10)."""
    tenant_id: str
    schedule_id: str
    start_time: datetime
    end_time: datetime
    timezone_str: str = Field(default="UTC")
    affected_environments: List[str] = Field(default_factory=lambda: ["production"])
    reason: str = Field(..., description="e.g., 'Q4 Financial Close Freeze'")
```

---

## 4. Failure Modes Matrix & Resilience Invariants

| Quadrant | Failure Scenario | Detection Mechanism | Systemic Mitigation & Recovery |
| :--- | :--- | :--- | :--- |
| **Q1: Known Knowns** | **Policy Syntax / Compilation Bug ($KK5$)**: Newly deployed Cedar policy file contains a syntax error, threatening to crash authorization. | Cedar automated policy validator runs during CI/CD pre-commit. | CI/CD pipeline runs `cedar validate` against schemas; deployment halts if any policy fails formal validation. |
| **Q2: Known Unknowns** | **Cedar Engine Network Outage ($UU5$)**: Authorization microservice becomes unreachable due to a network partition. | Health check probe flags connection timeout to Cedar. | Asymmetric resilience (`SG-D17`): writes fail closed immediately; reads continue seamlessly using a 300s Redis cache. |
| **Q3: Unknown Knowns** | **Misconfigured Timezone Blackout Failure ($KU4$)**: Customer specifies blackout window in EST, but system evaluates in UTC, permitting peak restarts. | Timezone validator flags naive datetime inputs. | All tenant blackout schedules require explicit IANA timezone strings (`SG-D10`); engine normalizes to UTC prior to evaluation. |
| **Q4: Unknown Unknowns** | **Colleague Ticket Snooping Probe ($KR-UK3$)**: User queries knowledge base for salary disputes filed by their team lead. | Ticket metadata author filter intercepts search query. | Cedar policy engine restricts ticket retrieval to author and tenant support admins (`SG-D9`); colleague tickets are filtered from results. |

---

## 5. Closed-Loop Feedback & Verification Signals

1. **System Health Telemetry**:
   - `Authorization_Denial_Rate`: Monitored per tenant; alerts if denial rate surges by $>5\%$, indicating misconfigured role bindings.
   - `Blackout_Window_Override_Count`: Tracks how frequently emergency overrides are triggered during change freezes.
   - `Policy_Evaluation_Latency_p99`: Monitored via StatsD; alerts if Cedar evaluation exceeds $5\text{ms}$.
2. **Weekly Automated Policy Verification (Cedar SMT Solver)**:
   - Run the Cedar automated reasoning analyzer in CI, proving that no combination of policies allows a non-admin user to execute production mutations or inspect colleagues' tickets.

---

## 6. Genesis Implementation Directives

1. **Code Locations**:
   - Implement the Cedar engine wrapper in `core/safety/cedar_engine.py`.
   - Store Cedar policy files in `config/policies/` (`tools.cedar`, `knowledge.cedar`, `blackout.cedar`).
   - Implement the blackout window validator in `core/safety/blackout_guard.py`.
   - Implement the authorization cache in `core/safety/auth_cache.py`.
2. **Cedar CLI Directives**:
   - Add pre-commit git hook running:
     ```bash
     cedar validate --schema config/policies/schema.cedarschema --policies config/policies/
     ```

---

## 7. Consequences & Trade-offs

### Positive Consequences
- **Formally Verified Authorization**: Centralizing access control in Cedar enables mathematical verification of security boundaries.
- **Robust Within-Tenant Privacy**: Filtering ticket retrieval by author and support role completely eliminates colleague data snooping.
- **Production Blackout Protection**: Automated change freeze enforcement prevents autonomous agents from destabilizing peak customer operations.

### Negative Consequences & Trade-offs
- **Cedar Learning Curve**: Developers must author and test declarative Cedar policies rather than writing simple Python conditionals.
- **Cache Invalidation Latency**: Caching read decisions for $300$ seconds means revoked read permissions may take up to $5$ minutes to take effect.
- **Fail-Closed Write Disruption**: Complete shutdown of mutating operations during Cedar outages temporarily blocks automated remediation workflows.

---

## 8. References & Cross-Disciplinary Grounding

1. **Cedar: A Formally Verified Policy Language**: Amazon Web Services. (2023). ACM SIGPLAN. (Foundations of verified ABAC and SMT solver policy analysis).
2. **NIST Special Publication 800-162**: *Guide to Attribute Based Access Control (ABAC) Definition and Considerations*.
3. **ITIL 4 Service Management**: *Change Enablement and Release Management Practice*. (Foundations of Blackout Windows and Change Freezes).
4. **OWASP Top 10 for LLM Applications (2025)**: Threat LLM06 — Excessive Agency and Broken Access Control.
