# DL-ADP-05: Secrets Custody & Cryptographic Key Governance (Regional Secrets Managers, Scheduled Credential Rotation & Static Token Salt Custody)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-06 *(Confirmed per DL-D7 Regional Secrets Rotation KK2, DL-D8 Non-Rotated Global Token Key Salt SG-D5 & UU5 Accepted Key Risk)*
- **Deciders**: Architecture Team, Chief Information Security Officer (CISO), Principal Security Engineer, Cloud Platform Lead
- **Component**: `[14] Deployment & LLMOps` (`Component [ 14 ]`)
- **Reasoning Source**: `checkpoint.md` §18 · Diagram: `LLD - [14] Deployment & LLMOps`
- **Decisions Covered**:
  - `DL-D7`: Regional Secrets Management & Automated Credential Rotation — Operational secrets (PostgreSQL database credentials, Redis auth tokens, Temporal mTLS certificates, commercial LLM provider API keys, and `TYPESAFE_API_KEY`) are managed via dedicated regional cloud secrets managers (AWS Secrets Manager / Azure Key Vault) deployed in each sovereign cloud region; enforces automated 90-day scheduled rotation ($KK2$); running Kubernetes pods refresh credentials via dynamic reload signals without downtime
  - `DL-D8`: Custody of the Static Shared Token Key — Establishes explicit cryptographic key custody for the global HMAC secret key utilized in reversible deterministic PII tokenization (`SG-D4`, `SG-D5`); the secret key is provisioned identically in each region's secrets manager and is **intentionally never rotated** ($UU5$ accepted engineering risk); rotating the global token key would alter token hashes globally, permanently breaking vector index joins, Qdrant embeddings, database foreign keys, and audit log cross-references; access to the key is restricted to the isolated Token Vault pod via strict hardware KMS IAM boundaries
- **Related Architectural Decision Points**:
  - [`SG-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/06-safety-security-governance/SG-ADP-02-pii-protection.md): PII Protection *(Reversible Tokenization & Global Deterministic Tokens)*
  - [`DP-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/07-data-persistence/DP-ADP-02-tenant-isolation-encryption.md): Tenant Isolation & Encryption *(Isolated Vault Architecture)*
  - [`DL-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/14-deployment-llmops/DL-ADP-01-environments-infrastructure.md): Environments & Infrastructure *(Regional Cloud Topologies)*
  - [`TA-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/04-tools-actions/TA-ADP-04-execution-credentials-isolation.md): Execution Credentials Isolation *(Scoped Service Accounts)*

---

## 1. Context & Problem Statement

Managing credentials and cryptographic secrets across distributed, multi-region agent platforms involves deep architectural trade-offs:
1. **The Credential Sprawl & Leakage Vector ($KK2$)**:
   - In modern multi-system agent platforms, microservices interact with heterogeneous external APIs (OpenAI, Anthropic, AWS Bedrock, Zendesk, Salesforce, Stripe).
   - Ingesting secrets via raw CI environment variables or hardcoded configuration files exposes API tokens in build logs, container image layers, and developer workstations ($KK2$). Compromised credentials result in massive financial theft and data breach liabilities.
2. **The Deterministic Token Rotation Paradox ($UU5$, `SG-D5`)**:
   - Standard security best practices mandate scheduled 90-day rotation for all cryptographic keys.
   - However, our privacy architecture relies on **Global Deterministic PII Tokens** (`SG-D5`) to replace customer names, emails, and account IDs with pseudonymous HMAC tokens (e.g., `HMAC-SHA256("john.doe@acme.com", Key) = tok_usr_8f1a...`).
   - These tokens reside inside millions of archived customer conversations, long-term memory facts (`MS-D2`), and Qdrant vector index chunks (`KR-D4`).
   - If the global token key is rotated, identical customer entities generate completely different tokens. Existing vector indices become unsearchable, memory cross-references break, and multi-turn conversations lose all entity coherence ($UU5$).

### The Core Architectural Question
> **How do we engineer a secure, automated secrets lifecycle that rotates operational credentials without downtime, while maintaining absolute cryptographic immutability for the global deterministic tokenization key?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `DL-D7` and `DL-D8` establish the **Regional Secrets Manager and Static Token Salt Custody Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   SECRETS CUSTODY & TOKEN KEY ARCHITECTURE (DL-D7, DL-D8)                        │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                                    REGIONAL SECRETS MANAGEMENT LAYER
                                                   │
                     ┌─────────────────────────────┴─────────────────────────────┐
                     ▼                                                           ▼
