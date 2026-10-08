# DP-ADP-02: Multi-Tenant Database Isolation & Cryptographic Envelope Shredding (PostgreSQL RLS, Per-User DEK Envelope Encryption & Isolated Token Vault)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-01 *(Confirmed per DP-D2 Pool RLS, DP-D4 Envelope Encryption revised by CR-D10, & DP-D5 Dedicated Token Vault Database)*
- **Deciders**: Architecture Team, Principal Security Architect, Data Platform Lead, Cryptography & Compliance Engineer
- **Component**: `[7] Data & Persistence` (`Component [ 7 ]`)
- **Reasoning Source**: `checkpoint.md` §11 · Diagram: `LLD - [7] Data & Persistence`
- **Decisions Covered**:
  - `DP-D2`: Multi-Tenant Isolation Model — Pool model: shared PostgreSQL tables partitioned logically by `tenant_id` with strictly enforced Row-Level Security (`ALTER TABLE ... FORCE ROW LEVEL SECURITY`); database connections dynamically bind `app.current_tenant_id` from verified cryptographically signed caller JWTs (`UA-D4`); silo and bridge models rejected to preserve horizontal connection pooling efficiency and rapid schema migrations
  - `DP-D4`: Cryptographic Envelope Encryption & Crypto-Shredding — Hierarchical envelope encryption: ephemeral Data Encryption Key per user ($K_{\text{user}}$) encrypted under per-tenant Key Encryption Key ($K_{\text{tenant}}$) managed in regional Cloud KMS; personal fields in facts (`MS-D19`) and tool audit logs (`TA-D15`) encrypted with $K_{\text{user}}$; user erasure deletes $K_{\text{user}}$ (crypto-shredding), instantly rendering all historic records cryptographically unreadable; wrapped keys reside in a segregated key store with strict 1-day backup retention (`CR-D13`)
  - `DP-D5`: Token Vault Physical Isolation — Dedicated, physically isolated PostgreSQL instance for the PII Token Vault (`SG-D4`, `SG-D5`); operates under distinct VPC security groups, isolated database roles, and dedicated KMS encryption; compromise of the operational database cluster yields zero access to PII vault cleartext
