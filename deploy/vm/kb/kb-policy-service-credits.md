---
doc_id: kb-policy-service-credits
title: Service credit policy: credit tiers, 30% monthly cap, and invoice application
source_system: policies
source_kind: curated
audience: customer_visible
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-09-15
intents: [BILLING_INQUIRY]
test_case: none
---

# Service credit policy: credit tiers, 30% monthly cap, and invoice application

## Service credit calculation tiers for SLA uptime shortfalls

When Nimbus Systems, Inc. verifies that a covered production service (Nimbus DB, Nimbus Run, Nimbus Net, or Nimbus POS Gateway) failed to meet the contracted **Monthly Uptime Percentage** defined in the Nimbus Cloud Platform Service Level Agreement (`99.90%` for **Growth** tenants; `99.95%` for **Enterprise** tenants), the affected tenant is entitled to a **Service Credit** calculated as a percentage of the monthly recurring charge paid for the affected service in the affected region during that billing month.

### Growth and Enterprise service credit tier schedule

| Achieved Monthly Uptime % (Growth Plan) | Achieved Monthly Uptime % (Enterprise Plan) | Service Credit % of Affected Monthly Service Fee |
| :--- | :--- | :--- |
| `99.90%` to `100.00%` | `99.95%` to `100.00%` | **0%** (SLA target met) |
| `99.00%` to `99.89%` | `99.00%` to `99.94%` | **10% Service Credit** |
| `95.00%` to `98.99%` | `95.00%` to `98.99%` | **20% Service Credit** |
| Less than `95.00%` | Less than `95.00%` | **30% Service Credit** (Maximum Tier) |

### Worked example of a regional SLA credit audit

Suppose an Enterprise tenant (`Globex Corp`, target `99.95%` monthly uptime) pays a monthly recurring charge of **$4,000 USD** for its EU production database cluster (`Nimbus DB - eu-central-1`) during May (a 31-day month containing `44,640` total minutes). If `Nimbus DB - eu-central-1` experiences **45 minutes** of verified unscheduled multi-AZ downtime during May, the achieved Monthly Uptime Percentage is:

- `(44,640 - 45) / 44,640 = 99.899%` (rounded to `99.90%`).
- Because `99.90%` falls below the Enterprise `99.95%` target and within the `99.00% to 99.94%` tier, `Globex Corp` qualifies for a **10% Service Credit** (`$4,000 * 10% = $400.00 USD`).
- If `Globex Corp` were on the Growth plan (`99.90%` target), `99.90%` uptime would meet the Growth SLA target and yield `$0.00` credit.

## Maximum monthly service credit cap (30% ceiling)

Under no circumstances may the aggregate Service Credits issued to a tenant for any single calendar month exceed **30% of the total monthly recurring fee** paid by the tenant for the affected Nimbus Cloud Platform service in that calendar month. Service credits are calculated strictly against the specific degraded service and region (for example, an outage isolated to `Nimbus POS Gateway` in `us-west-2` does not generate credits against unaffected `Nimbus DB` clusters in `us-east-1`).

## How service credits are applied (account credit vs. cash refund)

### Account credit only—not redeemable for cash

Service Credits are issued exclusively as **USD account credit balances** applied toward future Nimbus Cloud Platform invoices. Service Credits are **never** paid out as cash refunds or wire transfers to a customer's bank account or credit card, and Service Credits cannot be transferred between separate Tenant IDs. The sole exception occurs if Nimbus Systems terminates a customer's Enterprise contract without cause while an unused verified Service Credit balance remains on the ledger.

### How service credits appear on Nimbus Cloud Platform invoices and audits

Once an SLA claim is approved by Nimbus Billing Operations (within **10 business days** of claim submission), the credit is posted to the tenant's billing ledger with transaction code `SLA_CREDIT_ADJ` and appears as a dedicated credit line item on the **next scheduled monthly invoice** (or against the next quarterly overage/renewal invoice for annual pay-in-advance Enterprise tenants). Customers auditing historical SLA credits (such as reviewing Q2 EU database uptime and applied credits) can verify all issued credits under **Organization Settings > Billing & Plan > Credit Ledger**.
