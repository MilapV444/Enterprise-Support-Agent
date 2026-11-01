---
doc_id: kb-ticket-eu-db-sla-audit-q2
title: Resolved ticket: Q2 EU database uptime audit and 10% SLA credit for Globex Corp
source_system: tickets
source_kind: ticket
audience: internal
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-07-18
intents: [BILLING_INQUIRY, TECHNICAL_OUTAGE]
test_case: none
---

# Resolved ticket: Q2 EU database uptime audit and 10% SLA credit for Globex Corp

## Case metadata and problem summary

- **Ticket ID:** `TCK-2026-71204`
- **Tenant Organization:** `Globex Corp` (EU Region `eu-central-1`, Enterprise Plan)
- **Requester Contact:** `<NAME_1>` (`<EMAIL_1>`, Phone: `<PHONE_1>`, Role: `Billing Administrator`, Verified at **Tier 2** via Corporate SSO + MFA)
- **Affected Resource:** Nimbus DB production cluster `db-eu-core-01` (`eu-central-1` Frankfurt)

### Reported problem description

During their quarterly vendor compliance review in July, `<NAME_1>` at `Globex Corp` asked Nimbus Support to *"compare our EU database uptime for Q2 against our Enterprise SLA target and confirm any service credits applied to our invoices."*

## Audit analysis against the Nimbus SLA and Service Credit Policy

### Reviewing Q2 monthly uptime against the 99.95% Enterprise target

Billing Specialist `<NAME_2>` verified `<NAME_1>`'s **Tier 2 (T2)** authentication on tenant `globex-corp-eu` and retrieved the official Q2 (April, May, June) availability telemetry for `Nimbus DB - eu-central-1` alongside `kb-policy-sla-uptime-targets` and `kb-policy-service-credits`:

1. **Contracted Enterprise Uptime Target:** **99.95%** Monthly Uptime Percentage per calendar month.
2. **April Uptime Breakdown (`43,200` total minutes):**
   - `0 minutes` of unscheduled downtime (`100.00%` uptime). A 20-minute planned maintenance window on `2026-04-12` was announced 5 days in advance on `status.nimbuscloud.example.com` and is excluded under the **Scheduled Maintenance** exclusion.
3. **May Uptime Breakdown (`44,640` total minutes):**
   - On `2026-05-19`, incident `INC-2026-0519` caused **45 minutes** of unscheduled multi-AZ storage control-plane unavailability in `eu-central-1`.
   - Achieved Monthly Uptime Percentage for May: `((44,640 - 45) / 44,640) * 100 = 99.899%` (rounded to **`99.90%`**).
   - Because `99.90%` fell below the Enterprise `99.95%` target and landed inside the `99.00% to 99.94%` Enterprise shortfall tier, `Globex Corp` qualified for a **10% Service Credit** on the `$4,000.00 USD` monthly fee for `db-eu-core-01` (`$400.00 USD`).
4. **June Uptime Breakdown (`43,200` total minutes):**
   - An 18-minute connection drop occurred on `2026-06-08` when a customer batch script exhausted `max_connections` (`SQLSTATE 53300`). Because customer-caused connection exhaustion is excluded from SLA downtime under `kb-policy-sla-uptime-targets`, SLA-eligible uptime for June was **`100.00%`**.

## Resolution and invoice credit confirmation

`<NAME_1>` had filed the May SLA claim on `2026-06-10` (well within the **30-calendar-day** post-month filing deadline). Because the **$400.00 USD** service credit was below the **USD 1,000** peer-approval threshold, it was approved and applied automatically as line item `SLA_CREDIT_ADJ (-$400.00 USD)` on `Globex Corp`'s July 1 invoice (`inv_2026_07_31008`). `<NAME_2>` exported the signed Q2 SLA Audit PDF for `<NAME_1>`.