- **Related Architectural Decision Points**:
  - [`SG-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/06-safety-security-governance/SG-ADP-02-pii-protection.md): PII Protection *(Reversible Tokenization & Needs-PII Fields)*
  - [`MS-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/03-memory-state/MS-ADP-02-long-term-fact-model.md): Long-Term Fact Model *(Encrypted Per-User Fact Storage)*
  - [`TA-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/04-tools-actions/TA-ADP-05-transactional-integrity-audit.md): Transactional Integrity & Audit *(Crypto-Shredded Tool Audit Trails)*
  - [`CR-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#cr-adp-05--database-caching--kms-cost-optimization): Database Caching & KMS Cost Optimization *(Envelope Key Caching vs. Direct KMS Invocation)*
  - [`TQ-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#tq-adp-02--contract-testing--isolation-verification): Contract Testing & Isolation Verification *(CI RLS Leakage Verification)*

---

## 1. Context & Problem Statement

In an enterprise multi-tenant environment serving B2B clients across regulated sectors (finance, healthcare, telecommunications), persistence security rests on two non-negotiable foundations:
1. **Absolute Multi-Tenant Boundary Enforcement**:
   - Multiple enterprise customers share computing resources. Under no circumstance may a SQL injection bug, an unparameterized query, an asynchronous worker race condition, or an operator error allow Tenant $A$ to read or mutate the conversation records, session tokens, or facts of Tenant $B$.
2. **Deterministic Right-to-be-Forgotten & Irreversible Erasure (GDPR Art. 17, CCPA §1798.105)**:
   - When an end-user Sarah exercises her legal right to erasure, her personal data must become permanently and provably irrecoverable.
   - However, relational databases maintain automated continuous point-in-time recovery (PITR) backups and daily snapshots retained for up to 35 days (`DP-D9`, `DP-Q4`). Relational `DELETE` operations executed on live tables do not purge data embedded in immutable database backup files.
3. **The KMS Scalability & Rate-Limit Cliff ($KU1$, `CR-D10`)**:
   - Initial naive designs considered assigning a dedicated AWS/GCP KMS key per end-user. With millions of enterprise end-users, direct KMS keys exhaust cloud account quotas ($10,000$ keys per account default) and incur unsustainable monthly fixed costs ($\$1.00/\text{key/month} \implies \$1,000,000/\text{year}$ for $1\text{M}$ users) while hitting strict cryptographic API request rate limits ($10,000\text{ req/sec}$).
4. **Blast Radius of Operational Database Breaches**:
   - If PII token mapping tables reside in the same relational database as operational agent conversation logs, an SQL exfiltration flaw or compromised application read credential simultaneously leaks both the pseudonymized tokens and the cleartext identity mappings.

### The Core Architectural Question
> **How do we achieve provable multi-tenant isolation within a cost-effective pooled PostgreSQL architecture while providing sub-millisecond, quota-sustainable per-user cryptographic shredding that guarantees immutable backups cannot resurrect erased personal data?**

---

## 2. Decision Framework & Theoretical Formulation

To solve these challenges, `DP-D2`, `DP-D4`, and `DP-D5` establish the **Tri-Tier Persistence Isolation and Envelope Shredding Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│             MULTI-TENANT ISOLATION & ENVELOPE ENCRYPTION ARCHITECTURE (DP-D2, DP-D4)             │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                       Inbound Request from Authenticated User Sarah
                                             │
                                             ▼
                 ┌───────────────────────────────────────────────────────┐
                 │ Gateway Identity Verification (UA-D4)                 │
                 │ Claims: tenant_id = "ten_acme_01", user_id = "usr_98" │
                 └───────────────────────────┬───────────────────────────┘
                                             │
             ┌───────────────────────────────┴───────────────────────────────┐
             ▼                                                               ▼
┌─────────────────────────────────────────┐     ┌─────────────────────────────────────────┐
│ OPERATIONAL DB CONNECTION POOL (DP-D2)  │     │ ISOLATED PII TOKEN VAULT DB (DP-D5)     │
│ Shared Tables with Forced RLS           │     │ Segregated VPC, Distinct IAM & DB Role  │
│ SET LOCAL app.current_tenant_id = '...';│     │ Mapping: [Token UUID] <---> [Cleartext] │
└────────────────────┬────────────────────┘     └─────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ TWO-TIER CRYPTOGRAPHIC ENVELOPE SHREDDING HIERARCHY (DP-D4, CR-D10)                              │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                  │
│   AWS KMS / HSM (Cloud Provider Master Key)                                                      │
│   ┌────────────────────────────────────────────────────────────┐                                 │
│   │ Tenant Key Encryption Key: K_tenant = KMS_Key("ten_acme_01") │                                 │
│   └─────────────────────────────┬──────────────────────────────┘                                 │
│                                 │ Encrypts / Decrypts DEK                                        │
│                                 ▼                                                                │
│   Dedicated Key Store (1-Day Backup Retention, CR-D13)                                           │
│   ┌────────────────────────────────────────────────────────────┐                                 │
│   │ Wrapped User Data Encryption Key:                          │                                 │
│   │ C_dek = AES-GCM-Encrypt(K_tenant, K_user("usr_98"))        │                                 │
│   └─────────────────────────────┬──────────────────────────────┘                                 │
│                                 │ Decrypted into In-Memory Cache (TTL: 5 min)                    │
│                                 ▼                                                                │
│   Operational DB Payload Rows (Facts MS-D19, Tool Audit TA-D15)                                  │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ Row: tenant_id | user_id | encrypted_payload = AES-256-GCM(K_user, Payload, IV, AAD)    │   │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                                  │
│   ON USER ERASURE:                                                                               │
│   1. DELETE row where user_id = 'usr_98' in Key Store                                            │
│   2. Evict K_user from Memory Cache                                                              │
│   ===> All historical facts and audit records in live DB AND 35-day backups INSTANTLY SHREDDED   │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Pillar 1: Forced Row-Level Security (RLS) in Pooled Schema (`DP-D2`)

We deploy the **Pool Tenancy Model**: all enterprise tenants share consolidated PostgreSQL tables partitioned logically by `tenant_id`. To eliminate human application developer error, multi-tenant isolation is enforced at the database engine kernel level via PostgreSQL **Forced Row-Level Security**:
```sql
ALTER TABLE agent_checkpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_checkpoints FORCE ROW LEVEL SECURITY;
```

#### The RLS Invariant Formulation
Let $\mathcal{T}$ be the set of all tenants, and $q(s)$ be an arbitrary SQL query executed within database session $s$. The database engine enforces:
$$\text{ResultSet}(q(s)) \subseteq \{ r \in \text{Table} \mid r.\text{tenant\_id} = \text{SessionContext}(s).\text{tenant\_id} \}$$

1. **Session Context Binding**: Every database connection retrieved from the PgBouncer pool executes a local, non-reentrant session configuration statement within the transaction block:
   ```sql
   SET LOCAL app.current_tenant_id = 'ten_acme_01';
   ```
2. **Kernel Enforcement**: The table policy evaluates:
   ```sql
   CREATE POLICY tenant_isolation_policy ON agent_checkpoints
   FOR ALL
   USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''))
   WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''));
   ```
3. **The `FORCE` Modifier Guarantee ($KK1$)**: By default, PostgreSQL disables RLS for table owners (`postgres` superuser or migration role). By executing `FORCE ROW LEVEL SECURITY`, RLS policies are applied unconditionally, even to database administrators and maintenance roles, preventing unintended cross-tenant leaks during background scripts.

---

### Pillar 2: Hierarchical Envelope Encryption & Crypto-Shredding (`DP-D4`)

To resolve the tension between 35-day database backup retention (`DP-D9`) and immediate GDPR erasure, we implement two-tier cryptographic envelope shredding:

#### Mathematical Cryptographic Definition
1. **Per-Tenant Key Encryption Key ($K_{\text{tenant}}$)**:
   Managed inside Hardware Security Modules (AWS KMS / Cloud HSM) in the tenant's sovereign region (`DP-D10`):
   $$K_{\text{tenant}} \in \text{KMS}_{\text{regional}}(\text{tenant\_id})$$
2. **Per-User Data Encryption Key ($K_{\text{user}}$)**:
   Generated as a cryptographically secure 256-bit symmetric key:
   $$K_{\text{user}} \xleftarrow{\$} \{0,1\}^{256}$$
3. **Key Wrapping**:
   The user key is wrapped using AES-256 Key Wrap (KW) or AES-256-GCM under the tenant master key:
   $$C_{\text{DEK}} = \text{KMS.Encrypt}(K_{\text{tenant}}, K_{\text{user}})$$
   The wrapped key $C_{\text{DEK}}$ is stored in a dedicated, low-retention Key Store table:
   $$\text{KeyStore}(\text{tenant\_id}, \text{user\_id}, C_{\text{DEK}}, \text{created\_at})$$
4. **Payload Encryption (Facts & Personal Audit Trails)**:
   Any personal field $M$ (e.g., customer address in `MS-D19` or financial before/after delta in `TA-D15`) is encrypted with AES-256-GCM using an authenticated initialization vector $\text{IV} \xleftarrow{\$} \{0,1\}^{96}$ and authenticated data $\text{AAD} = (\text{tenant\_id} \parallel \text{user\_id})$:
   $$C_{\text{payload}} = \text{AES-256-GCM-Encrypt}(K_{\text{user}}, \text{IV}, M, \text{AAD})$$

#### The Crypto-Shredding Proof
When a user deletion request is processed:
$$\text{DELETE FROM KeyStore WHERE tenant\_id} = T \text{ AND user\_id} = U;$$
The user key $K_{\text{user}}$ is eradicated from active storage. By the Shannon security theorem of symmetric ciphers under the Indistinguishability under Chosen Ciphertext Attack (IND-CCA2) assumption:
$$\forall \mathcal{A}, \quad \left| \mathbb{P}\left[ \mathcal{A}(C_{\text{payload}}, C_{\text{DEK}}) = M \right] - \frac{1}{|M|} \right| \le \text{negl}(\lambda)$$
Even if an attacker, rogue DBA, or restored 30-day-old backup snapshot possesses $C_{\text{payload}}$, the ciphertext is computationally indistinguishable from uniform random noise.

#### 1-Day Key Store Backup Retention (`CR-D13`)
To prevent old database backups from restoring the wrapped key $C_{\text{DEK}}$, the Key Store operates on an isolated backup schedule with a strict **24-hour backup expiration** (`CR-D13`). After 24 hours, deleted keys are permanently wiped from all physical media across the universe.

---

### Pillar 3: Segregated Token Vault Database (`DP-D5`)

The PII Token Vault (`SG-D4`) is strictly isolated from the operational database:
1. **Network & Instance Boundary**: Operates as a distinct Aurora PostgreSQL instance within a non-routable private subnet.
2. **Access Control Segregation**: The primary application database credentials have zero network access or database grants on the Token Vault database.
3. **Dedicated Vault Microservice**: Only the stateless Token Vault Gateway daemon possesses mutual TLS (mTLS) credentials to connect to the Vault DB.

---

## 3. Data Contracts & Execution Invariants

### 3.1 Envelope Key Management Contract

```python
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator

