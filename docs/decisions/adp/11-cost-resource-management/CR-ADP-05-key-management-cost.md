# CR-ADP-05: Key-Management Cost & Envelope Crypto-Shredding (Per-Tenant KMS Keys, Ephemeral DEK Stores & 24-Hour Backup Isolation)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-03 *(Confirmed per CR-D10 Envelope Encryption revising DP-D4 DP-KU1, CR-D13 Separate Key Store with 1-Day Backups UU1 & TA-D15 Cryptographic Erasure)*
- **Deciders**: Architecture Team, Chief Information Security Officer (CISO), Principal Data Architect, Lead FinOps Engineer
- **Component**: `[11] Cost & Resource Management` (`Component [ 11 ]`)
- **Reasoning Source**: `checkpoint.md` §15 · Diagram: `LLD - [11] Cost & Resource Management`
- **Decisions Covered**:
  - `CR-D10`: Envelope Encryption Architecture (Revising `DP-D4`) — Replaces the economically unsustainable model of provisioning individual hardware KMS master keys per end-user ($DP\text{ }KU1$) with hierarchical two-tier envelope encryption: data is encrypted under an ephemeral per-user Data Encryption Key (DEK), which is wrapped and stored under a dedicated per-tenant Key Encryption Key (KEK) managed in cloud KMS; eliminates cloud KMS quota bottlenecks while preserving tenant-level hardware root-of-trust
  - `CR-D13`: Isolated DEK Store with 24-Hour Backup Lifecycle — Wrapped per-user data keys (DEKs) are stored in a dedicated, isolated regional key-value store separated from primary PostgreSQL application tables; backup retention for the DEK store is strictly constrained to 24 hours ($UU1$); guarantees that upon a GDPR Article 17 erasure request (`MS-D14`), shredding the user's DEK renders encrypted fields permanently unrecoverable from standard 35-day database backups (`DP-D9`) after at most one day