┌───────────────────────────────────────────────┐ ┌────────────────────────────────────────────────┐
│ CLASS A: ROTATING OPERATIONAL SECRETS (DL-D7) │ │ CLASS B: STATIC DETERMINISTIC TOKEN KEY (DL-D8)│
├───────────────────────────────────────────────┤ ├────────────────────────────────────────────────┤
│ Secrets Managed in AWS Secrets Manager:       │ │ Cryptographic HMAC Key for SG-D5 Tokenization: │
│ • PostgreSQL App Credentials                  │ │ • Cardinality: Exactly ONE Key replicated to   │
│ • Commercial LLM API Keys (OpenAI, Anthropic) │ │   US and EU regional secrets managers          │
│ • Typesafe Jev API Key (`TYPESAFE_API_KEY`)   │ │ • ZERO SCHEDULED ROTATION (Accepted Risk UU5)  │
│ • Temporal mTLS Client Certificates           │ │ • Immutable Root-of-Trust: Guarantees token    │
│                                               │ │   stability across Qdrant, Memory, & Postgres  │
│ AUTOMATED 90-DAY SCHEDULED ROTATION:          │ │ STRICT ACCESS RESTRICTION:                     │
│ • AWS Lambda rotation functions update DB     │ │ • Accessible ONLY by isolated Vault Pod (DP-D5)│
│ • Pods reload credentials via SIGHUP signal   │ │ • Hardware KMS IAM boundary + CloudTrail alerts│
└───────────────────────────────────────────────┘ └────────────────────────────────────────────────┘
```

---

### Pillar 1: Regional Secrets Management & 90-Day Rotation (`DL-D7`, $KK2$)

Operational credentials follow zero-trust cloud security standards:
1. **Regional Cloud Secrets Store**:
   - AWS Secrets Manager / Azure Key Vault instances are deployed per sovereign region (`DP-D10`).
   - Container environments mount secrets dynamically at runtime using the Kubernetes Secrets Store CSI Driver; zero plaintext secrets are written to disk or container images.
2. **Scheduled Automated Rotation**:
   - Database passwords and internal service tokens rotate automatically every 90 days via automated cloud functions.
   - Services implement connection pool retry handlers that reload credentials upon authentication failures, enabling zero-downtime rotation without pod restarts.

---

### Pillar 2: Custody of the Static Shared Token Key (`DL-D8`, `SG-D5`, $UU5$)

To resolve the deterministic token rotation paradox:
1. **The Immutability Rationale ($UU5$)**:
   - `DL-D8` establishes that the secret HMAC key utilized for deterministic PII tokenization (`SG-D5`) **shall never be rotated**.
   - Preserves mathematical entity identity: `john.doe@acme.com` always maps to `tok_usr_8f1a...` across all years of operational history, ensuring that vector search, memory retrieval, and analytics remain fully functional.
2. **Compensating Security Controls ($UU5$ Mitigation)**:
   - Because the key is static, compromising it allows an attacker to compute tokens for guessed email addresses or names. To prevent unauthorized extraction:
     - **Micro-Segmentation**: The token key is accessible exclusively by the isolated **Token Vault Pod** (`DP-D5`). No orchestrator, LLM agent, or tool worker pod possesses IAM permissions to read the secret.
     - **Hardware HSM Root**: The key is stored in AWS KMS / Cloud HSM and decrypted only into the volatile memory of the Vault container.
     - **Audit Anomaly Alerts**: Any KMS `Decrypt` call on the token key originating outside the designated Vault Kubernetes service account triggers an immediate PagerDuty security alarm.

---

## 3. Technical Implementation & Genesis Contracts

```terraform
# infrastructure/terraform/modules/secrets/main.tf
# Terraform configuration for Regional Secrets Manager and Token Salt Custody (DL-D7, DL-D8).

variable "region" {
  type = string
}

# 1. Operational Rotating Secrets (DL-D7)
resource "aws_secretsmanager_secret" "operational_credentials" {
  name                    = "agent/operational-secrets-${var.region}"
  description             = "Rotating database, provider, and Jev API keys"
  kms_key_id              = aws_kms_key.regional_kms.arn
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_rotation" "db_rotation" {
  secret_id           = aws_secretsmanager_secret.operational_credentials.id
  rotation_lambda_arn = aws_lambda_function.secret_rotator.arn
  rotation_rules {
    automatically_after_days = 90
  }
}

# 2. Static Deterministic Token Key (DL-D8, SG-D5)
resource "aws_secretsmanager_secret" "static_token_key" {
  name                    = "agent/static-token-salt-global"
  description             = "Immutable HMAC key for deterministic PII tokenization. DO NOT ROTATE!"
  kms_key_id              = aws_kms_key.vault_kms.arn
  recovery_window_in_days = 30 # Protected from accidental deletion
}