class UserKeyRecord(BaseModel):
    """
    Contract for user-level data encryption keys stored in the dedicated Key Store.
    Governs cryptographic shredding lifecycles.
    """
    tenant_id: str = Field(..., regex=r"^ten_[a-zA-Z0-9]{16}$", description="Tenant Identifier")
    user_id: str = Field(..., regex=r"^usr_[a-zA-Z0-9]{16}$", description="Unique User Identifier")
    wrapped_dek: bytes = Field(..., description="AES-GCM wrapped user key (under tenant KMS KEK)")
    dek_key_version: int = Field(default=1, description="Key rotation generation number")
    created_at_utc: datetime = Field(default_factory=datetime.utcnow)
    shredded_at_utc: Optional[datetime] = Field(None, description="Timestamp when key was destroyed")

class EncryptedPayloadEnvelope(BaseModel):
    """
    Serialized container for personal data fields in relational tables.
    """
    cipher_text: bytes = Field(..., description="AES-256-GCM ciphertext payload")
    iv: bytes = Field(..., min_length=12, max_length=12, description="96-bit AES-GCM Initialization Vector")
    auth_tag: bytes = Field(..., min_length=16, max_length=16, description="128-bit Authentication Tag")
    key_version: int = Field(default=1, description="Version of the DEK used for encryption")
    aad_metadata: str = Field(..., description="Associated Authenticated Data string binding context")

    @field_validator("iv")
    @classmethod
    def validate_iv_length(cls, v: bytes) -> bytes:
        if len(v) != 12:
            raise ValueError("Cryptographic invariant: AES-GCM IV must be exactly 96 bits (12 bytes)")
        return v
