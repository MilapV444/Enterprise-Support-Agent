---
doc_id: kb-ticket-renewal-overcharge-dispute
title: Resolved ticket: Auto-renewal billed $48,000 list price instead of $32,000 contracted rate
source_system: tickets
source_kind: ticket
audience: internal
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-10-08
intents: [BILLING_INQUIRY, SUBSCRIPTION_UPDATE]
test_case: none
---

# Resolved ticket: Auto-renewal billed $48,000 list price instead of $32,000 contracted rate

## Case metadata and problem summary

- **Ticket ID:** `TCK-2026-86044`
- **Tenant Organization:** `Initech Logistics` (US Region `us-west-2`, Enterprise Plan)
- **Requester Contact:** `<NAME_1>` (`<EMAIL_1>`, Phone: `<PHONE_1>`, Role: `Billing Administrator`, Verified at **Tier 2** via Corporate SSO + MFA)
- **Disputed Invoice:** `inv_2026_10_44910` (Issued `2026-10-01`, ACH debit of **$48,000.00 USD**)

### Reported problem description

`<NAME_1>`, Billing Administrator for `Initech Logistics`, contacted Nimbus Support stating: *"Our annual Enterprise auto-renew just charged our corporate bank account $48,000 USD instead of our contracted $32,000 USD rate, and we never received any 60-day price increase notice. We need the $16,000 USD overcharge refunded immediately."*

## Root cause investigation

### Audit against Renewal Pricing Policy and Refund Policy

1. The AI assistant verified that the disputed delta (**$16,000.00 USD**) exceeded the **USD 1,000.00** human escalation threshold and the **USD 5,000.00** Senior Billing Specialist approval threshold under `kb-policy-internal-refund-approval-matrix`, and immediately handed the conversation over to `queue-billing-ops`.
2. Billing Specialist `<NAME_2>` audited `Initech Logistics`'s signed Enterprise Order Form (`OF-2025-1192`) and confirmed:
   - The contracted annual renewal rate was **$32,000.00 USD/year** (representing a contracted discount off the $48,000.00 USD public list price).
   - No 60-calendar-day advance written notice of a price adjustment had ever been sent to `<EMAIL_1>`.
   - Furthermore, under `kb-policy-renewal-pricing`, without 60-day notice an unchanged annual contract must renew at the exact prior contracted rate (`$32,000.00 USD`), and even with notice annual increases are capped at 7%.
   - Root cause in the billing engine was `ERR_RENEWAL_DISCOUNT_DROP`: the discount token on `OF-2025-1192` lacked the `auto_carry_forward: true` flag.

## Resolution steps executed

### Separation of duties, Senior Specialist approval, and ledger confirmation

1. Billing Specialist `<NAME_2>` registered a formal billing dispute with `DISPUTE_HOLD_ACTIVE`, issued Credit Memo `cm_2026_10_0091` for **$16,000.00 USD**, and initiated a `$16,000.00 USD` refund back to the original ACH payment method (`pm_ach_9921`).
2. In strict compliance with `kb-policy-internal-refund-approval-matrix`:
   - Because the refund was **USD 5,000 or above** (`$16,000.00 USD`) and the specialist handling the ticket (`<NAME_2>`) **can never approve their own case**, `<NAME_2>` routed the approval request to Senior Billing Specialist `<NAME_3>`.
   - `<NAME_2>` informed `<NAME_1>` that the `$16,000.00 USD` refund was approved in principle and queued for senior sign-off, without claiming the money was already refunded.
3. Senior Billing Specialist `<NAME_3>` approved the `$16,000.00 USD` refund in the Nimbus Billing Tool, and restored the `$32,000.00 USD` contracted rate flag on the tenant's subscription record.
4. Once the Nimbus Billing Ledger confirmed status **`SETTLED_REFUND`** (settlement reference `ref_tx_8839201a`), `<NAME_2>` sent the final confirmation to `<NAME_1>`.
