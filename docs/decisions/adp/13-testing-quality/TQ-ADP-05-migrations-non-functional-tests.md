# TQ-ADP-05: Non-Functional Validation & Checkpoint Migration Verification (Pre-Release Load/Chaos Testing & Backward-Compatible Statechart Migrations)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-05 *(Confirmed per TQ-D7 Expand/Contract SQL Review DP-KK2, TQ-D10 Pre-Release Load & Chaos Staging Gates RP-D12, TQ-D14 Checkpoint Migration Library KK4)*
- **Deciders**: Architecture Team, Lead SRE, Principal Database Architect, Chaos Engineering Lead
- **Component**: `[13] Testing & Quality` (`Component [ 13 ]`)
- **Reasoning Source**: `checkpoint.md` §17 · Diagram: `LLD - [13] Testing & Quality`
- **Decisions Covered**:
  - `TQ-D7`: Expand/Contract SQL Schema Review — Relational database schema migrations follow peer code review and the strict Expand/Contract pattern (`DP-KK2`); breaking schema modifications (column renames, type mutations, dropped tables) are prohibited in single deployments, guaranteeing that in-flight applications on prior code revisions remain fully functional during rolling zero-downtime database upgrades
  - `TQ-D10`: Pre-Release Load & Chaos Verification Gates — Mandates comprehensive non-functional verification on Staging prior to every production release (`RP-D12`); executes automated multi-thousand concurrent virtual user stress tests (Locust/k6) verifying admission control rate limiters (`RP-D1`) and P95 latency envelopes (`RP-D8`), combined with Chaos Mesh fault injection simulating regional database partitions and external LLM provider outages (`RP-D4`)
  - `TQ-D14`: Automated Checkpoint Migration Compatibility Tests — Resolves the catastrophic state deserialization failure mode ($KK4$); maintains a versioned library of serialized historical LangGraph FSM checkpoints across all supported schema revisions; an automated CI test verifies that every archived checkpoint deserializes, migrates, and resumes execution cleanly through registered state migrations (`MS-D13`)
- **Related Architectural Decision Points**:
  - [`MS-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/03-memory-state/MS-ADP-04-agent-state-durability.md): Agent State & Durability *(LangGraph Versioned Checkpointers)*
  - [`RP-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/10-reliability-performance-scale/RP-ADP-05-resilience-testing.md): Resilience Testing *(Load & Chaos Scenarios)*
  - [`DL-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/14-deployment-llmops/DL-ADP-04-versioning-models-indexes-workflows.md): Versioning of Models, Indexes & Workflows *(Continue-As-New Upgrades)*
  - [`DP-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/07-data-persistence/DP-ADP-02-tenant-isolation-encryption.md): Tenant Isolation & Encryption *(Database Schema Invariants)*

---

## 1. Context & Problem Statement

Maintaining backward compatibility across long-running autonomous workflows presents complex state persistence challenges:
1. **The In-Flight Workflow Deserialization Crash ($KK4$)**:
   - In enterprise support, complex cases and financial approvals remain paused in Temporal and LangGraph state stores for up to 3 business days (`HL-D9`).
   - If an engineering team deploys a new release that modifies the internal LangGraph state schema (e.g., renaming `user_intent` to `triage_classification`), in-flight workflows that resume execution crash with `KeyError` or Pydantic deserialization errors. Paused customer cases become corrupted, stranding users in deadlocks ($KK4$).
2. **The Database Migration Lockout (`DP-KK2`)**:
   - Applying synchronous database column renames or schema alterations during active traffic locks relational tables. Old application instances running concurrently with newly deployed pods fail when querying altered columns, resulting in widespread 500 errors.
3. **The Unverified Chaos Horizon (`RP-D12`)**:
   - Architectural fallbacks (such as switching to the local open-weights model `RP-D4` or gracefully degrading to knowledge-base answers `RP-D2`) look sound on paper. However, without continuous automated chaos injection on staging, unexercised fallback circuits fail when real production dependencies degrade.