```

### 3.2 SQL Invariant: Forced RLS Definition

```sql
-- DDL Template for all operational tables holding tenant data
CREATE OR REPLACE FUNCTION verify_tenant_session() 
RETURNS void AS $$
BEGIN
    IF NULLIF(current_setting('app.current_tenant_id', true), '') IS NULL THEN
        RAISE EXCEPTION 'CRITICAL SECURITY VIOLATION: Transaction executed without bound app.current_tenant_id';
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Apply to LangGraph checkpoints table
ALTER TABLE langgraph_checkpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE langgraph_checkpoints FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_checkpoints ON langgraph_checkpoints
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true));
```

---

## 4. Quantitative Failure Modes & Operational Risk Bounds

| Failure Mode ID | Sub-Component & Severity | Risk Classification | Empirical Trigger Condition | Detection Vector | Automated Mitigation & Architectural Enforcement |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **DP-FM-201** | Database Pool (`DP-D2`)<br>**CRITICAL** | Q1 Known Known (Security Vulnerability) | Application connection retrieved from pool executes query without executing `SET LOCAL app.current_tenant_id`. | Postgres `verify_tenant_session()` function triggers SQL exception `CRITICAL SECURITY VIOLATION`. | **Transaction Abort & Connection Ejection**: Query immediately fails; connection pooler terminates the poisoned connection and dispatches alert. |
| **DP-FM-202** | Schema Evolution (`DP-D2`)<br>**CRITICAL** | Q1 Known Known (Contract Breach) | Developer adds a new multi-tenant table via migration script but omits `FORCE ROW LEVEL SECURITY`. | Automated CI pipeline DDL migration linter (`TQ-ADP-02`) checks `pg_tables` and `pg_class`. | **Deployment Block**: CI fails migration build immediately if `relrowsecurity` or `relforcerowsecurity` is false for any tenant table. |
| **DP-FM-203** | Envelope Encryption (`DP-D4`)<br>**HIGH** | Q2 Known Unknown (Cost & Throughput) | High turn concurrency exhausts Cloud KMS cryptographic API quotas during DEK unwrap operations. | KMS client emits `ThrottlingException` / HTTP 429; unwrapping latency $p99 > 150\text{ms}$. | **LRU In-Memory DEK Caching (`CR-ADP-05`)**: Unwrapped $K_{\text{user}}$ cached in memory with a strictly bounded 5-minute TTL; keys purged on user deletion signal. |
| **DP-FM-204** | Token Vault (`DP-D5`)<br>**HIGH** | Q3 Unknown Known (Tacit Convention) | Database operator creates cross-database foreign data wrapper (FDW) between main DB and Vault DB for reporting. | Audit log inspection on PostgreSQL extensions detects unauthorized `postgres_fdw` installation. | **IAM Hard Restriction & Engine Lock**: Dedicated Vault RDS cluster parameters disable untrusted extensions; IAM forbids shared administrative roles. |
| **DP-FM-205** | Backup Restoration (`DP-D4`, `DP-D9`)<br>**CRITICAL** | Q4 Unknown Unknown (Resurrection Risk) | Database restored from a 30-day-old backup snapshot resurrects rows of erased users. | Live audit reconciler detects restored customer records whose user ID is marked as erased in the ledger. | **Cryptographic Invalidation Guarantee**: Although database rows reappear, their $K_{\text{user}}$ does not exist in the Key Store (1-day backup retention); decryption fails permanently. |

---

## 5. Closed-Loop Architectural Feedback

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│             MULTI-TENANT ISOLATION & CRYPTO-INTEGRITY OBSERVABILITY ENGINE                       │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

        Application Query Dispatch
                     │
                     ▼
      ┌───────────────────────────────┐
      │ RLS Session Context Checker   │─────► [Metric: rls_missing_context_errors_total]
      │ (PostgreSQL Function)         │       Target: Strict 0 (P0 Paging on > 0)
      └──────────────┬────────────────┘
                     │
                     ▼
      ┌───────────────────────────────┐
      │ Key Store Envelope Resolver   │─────► [Metric: dek_cache_hit_ratio]
      │ (In-Memory LRU Cache)         │       Target: > 92% (Minimizes KMS calls)
      └──────────────┬────────────────┘
                     │
                     ├──────────────────────────────────────────────┐
                     ▼                                              ▼
      ┌───────────────────────────────┐              ┌───────────────────────────────┐
      │ Decryption Success Pipeline   │              │ User Erasure / Shred Signal   │
      └──────────────┬────────────────┘              └──────────────┬────────────────┘
                     │                                              │
                     ▼                                              ▼
      [Metric: decryption_failures]                  ┌───────────────────────────────┐
      Target: 0 for active users;                     │ Evict DEK from LRU Cache +    │
      > 0 expected during restore drill              │ Delete KeyStore DB Record     │
      of erased historical records                   └───────────────────────────────┘
```