# Strict IAM Policy: ONLY Token Vault Role can read the Static Token Key (DP-D5)
resource "aws_secretsmanager_secret_policy" "token_key_access_policy" {
  secret_arn = aws_secretsmanager_secret.static_token_key.arn
  policy     = jsonencode({
    Version   = "2012-10-17"
    Statement = [
      {
        Sid       = "RestrictToTokenVaultPodOnly"
        Effect    = "Allow"
        Principal = {
          AWS = aws_iam_role.token_vault_pod_role.arn
        }
        Action   = "secretsmanager:GetSecretValue"
        Resource = "*"
      }
    ]
  })
}
```

```python
"""
core/security/secrets_loader.py
Secure runtime secrets loader with dynamic in-memory caching (DL-D7).
"""

import os
from typing import Dict, Any, Optional
from pydantic import BaseModel


class OperationalSecrets(BaseModel):
    database_url: str
    typesafe_api_key: str
    anthropic_api_key: str
    openai_api_key: str
    redis_auth_token: str


class SecretsManagerClient:
    """
    Retrieves operational credentials dynamically from regional secrets manager (DL-D7).
    """

    def __init__(self, regional_client: Any):
        self.client = regional_client
        self._cached_secrets: Optional[OperationalSecrets] = None

    def get_operational_secrets(self, force_refresh: bool = False) -> OperationalSecrets:
        """
        Loads operational secrets into memory. Reloads upon rotation event.
        """
        if self._cached_secrets and not force_refresh:
            return self._cached_secrets

        raw_payload = self.client.get_secret_value(SecretId="agent/operational-secrets")
        self._cached_secrets = OperationalSecrets.model_validate_json(raw_payload)
        return self._cached_secrets
```

---

## 4. Failure Modes & Mitigation Matrix

| Failure ID | Sub-Component | Failure Mode Description | Root Cause | Effect on System | Architectural Mitigation (`DL-D7`, `DL-D8`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **$KK2$** | Secrets | Expired database credential breaks agent cluster | Secret rotated in database but application not updated | Cluster-wide 500 errors and connection pool failures | `DL-D7` connection pool handles retry with dynamic secrets cache refresh |
| **$UU5$** | Secrets | Compromised static token key allows entity inference | Attacker steals token salt from secrets manager | Attacker computes tokens for known customer emails | `DL-D8` restricts key access exclusively to isolated Vault pod via KMS IAM policy |
| **$DL-D8$** | Secrets | Accidental rotation of global token key destroys data | Well-meaning security engineer rotates static token key | Qdrant vector index search and long-term memory permanently severed | `DL-D8` disables rotation triggers; Terraform lifecycle blocks automated rotation |

---

## 5. Closed-Loop Telemetry & Verification Directives

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   SECRETS TELEMETRY & AUDIT PIPELINE                                             │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Secret Access Event ──► [ AWS CloudTrail / Audit Log ] ──► Metric: `secrets.access.rate`
                                  │
                                  ├──► [ IAM Policy Watcher ] ──► Alert: `secrets.unauthorized_attempt`
                                  │
                                  └──► [ 90d Rotation Monitor ] ──► Metric: `secrets.age_days`
```

### 1. Prometheus Telemetry Indicators
- `secrets.operational.age_days`: Gauge tracking days elapsed since last credential rotation.
- `secrets.token_key.access_events_total`: Counter tracking access to static token salt (Must strictly originate from Vault pod IP).
- `secrets.rotation.failures_total`: Counter tracking failed automated credential rotation routines.

---

## 6. Alternatives Considered & Trade-Off Analysis

| Architectural Alternative | Technical Mechanism | Why Rejected / Trade-Off Analysis |
| :--- | :--- | :--- |
| **Scheduled 90-Day Rotation for Token Salt** | Rotate the global deterministic token key every 90 days | **Rejected ($UU5$)**: Catastrophic data corruption; invalidates all historical vector indices, memory facts, and transcripts. |
| **Environment Variables in CI/CD (DL-F7(a))** | Inject secrets as plain environment variables in GitHub Actions | **Rejected ($KK2$)**: High leakage risk; secrets appear in container build layers and shell debugging logs. |
| **HashiCorp Vault per Region** | Deploy dedicated self-hosted HashiCorp Vault clusters in each region | **Rejected**: Massive operational maintenance overhead; cloud-native secrets managers provide equivalent security with zero maintenance. |

---

## 7. References & Academic Foundations

1. **NIST Special Publication 800-57, Part 1, Rev. 5.** (2020). *Recommendation for Key Management: General.* Section 5.3: Cryptographic Key Management.
2. **Center for Internet Security (CIS).** (2024). *CIS AWS Foundations Benchmark: Credential and Key Rotation Standards.*
3. **AWS Security Best Practices.** (2024). *Automating Secrets Rotation with AWS Secrets Manager.*
