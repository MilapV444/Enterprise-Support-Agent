---
doc_id: kb-policy-security-incident-notification
title: Customer-facing security incident response and breach notification policy
source_system: policies
source_kind: curated
audience: customer_visible
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-09-20
intents: [TECHNICAL_OUTAGE, GENERAL_INQUIRY]
test_case: none
---

# Customer-facing security incident response and breach notification policy

## Commitment to transparent security incident communication

Nimbus Systems, Inc. maintains a 24/7 Security Operations Center (SOC) and Computer Security Incident Response Team (CSIRT) monitoring both the US (`us-east-1`, `us-west-2`) and EU (`eu-central-1`, `eu-west-1`) realms of **Nimbus Cloud Platform**. This policy outlines our contractual commitments for notifying affected business tenants in the event of a confirmed **Security Incident** or **Personal Data Breach**, in alignment with GDPR Articles 33 and 34, ISO/IEC 27001, and SOC 2 Type II standards.

## Definition of a reportable Security Incident

A reportable **Security Incident** under the Nimbus Cloud Platform Master Subscription Agreement (MSA) and Data Processing Addendum (DPA) is any confirmed breach of Nimbus Systems' physical, hypervisor, network, or control-plane security controls that leads to the accidental or unlawful destruction, loss, alteration, unauthorized disclosure of, or unauthorized access to **Customer Content** (data stored in Nimbus DB, Nimbus Run, Nimbus Net, or Nimbus POS Gateway) or tenant authentication credentials.

Unsuccessful security events—such as blocked port scans, mitigated DDoS floods, rejected brute-force login attempts (`AUTH_ACCOUNT_LOCKED_TEMP`), or automated firewall blocks that do not compromise tenant data—do not constitute a reportable Security Incident.

## Contractual breach notification timelines

### 24-hour Enterprise SLA and 48-hour platform-wide guarantee (well inside GDPR 72 hours)

Upon confirming that a Security Incident has impacted one or more customer tenants, Nimbus CSIRT notifies affected customers without undue delay and strictly within the following contractual ceilings:

- **Enterprise Plan Tenants:** Direct written notification within **24 hours** of confirmation, delivered via encrypted email to the `Tenant Owner` and designated Security Contact (`<EMAIL_1>`), plus direct outreach from the tenant's **Named Support Manager**.
- **Starter and Growth Plan Tenants:** Direct written notification within **48 hours** of confirmation (guaranteeing that EU Data Controllers have ample lead time to meet their own **72-hour regulatory notification window** under GDPR Article 33).

### Information included in a Nimbus Security Incident Notice

Every official Security Incident Notice delivered by Nimbus CSIRT includes:

1. **Incident Identifier and Timeline:** Unique tracking ID (`SEC-INC-YYYY-NNNN`), UTC timestamp of discovery, and estimated UTC window of exposure.
2. **Scope of Affected Resources:** Specific Tenant IDs (`tnt_...`), regional realms, and resource identifiers (such as specific Nimbus DB clusters or service account tokens) impacted.
3. **Nature of the Data Affected:** Categories of Customer Content or metadata involved and whether encryption keys were affected.
4. **Containment and Remediation Actions Taken:** Immediate steps executed by Nimbus CSIRT (for example, rotating regional control-plane signing keys or isolating a compromised host).
5. **Recommended Customer Actions:** Specific remediation steps the customer should take (such as rotating API bearer tokens `nmb_live_...` or reviewing audit logs).

## How customers should report a suspected security vulnerability or tenant compromise

If you suspect that your Nimbus Cloud Platform tenant credentials, API keys, or instances (such as `srv-alpha-12`) have been compromised by an unauthorized actor, immediately contact Nimbus Support via web chat and state **"Security Incident"**. In accordance with the **Nimbus Internal Escalation Policy**, any mention of a confirmed or suspected security incident triggers an **immediate priority handover from the AI assistant to a human specialist** in the Account & Security queue (`queue-account-sec`) with a **15-minute P1 response target**.
