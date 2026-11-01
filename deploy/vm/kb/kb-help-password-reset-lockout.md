---
doc_id: kb-help-password-reset-lockout
title: Self-service password reset, account lockout rules, and what support can do
source_system: helpcenter
source_kind: curated
audience: customer_visible
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-09-16
intents: [PASSWORD_RESET]
test_case: none
---

# Self-service password reset, account lockout rules, and what support can do

## Self-service password reset on Nimbus Cloud Platform

Users who sign in to Nimbus Cloud Platform with a local email and password can reset a forgotten or expired password using the automated self-service workflow. Organizations that enforce Single Sign-On (SAML 2.0 or OIDC) do not store user passwords inside Nimbus Cloud Platform; SSO users must reset their corporate password directly within their company Identity Provider (IdP) portal.

### How to reset your Nimbus Cloud Platform console password

1. Navigate to the Nimbus Cloud Platform sign-in page (`https://console.nimbuscloud.example.com/login`).
2. Enter your corporate email address (`<EMAIL_1>`) and Tenant Slug, then click **Forgot Password?**.
3. Check your inbox for an email from `no-reply@notifications.nimbuscloud.example.com` with the subject `Nimbus Cloud Platform password reset request`.
4. Click the single-use password reset link within **15 minutes** of issuance. After 15 minutes, the reset token expires automatically and you must request a new link.
5. Complete your Multi-Factor Authentication (MFA) challenge (TOTP code or FIDO2 security key).
6. Enter a new password that meets the Nimbus Cloud Platform password policy: at least **14 characters**, containing at least one uppercase letter, one lowercase letter, one number, and one special character, and not matching any of your last 12 passwords or known breached password hashes.

When your password is changed, Nimbus Cloud Platform immediately revokes all active browser sessions and temporary CLI access tokens (`nimbus auth token`), requiring you to re-authenticate across your devices. However, long-lived service account API keys are not affected by an individual user's password reset.

## Account lockout rules and automated unlock timers

### Failed login attempt thresholds on Nimbus Cloud Platform

To defend customer tenants against brute-force attacks, Nimbus Cloud Platform tracks failed password and MFA verification attempts per user account and source IP address:

- **5 consecutive failed password or MFA attempts** within a 10-minute rolling window trigger an automatic temporary account lockout (`Error AUTH_ACCOUNT_LOCKED_TEMP`).
- The temporary lockout lasts for **30 minutes**, after which the account automatically unlocks without requiring support intervention.
- **15 consecutive failed attempts** within a 60-minute window trigger a hard security lockout (`Error AUTH_ACCOUNT_LOCKED_HARD`), which blocks authentication until either the user completes a password reset with a valid MFA factor or a **Tenant Owner** unlocks the account under **Organization Settings > Users & Roles > Unlock Account**.

## What Nimbus Support can and cannot do for password and credential resets

### Console user passwords and MFA lockouts

Nimbus Support specialists **never** have access to view, set, or generate temporary passwords for customer user accounts, and Nimbus Support cannot manually bypass a user's MFA challenge or send password reset links to an alternate personal email address. If you are locked out of your Nimbus Cloud Platform console account:

- Wait 30 minutes for a temporary lockout (`AUTH_ACCOUNT_LOCKED_TEMP`) to clear automatically, or use the self-service **Forgot Password?** flow with your registered MFA device.
- Ask another **Tenant Owner** in your organization to unlock a hard lockout (`AUTH_ACCOUNT_LOCKED_HARD`) or reset your MFA device from **Organization Settings > Users & Roles**.

### Infrastructure instance root credential resets (such as `srv-alpha-12`)

If an administrator needs to reset the root or administrative operating-system/database credentials on a managed compute or database instance (for example, `srv-alpha-12` or `db-prod-west`), Nimbus Support can trigger an automated ephemeral key rotation only after the requester satisfies **Tier 2 (T2) identity verification** (authenticated via corporate SSO with MFA and holding the `Tenant Owner` or `Infrastructure Operator` role). Nimbus Support will never reset instance root credentials for an anonymous user (T0) or a user verified only by a one-time email code (T1).