### The Core Architectural Question
> **How do we engineer an automated verification suite that guarantees old in-flight conversational checkpoints migrate cleanly across code deployments, validates zero-downtime database changes, and subjects releases to realistic chaos testing?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `TQ-D7`, `TQ-D10`, and `TQ-D14` establish the **Checkpoint Migration Library and Pre-Release Non-Functional Verification Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   MIGRATION & NON-FUNCTIONAL VERIFICATION PIPELINE (TQ-D7, TQ-D10, TQ-D14)       │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                                    PRE-RELEASE STAGING VALIDATION GATE
                                                   │
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 1. CHECKPOINT MIGRATION COMPATIBILITY SUITE (TQ-D14, MS-D13, KK4)                                 │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Stored Historical Checkpoint Library: `tests/fixtures/checkpoints/`                              │
│ • Loads Checkpoints from: v1.0.0, v1.1.0, v1.2.0 (Serialized JSON State Blobs)                   │
│ • Executes Registered Upward Migrations: v1.0 -> v1.1 -> v1.2 -> vCurrent                        │
│ • Asserts: Every checkpoint deserializes cleanly into current LangGraph StateGraph schema        │
│ • Asserts: StateGraph can execute at least one forward step without runtime exception           │
└──────────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                   │
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 2. EXPAND / CONTRACT SQL MIGRATION PEER REVIEW (TQ-D7, DP-KK2)                                   │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Two-Phase Zero-Downtime Migration Pattern:                                                       │
│ • Phase 1 (Expand): Add new nullable columns / tables. Both old and new code operate.           │
│ • Phase 2 (Contract): Drop deprecated columns ONLY after 100% of traffic runs on new code.       │
│ • Prohibits single-PR destructive table modifications.                                           │
└──────────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                   │
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 3. PRE-RELEASE LOAD & CHAOS RESILIENCE GATE (TQ-D10, RP-D12)                                     │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Staging Multi-Hour Verification Battery:                                                         │
│ 1. Load Test (k6 / Locust): 2,500 Concurrent Turns -> Asserts RP-D8 P95 Latency Envelopes       │
│ 2. Chaos Injection (Chaos Mesh):                                                                 │
│    • Kill Primary PostgreSQL AZ -> Asserts Automatic Failover in < 30s (`RP-D10`)                │
│    • Blackhole Anthropic API -> Asserts Graceful Fallback to Local Llama 3.1 70B (`RP-D4`)       │
│    • Inject 500ms Network Jitter -> Asserts Temporal Saga Retry Circuit Breakers (`TA-D10`)      │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Pillar 1: Automated Checkpoint Migration Library (`TQ-D14`, `MS-D13`, $KK4$)

To guarantee that long-running workflows survive continuous deployments:
1. **The Checkpoint Archive Library**:
   - The test repository maintains immutable serialized state payloads captured from every prior production release (`v1.0.0_checkpoint.json`, `v1.1.0_checkpoint.json`, etc.).
2. **Automated Migration Runner**:
   - The test harness loads each historical checkpoint file, passes it through the chain of versioned reducer migrations (`MS-D13`), and parses it into the latest `AgentState` schema.
3. **Execution Verification**:
   - The harness instantiates the LangGraph compiler and executes a mocked transition step against the migrated state.
   - If any missing key, type mismatch, or schema breakage occurs, the pre-release gate fails immediately ($KK4$ mitigated).

---

### Pillar 2: Expand / Contract Database Migrations (`TQ-D7`, `DP-KK2`)

To prevent database migrations from breaking running pods during rolling deployments:
1. **The Expand Phase**:
   - Schema additions (new columns, indexes, tables) are deployed in Release $N$. New columns must be `NULLABLE` or define safe defaults. The application writes to both old and new columns.
2. **The Contract Phase**:
   - Deprecated columns or legacy tables are removed in Release $N+1$, strictly after all pods in all regions have been upgraded to Release $N$.
3. **Code Review Gate**:
   - All migration pull requests require mandatory sign-off from a Principal Database Architect to verify expand/contract discipline.

---

### Pillar 3: Staging Load and Chaos Verification (`TQ-D10`, `RP-D12`)

Prior to promoting any release to production canary tracks:
1. **Full-Scale Load Simulation**:
   - k6 test suites simulate $2,500$ concurrent user sessions generating continuous dialogue turns.
   - Asserts that P95 response latencies comply with `RP-D8` targets (FAQ $\le 5\text{s}$, Diagnostic $\le 20\text{s}$, Multi-Specialist $\le 45\text{s}$).
2. **Chaos Mesh Injection**:
   - The CI harness programmatically injects synthetic infrastructure failures:
     - Partitions the Redis cache cluster to verify in-memory fallback.
     - Injects $100\%$ HTTP 500 errors from commercial LLM providers to verify that the local vLLM fallback pool (`RP-D4`, `CR-D9`) absorbs traffic without dropped turns.

---

## 3. Technical Implementation & Genesis Contracts

