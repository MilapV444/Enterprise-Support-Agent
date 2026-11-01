---
doc_id: kb-billing-refund-policy
title: Refund policy
source_system: policies
source_kind: curated
audience: customer_visible
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-09-15
intents: [BILLING_INQUIRY, SUBSCRIPTION_UPDATE]
test_case: none
---

# Refund policy

## Overview of the Nimbus Cloud Platform refund policy

Nimbus Systems, Inc. bills subscription fees in advance and metered infrastructure usage in arrears in United States Dollars (USD). Except in the specific scenarios defined in this Refund Policy, all Nimbus Cloud Platform subscription charges, seat commitments, and metered resource consumption fees are **non-refundable**. This policy applies to all Starter, Growth, and Enterprise tenants across the US and EU regions as of its effective update on `2026-09-15`.

## When cash refunds are granted by Nimbus Systems

A `Tenant Owner` or `Billing Administrator` (authenticated at Tier T2 via corporate SSO with MFA) may request a monetary refund back to the original payment method under exactly three qualifying conditions:

### 1. Verified duplicate charges

If a payment gateway timeout or automated retry defect causes a customer's credit card, ACH account, or SEPA account to be billed twice for the same invoice number (`inv_...`), Nimbus Systems refunds 100% of the duplicate transaction within **5 business days** of verification.

### 2. Confirmed Nimbus Systems billing or renewal pricing errors

If Nimbus Cloud Platform erroneously bills an amount that contradicts an active signed Enterprise Order Form or violates the **Nimbus Renewal Pricing Policy**—for example, if auto-renewal charges a customer the standard un-discounted list price (`$48,000 USD`) instead of their contracted renewal rate (`$32,000 USD`) without a signed tier upgrade or valid 60-day notice—the overcharged delta (`$16,000 USD`) is classified as a **Verified Billing Error**. Verified Billing Errors are eligible for a full refund of the overcharge to the original payment method (or immediate invoice re-issuance if unpaid).

### 3. First-time subscription cancellation within the 14-day initial window

New business customers signing up for their very first **Starter** or **Growth** subscription on Nimbus Cloud Platform may cancel their tenant within **14 calendar days** of initial account creation and request a full refund of the base monthly subscription fee, provided that:

- The organization has never previously held a paid Nimbus Cloud Platform tenant.
- Total metered infrastructure usage (Nimbus DB, Nimbus Run, Nimbus Net, and Nimbus POS Gateway combined) accrued during those 14 days is **less than $100.00 USD**.
- The cancellation and refund request is submitted before `23:59 UTC` on Day 14.

## When refunds are NOT granted

Nimbus Systems does **not** issue monetary refunds or pro-rated credits under any of the following circumstances:

- **Renewal Charges After Missed Notice Deadlines:** Monthly plans that auto-renew because the customer did not cancel at least **7 calendar days** before the billing date, and annual contracts that auto-renew because the customer did not provide written non-renewal notice at least **30 calendar days** before the renewal date (provided the correct contracted rate was billed).
- **Mid-Cycle Cancellations or Plan Downgrades:** Cancelling a subscription or downgrading from Enterprise to Growth or Growth to Starter mid-term does not generate a pro-rated refund for unused days or months remaining in the term.
- **Unused Seats or Idle Infrastructure:** Provisioned user seats that remained uninvited and idle Nimbus DB or Nimbus Run instances that the customer forgot to decommission.
- **SLA Uptime Breaches:** Availability shortfalls are compensated exclusively via account **Service Credits** (up to 30% of the monthly service fee), never via cash refunds.

## Payment method return rules and settlement timelines

All approved refunds are returned strictly to the **original payment method** used for the transaction (the exact Visa/Mastercard/AMEX card, ACH bank account, or originating wire bank account). Nimbus Systems never issues refunds to alternate cards, third-party bank accounts, or cryptocurrency wallets. Once the Nimbus Billing Ledger confirms `SETTLED_REFUND`, card refunds post within **5 to 7 business days** and ACH/wire returns settle within **7 to 10 business days**.