### Telemetry & Operational SLOs
1. **RLS Context Violation Rate**:
   - Metric: `db_rls_violation_attempts_total{tenant_id}`
   - Target: **Strictly 0**. Any attempt triggers immediate security audit and worker pod isolation.
2. **KMS Envelope Decryption Latency**:
   - Metric: `kms_dek_unwrap_duration_seconds`
   - SLO: $p95 < 25\text{ms}$, $p99 < 80\text{ms}$.
3. **DEK Cache Hit Ratio**:
   - Metric: `crypto_dek_cache_hits / (crypto_dek_cache_hits + crypto_dek_cache_misses)`
   - Target: $\ge 0.90$. Bounds KMS API expenditures (`CR-D10`).
4. **Crypto-Shredding Verification Latency**:
   - Time from erasure command receipt to key eradication: $< 200\text{ms}$.

---

## 6. Genesis Implementation Directive & Verification Protocol

### 6.1 Session Setup Directive in SQLAlchemy / AsyncPG Connection Lifecycle

```python
from contextlib import asynccontextmanager
from typing import AsyncGenerator
import asyncpg

class TenantBoundSessionManager:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @asynccontextmanager
    async def acquire_tenant_connection(self, tenant_id: str) -> AsyncGenerator[asyncpg.Connection, None]:
        """
        Guarantees that every database transaction acquired from the pool has
        SET LOCAL app.current_tenant_id bound before any application query executes.
        """
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                # Enforce tenant context in the transaction
                await connection.execute(
                    "SELECT set_config('app.current_tenant_id', $1, true);",
                    tenant_id
                )
                try:
                    yield connection
                finally:
                    # Transaction commit or rollback automatically clears LOCAL configuration
                    pass
```