- **Related Architectural Decision Points**:
  - [`DP-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/07-data-persistence/DP-ADP-02-tenant-isolation-encryption.md): Tenant Isolation & Encryption *(Database Row-Level Security & Cryptography)*
  - [`DP-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/07-data-persistence/DP-ADP-05-erasure-backups-restore.md): Erasure, Backups & Restore *(35-Day Database Backups & Fan-Out)*
  - [`MS-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/03-memory-state/MS-ADP-05-retention-erasure.md): Retention & Erasure *(Erasure Inventory Coverage)*
  - [`TA-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/04-tools-actions/TA-ADP-05-transactional-integrity-audit.md): Transactional Integrity & Audit *(Crypto-Shredding Audit Logs)*
  - [`RP-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/10-reliability-performance-scale/RP-ADP-04-disaster-recovery-regions.md): Disaster Recovery *(Key Store Inclusion in Monthly DR Drills)*

---

## 1. Context & Problem Statement

Enforcing individual customer data privacy and GDPR Article 17 "Right to Erasure" at cloud scale presents profound cryptographic and economic tensions:
1. **The Cloud KMS Financial & Quota Ceiling ($DP\text{ }KU1$)**:
   - Initial naive designs (`DP-D4` original formulation) proposed provisioning an independent Hardware Security Module (HSM) Customer Master Key (CMK) in AWS KMS / GCP Cloud KMS for every registered end-user.
   - Cloud KMS providers charge $\$1.00$ per key per month and enforce hard account quota ceilings (typically $10,000$ to $50,000$ active CMKs). An enterprise SaaS agent supporting $1,500,000$ customer profiles would incur $\$1.5\text{M}$ in fixed monthly KMS fees alone, causing immediate financial insolvency.
2. **The Backup Crypto-Shredding Dilemma ($UU1$, `TA-D15`, `DP-D9`)**:
   - To comply with disaster recovery standards, PostgreSQL enterprise databases maintain 35-day automated point-in-time recovery (PITR) backups (`DP-D9`).
   - If per-user data encryption keys are stored alongside encrypted records in primary PostgreSQL tables, a GDPR deletion request deletes the key from live tables, but the key remains fully preserved in database backup snapshots for 35 days.
   - An administrator restoring a backup could unwrap the archived keys using the surviving tenant KMS master key, rendering deleted customer PII readable again and violating GDPR Art. 17 compliance.

### The Core Architectural Question
> **How do we design an envelope encryption architecture that bounds KMS infrastructure costs to predictable per-tenant constants while guaranteeing that per-user cryptographic shredding takes permanent effect across all disaster recovery backups within 24 hours?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `CR-D10` and `CR-D13` establish the **Two-Tier Envelope Encryption and Ephemeral DEK Store Architecture**, revising `DP-D4` and resolving $DP\text{ }KU1$ and $UU1$.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   ENVELOPE ENCRYPTION & DEK ISOLATION ARCHITECTURE (CR-D10, CR-D13)              │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                                    DATA WRITE PIPELINE (User PII / Audit Log)
                                                        │
                                                        ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 1. DATA ENCRYPTION KEY (DEK) GENERATION                                                          │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Ephemeral AES-256-GCM Symmetric Key: $\text{DEK}_u \leftarrow \text{CSPRNG}(256\text{ bits})$  │
│ Ciphertext: $C = \text{AES-GCM-Encrypt}(\text{DEK}_u, \text{Plaintext})$                         │
└─────────────────────────────────────────────────┬────────────────────────────────────────────────┘
                                                  │
                                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 2. KMS KEY ENCRYPTION KEY (KEK) WRAPPING (CR-D10)                                                │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Request Cloud KMS: `kms:Encrypt(KeyId=KEK_Tenant, Plaintext=DEK_u)`                              │
│ • Exactly ONE Cloud KMS Master Key per Enterprise Tenant ($\approx \$1.00/\text{tenant}/\text{mo}$)│
│ • Wrapped DEK: $W = \text{KMS-Wrap}(\text{KEK}_T, \text{DEK}_u)$                                 │
└───────────────────────┬─────────────────────────────────────────────────┬────────────────────────┘
                        │                                                 │
                        ▼                                                 ▼
┌───────────────────────────────────────────────┐ ┌────────────────────────────────────────────────┐
│ STORE A: PRIMARY DATABASE (PostgreSQL DP-D1)  │ │ STORE B: ISOLATED DEK STORE (CR-D13)           │
├───────────────────────────────────────────────┤ ├────────────────────────────────────────────────┤
│ Stores:                                       │ │ Stores:                                        │
│ • Encrypted Ciphertext $C$                    │ │ • Mapping: $\text{UserUUID} \to W$ (Wrapped Key)│
│ • Zero Key Material Stored Here               │ │ • Independent Regional KV Store (Postgres/Redis│
│ • 35-Day Automated Backup Retention (`DP-D9`) │ │ • STRICT 24-HOUR BACKUP RETENTION (CR-D13, UU1) │
└───────────────────────────────────────────────┘ └────────────────────────────────────────────────┘
                                                                  │
                                                                  ▼ (GDPR Deletion Request MS-D14)
                                                  ┌────────────────────────────────────────────────┐
                                                  │ 3. CRYPTOGRAPHIC SHREDDING (TA-D15, DP-D13)    │
                                                  ├────────────────────────────────────────────────┤
                                                  │ • Live Purge: `DELETE FROM dek_store WHERE ...`│
                                                  │ • After 24 Hours: Backups expire & purge       │
                                                  │ • Outcome: Ciphertext in 35-day DB backups     │
                                                  │   is permanently mathematically irrecoverable! │
                                                  └────────────────────────────────────────────────┘
```

---

### Pillar 1: Two-Tier Envelope Encryption Hierarchy (`CR-D10`)

`CR-D10` formally supersedes the per-user KMS CMK design (`DP-D4`):
1. **Tier 1: Tenant Key Encryption Key (KEK)**:
   - Rooted in dedicated regional Cloud KMS HSMs (AWS KMS / GCP Cloud KMS).
   - Cardinality: Exactly $1$ KMS key per enterprise tenant ($\mathcal{O}(\text{Tenants})$, e.g., $200$ keys for $200$ tenants $\approx \$200/\text{month}$).
   - Governed by strict IAM policies: rotation scheduled annually (`DL-ADP-05`).
2. **Tier 2: User Data Encryption Key (DEK)**:
   - Ephemeral 256-bit symmetric keys generated locally via cryptographically secure pseudo-random number generators (CSPRNG).
   - Encrypts user-specific PII, long-term memory facts (`MS-D3`), and sensitive audit log fields (`TA-D15`).
   - Encrypted locally under the tenant's KEK:
     $$W_u = \text{KMS}_{\text{KEK}_T}(\text{DEK}_u)$$

---

### Pillar 2: Isolated DEK Storage & 24-Hour Backup Purge (`CR-D13`, $UU1$)

To reconcile crypto-shredding with long-term database disaster recovery backups:
1. **Physical & Logical Separation**:
   - Wrapped keys $W_u$ are strictly forbidden from PostgreSQL application tables.
   - Keys reside in a dedicated regional **Key Store** (a hardened, encrypted key-value database deployed per region, `DP-D10`).
2. **24-Hour Backup Lifecycle ($UU1$)**:
   - While primary PostgreSQL application data utilizes 35-day automated snapshots (`DP-D9`), the Key Store backup policy is strictly capped at **24 hours**.
   - Point-in-time recovery for the Key Store is restricted to a 1-day rolling window.
3. **Cryptographic Shredding Guarantee**:
   - When a user deletion request arrives via the Temporal erasure fan-out (`DP-D13`), the system immediately deletes the user's entry from the Key Store.
   - Within $\le 24\text{ hours}$, all Key Store backup snapshots containing that key age out and are deleted.
   - Even if an attacker or administrator subsequently restores a 30-day-old PostgreSQL database backup, the ciphertext $C$ cannot be decrypted because the required $\text{DEK}_u$ no longer exists anywhere in the universe ($UU1$ mitigated).

---

### Pillar 3: Disaster Recovery Drills & Failure Trade-Offs (`RP-D11`)

The isolation of the Key Store introduces operational resilience invariants:
1. **DR Drill Inclusion (`RP-D11`)**:
   - The monthly disaster recovery drill must restore the Key Store alongside primary PostgreSQL and Qdrant clusters.
2. **Owned Loss Risk**:
   - In the catastrophic event of a total Key Store loss requiring snapshot restoration, at most **1 day** of newly created user keys could be lost (fields encrypted within that 24-hour window become unreadable). This residual risk is explicitly accepted to satisfy GDPR cryptographic erasure.

---

## 3. Technical Implementation & Genesis Contracts

```python
"""
core/security/envelope_crypto.py
Pydantic v2 schemas and Envelope Encryption Manager with Isolated DEK Storage.
"""

import os
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class EncryptedPayload(BaseModel):
    ciphertext_hex: str
    nonce_hex: str
    tenant_id: str
    user_id: str


class WrappedKeyRecord(BaseModel):
    user_id: str
    tenant_id: str
    wrapped_dek_hex: str
    created_at_utc: str
    key_version: int = 1


class EnvelopeCryptoManager:
    """
    Executes Two-Tier Envelope Encryption and manages isolated DEK lifecycle (CR-D10, CR-D13).
    """

    def __init__(self, kms_client: Any, key_store_client: Any):
        self.kms_client = kms_client
        self.key_store = key_store_client  # Isolated Key Store with 24h backups (CR-D13)

    def _get_or_create_user_dek(self, tenant_id: str, user_id: str) -> bytes:
        """
        Retrieves existing DEK or generates and wraps a new one under tenant KEK.
        """
        key_record = self.key_store.get(f"dek:{tenant_id}:{user_id}")
        
        if key_record:
            wrapped_dek = bytes.fromhex(key_record["wrapped_dek_hex"])
            # Unwrap DEK via Cloud KMS using tenant KEK (CR-D10)
            dek = self.kms_client.decrypt(
                KeyId=f"alias/tenant-{tenant_id}",
                CiphertextBlob=wrapped_dek
            )["Plaintext"]
            return dek

        # Generate fresh 256-bit DEK
        new_dek = AESGCM.generate_key(bit_length=256)
        
        # Wrap DEK under Tenant KEK
        wrapped_blob = self.kms_client.encrypt(
            KeyId=f"alias/tenant-{tenant_id}",
            Plaintext=new_dek
        )["CiphertextBlob"]

        # Store wrapped key exclusively in isolated Key Store (CR-D13)
        self.key_store.set(
            f"dek:{tenant_id}:{user_id}",
            {
                "user_id": user_id,
                "tenant_id": tenant_id,
                "wrapped_dek_hex": wrapped_blob.hex(),
                "created_at_utc": "2026-10-03T12:00:00Z",
                "key_version": 1
            }
        )
        return new_dek

    def encrypt_user_data(self, tenant_id: str, user_id: str, plaintext: str) -> EncryptedPayload:
        """
        Encrypts plaintext with user DEK using AES-256-GCM.
        """
        dek = self._get_or_create_user_dek(tenant_id, user_id)
        aesgcm = AESGCM(dek)
        nonce = os.urandom(12)  # 96-bit standard nonce
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)

        return EncryptedPayload(
            ciphertext_hex=ciphertext.hex(),
            nonce_hex=nonce.hex(),
            tenant_id=tenant_id,
            user_id=user_id
        )

    def decrypt_user_data(self, payload: EncryptedPayload) -> Optional[str]:
        """
        Decrypts ciphertext. Returns None if key has been crypto-shredded (TA-D15).
        """
        key_record = self.key_store.get(f"dek:{payload.tenant_id}:{payload.user_id}")
        if not key_record:
            # Key has been permanently erased/shredded!
            return None

        wrapped_dek = bytes.fromhex(key_record["wrapped_dek_hex"])
        try:
            dek = self.kms_client.decrypt(
                KeyId=f"alias/tenant-{payload.tenant_id}",
                CiphertextBlob=wrapped_dek
            )["Plaintext"]
            aesgcm = AESGCM(dek)
            plaintext_bytes = aesgcm.decrypt(
                bytes.fromhex(payload.nonce_hex),
                bytes.fromhex(payload.ciphertext_hex),
                None
            )
            return plaintext_bytes.decode("utf-8")
        except Exception:
            return None

    def crypto_shred_user(self, tenant_id: str, user_id: str) -> bool:
        """
        Permanently purges user DEK from Key Store.
        Survives in backups for at most 24 hours (CR-D13, UU1).
        """
        return bool(self.key_store.delete(f"dek:{tenant_id}:{user_id}"))
```

---

## 4. Failure Modes & Mitigation Matrix

| Failure ID | Sub-Component | Failure Mode Description | Root Cause | Effect on System | Architectural Mitigation (`CR-D10`, `CR-D13`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **$DP\text{ }KU1$** | Cost Optimization | Millions in monthly KMS bills | Individual Cloud KMS CMK created per customer | Financial insolvency and cloud account quota breaches | `CR-D10` implements envelope encryption; exactly one Cloud KMS KEK per enterprise tenant |
| **$UU1$** | Cost Optimization | Erased user PII readable from backups | Wrapped DEK stored in PostgreSQL with 35-day backup retention | Restoring backup allows unwrap via KMS, violating GDPR Art. 17 | `CR-D13` isolates DEKs in dedicated key store with strict 24-hour backup retention |
| **$KK1$** | Key Storage | Key store outage blocks data decryption | Redis/Postgres key store cluster unreachable | Inability to serve customer turns requiring PII | High-availability multi-AZ deployment in region; fallback degrades per `SG-D18` |
| **$KU1$** | Key Storage | Loss of recent keys during key store restore | Disaster requires restoring key store from 24h backup | Data encrypted within last 24h becomes permanently unreadable | Owned engineering risk; mitigated by multi-AZ replication to minimize restore necessity |
| **$UK1$** | Cost Optimization | Orphaned DEKs persist after tenant offboarding | Tenant deleted but DEK records remain in key store | Wasted key store capacity | Tenant offboarding workflow cascades deletion across both Cloud KMS KEK and all tenant DEKs |

---

## 5. Closed-Loop Telemetry & Verification Directives

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   ENVELOPE CRYPTO TELEMETRY & AUDIT PIPELINE                                     │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Encryption Operation ──► [ KMS API Call Counter ] ──► Metric: `crypto.kms.wrap_unwrap_count`
                                   │
                                   ├──► [ Key Store Ops ] ──► Metric: `crypto.keystore.operations`
                                   │
                                   └──► [ Crypto-Shred Audit ] ──► Append-Only Log:
                                                                   `crypto.shred.completed`
```

### 1. Prometheus Telemetry Indicators
- `crypto.kms.active_keks_total`: Number of active cloud KMS keys (Target: Equals active tenant count).
- `crypto.keystore.active_deks_total`: Gauge tracking total registered user DEKs.
- `crypto.shred.requests_total`: Counter tracking executed GDPR crypto-shred operations.
- `crypto.keystore.backup_age_seconds`: Age of oldest active key store backup snapshot (Must be $\le 86,400\text{s}$).

### 2. Audit Trail Events (`TA-ADP-05`)
- `crypto.shred.executed`: Logged with Tenant ID, User UUID, UTC timestamp, and Key Store confirmation hash. Zero plaintext or key bytes are logged.

---

## 6. Alternatives Considered & Trade-Off Analysis

| Architectural Alternative | Technical Mechanism | Why Rejected / Trade-Off Analysis |
| :--- | :--- | :--- |
| **Cloud KMS Key Per User (Original DP-D4)** | Provision dedicated AWS/GCP KMS key for every user | **Rejected ($DP\text{ }KU1$)**: Costs $\$1.00$/user/month ($\$1.5\text{M}$/mo for $1.5\text{M}$ users); immediately exhausts cloud provider account key limits. |
| **DEKs Stored in Primary PostgreSQL Tables** | Store wrapped DEKs in a `user_keys` table in PostgreSQL | **Rejected ($UU1$)**: 35-day database backups preserve deleted keys; restoring a backup resurrects shredded PII, breaching GDPR Art. 17. |
| **Zero Key Store Backups (Option B)** | Pure in-memory replication across AZs with zero backups | **Rejected**: A correlated cluster corruption permanently destroys all customer DEKs, resulting in irreversible, unrecoverable data loss across the entire platform. |
| **Shared Tenant DEK (No Per-User Keys)** | Encrypt all tenant data under a single tenant key | **Rejected**: Eliminates cryptographic erasure capability (`TA-D15`); GDPR erasure would require rewriting and vacuuming gigabytes of PostgreSQL tables instead of shredding one key. |

---

## 7. References & Academic Foundations

1. **NIST Special Publication 800-57, Part 1, Rev. 5.** (2020). *Recommendation for Key Management: General.* National Institute of Standards and Technology.
2. **Barker, E.** (2016). *Recommendation for Key Management: Part 2 – Best Practices for Key Management Organizations.* NIST SP 800-57 Part 2.
3. **AWS Security Best Practices.** (2024). *Envelope Encryption Concepts and KMS Key Hierarchy.* AWS Documentation.
4. **GDPR Article 17.** (2016). *Right to Erasure ('Right to be Forgotten').* Cryptographic Shredding Compliance Guidelines.
5. **NIST Special Publication 800-88, Rev. 1.** (2014). *Guidelines for Media Sanitization.* Cryptographic Erase (CE) Techniques.
