---
doc_id: kb-help-billing-faq-invoices-payments
title: Billing FAQ: invoices, payment methods, taxes, proration, and grace periods
source_system: helpcenter
source_kind: curated
audience: customer_visible
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-09-18
intents: [BILLING_INQUIRY, SUBSCRIPTION_UPDATE]
test_case: none
---

# Billing FAQ: invoices, payment methods, taxes, proration, and grace periods

## How Nimbus Cloud Platform invoicing works

Nimbus Systems, Inc. bills customer tenants in **United States Dollars (USD) only**, regardless of whether your infrastructure is deployed in the US (`us-east-1`, `us-west-2`) or EU (`eu-central-1`, `eu-west-1`) region. Invoices are generated on the 1st calendar day of each month at `00:00 UTC` (or on your annual contract anniversary date for annual commitments) and delivered as PDF attachments to all users holding the `Tenant Owner` or `Billing Administrator` role, as well as to the designated billing contact email (`<EMAIL_1>`).

### Fixed subscription fees versus metered usage charges

Every monthly or annual Nimbus Cloud Platform invoice consists of two distinct sections:

1. **Base Platform Subscription & Seat Commitments (billed in advance):** Covers your Starter ($250/month), Growth ($1,200/month), or Enterprise (custom contracted annual rate, minimum $24,000/year) base plan fee plus any additional provisioned user seats ($20/seat/month on Starter, $35/seat/month on Growth, $45/seat/month on Enterprise above contracted block).
2. **Metered Infrastructure Overages (billed in arrears):** Covers hourly compute node usage in Nimbus Run, storage and IOPS in Nimbus DB, cross-region data transfer in Nimbus Net, and transaction volume overages in Nimbus POS Gateway accrued during the preceding billing period.

## Accepted payment methods and settlement terms

### Self-service and Enterprise payment options

- **Corporate Credit and Debit Cards:** Visa, Mastercard, and American Express cards billed in USD. Cards are charged automatically within 24 hours of invoice issuance.
- **ACH Direct Debit (US Tenants):** Automated Clearing House bank debit in USD for US business checking accounts.
- **SEPA Direct Debit (EU Tenants, USD-denominated):** Available for Growth and Enterprise tenants in the EU; converted by the customer's bank into USD at settlement without currency markup by Nimbus Systems.
- **Wire Transfer / ACH Push (Enterprise Annual Only):** Available exclusively for Enterprise tenants with an annual contract of $24,000/year or higher under **Net-30** payment terms.

## Taxes, US sales tax, and EU VAT reverse charge

### How to submit tax exemption certificates and EU VAT IDs

Nimbus Cloud Platform calculates applicable state sales tax for US tenants based on the service billing address registered under **Organization Settings > Billing & Plan > Tax Information**. US tax-exempt entities may upload a valid state resale or exemption certificate for verification by the Nimbus Billing team.

For business tenants located in the European Union, Nimbus Systems, Inc. applies the **EU VAT Reverse Charge** mechanism on B2B transactions once you enter and validate a valid VIES VAT registration number (for example, `DE999999999` or `IE9999999L`) in the Nimbus Cloud Platform billing console. If no valid VAT ID is on file prior to invoice generation, standard local VAT is charged and cannot be retroactively credited onto an already closed prior-quarter tax filing.

## Proration rules for mid-cycle upgrades and downgrades

### Upgrading plans or adding seats mid-cycle

When you upgrade your Nimbus Cloud Platform plan (for example, from Starter to Growth) or add user seats mid-month, the upgrade takes effect **immediately**. Nimbus Cloud Platform calculates a pro-rated charge based on the exact number of calendar days remaining in the current billing period and issues an immediate pro-rated invoice.

### Downgrading plans or reducing seats

When you downgrade your subscription tier or remove paid seats, the reduction does **not** take effect mid-cycle and does not generate a pro-rated refund or credit. Instead, the downgrade is scheduled to take effect at the start of the **next billing period** (subject to required notice periods: 7 calendar days for monthly plans, 30 calendar days prior to anniversary for annual contracts).

## Failed payments and the 14-day grace period

If an automated card or direct debit charge fails, Nimbus Cloud Platform marks the invoice `PAST_DUE` and initiates a **14-calendar-day grace period**:

- **Automated Retries:** Nimbus retries the primary payment method automatically on **Day 3**, **Day 7**, and **Day 12** after the initial failure, sending urgent payment failure alerts after each attempt.
- **Day 15 Read-Only Suspension:** If the invoice remains unpaid at `00:00 UTC` on Day 15, non-Enterprise tenants enter **Read-Only Suspension** (console mutations and new deployments are blocked, and API write requests return `402 Payment Required`).
- **Day 45 Termination:** If an account remains unpaid 45 calendar days past the due date without an active billing dispute hold, the tenant is scheduled for termination and data reclamation.
