---
doc_id: kb-help-status-page-incidents
title: Checking the Nimbus Status Page and subscribing to incident communications
source_system: helpcenter
source_kind: curated
audience: customer_visible
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-09-20
intents: [TECHNICAL_OUTAGE, GENERAL_INQUIRY]
test_case: none
---

# Checking the Nimbus Status Page and subscribing to incident communications

## Where to check live Nimbus Cloud Platform operational status

Nimbus Systems, Inc. maintains an external, independently hosted status portal at **`https://status.nimbuscloud.example.com`**. Because the status portal runs on isolated infrastructure outside the primary Nimbus Cloud Platform US and EU control planes, `https://status.nimbuscloud.example.com` remains reachable even during a regional control-plane or DNS incident.

### Components tracked on the Nimbus Status Page

The Nimbus Status Page displays real-time health indicators (`Operational`, `Degraded Performance`, `Partial Outage`, `Major Outage`, or `Under Maintenance`) segmented by geographical region and core service:

- **US Region (`us-east-1` Virginia and `us-west-2` Oregon):**
  - Nimbus Control Plane & Public REST API (`api.nimbuscloud.example.com`)
  - Nimbus Identity & SSO Gateway (`auth.nimbuscloud.example.com`)
  - Nimbus DB (Managed PostgreSQL Clusters & Automated Backups)
  - Nimbus Run (Managed Container Clusters & Registry Proxy)
  - Nimbus Net (VPC Routing, NAT Gateways & VPN Endpoints)
  - Nimbus POS Gateway (US Retail Payment Relay & Terminal Sync)
- **EU Region (`eu-central-1` Frankfurt and `eu-west-1` Dublin):**
  - Nimbus Control Plane & Public REST API (`eu.api.nimbuscloud.example.com`)
  - Nimbus Identity & SSO Gateway
  - Nimbus DB, Nimbus Run, Nimbus Net, and Nimbus POS Gateway (EU Retail Relay)

Customers can also query the machine-readable JSON status endpoint at `https://status.nimbuscloud.example.com/api/v2/summary.json` to integrate regional health checks directly into internal monitoring dashboards or retail store back-office alerts.

## How Nimbus Systems posts incident updates and RCA reports

### Incident declaration and communication cadence

When automated synthetic probes or on-call Site Reliability Engineers (SREs) detect elevated error rates, latency spikes, or component unavailability on Nimbus Cloud Platform, the Incident Commander publishes an initial incident notice on `https://status.nimbuscloud.example.com` within **10 minutes** of detection. Active incidents follow a strict update cadence based on severity:

- **Severity 1 (Major Outage / Multi-Tenant Production Down):** Status updates are posted every **15 minutes** until mitigation is verified.
- **Severity 2 (Partial Outage / Elevated Latency or Single Availability Zone Degradation):** Status updates are posted every **30 minutes** until service metrics return to baseline.
- **Severity 3 (Minor Component Degradation or Delayed Asynchronous Jobs):** Status updates are posted every **60 minutes** or upon status change.

### Post-Incident Reviews (PIR) and Root Cause Analysis (RCA)

Following any Severity 1 or Severity 2 production incident, Nimbus Engineering publishes a preliminary incident summary on the status page within **24 hours** of resolution and delivers a comprehensive Root Cause Analysis (RCA) document within **5 business days**. Growth and Enterprise customers can download signed PDF copies of historical RCA reports under **Organization Settings > Compliance & SLA > Incident Reports** to support internal audits or SLA service credit claims.

## Subscribing to real-time status notifications

Administrators, on-call engineers, and retail store operations leads can subscribe to component-specific alerts at `https://status.nimbuscloud.example.com/subscribe` via four delivery channels:

1. **Email Alerts:** Scoped to specific regions (US or EU) and services (for example, only `Nimbus POS Gateway - US`).
2. **Webhook Notifications:** Signed JSON payloads delivered to your incident management endpoint with header `X-Nimbus-Status-Signature`.
3. **RSS / Atom Feed:** `https://status.nimbuscloud.example.com/history.rss`.
4. **In-Console Banner Alerts:** Automatically displayed at the top of the Nimbus Cloud Platform web console whenever an active incident affects your tenant's deployed region.