```python
"""
tests/migrations/test_checkpoint_migrations.py
Verification suite asserting that stored historical checkpoints deserialize and resume (TQ-D14).
"""

import json
import glob
from typing import Dict, Any
import pytest
from pydantic import BaseModel, Field


class AgentStateVCurrent(BaseModel):
    """
    Current canonical LangGraph statechart schema.
    """
    conversation_id: str
    tenant_id: str
    schema_version: int = 3
    triage_domain: str
    completed_steps: int
    context_tokens_used: int
    active_tools_executed: list[str]


def migrate_checkpoint(raw_data: Dict[str, Any]) -> AgentStateVCurrent:
    """
    Applies sequential schema migrations from v1/v2 to vCurrent (MS-D13).
    """
    version = raw_data.get("schema_version", 1)

    if version == 1:
        # v1 -> v2: Added context_tokens_used
        raw_data["context_tokens_used"] = 0
        raw_data["schema_version"] = 2
        version = 2

    if version == 2:
        # v2 -> v3: Renamed intent_category -> triage_domain
        raw_data["triage_domain"] = raw_data.pop("intent_category", "general")
        raw_data["active_tools_executed"] = []
        raw_data["schema_version"] = 3

    return AgentStateVCurrent(**raw_data)


def test_historical_checkpoints_migrate_cleanly():
    """
    CI Test: Loads all stored checkpoints across releases and asserts clean migration (TQ-D14, KK4).
    """
    # Sample historical state payloads representing v1 and v2 releases
    historical_samples = [
        {
            "conversation_id": "conv_legacy_v1_001",
            "tenant_id": "tenant_acme",
            "schema_version": 1,
            "intent_category": "billing",
            "completed_steps": 2
        },
        {
            "conversation_id": "conv_legacy_v2_042",
            "tenant_id": "tenant_globex",
            "schema_version": 2,
            "intent_category": "technical",
            "completed_steps": 4,
            "context_tokens_used": 3500
        }
    ]

    for sample in historical_samples:
        migrated_state = migrate_checkpoint(sample)
        assert migrated_state.schema_version == 3
        assert migrated_state.conversation_id == sample["conversation_id"]
        assert migrated_state.triage_domain in ["billing", "technical"]
```

---

## 4. Failure Modes & Mitigation Matrix

| Failure ID | Sub-Component | Failure Mode Description | Root Cause | Effect on System | Architectural Mitigation (`TQ-D7`, `TQ-D10`, `TQ-D14`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **$KK4$** | Regression | Paused in-flight workflow crashes after deploy | Statechart schema changed without migration | Long-running customer approval cases permanently deadlocked | `TQ-D14` automated test verifies historical checkpoint library migrates cleanly |
| **`DP-KK2`** | Regression | Database migration locks table during deploy | Destructive `ALTER TABLE` run during active traffic | System-wide 500 errors and connection pool exhaustion | `TQ-D7` strictly enforces two-phase Expand/Contract database migration pattern |
| **`RP-D12`** | Scalability | Provider failover breaks under unexpected surge | Standby GPU pool undersized for burst traffic | Cascading platform outage during commercial API outage | `TQ-D10` executes pre-release load and chaos simulations on Staging |

---

## 5. Closed-Loop Telemetry & Verification Directives

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   PRE-RELEASE NON-FUNCTIONAL TELEMETRY DIRECTIVES                                │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Staging Chaos Run ──► [ Chaos Mesh Controller ] ──► Metric: `chaos.injection.recovery_ms`
                                │
                                ├──► [ k6 Load Engine ] ──► Histogram: `staging.load.p95_latency_ms`
                                │
                                └──► [ Checkpoint Test ] ──► Status: `checkpoint_migrations_passed`
```

### 1. Pre-Release Quality Metrics
- `chaos.failover.duration_seconds`: Time required to shift traffic to local GPU cluster during simulated outage (Target: $\le 15\text{s}$).
- `staging.load.p95_latency_ms`: P95 end-to-end turn latency under 2,500 concurrent load (Must satisfy `RP-D8`).
- `migrations.checkpoints_verified_count`: Total historical state payloads validated in CI (Target: $100\%$ pass).

---

## 6. Alternatives Considered & Trade-Off Analysis

| Architectural Alternative | Technical Mechanism | Why Rejected / Trade-Off Analysis |
| :--- | :--- | :--- |
| **Drop In-Flight Checkpoints on Deploy (Option A)** | Abort and restart all running workflows during code updates | **Rejected ($KK4$)**: Destroys customer experience; aborts multi-day approval workflows and loses pending refund states. |
| **Single-Phase Synchronous SQL Migrations (Option B)** | Rename columns and drop tables directly in production | **Rejected (`DP-KK2`)**: Causes application downtime and rolling deployment failures as old pods crash on altered schemas. |
| **Skip Chaos Testing on Staging (Option C)** | Validate failover purely through unit tests and code inspection | **Rejected (`RP-D12`)**: Leaves disaster recovery circuits unproven; real failure modes emerge only under distributed network pressure. |

---

## 7. References & Academic Foundations

1. **Sadalage, P. J., & Fowler, M.** (2006). *Evolutionary Database Design: The Expand-Contract Pattern.* martinfowler.com.
2. **Basiri, A. et al.** (2016). *Chaos Engineering: Building Confidence in System Behavior at Scale.* IEEE Software, 33(3), 35-41.
3. **Temporal Technologies.** (2024). *Workflow Versioning and Deterministic Replay Guarantees.* Temporal Developer Documentation.
4. **NIST SP 800-53, Rev. 5.** (2020). *Security and Privacy Controls for Information Systems and Organizations.* Control CP-4: Contingency Plan Testing.
