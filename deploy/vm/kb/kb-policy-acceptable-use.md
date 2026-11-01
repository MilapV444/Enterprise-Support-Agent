---
doc_id: kb-policy-acceptable-use
title: Nimbus Cloud Platform Acceptable Use Policy (AUP)
source_system: policies
source_kind: curated
audience: customer_visible
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-09-19
intents: [GENERAL_INQUIRY]
test_case: none
---

# Nimbus Cloud Platform Acceptable Use Policy (AUP)

## Purpose and scope of the Acceptable Use Policy

This Acceptable Use Policy (AUP) governs the use of all infrastructure services provided by Nimbus Systems, Inc., including **Nimbus DB**, **Nimbus Run**, **Nimbus Net**, **Nimbus POS Gateway**, the public REST API, and the Nimbus Support web chat. Every customer tenant (Starter, Growth, and Enterprise) and every end user accessing resources hosted on Nimbus Cloud Platform must comply with this AUP.

## Prohibited infrastructure and network activities

### 1. Unauthorized security probing, network abuse, and DDoS attacks

Tenants may not use Nimbus Run containers, Nimbus Net VPC egress nodes, or any other Nimbus Cloud Platform resource to:

- Launch Distributed Denial of Service (DDoS) attacks, SYN floods, UDP amplification, or BGP route hijacking against any internal or external network target.
- Perform unconsented port scanning, vulnerability scanning, credential stuffing, or penetration testing against other Nimbus tenants or external third-party hosts.
- Spoof IP headers, MAC addresses, or ARP packets, or attempt to bypass regional VPC network isolation boundaries.

Customers who wish to conduct authorized penetration testing against their own isolated Nimbus Cloud Platform resources must submit a **Penetration Test Notification Form** under **Organization Settings > Security > Pen-Test Authorization** at least **5 business days** in advance.

### 2. Cryptocurrency mining and resource quota circumvention

- **Strict Ban on Proof-of-Work Mining:** Running cryptocurrency mining software, blockchain proof-of-work hashers, or distributed compute farming inside Nimbus Run pods or Nimbus DB procedural functions is strictly prohibited across all subscription tiers.
- **Quota Evasion:** Creating multiple Starter or Growth tenants to evade API rate limits (`HTTP 429` caps), circumvent free-trial or 14-day refund rules, or bypass regional VPC quotas is prohibited.

### 3. Malicious content, phishing, and unlawful processing

Tenants must not store, transmit, or process malware command-and-control (C2) servers, ransomware payloads, phishing kits, unsolicited bulk spam (violating CAN-SPAM or EU ePrivacy directives), child sexual abuse material (CSAM), or stolen payment card data on Nimbus Cloud Platform. Tenants using **Nimbus POS Gateway** must transmit cardholder data exclusively through the hardware-encrypted P2PE terminal SDK and must never log raw primary account numbers (PAN) or CVV codes into plaintext Nimbus DB tables or Nimbus Run stdout logs.

## Enforcement, emergency suspension, and appeals

### Protective suspension for critical AUP violations

If Nimbus Security detects active malware distribution, outbound DDoS traffic, or cryptocurrency mining originating from a tenant's workload, Nimbus Systems reserves the right to immediately isolate the offending Nimbus Run pod or Nimbus Net subnet (`AUP_PROTECTIVE_QUARANTINE`) and notify the `Tenant Owner` via email and console alert. For non-critical AUP issues, Nimbus provides **24 hours' written notice** for the customer to remediate the violation before throttling or suspending the resource. Downtime resulting from an AUP suspension is excluded from all SLA uptime calculations.
