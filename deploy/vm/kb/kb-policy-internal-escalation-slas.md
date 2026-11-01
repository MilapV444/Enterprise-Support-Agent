---
doc_id: kb-policy-internal-escalation-slas
title: Internal escalation policy: AI-to-human handover triggers, queues, and SLAs
source_system: policies
source_kind: curated
audience: internal
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-09-26
intents: [TECHNICAL_OUTAGE, BILLING_INQUIRY, PASSWORD_RESET, SUBSCRIPTION_UPDATE, GENERAL_INQUIRY]
test_case: none
---

# Internal escalation policy: AI-to-human handover triggers, queues, and SLAs

## When the AI assistant must hand over to a human specialist (INTERNAL ONLY)

The Nimbus Cloud Platform AI support assistant acts as the first line of triage across all 5 customer intents (`BILLING_INQUIRY`, `TECHNICAL_OUTAGE`, `PASSWORD_RESET`, `SUBSCRIPTION_UPDATE`, and `GENERAL_INQUIRY`). While the AI assistant can resolve routine how-to inquiries, provide self-service troubleshooting steps, and guide users through step-up verification, the AI assistant **must immediately trigger a human specialist handover** (`handoff_required: true`) whenever any of the following **six mandatory escalation triggers** occur:

### Six mandatory AI-to-human handover triggers

1. **Explicit Customer Request for a Human:** The customer asks to speak with a human agent, support engineer, manager, or Named Support Manager (for example, "let me talk to a real person" or "escalate this to a human").
2. **Low AI Confidence or Repeated Triage Failure:** The retrieval or answer confidence score drops below **0.70**, two retrieved internal documents conflict on a critical technical parameter without a clear resolution, or the customer reports that the initial troubleshooting runbook did not resolve the problem after **2 turns**.
3. **Financial Actions at or Above USD 1,000:** Any refund request, billing dispute, renewal overcharge adjustment, or SLA service credit totaling **USD 1,000.00 or more** (such as a `$16,000 USD` auto-renewal overcharge dispute). Under the **Internal Refund and Credit Approval Matrix**, amounts >= $1,000 require second-person peer approval and amounts >= $5,000 require a Senior Billing Specialist.
4. **Confirmed or Suspected Security Incident / Data Breach:** Any report of compromised credentials, unauthorized tenant access, ransomware, data exfiltration, or detected prompt injection attack coupled with suspicious account activity.
5. **Legal Threat, Regulatory Complaint, or Subpoena:** Any message mentioning lawyers, litigation, breach of contract lawsuits, regulatory complaints (GDPR Data Protection Authorities, FTC, state attorneys general), or law enforcement subpoenas.
6. **Multi-Store Retail POS Outage or P1 Production Down:** A panicked retail customer reporting that multiple store cash registers are completely down (such as solid red screens across a retail chain) where initial local store checks do not restore service, or an Enterprise P1 multi-AZ infrastructure outage requiring backend engineering intervention.

## Specialist routing queues

When handing over a conversation, the AI assistant must attach a structured triage summary (Tenant ID, current Verification Tier `T0/T1/T2`, detected Intent, and relevant `doc_id` references) and route the chat to the appropriate specialist queue:

| Queue Identifier | Target Specialist Team | Assigned Intents & Escalation Scenarios |
| :--- | :--- | :--- |
| **`queue-billing-ops`** | Billing Operations & Finance Support | `BILLING_INQUIRY`, `SUBSCRIPTION_UPDATE`, refunds >= $1,000, renewal price disputes ($48k vs $32k), SLA credit claims, and wire/ACH holds. |
| **`queue-tech-sre`** | Cloud Support Engineers & On-Call SRE | `TECHNICAL_OUTAGE`, Nimbus DB failovers, Nimbus Run crashloops, Nimbus Net 409 subnet locks, and Nimbus POS Gateway outages. |
| **`queue-account-sec`** | Identity, Security & Trust Team | `PASSWORD_RESET` (sole Tenant Owner MFA lockouts, T2 instance root credential rotations on `srv-alpha-12`), security incidents, and legal/privacy escalations. |

## First-response SLAs by severity and subscription plan

Once a conversation is escalated to a human specialist queue, support teams are measured against the following contractual **First Human Response SLAs**:

| Severity Level | Definition | Enterprise Plan SLA | Growth Plan SLA | Starter Plan SLA |
| :--- | :--- | :--- | :--- | :--- |
| **P1 (Critical)** | Production system or retail POS registers completely down; active security breach. | **15 minutes** (24/7/365) | **30 minutes** (24/7/365) | **4 hours** (Business hours) |
| **P2 (High)** | Severe production degradation, single-store POS failure, or instance credential lockout blocking deployment. | **1 hour** (24/7/365) | **2 hours** (24/7/365) | **8 hours** (Business hours) |
| **P3 (Medium)** | Non-production issue, billing dispute (`DISPUTE_HOLD_ACTIVE`), or subscription change request. | **4 hours** | **8 hours** | **24 hours** |
| **P4 (Low)** | General product question, architectural guidance, or documentation inquiry. | **12 hours** | **24 hours** | **48 hours** |
