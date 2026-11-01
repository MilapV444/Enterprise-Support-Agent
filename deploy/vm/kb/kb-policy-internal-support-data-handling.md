---
doc_id: kb-policy-internal-support-data-handling
title: Internal data handling policy for support staff: PII minimization and secret redaction
source_system: policies
source_kind: curated
audience: internal
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-09-26
intents: [GENERAL_INQUIRY, PASSWORD_RESET, TECHNICAL_OUTAGE]
test_case: none
---

# Internal data handling policy for support staff: PII minimization and secret redaction

## Core principles of support data handling (INTERNAL ONLY)

All Nimbus Support specialists, Site Reliability Engineers (SREs), and AI support pipelines must adhere to strict **Personal Data Minimization** and **Secret Zero-Persistence** standards when handling customer chats, diagnostic bundles, and resolved ticket write-ups. Because resolved ticket summaries (`source_kind: ticket`) are indexed into the internal RAG knowledge base to train and assist support agents, leaking raw customer PII or infrastructure secrets into ticket notes creates a severe compliance and security violation.

## Mandatory PII minimization and placeholder tokenization

### Rules for recording customer contact details in tickets and KB summaries

Support staff must never copy or store raw personal names, personal or corporate email addresses, phone numbers, physical home addresses, or payment card numbers inside ticket summaries, escalation notes, or internal Slack channels. When authoring or editing a ticket write-up, replace all personal identifiers with standardized angle-bracket placeholders:

- **Email Addresses:** Replace with `<EMAIL_1>`, `<EMAIL_2>`, etc.
- **Person Names:** Replace with `<NAME_1>`, `<NAME_2>`, etc.
- **Phone Numbers:** Replace with `<PHONE_1>`, `<PHONE_2>`, etc.
- **IP Addresses (End-User Home/Client IPs):** Replace with `<CLIENT_IP_1>` (internal RFC 1918 VPC CIDRs such as `10.42.16.0/24` may be retained for networking context).

Organizational tenant names (such as `Acme Retail`, `Globex Corp`, or `Initech Logistics`) and non-sensitive resource identifiers (such as cluster `db-prod-west` or instance `srv-alpha-12`) may be referenced in internal tickets, provided no live customer secrets or actual private billing ledger snapshots are embedded in shared training docs.

## Never paste customer secrets into tickets or chat transcripts

### Prohibited credential types

Support staff must **never** ask a customer to paste, and must **never** copy or store, any of the following sensitive secrets inside a ticket comment, chat message, or runbook note:

1. **Nimbus API Bearer Tokens and Webhook Secrets:** Strings starting with `nmb_live_`, `nmb_test_`, or `whsec_`.
2. **Database Passwords and Connection URIs:** PostgreSQL connection strings containing plaintext passwords (`postgresql://admin:SECRET@db-prod-west...`).
3. **SSH Private Keys and TLS Private Keys:** PEM blocks beginning with `-----BEGIN OPENSSH PRIVATE KEY-----` or `-----BEGIN RSA PRIVATE KEY-----`.
4. **SAML Signing Certificates / OIDC Client Secrets:** Identity Provider client secrets or raw bearer JWT assertions.
5. **Instance Root Passwords:** Temporary or rotated root passwords for instances such as `srv-alpha-12` (which must only be delivered via encrypted one-time Vault links `https://vault.nimbuscloud.example.com/v1/secret/once/...`).
6. **Retail Payment Card Data (PCI-DSS):** Primary Account Numbers (PAN), CVV/CVC codes, or magnetic stripe track data from Nimbus POS Gateway terminals.

## Using the Nimbus Redaction Tool (`nimbus-redact`)

If a customer inadvertently pastes a plaintext password, API token, private key, or credit card number into the web chat window or uploads an unredacted `.env` file or Kubernetes manifest:

1. **Immediate Secret Revocation:** Advise the customer that the exposed credential is compromised and must be rotated immediately (or revoke the `nmb_live_` token directly if the user is verified at Tier T2).
2. **Execute `nimbus-redact` on the Ticket Thread:** Run the internal CLI redaction utility within **15 minutes** of detection to scrub the secret from the primary chat database, Elasticsearch ticket index, and LLM context window:

```bash
# Scrub a specific message ID and purge cached RAG embeddings for the ticket
nimbus-redact purge-message \
  --ticket-id <TICKET_ID> \
  --message-id <MSG_ID> \
  --reason "CUSTOMER_PASTED_SECRET_OR_PII" \
  --purge-rag-cache
```

3. **Verify Redaction Output:** Confirm that the message body now displays `[REDACTED BY NIMBUS DLP - SECRET_SCRUBBED]` and that the audit log records the `nimbus-redact` execution ID.
