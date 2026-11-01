---
doc_id: kb-policy-renewal-pricing
title: Renewal pricing policy: contracted price protection and 60-day notice rules
source_system: policies
source_kind: curated
audience: customer_visible
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-09-17
intents: [BILLING_INQUIRY, SUBSCRIPTION_UPDATE]
test_case: none
---

# Renewal pricing policy: contracted price protection and 60-day notice rules

## Contracted price protection during an active subscription term

Nimbus Systems, Inc. provides strict **Contracted Price Protection** for all annual **Growth** and **Enterprise** subscriptions on Nimbus Cloud Platform. Throughout the duration of an active 12-month or multi-year subscription term, your base platform fee, included seat block rate, and contracted per-unit rates are locked and cannot be increased by Nimbus Systems, even if Nimbus updates its public list prices on the website.

## How pricing works upon annual auto-renewal

### Standard renewal rate continuity

Under the Nimbus Cloud Platform Master Subscription Agreement (MSA), when an annual subscription auto-renews for a subsequent 12-month renewal term without any customer-initiated tier upgrade or seat block expansion:

1. **Carry-Forward of Contracted Pricing (Default):** Unless Nimbus Systems has delivered timely written notice of a renewal price adjustment (at least **60 calendar days** before the renewal date), the subscription **must auto-renew at the exact same contracted annual rate** specified on the customer's prior Order Form (for example, `$32,000 USD/year`), **not** at the un-discounted public list price (`$48,000 USD/year`).
2. **Maximum Annual Renewal Cap (7% CPI/Platform Cap):** Even when Nimbus Systems provides proper 60-day advance written notice of a pricing update, the renewal price increase for an unchanged Enterprise footprint is capped at a maximum of **7% above the immediately preceding term's contracted rate**, unless the customer's Order Form explicitly states a multi-year fixed rate (0% increase).

### Mandatory 60-calendar-day advance notice for list-price or renewal adjustments

Nimbus Systems may only apply a list-price adjustment or renewal rate increase if **all** of the following conditions are met:

- Nimbus Systems sends a formal written **Renewal Pricing Notice** via email to all users holding the `Tenant Owner` and `Billing Administrator` roles at least **60 calendar days prior to the annual renewal date**.
- This 60-day advance window gives the customer at least **30 full calendar days** to evaluate the proposed renewal pricing before the customer's **30-calendar-day non-renewal notice deadline** arrives.

## Remediation when auto-renewal charges list price instead of contracted price

### Why erroneous list-price renewal charges happen (`ERR_RENEWAL_DISCOUNT_DROP`)

In rare cases, if a legacy annual Order Form discount code (`CONTRACT_OVERRIDE_...`) was set to expire after 12 months in the billing engine without an automated carry-forward flag, the billing system may erroneously revert the tenant to the un-discounted public list price at auto-renewal—for example, charging **$48,000 USD** instead of the customer's contracted **$32,000 USD** annual rate.

### Customer entitlement when overcharged on auto-renewal

If your tenant is charged the public list price (`$48,000 USD`) instead of your contracted renewal price (`$32,000 USD`), or if any price increase was applied without the mandatory **60-calendar-day advance written notice**:

- The excess charge (`$16,000 USD` in the `$48,000` vs. `$32,000` scenario) is an invalid overcharge and a **Verified Nimbus Billing Error** under the **Nimbus Refund Policy**.
- The customer is entitled to an immediate credit memo and a **100% cash refund of the overcharged difference (`$16,000 USD`)** back to the original payment method (or an immediate re-issued invoice for `$32,000 USD` if paying via Net-30 wire).
- Because a `$16,000 USD` refund exceeds the **$5,000 USD** senior approval threshold in the Nimbus Internal Refund and Credit Approval Matrix, the AI support assistant must immediately verify the customer at Tier T2, log the billing dispute under `DISPUTE_HOLD_ACTIVE`, and **hand over the conversation to a human Billing Specialist** (`queue-billing-ops`) so a Senior Billing Specialist can authorize the `$16,000 USD` refund.
