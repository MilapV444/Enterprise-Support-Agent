# DP-ADP-03: Audit Trails, Transcript Archiving & Dual-Tier Configuration Persistence (Append-Only PostgreSQL Records, Restricted Archive Roles & Code-vs-Database Settings Boundary)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-01 *(Confirmed per DP-D3 Append-Only Audit, DP-D8 Restricted Transcript Archive & DP-D12 Code-vs-Database Settings Split)*
- **Deciders**: Architecture Team, Compliance Officer, Principal Data Architect, Lead Security Engineer
- **Component**: `[7] Data & Persistence` (`Component [ 7 ]`)
- **Reasoning Source**: `checkpoint.md` §11 · Diagram: `LLD - [7] Data & Persistence`
- **Decisions Covered**:
  - `DP-D3`: Audit & Decision Record Store — Append-only PostgreSQL tables (`tool_audit_records`, `decision_records`) with explicit database-level revocation of `UPDATE` and `DELETE` grants across application roles; complex WORM object storage and cryptographic hash chaining rejected for v1 in favor of operational simplicity; DBA tamper capability accepted as a documented operational risk ($UK1$)
  - `DP-D8`: Transcript Legal Archive — Structured 2-year conversation transcript archive stored in a dedicated PostgreSQL table accessible exclusively via a restricted legal audit role; separated from active conversation memory (`MS-D2`); survives user-level operational agent store erasures (`SG-D12`) to meet regulatory compliance requirements
  - `DP-D12`: Configuration & Settings Boundary — Strict dual-tier split: Platform core definitions (tool registry `TA-D1`, specialist topology `MA-D10`, Cedar authorization policies `SG-D8`, agent system prompts `DL-D2`) are version-controlled in immutable application code and deployed via CI/CD; Tenant-specific runtime settings (financial approval threshold default $1,000 `TA-D5`, tenant blackout windows `SG-D10`) reside in versioned, audited database tables