### 6.2 Verification Checklist & Integration Tests

```bash
# 1. Verify RLS Cross-Tenant Leakage Prevention
pytest tests/persistence/test_rls_isolation.py -k "test_cross_tenant_query_returns_empty"

# Expected Output:
# PASS: Query executed with tenant_id="ten_01" returns 0 records for data belonging to "ten_02".
# PASS: Query executed without setting app.current_tenant_id raises SecurityException.

# 2. Verify Crypto-Shredding Irreversibility
pytest tests/persistence/test_crypto_shredding.py -k "test_deleted_dek_renders_facts_unreadable"

# Expected Output:
# PASS: Payload successfully decrypts with active DEK.
# PASS: After delete_user_dek(user_id), AES-GCM decryption raises InvalidTag / KeyNotFoundError.
```

---

## 7. Trade-Off Analysis & Rejected Alternatives

| Dimension | Selected Paradigm (`DP-D2`, `DP-D4`, `DP-D5`) | Rejected Alternative A: Silo Tenancy (Database per Tenant) | Rejected Alternative B: Dedicated KMS Key per User |
| :--- | :--- | :--- | :--- |
| **Operational & Hardware Cost** | **Lowest**: Pooled database shares connection pools, CPU, and RAM across thousands of tenants. | **Extreme**: Provisioning hundreds of RDS instances multiplies fixed compute costs ($>\$150\text{k}/\text{month}$). | **Prohibitive**: Direct KMS key per user costs $\$1.00/\text{month}$ per user, bankrupting consumer-scale support models. |
| **Isolation Strength** | **Absolute (Engine Enforced)**: PostgreSQL Forced RLS provides kernel-level filtering independent of app code. | **Absolute (Physical)**: Physical hardware separation, but connection management is unscalable. | **Identical**: Cryptographic strength is identical to hierarchical envelope keys. |
| **Schema Migration Agility** | **High**: One unified schema migration applies atomically to all tenants in a single deployment (`DL-ADP-04`). | **Unmanageable**: Migrating thousands of individual database schemas leads to migration drift and deployment failures. | **N/A**: Relates purely to encryption key management. |
| **Backup Erasure Defensibility** | **Complete**: Deleting the user DEK crypto-shreds all personal data in 35-day backup files without modifying the backup. | **None**: Live database deletion leaves user personal data intact inside un-editable database backup images. | **Complete**: But hits AWS account KMS key quotas ($10,000$ default) almost immediately. |

---

## 8. Formal References & Literature Grounding

1. **Barker, E. (2020).** *Recommendation for Key Management: Part 1 – General*. National Institute of Standards and Technology (NIST) Special Publication 800-57 Part 1, Revision 5. *(Theoretical specification for hierarchical cryptographic key wrapping and crypto-shredding).*
2. **Dworkin, M. (2007).** *Recommendation for Block Cipher Modes of Operation: Galois/Counter Mode (GCM) and GMAC*. NIST Special Publication 800-38D. *(Mathematical standard for authenticated encryption with associated data [AEAD] preventing ciphertext tampering).*
3. **Richardson, C. (2018).** *Microservices Patterns: With Examples in Java*. Manning Publications. *(Multi-tenant data isolation patterns and connection pooling invariants).*
4. **Amazon Web Services. (2021).** *AWS SaaS Lens: Multi-Tenant Data Isolation*. AWS Well-Architected Framework Whitepaper. *(Comparative analysis of Pool vs. Bridge vs. Silo database isolation models).*
5. **European Union General Data Protection Regulation (GDPR). (2016).** *Regulation (EU) 2016/679: Article 17 (Right to erasure / "right to be forgotten")*. *(Legal requirement establishing that cryptographic erasure meets regulatory standards when backup destruction is unfeasible).*
