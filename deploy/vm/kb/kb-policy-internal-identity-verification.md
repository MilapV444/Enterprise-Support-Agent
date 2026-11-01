---
doc_id: kb-policy-internal-identity-verification
title: Internal identity verification policy: T0, T1, and T2 tiers and step-up rules
source_system: policies
source_kind: curated
audience: internal
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-09-25
intents: [PASSWORD_RESET, BILLING_INQUIRY, SUBSCRIPTION_UPDATE, GENERAL_INQUIRY]
test_case: none
---

# Internal identity verification policy: T0, T1, and T2 tiers and step-up rules

## Purpose of the three-tier identity verification framework (INTERNAL ONLY)

To prevent social engineering, unauthorized account takeovers, and cross-tenant data leakage across Nimbus Cloud Platform, all customer interactions handled by the AI support assistant or human support specialists are governed by three strict **Identity Verification Tiers**: **Tier 0 (T0)**, **Tier 1 (T1)**, and **Tier 2 (T2)**. Support personnel and the AI agent must check the session's current `verification_tier` before disclosing any account information or executing any operational command.

## Summary of verification tiers and permitted actions

| Verification Tier | How the User Is Verified | Permitted Disclosures & Actions | Strictly Prohibited Actions |
| :--- | :--- | :--- | :--- |
| **Tier 0 (T0): Anonymous / Unverified** | Unauthenticated web chat visitor or user who has only typed a name/email/tenant name in chat without verification. | **Public Info Only:** Public documentation, how-to guides, general pricing/SLA rules, status page URLs (`status.nimbuscloud.example.com`), and console navigation paths. | **Zero Tenant Reads or Mutations:** Cannot disclose a tenant's subscription tier, renewal date, invoice balance, or ticket history; cannot reset credentials or change billing. |
| **Tier 1 (T1): Email OTP Verified** | Verified via a 6-digit **One-Time Email Code** (`OTP`) sent to a registered corporate email address (`<EMAIL_1>`) belonging to that specific tenant. | **Own Tickets & Account Reads Only:** Read status of the user's own support tickets; read non-sensitive tenant metadata for their own tenant (current subscription tier, renewal date, region, open invoice balance). | **Zero Mutations or Credential Resets:** Cannot reset instance root credentials (`srv-alpha-12`), cannot reset MFA, cannot change plans/seats, and cannot issue refunds or modify billing. |
| **Tier 2 (T2): SSO + MFA Verified** | Authenticated via **Corporate SSO (SAML 2.0 / OIDC) with MFA enforced** (or local console login + FIDO2/TOTP MFA for non-SSO Starter tenants) **AND** verified RBAC role (`Tenant Owner`, `Billing Administrator`, or `Infrastructure Operator`). | **Account Changes, Credential Resets & Financial Actions:** Instance root credential rotation, VPC lock releases, plan upgrades/downgrades, billing disputes, and refunds/credits (subject to the approval matrix). | Cannot access or modify any tenant other than the authenticated `tenant_id` in the signed T2 session assertion, and cannot bypass peer/senior refund approval thresholds. |

## Handling common support verification scenarios

### Scenario 1: Account read request (e.g., "What is the current subscription tier and renewal date for tenant Globex Corp?")

1. **Never store or guess live customer data from the KB:** The knowledge base intentionally contains no live subscription records for `Globex Corp`, `Acme Retail`, or `Initech Logistics`.
2. **Check Verification Tier:**
   - If the requester is at **T0 (Anonymous)**, explain where plan information lives in the console (**Organization Settings > Billing & Plan > Subscription Overview**) and state that Nimbus Support can only look up and disclose `Globex Corp`'s live subscription tier and renewal date after the requester completes at least **Tier 1 (T1) one-time email verification** (or signs in via **T2 SSO with MFA**) as an authorized user on the `Globex Corp` tenant.
   - If the requester is authenticated at **T1 or T2** for a *different* tenant, refuse disclosure immediately (`CROSS_TENANT_ACCESS_DENIED`).

### Scenario 2: Instance root credential reset (e.g., "Reset the root credentials on instance srv-alpha-12")

1. **Strict Tier 2 (T2) Requirement:** Rotating or resetting root/administrator credentials on any compute or database instance (such as `srv-alpha-12`) is a high-privilege mutation that **strictly requires Tier 2 (T2) verification** (SSO with MFA) plus the `Tenant Owner` or `Infrastructure Operator` RBAC role.
2. **Never Execute for T0 or T1:** Even if a user provides a valid T1 one-time email code and claims an emergency outage on `srv-alpha-12`, support **must never** reset credentials at T0 or T1.

## Step-up authentication procedure (T0/T1 to T2)

When a user at T0 or T1 requests a T2-gated action (such as resetting root credentials on `srv-alpha-12`, changing a subscription plan, or filing a billing dispute/refund):

1. Inform the user clearly that the requested action requires **Tier 2 (T2) SSO + MFA authentication**.
2. Trigger the in-chat **Step-Up Verification Challenge** (`nimbus-support-cli auth step-up --target-tier T2 --tenant <TENANT_SLUG>`), which prompts the user to authenticate through their corporate SSO Identity Provider with an active MFA claim (`amr: ["mfa"]`).
3. Confirm that the session header updates to `verification_tier: T2` and verify the user's RBAC role before proceeding with the runbook or billing workflow.
