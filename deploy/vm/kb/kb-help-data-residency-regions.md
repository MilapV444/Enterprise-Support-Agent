---
doc_id: kb-help-data-residency-regions
title: US and EU data residency guarantees and regional data boundaries
source_system: helpcenter
source_kind: curated
audience: customer_visible
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-09-22
intents: [GENERAL_INQUIRY]
test_case: none
---

# US and EU data residency guarantees and regional data boundaries

## Overview of Nimbus Cloud Platform regional architecture

Nimbus Cloud Platform operates two physically and logically isolated regional realms—**United States (US)** and **European Union (EU)**—to help business customers meet regulatory, contractual, and data sovereignty obligations such as GDPR. When a customer organization creates a tenant on Nimbus Cloud Platform (for example, `Acme Retail` in the US realm or `Globex Corp` in the EU realm), the tenant's primary Data Residency Realm is permanently bound at provisioning time.

### Available regions and availability zones

- **US Data Residency Realm:**
  - `us-east-1` (Northern Virginia, USA — 3 Availability Zones: `us-east-1a`, `us-east-1b`, `us-east-1c`)
  - `us-west-2` (Oregon, USA — 3 Availability Zones: `us-west-2a`, `us-west-2b`, `us-west-2c`)
- **EU Data Residency Realm:**
  - `eu-central-1` (Frankfurt, Germany — 3 Availability Zones: `eu-central-1a`, `eu-central-1b`, `eu-central-1c`)
  - `eu-west-1` (Dublin, Ireland — 3 Availability Zones: `eu-west-1a`, `eu-west-1b`, `eu-west-1c`)

## What customer data stays strictly within your selected region

### Data guaranteed to remain inside the chosen US or EU realm

For every tenant provisioned in the EU realm (`eu-central-1` and `eu-west-1`) or US realm (`us-east-1` and `us-west-2`), Nimbus Systems guarantees that all **Customer Content and Operational Telemetry** remains stored and processed exclusively within that realm:

1. **Nimbus DB Data and Backups:** All relational database tables, Write-Ahead Logs (WAL), automated daily snapshots, and point-in-time recovery archives are encrypted at rest with AES-256-GCM using regionally isolated KMS keys. Cross-region read replicas and backup replication for an EU tenant can only replicate between `eu-central-1` and `eu-west-1`—never to a US region.
2. **Nimbus Run Workloads and Container Images:** Container filesystem layers, persistent volumes, Kubernetes secrets, config maps, and application stdout/stderr logs remain inside the selected regional realm.
3. **Nimbus Net VPC Traffic and Flow Logs:** Private subnet traffic, NAT gateway state, and VPC flow logs never traverse outside the regional realm unless the customer explicitly configures an external public internet egress or custom third-party VPN tunnel.
4. **Nimbus POS Gateway Transaction Payloads:** Retail terminal diagnostic logs, receipt metadata, and encrypted payment token payloads stay strictly within the tenant's assigned regional realm.
5. **Authentication Tokens and Audit Logs:** Tenant IAM audit trails, SAML/OIDC session assertions, and KMS encryption keys remain pinned to the regional control plane.

## Global administrative metadata and billing exceptions

### Limited account billing metadata processed in the US

While all Customer Content and workload telemetry stay strictly in-region, minimal B2B **Contract and Invoicing Metadata** required for financial accounting by Nimbus Systems, Inc. (a US corporation) is replicated to the Nimbus global billing ledger:

- Organization legal name, Tenant ID (`tnt_...`), and corporate billing address.
- Designated `Billing Administrator` contact name (`<NAME_1>`) and billing email address (`<EMAIL_1>`).
- Aggregated monthly resource usage counters (for example, total vCPU-hours or GB-months used to compute invoice line items, devoid of database content or end-customer PII).

Cross-border transfer of this limited B2B administrative contact metadata for EU tenants is governed by the European Commission Standard Contractual Clauses (SCCs) incorporated into the Nimbus Cloud Platform Data Processing Addendum (DPA).

## Moving workloads between the US and EU realms

Because US and EU control planes share no underlying storage or KMS key hierarchy, a tenant cannot automatically live-migrate an existing Nimbus DB cluster across the Atlantic. Customers expanding into a second realm must provision a separate regional tenant (for example, `globex-corp-us` alongside `globex-corp-eu`) and export/import sanitized schema data manually.
