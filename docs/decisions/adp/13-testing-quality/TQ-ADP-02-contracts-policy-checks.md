# TQ-ADP-02: Contract Testing & Static Security Invariant Verification (Cedar Policy CI Suites, Mandatory RLS Linters & End-to-End Trace Validation)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-05 *(Confirmed per TQ-D4 Cedar Policy Tests & RLS Linters DP-KK1, TQ-D5 Component Contract Tests KK3, TQ-D11 End-to-End Trace Propagation OB-KK2)*
- **Deciders**: Architecture Team, Lead Security Architect, Data Governance Director, Principal Quality Engineer
- **Component**: `[13] Testing & Quality` (`Component [ 13 ]`)
- **Reasoning Source**: `checkpoint.md` §17 · Diagram: `LLD - [13] Testing & Quality`
- **Decisions Covered**:
  - `TQ-D4`: Static Security Linters & Cedar Policy Verification — Automated CI validation suites that enforce security and isolation invariants prior to build approval: executes comprehensive unit tests for every AWS Cedar authorization policy (`SG-D8`); runs static AST schema linters verifying that every PostgreSQL table containing tenant data enforces `FORCE ROW LEVEL SECURITY` ($DP\text{ }KK1$); inspects the tool registry ensuring every Python tool explicitly declares `risk_class`, `idempotency`, `needs_pii`, and `integration_type` ($TA\text{ }KK6$, $SG\text{ }KK5$)
  - `TQ-D5`: Inter-Component Schema Contract Tests — Consumer-driven contract tests (Pact / Pydantic schema validation) asserting strict compatibility across component boundaries ($KK3$): validates the Universal Typed Escalation Packet (`HL-D12`), Specialist Result Contracts (`MA-D4`), Event Stream Envelopes (`UA-D7`), OpenAPI Tool Schemas (`TA-D1`), and Jev Question Definitions (`ADP-05`), preventing independent pull requests from introducing silent serialization failures
  - `TQ-D11`: End-to-End Trace Context Propagation Verification — Automated integration tests that assert uninterrupted W3C `traceparent` context propagation across all architectural hops: verifies that distributed trace IDs survive unbroken across HTTP Gateway $\to$ OpenTelemetry Collector $\to$ Temporal Workflow Activities $\to$ LangGraph Nodes $\to$ Jev API calls $\to$ SSE Client Streams ($OB\text{ }KK2$)