- **Related Architectural Decision Points**:
  - [`TA-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/04-tools-actions/TA-ADP-05-transactional-integrity-audit.md): Transactional Integrity & Audit *(SOX §404 Tool Invocations)*
  - [`SG-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/06-safety-security-governance/SG-ADP-04-authorization-tool-permissions.md): Authorization & Tool Permissions *(Cedar Policy Definitions in Code)*
  - [`SG-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/06-safety-security-governance/SG-ADP-05-governance-retention-providers.md): Governance, Retention & Providers *(2-Year Transcript Mandate & "Why" Records)*
  - [`DL-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#dl-adp-02--configuration-management--prompt-versioning): Configuration Management & Prompt Versioning *(GitOps Configuration Life Cycle)*

---

## 1. Context & Problem Statement

Enterprise customer support agents perform stateful, legally binding actions across financial, technical, and operational systems. These autonomous interactions generate three distinct classes of persistent data, each governed by conflicting engineering and regulatory imperatives:

1. **Immutable Regulatory Audit Trails (SOX §404, SOC 2 Type II)**:
   - Every external tool invocation (`TA-D12`), financial state change, and automated policy/screening decision (`SG-D13`) must produce an immutable audit trail.
   - Engineering simplicity dictates leveraging the existing primary PostgreSQL relational cluster. However, standard relational database architectures allow database superusers or application connections with broad DML permissions to mutate or delete historical records, conflicting with tamper-evidence expectations ($UK1$).
2. **Long-Term Transcript Compliance vs. Operational Memory Erasure (GDPR Art. 17 vs. Legal Defense)**:
   - When an end-user Sarah requests account deletion, her operational memory (working memory, session history, semantic facts) must be erased immediately (`MS-D10`).
   - Conversely, statutory corporate and consumer defense regulations mandate that full verbatim transcripts of financial disputes and contractual commitments be retained for 2 years (`SG-D12`). Keeping these historical transcripts in the live conversation tables degrades agent context retrieval and risks accidental cross-conversation prompt contamination.
3. **The Configuration Management Dilemma (Speed vs. Safety)**:
   - Storing all agent configurations, system prompts, specialist topologies, and security rules in a relational database allows administrative self-service via UI, but exposes the core safety harness to runtime tampering, eliminates Git pull request reviews, and bypasses automated CI evaluation suites (`EV-D1`).
   - Conversely, hardcoding all tenant settings (such as custom financial thresholds or customer support operating hours) in application code forces full software redeployments for trivial operational adjustments.

### The Core Architectural Question
> **How do we establish a tamper-resistant, append-only persistence layer for high-throughput audit and transcript archives within our existing PostgreSQL topology while enforcing a clean, secure boundary between immutable code-defined agent behaviors and dynamic tenant-configurable parameters?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `DP-D3`, `DP-D8`, and `DP-D12` establish the **Append-Only Auditing and Tiered Configuration Persistence Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│               PERSISTENCE ARCHITECTURE FOR AUDIT, ARCHIVE & CONFIGURATION                        │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

 ┌───────────────────────────────────────────────────────────────────────────────────────────────┐
 │ TIER 1: IMMUTABLE PLATFORM DEFINITIONS IN CODE (DP-D12)                                        │
 │ • Tool Registry & Schemas (TA-D1)       • Specialist Graph Topology (MA-D10)                  │
 │ • System Prompts & Jinja2 Templates     • Central Cedar Auth Policies (SG-D8)                 │
 │ Verified via Git Pull Request, Automated Linters, CI Test Suites, and Signed Container Images  │
 └───────────────────────────────────────────────────────────────────────────────────────────────┘
                                                 │
                                                 │ Deployed as Stateless Binary
                                                 ▼
 ┌───────────────────────────────────────────────────────────────────────────────────────────────┐
 │ TIER 2: RUNTIME APPLICATION & OPERATIONAL POSTGRESQL (DP-D3, DP-D8, DP-D12)                   │
 ├───────────────────────────────────────────────────────────────────────────────────────────────┤
 │                                                                                               │
 │   Role: app_runtime_user (Granted: SELECT, INSERT, UPDATE on operational tables)              │
 │   ┌───────────────────────────────────────────────────────────────────────────────────────┐   │
 │   │ Tenant Settings Table (DP-D12)                                                        │   │
 │   │ • approval_threshold_usd (default $1,000)                                              │   │
 │   │ • blackout_windows (cron schedules, active flags)                                     │   │
 │   │ • versioned with optimistic concurrency (version int) + change audit trigger          │   │
 │   └───────────────────────────────────────────────────────────────────────────────────────┘   │
 │                                                                                               │
 │   Role: app_audit_writer (Granted: SELECT, INSERT ONLY; Revoked: UPDATE, DELETE, TRUNCATE)    │
 │   ┌───────────────────────────────────────────────────────────────────────────────────────┐   │
 │   │ Tool Audit Records Table (DP-D3, TA-D12)                                              │   │
 │   │ • id (UUIDv7) | timestamp | tool_call_id | tenant_id | args_hash | before_state       │   │
 │   │ • personal fields encrypted under user DEK (TA-D15 crypto-shredding)                  │   │
 │   ├───────────────────────────────────────────────────────────────────────────────────────┤   │
 │   │ Decision Records Table (DP-D3, SG-D13)                                                │   │
 │   │ • id (UUIDv7) | timestamp | decision_type | prompt_ver | model_id | "why" reasoning   │   │
 │   └───────────────────────────────────────────────────────────────────────────────────────┘   │
 │                                                                                               │
 │   Role: legal_archive_service (Dedicated mTLS microservice; Isolated from runtime agents)    │
 │   ┌───────────────────────────────────────────────────────────────────────────────────────┐   │
 │   │ Transcript Legal Archive Table (DP-D8, SG-D12)                                        │   │
 │   │ • conversation_id | tenant_id | user_id | rendered_transcript | retention_until (2yr) │   │
 │   │ • RLS Enforced; Excluded from agent context assembly and LangGraph checkpointer       │   │
 │   └───────────────────────────────────────────────────────────────────────────────────────┘   │
 └───────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Pillar 1: Append-Only PostgreSQL Audit Schema (`DP-D3`)

Rather than introducing distributed Kafka infrastructure or S3 WORM Object Lock pipelines for v1, audit records (`TA-D12`) and decision logs (`SG-D13`) persist directly to PostgreSQL within the turn transaction.

#### Immutability Enforcement Mechanism
To guarantee that records cannot be altered by application bugs or compromised application roles:
1. **DML Privilege Revocation**:
   ```sql
   REVOKE UPDATE, DELETE, TRUNCATE ON TABLE tool_audit_records FROM app_agent_role;
   REVOKE UPDATE, DELETE, TRUNCATE ON TABLE decision_records FROM app_agent_role;
   GRANT SELECT, INSERT ON TABLE tool_audit_records TO app_agent_role;
   GRANT SELECT, INSERT ON TABLE decision_records TO app_agent_role;
   ```
2. **Defensive Database Trigger**:
   An unconditional trigger serves as a defense-in-depth barrier preventing accidental execution even if a migration script inadvertently grants broad table permissions:
   ```sql
   CREATE OR REPLACE FUNCTION prevent_audit_tampering()
   RETURNS TRIGGER AS $$
   BEGIN
       RAISE EXCEPTION 'SECURITY ERROR: Audit records are immutable. Operation % rejected.', TG_OP;
   END;
   $$ LANGUAGE plpgsql;

   CREATE TRIGGER trg_no_update_delete_tool_audit
   BEFORE UPDATE OR DELETE ON tool_audit_records
   FOR EACH ROW EXECUTE FUNCTION prevent_audit_tampering();
   ```
3. **The Accepted DBA Risk ($UK1$)**:
   We formally document that a PostgreSQL superuser (`rds_superuser` or root cloud administrator) can execute `ALTER TABLE ... DISABLE TRIGGER` or connect directly to raw database blocks to alter records. Full WORM storage and cryptographic Merkle tree hash chaining are deferred to Phase 2 enterprise compliance milestones.

---

### Pillar 2: Isolated Transcript Legal Archive (`DP-D8`)

To decouple operational memory lifecycle from corporate legal retention mandates:
1. **Dual Storage Lifecycle**:
   - When a conversation concludes or is marked resolved, the final rendered dialogue is compiled into a canonical, signed transcript payload.
   - The compiled payload is inserted into the `transcript_legal_archive` table with a mandatory expiration timestamp:
     $$t_{\text{expire}} = t_{\text{creation}} + 730 \text{ days (2 calendar years)}$$
2. **Operational Segregation**:
   - The runtime conversational agent and LangGraph checkpointer have zero read grants on `transcript_legal_archive`. The agent cannot accidentally retrieve old legal transcripts into active prompt context.
   - When a GDPR erasure request executes (`MS-D10`, `DP-D13`), operational memory tables (`conversation_memory`, `langgraph_checkpoints`, `fact_store`) purge Sarah's data immediately.
   - Under GDPR Art. 17(3)(e) (*"establishment, exercise or defence of legal claims"*), the archive record in `transcript_legal_archive` is legally retained, but Sarah's identity is pseudonymized via the token vault (`SG-D4`) or segregated behind the restricted legal compliance role.

---

### Pillar 3: Clean Settings vs. Platform Code Boundary (`DP-D12`)

We establish an unambiguous separation between code-managed platform definitions and database-managed tenant settings:

| Asset Class | Storage Location | Update Mechanism | Governance & Audit Model |
| :--- | :--- | :--- | :--- |
| **Tool Registry & Risk Tiers** (`TA-D1`) | Application Code (Python/Pydantic) | Git PR + Release Deployment | Peer code review, static AST linting, CI/CD pipeline |
| **Specialist Subgraphs** (`MA-D10`) | Application Code (LangGraph) | Git PR + Release Deployment | Regression testing, topological cycle checking |
| **Cedar Authorization Policies** (`SG-D8`) | Application Code (`.cedar` files) | Git PR + Release Deployment | Formal Cedar policy validator (`cedar validate`) |
| **Agent Personas & System Prompts** | Application Code (Jinja2 Templates) | Git PR + Release Deployment | Automated golden set evaluation (`EV-D1`) |
| **Tenant Financial Threshold** (`TA-D5`) | Database (`tenant_settings`) | Admin API via Back-Office UI | Row versioning, audit logging, RBAC validation |
| **Tenant Blackout Windows** (`SG-D10`) | Database (`tenant_settings`) | Admin API via Back-Office UI | Row versioning, cron schedule syntax validation |

#### Optimistic Concurrency Control for Settings Mutation
Database mutations on tenant settings execute under strict optimistic locking to prevent concurrent administrator overwrites:
$$\text{UPDATE tenant\_settings SET value} = v, \text{version} = \text{version} + 1 \quad \text{WHERE tenant\_id} = T \text{ AND key} = K \text{ AND version} = \text{version}_{\text{expected}}$$
If rows affected equals zero, an `OptimisticLockException` is returned, requiring the administrator to fetch the latest state.

---

## 3. Data Contracts & Execution Invariants

### 3.1 Tool Audit & Decision Record Contracts

```python
from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, UUID7, field_validator

class ToolAuditRecord(BaseModel):
    """
    Contract for immutable tool audit persistence (TA-D12, DP-D3).
    Logs all parameters, executions, and state changes.
    """
    id: UUID7 = Field(..., description="Time-ordered UUIDv7 record identifier")
    tenant_id: str = Field(..., regex=r"^ten_[a-zA-Z0-9]{16}$")
    conversation_id: str = Field(..., regex=r"^conv_[a-zA-Z0-9]{16}$")
    turn_id: str = Field(..., regex=r"^turn_[a-zA-Z0-9]{16}$")
    tool_name: str = Field(..., min_length=2, max_length=64)
    caller_agent: str = Field(..., description="Specialist name executing invocation")
    
    # Arguments & Results
    args_sha256: str = Field(..., min_length=64, max_length=64, description="Hash of unmasked arguments")
    encrypted_args_payload: Optional[bytes] = Field(None, description="Personal fields under User DEK (TA-D15)")
    execution_status: str = Field(..., regex=r"^(SUCCESS|FAILURE|COMPENSATED)$")
    
    # Financial State Capture
    financial_before_state: Optional[Dict[str, Any]] = Field(None, description="Snapshot prior to execution")
    financial_after_state: Optional[Dict[str, Any]] = Field(None, description="Snapshot post execution")
    execution_duration_ms: int = Field(..., ge=0)
    created_at_utc: datetime = Field(default_factory=datetime.utcnow)

class DecisionAuditRecord(BaseModel):
    """
    Contract for immutable policy and Jev decision persistence (SG-D13, DP-D3).
    Captures exact model, prompt, and policy versions for auditability.
    """
    id: UUID7 = Field(..., description="Time-ordered UUIDv7 record identifier")
    tenant_id: str = Field(..., regex=r"^ten_[a-zA-Z0-9]{16}$")
    decision_type: str = Field(..., description="e.g., SCREENING_VERDICT, ACTION_APPROVAL, JEV_ROUTING")
    model_version: str = Field(..., description="Exact model snapshot ID")
    prompt_template_git_hash: str = Field(..., min_length=40, max_length=40)
    cedar_policy_version: str = Field(..., description="Git commit hash of active Cedar rules")
    
    input_features_hash: str = Field(..., min_length=64, max_length=64)
    decision_output: Dict[str, Any] = Field(..., description="Deterministic decision result")
    reasoning_summary: str = Field(..., description="Structured explanation / 'Why' record")
    created_at_utc: datetime = Field(default_factory=datetime.utcnow)
```

### 3.2 SQL Invariant: Audit Table Definition

```sql
CREATE TABLE IF NOT EXISTS tool_audit_records (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    conversation_id VARCHAR(64) NOT NULL,
    turn_id VARCHAR(64) NOT NULL,
    tool_name VARCHAR(64) NOT NULL,
    caller_agent VARCHAR(64) NOT NULL,
    args_sha256 CHAR(64) NOT NULL,
    encrypted_args_payload BYTEA,
    execution_status VARCHAR(16) NOT NULL,
    financial_before_state JSONB,
    financial_after_state JSONB,
    execution_duration_ms INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP()
);

-- Indexing for tenant-specific compliance audits
CREATE INDEX idx_tool_audit_tenant_created 
ON tool_audit_records (tenant_id, created_at DESC);

-- Forced Row Level Security
ALTER TABLE tool_audit_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE tool_audit_records FORCE ROW LEVEL SECURITY;

CREATE POLICY tool_audit_tenant_isolation ON tool_audit_records
FOR ALL
USING (tenant_id = current_setting('app.current_tenant_id', true));
```

---

## 4. Quantitative Failure Modes & Operational Risk Bounds

| Failure Mode ID | Sub-Component & Severity | Risk Classification | Empirical Trigger Condition | Detection Vector | Automated Mitigation & Architectural Enforcement |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **DP-FM-301** | Audit Security (`DP-D3`)<br>**HIGH** | Q1 Known Known (Tamper Attempt) | Rogue application worker or bug attempts to issue SQL `UPDATE` against historical `tool_audit_records`. | Postgres trigger `trg_no_update_delete_tool_audit` aborts transaction with SQL exception. | **Immediate Worker Termination**: Database aborts turn transaction; SIEM alerts Security Operations of unauthorized audit modification attempt. |
| **DP-FM-302** | Settings Drift (`DP-D12`)<br>**HIGH** | Q1 Known Known (Concurrency Conflict) | Two administrators simultaneously modify the tenant approval threshold via the admin portal. | Optimistic concurrency check: `WHERE version = expected_version` returns zero updated rows. | **HTTP 409 Conflict Rejection**: API rejects mutation with state divergence payload, prompting operator to reload fresh settings state. |
| **DP-FM-303** | Archive Growth (`DP-D8`)<br>**MEDIUM** | Q2 Known Unknown (Storage Growth) | Millions of concluded conversation transcripts cause `transcript_legal_archive` table to consume excessive SSD storage. | Database table size monitor exceeds $500\text{GB}$; table scan latency degrades. | **Range Partitioning by Month**: The archive table is partitioned by `created_at` monthly range; partitions older than 2 years are dropped atomically via background maintenance. |
| **DP-FM-304** | Tamper Defensibility (`DP-D3`, `DP-D8`)<br>**CRITICAL** | Q3 Unknown Known (Tacit Convention) | Regulatory subpoena demands cryptographic proof that a database administrator did not alter an audit trail row ($UK1$). | Internal compliance review finds absence of cryptographic Merkle roots or WORM guarantees. | **Documented Accepted Risk**: SOC 2 compliance policy explicitly documents append-only Postgres role separation with centralized RDS CloudTrail write audit logging as the interim control. |
| **DP-FM-305** | Config Decoupling (`DP-D12`)<br>**HIGH** | Q4 Unknown Unknown (Contract Drift) | Application code expects a new configuration parameter added in release v2.4, but database settings table contains legacy schema. | Dynamic settings loader raises `MissingConfigurationKeyException` during worker bootstrap. | **Safe Fallback to Code Defaults**: Configuration manager enforces Pydantic default fallback values for all optional tenant configurations. |

---

## 5. Closed-Loop Architectural Feedback

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   AUDIT & CONFIGURATION HEALTH & MONITORING ENGINE                               │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

     Application Turn Execution
                  │
                  ▼
   ┌──────────────────────────────┐
   │ Tool / Decision Invocations  │
   └──────────────┬───────────────┘
                  │
                  ▼
   ┌──────────────────────────────┐
   │ Audit Writer Pipeline        │─────► [Metric: audit_write_latency_ms]
   │ (Single Transaction Commit)  │       Target: p95 < 8ms
   └──────────────┬───────────────┘
                  │
                  ├──────────────────────────────────────────────┐
                  ▼                                              ▼
   ┌──────────────────────────────┐               ┌──────────────────────────────┐
   │ Append-Only Trigger Monitor  │               │ Settings Cache Validator     │
   │ (Detects Unauthorized DML)   │               │ (Detects Admin Mutations)    │
   └──────────────┬───────────────┘               └──────────────┬───────────────┘
                  │                                              │
                  ▼                                              ▼
   [Metric: audit_tamper_attempts]                [Metric: tenant_settings_version]
   Target: Strict 0                               Monitors cluster-wide config sync
   Alerts: P0 PagerDuty on > 0
```

### Telemetry & Operational SLOs
1. **Audit Write Commit Latency**:
   - Metric: `audit_write_duration_seconds{table="tool_audit_records"}`
   - Target: $p95 < 10\text{ms}$, $p99 < 30\text{ms}$.
2. **Audit Tampering Violation Rate**:
   - Metric: `audit_tamper_attempts_total`
   - SLO: **Strictly 0**. Any attempt triggers immediate database connection termination and security alert.
3. **Legal Archive Partition Drop Completeness**:
   - Metric: `archive_expired_records_purged_total`
   - Verification that records older than $730\text{ days}$ are purged within 24 hours of expiration.

---

## 6. Genesis Implementation Directive & Verification Protocol

### 6.1 Database Role & Grants Provisioning Directive

```sql
-- Create isolated application and audit roles
CREATE ROLE app_agent_runtime NOINHERIT LOGIN ENCRYPTED PASSWORD '...';
CREATE ROLE legal_archive_service NOINHERIT LOGIN ENCRYPTED PASSWORD '...';

-- Operational tables (Agent has full CRUD)
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE sessions, conversations, agent_checkpoints TO app_agent_runtime;

-- Immutable audit tables (Agent has INSERT and SELECT only)
GRANT SELECT, INSERT ON TABLE tool_audit_records TO app_agent_runtime;
GRANT SELECT, INSERT ON TABLE decision_records TO app_agent_runtime;
REVOKE UPDATE, DELETE, TRUNCATE ON TABLE tool_audit_records FROM app_agent_runtime;
REVOKE UPDATE, DELETE, TRUNCATE ON TABLE decision_records FROM app_agent_runtime;

-- Legal archive table (Agent runtime has ZERO access; Legal service has SELECT and INSERT)
REVOKE ALL ON TABLE transcript_legal_archive FROM app_agent_runtime;
GRANT SELECT, INSERT ON TABLE transcript_legal_archive TO legal_archive_service;
REVOKE UPDATE, DELETE, TRUNCATE ON TABLE transcript_legal_archive FROM legal_archive_service;
```

### 6.2 Verification Checklist & Integration Tests

```bash
# 1. Verify Immutability of Audit Records
pytest tests/persistence/test_audit_immutability.py -k "test_audit_update_fails"

# Expected Output:
# PASS: UPDATE query on tool_audit_records raises InsufficientPrivilege / TriggerException.
# PASS: DELETE query on decision_records raises InsufficientPrivilege / TriggerException.

# 2. Verify Legal Archive Access Boundary
pytest tests/persistence/test_legal_archive.py -k "test_runtime_agent_cannot_read_archive"

# Expected Output:
# PASS: Runtime agent connection querying transcript_legal_archive raises PermissionDenied.
# PASS: Legal archive service successfully fetches 2-year transcripts by compliance ID.
```

---

## 7. Trade-Off Analysis & Rejected Alternatives

| Dimension | Selected Paradigm (`DP-D3`, `DP-D8`, `DP-D12`) | Rejected Alternative A: Kafka Audit Bus + S3 Object Lock (WORM) | Rejected Alternative B: All Configurations in Database |
| :--- | :--- | :--- | :--- |
| **Operational Simplicity & Moving Parts** | **High**: Reuses existing primary PostgreSQL cluster; zero external brokers or synchronization pipelines. | **Low**: Introduces Kafka clusters, Debezium CDC connectors, and S3 retention policies ($DP\text{-}F3b$). | **Moderate**: Single database table, but requires full UI admin suite for code-level definitions. |
| **Tamper Evidence & Court Defensibility** | **Moderate**: Protected against app-tier bugs via role revokes and triggers; vulnerable to rogue DBAs ($UK1$). | **Absolute**: Cryptographic hash chaining and hardware WORM object locks satisfy SEC Rule 17a-4. | **Poor**: System prompts and authorization policies subject to unauthorized DBA/admin modification. |
| **Latency Impact on Execution Turn** | **Zero Overhead**: Direct database insert commits atomically inside the turn's existing transaction block. | **Asynchronous Overhead**: Requires dual-write handling or transactional outbox relay workers. | **Zero Overhead**: But lacks build-time static validation. |
| **Systemic Safety & GitOps Rigor** | **Absolute**: Critical security policies (Cedar) and system prompts are peer-reviewed in Git and tested in CI. | **Identical**: If configuration split is maintained. | **Fatal Risk**: Prompt injection defences or tool registries modified dynamically without automated eval suites. |

---

## 8. Formal References & Literature Grounding

1. **Sarbanes-Oxley Act of 2002 (SOX).** *Public Law 107-204, Section 404: Management Assessment of Internal Controls*. *(Mandate for immutable, non-repudiable audit records of automated financial transactions).*
2. **American Institute of Certified Public Accountants (AICPA). (2022).** *SOC 2® – SOC for Service Organizations: Trust Services Criteria*. Section CC6.1 & CC6.8 (Logical Access Controls and Audit Logging). *(Standard for audit trail retention and separation of administrative roles).*
3. **European Union General Data Protection Regulation (GDPR). (2016).** *Regulation (EU) 2016/679: Article 17(3)(e)*. *(Exemption allowing retention of otherwise erased customer records for the establishment, exercise, or defence of legal claims).*
4. **Fowler, M. (2018).** *Refactoring: Improving the Design of Existing Code*. Addison-Wesley. *(Architectural separation between executable declarative rules and runtime configuration data).*
5. **PostgreSQL Global Development Group. (2024).** *PostgreSQL 16 Documentation: Chapter 41 (Database Roles and Privileges) & Chapter 43 (Row Security Policies)*. *(Standard documentation establishing security invariants of DML privilege revocation and triggers).*