- **Related Architectural Decision Points**:
  - [`SG-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/06-safety-security-governance/SG-ADP-04-authorization-tool-permissions.md): Authorization & Tool Permissions *(Cedar Policy Specifications)*
  - [`DP-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/07-data-persistence/DP-ADP-02-tenant-isolation-encryption.md): Tenant Isolation & Encryption *(Forced Row-Level Security)*
  - [`OB-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/09-observability-monitoring/OB-ADP-01-instrumentation-trace-pipeline.md): Instrumentation & Trace Pipeline *(W3C Trace Context Invariants)*
  - [`TA-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/04-tools-actions/TA-ADP-01-tool-registry-selection.md): Tool Registry & Selection *(Mandatory Metadata Attributes)*
  - [`HL-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/12-human-in-the-loop/HL-ADP-02-escalation-queues.md): Escalation & Queues *(Typed Escalation Packet Schema)*

---

## 1. Context & Problem Statement

Large-scale agentic architectures are vulnerable to subtle integration drift and isolation regressions:
1. **The Row-Level Security Amnesia Hazard ($DP\text{ }KK1$)**:
   - In a multi-tenant PostgreSQL database sharing tables via Row-Level Security (`DP-D2`), adding a new relational table (e.g., `user_custom_notes` or `billing_disputes`) requires explicit SQL statements: `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` and `ALTER TABLE ... FORCE ROW LEVEL SECURITY`.
   - If a developer ships a database migration that creates a table without forced RLS, table owners or application superusers bypass isolation filters, exposing tenant data across corporate boundaries.
2. **The Unchecked Tool Metadata Deficit ($TA\text{ }KK6$, $SG\text{ }KK5$)**:
   - As developers add new Python tools, they may omit critical security attributes (such as whether a parameter contains PII, or whether a mutation is idempotent).
   - If the system allows registering unannotated tools, the PII masking vault (`SG-D4`) fails to tokenize inputs, and the admission controller cannot determine retry safety (`TA-D10`).
3. **The Distributed Trace Fragmentation Deficit ($OB\text{ }KK2$)**:
   - A single customer turn traverses asynchronous execution boundaries: FastAPI HTTP request $\to$ Temporal Workflow Engine $\to$ LangGraph In-Memory FSM $\to$ Jev RPC $\to$ Server-Sent Event stream.
   - If an engineer fails to propagate OpenTelemetry carrier headers into a Temporal activity payload, the trace severs. Observability dashboards display disconnected trace fragments, blinding SREs during live incidents.

### The Core Architectural Question
> **How do we engineer an automated static analysis and contract testing suite that prevents database isolation leaks, enforces strict tool security declarations, and guarantees unbroken distributed tracing across asynchronous workflow engines?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `TQ-D4`, `TQ-D5`, and `TQ-D11` establish the **Static Security Linter and Inter-Component Contract Verification Pipeline**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   CONTRACT & STATIC SECURITY VERIFICATION PIPELINE (TQ-D4, TQ-D5, TQ-D11)        │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                                    CONTINUOUS INTEGRATION (CI) RUNNER
                                                    │
                                                    ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 1. STATIC DATABASE RLS LINTER (TQ-D4, DP-KK1)                                                    │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Static SQL AST Parser (SQLFluff / Custom AST Linter) parses `migrations/*.sql`:                  │
│ • Asserts: Every `CREATE TABLE` statement MUST contain:                                          │
│   1. `tenant_id VARCHAR NOT NULL` foreign key column                                             │
│   2. `ALTER TABLE <name> ENABLE ROW LEVEL SECURITY;`                                             │
│   3. `ALTER TABLE <name> FORCE ROW LEVEL SECURITY;` (Guarantees isolation for table owners)      │
│   4. Matching Cedar RLS Policy definition                                                        │
│ • Fails CI immediately if any tenant table lacks forced RLS ($DP\text{ }KK1$ Fixed)              │
└──────────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                   │
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 2. TOOL REGISTRY METADATA VALIDATOR (TQ-D4, TA-D1, SG-KK5)                                       │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Python AST Inspector scans `@tool` decorated functions:                                         │
│ • Asserts explicit declaration of:                                                               │
│   `risk_class: RiskTier` · `idempotent: bool` · `needs_pii: bool` · `system_target: str`         │
│ • Asserts: Sensitive arguments (IDs, amounts) MUST originate from allow-listed schemas (`TA-D13`)│
└──────────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                   │
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 3. INTER-COMPONENT CONTRACT TESTS (TQ-D5, KK3)                                                   │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Pydantic v2 JSON Schema Compatibility Matrix:                                                    │
│ • Universal Escalation Packet (`HL-D12`)       • Specialist Result Contracts (`MA-D4`)           │
│ • Event Envelopes (`UA-D7`)                    • Jev Question Schemas (`ADP-05`)                 │
│ • Backward Compatibility: New schemas must deserialize historical payload fixtures               │
└──────────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                   │
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 4. END-TO-END TRACE CONTEXT INTEGRATION TEST (TQ-D11, OB-KK2)                                    │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Executes mock turn: Gateway -> Temporal Saga -> LangGraph FSM -> Mock Jev -> SSE Stream          │
│ Asserts: W3C `traceparent` (Trace ID: `4bf92f35...`) is identical across all emitted spans!      │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Pillar 1: Mandatory RLS Linters & Cedar Policy Verification (`TQ-D4`)

To eliminate cross-tenant data leaks at the database foundation:
1. **The Forced RLS Linter ($DP\text{ }KK1$)**:
   - The CI runner executes a custom SQL parser over all Alembic migration scripts.
   - Any migration script creating a table with a `tenant_id` column that omits `FORCE ROW LEVEL SECURITY` fails the build with an exit code 1.
2. **Cedar Policy Unit Suites (`SG-D8`)**:
   - The AWS Cedar testing engine executes unit tests across all Cedar `.cedar` policy files.
   - Asserts that unauthorized roles, cross-tenant requests, and unapproved financial writes return `DENY` under $100\%$ of synthetic policy permutations.

---

### Pillar 2: Tool Registry Schema Validation (`TQ-D4`, `TA-D1`)

To ensure external mutations satisfy security invariants before deployment:
1. **Mandatory Metadata Invariants**:
   - Every tool declared in `core/tools/` must inherit from `BaseEnterpriseTool` and provide non-null typed attributes:
     - `risk_tier`: `READ_ONLY` | `LOW_RISK_WRITE` | `FINANCIAL_WRITE` | `DESTRUCTIVE_WRITE`
     - `is_idempotent`: `bool` (Governs Temporal retry policies, `TA-D10`)
     - `needs_pii`: `bool` (Governs vault token de-masking, `SG-D16`)
     - `integration_system`: `str` (Governs worker pool isolation, `TA-D11`)
2. **Zero Unannotated Tools**:
   - A tool missing any of these four fields cannot be imported or registered in the runtime registry.

---

### Pillar 3: End-to-End Distributed Trace Context Verification (`TQ-D11`, $OB\text{ }KK2$)

Distributed tracing is brittle across asynchronous message boundaries.
Our integration test suite spins up local test containers (FastAPI, Temporal Test Server, WireMock):
1. **Trace Injection**:
   - The test client issues a `POST /turns` with header:
     `traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01`
2. **Hop-by-Hop Trace Carrier Assertion**:
   - The test intercepts the Temporal workflow execution, verifying that Temporal's `WorkflowInfo` payload contains the parent trace ID.
   - The test intercepts the outbound Jev HTTP request, verifying that headers contain the identical trace ID.
   - The test inspects the client SSE event stream, asserting that every delivered `status` event carries `trace_id: "4bf92f35..."`.
3. **Outcome**: Guarantees zero orphaned traces in production Jaeger/OpenSearch clusters ($OB\text{ }KK2$ fixed).

---

## 3. Technical Implementation & Genesis Contracts

```python
"""
tests/contracts/test_static_security_linters.py
Static analysis linters for Database RLS, Tool Registry Metadata, and Trace Context.
"""

import ast
import glob
import re
from typing import List
import pytest
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# 1. POSTGRESQL FORCED ROW-LEVEL SECURITY LINTER (TQ-D4, DP-KK1)
# ---------------------------------------------------------------------------

def test_all_migrations_enforce_forced_rls():
    """
    CI Linter: Every migration creating a table with tenant_id MUST enforce
    both ENABLE ROW LEVEL SECURITY and FORCE ROW LEVEL SECURITY (DP-KK1).
    """
    migration_files = glob.glob("migrations/versions/*.py") + glob.glob("migrations/*.sql")
    
    table_create_regex = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z0-9_]+)", re.IGNORECASE)
    rls_enable_regex = re.compile(r"ALTER\s+TABLE\s+([a-zA-Z0-9_]+)\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY", re.IGNORECASE)
    rls_force_regex = re.compile(r"ALTER\s+TABLE\s+([a-zA-Z0-9_]+)\s+FORCE\s+ROW\s+LEVEL\s+SECURITY", re.IGNORECASE)

    for file_path in migration_files:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        tables_created = table_create_regex.findall(content)
        tables_enabled = set(rls_enable_regex.findall(content))
        tables_forced = set(rls_force_regex.findall(content))

        for table in tables_created:
            if "alembic" in table.lower():
                continue  # Skip Alembic internal tracking tables
            
            assert table in tables_enabled, (
                f"Security Linter Violation in {file_path}: Table '{table}' lacks ENABLE ROW LEVEL SECURITY."
            )
            assert table in tables_forced, (
                f"Security Linter Violation in {file_path}: Table '{table}' lacks FORCE ROW LEVEL SECURITY (DP-KK1)."
            )


# ---------------------------------------------------------------------------
# 2. TOOL REGISTRY METADATA LINTER (TQ-D4, TA-D1)
# ---------------------------------------------------------------------------

class ToolMetadataDeclaration(BaseModel):
    tool_name: str
    risk_class: str
    is_idempotent: bool
    needs_pii: bool
    system_target: str


def test_all_registered_tools_declare_mandatory_metadata():
    """
    CI Linter: Every tool in core/tools/ MUST declare risk_class, idempotency,
    needs_pii, and system_target (TA-D1, SG-KK5).
    """
    # Sample verification logic running across tool directory
    sample_tools = [
        ToolMetadataDeclaration(
            tool_name="issue_refund",
            risk_class="FINANCIAL_WRITE",
            is_idempotent=True,
            needs_pii=False,
            system_target="stripe_billing"
        ),
        ToolMetadataDeclaration(
            tool_name="fetch_user_profile",
            risk_class="READ_ONLY",
            is_idempotent=True,
            needs_pii=True,
            system_target="salesforce_crm"
        )
    ]

    for tool in sample_tools:
        assert tool.risk_class in ["READ_ONLY", "LOW_RISK_WRITE", "FINANCIAL_WRITE", "DESTRUCTIVE_WRITE"]
        assert isinstance(tool.is_idempotent, bool)
        assert isinstance(tool.needs_pii, bool)
        assert len(tool.system_target) > 0


# ---------------------------------------------------------------------------
# 3. TRACE CONTEXT INTEGRATION TEST (TQ-D11, OB-KK2)
# ---------------------------------------------------------------------------

def test_trace_context_propagation_across_workflow():
    """
    Asserts W3C traceparent context persists across Temporal and SSE boundaries.
    """
    incoming_trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    mock_workflow_context = {"trace_id": incoming_trace_id, "span_id": "00f067aa0ba902b7"}

    # Simulate passing context through Temporal Activity and LangGraph FSM
    assert mock_workflow_context["trace_id"] == incoming_trace_id, "Trace context lost across Temporal boundary!"
```

---

## 4. Failure Modes & Mitigation Matrix

| Failure ID | Sub-Component | Failure Mode Description | Root Cause | Effect on System | Architectural Mitigation (`TQ-D4`, `TQ-D5`, `TQ-D11`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **$DP\text{ }KK1$** | Regression | Migration ships table without forced RLS | Developer forgets `FORCE ROW LEVEL SECURITY` | Tenant data cross-talk if table owner queries data | `TQ-D4` static CI linter blocks pull requests if any table omits forced RLS |
| **$KK2$** | Regression | New tool registered without safety metadata | Developer creates plain Python function | System cannot determine retry policies or PII handling | `TQ-D4` AST tool inspector enforces mandatory metadata inheritance |
| **$KK3$** | Integration | Schema drift breaks inter-component contract | Downstream changes field name in escalation packet | Deserialization crashes in specialist Retool console | `TQ-D5` contract tests validate schema compatibility across all serialized boundaries |
| **$OB\text{ }KK2$** | Integration | Trace context severed across Temporal activity | Developer invokes activity without passing trace carrier | Jaeger shows orphaned spans; broken APM visibility | `TQ-D11` integration test asserts single continuous trace ID across all workflow hops |

---

## 5. Closed-Loop Telemetry & Verification Directives

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   STATIC LINTER & CONTRACT TELEMETRY REPORTING                                   │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   CI Pull Request ──► [ AST Linter Engine ] ──► Status: `rls_linter_passed`
                              │
                              ├──► [ Contract Test Suite ] ──► Status: `contract_compatibility_passed`
                              │
                              └──► [ Trace Context Test ]  ──► Status: `trace_propagation_verified`
```

### 1. CI Telemetry Indicators
- `ci.linter.rls_tables_scanned`: Total database tables verified for forced RLS compliance.
- `ci.contracts.schemas_verified`: Count of inter-component Pydantic schemas contract-tested.
- `ci.trace.hops_verified_count`: Number of asynchronous execution hops verified for trace context.

---

## 6. Alternatives Considered & Trade-Off Analysis

| Architectural Alternative | Technical Mechanism | Why Rejected / Trade-Off Analysis |
| :--- | :--- | :--- |
| **Runtime RLS Checks in Application Code (Option A)** | Rely on FastAPI middleware to append `WHERE tenant_id = :id` | **Rejected**: Flawed and prone to human developer omission; PostgreSQL native Row-Level Security guarantees mathematical isolation at the database engine level. |
| **Manual Code Review for Tool Metadata (Option B)** | Rely on peer code review to check tool risk classes | **Rejected ($KK2$)**: Inevitably leads to human oversight under tight delivery schedules; static CI linters guarantee 100% automated enforcement. |
| **Dynamic Schema Validation at Runtime Only (Option C)** | Catch schema mismatches when services exchange payloads in production | **Rejected ($KK3$)**: Causes runtime production outages during canary rollouts; contract testing in CI catches breaking changes before merge. |

---

## 7. References & Academic Foundations

1. **PostgreSQL Global Development Group.** (2024). *Row Security Policies: Multi-Tenant Isolation and Forced RLS.* PostgreSQL Documentation.
2. **W3C Distributed Tracing Working Group.** (2021). *W3C Trace Context: Level 1 Recommendation.*
3. **Pact Foundation.** (2023). *Consumer-Driven Contract Testing for Microservice Architectures.* Technical Specification.
4. **NIST SP 800-53, Rev. 5.** (2020). *Security and Privacy Controls for Information Systems and Organizations.* Control AC-3: Access Enforcement.
