---
doc_id: kb-help-mfa-enrollment-recovery
title: Multi-Factor Authentication (MFA) enrollment, TOTP, and recovery codes
source_system: helpcenter
source_kind: curated
audience: customer_visible
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-09-14
intents: [PASSWORD_RESET]
test_case: none
---

# Multi-Factor Authentication (MFA) enrollment, TOTP, and recovery codes

## Mandatory MFA requirements on Nimbus Cloud Platform

Nimbus Cloud Platform enforces Multi-Factor Authentication (MFA) for all user accounts across Starter, Growth, and Enterprise subscription plans. MFA protects tenant infrastructure in Nimbus DB, Nimbus Run, Nimbus Net, and Nimbus POS Gateway against credential stuffing and unauthorized access. In addition, an active MFA-authenticated session (either through corporate SSO with MFA or local login with MFA for non-SSO tenants) is required to satisfy Tier 2 (T2) identity verification before Nimbus Support can execute sensitive operations such as instance credential resets or billing changes.

### Supported MFA factors on Nimbus Cloud Platform

Nimbus Cloud Platform supports two primary second-factor authentication mechanisms and one offline backup mechanism:

- **WebAuthn / FIDO2 Security Keys:** Hardware security keys and platform biometric authenticators compliant with FIDO2 standards. Enterprise tenants can require FIDO2-only authentication under **Organization Settings > Security > MFA Policy**.
- **Time-based One-Time Password (TOTP) Apps:** RFC 6238-compliant authenticator apps generating 6-digit codes every 30 seconds (SHA-1, 6 digits, 30-second period).
- **Single-Use Recovery Codes:** A batch of 10 single-use 12-character alphanumeric backup codes generated when you first enroll in MFA. Note that SMS and voice-call OTP are not supported on Nimbus Cloud Platform due to SIM-swapping security risks.

## Enrolling and managing MFA devices in Nimbus Cloud Platform

### Step-by-step MFA enrollment for new Nimbus Cloud Platform users

1. Sign in to the Nimbus Cloud Platform web console with your email address (`<EMAIL_1>`) and password.
2. On the **Secure Your Account with MFA** screen, select either **Register FIDO2 Security Key** or **Configure Authenticator App (TOTP)**.
3. For TOTP setup, scan the displayed QR code with your authenticator app and enter two consecutive 6-digit verification codes to confirm clock synchronization.
4. Download or copy your 10 single-use Nimbus Cloud Platform recovery codes and store them in an encrypted password manager. Each recovery code follows the format `NMB-XXXX-XXXX` and can only be used once.
5. Register a secondary backup MFA factor (such as a second hardware key) under **User Profile > Security > MFA Devices** to prevent lockouts if your primary device is lost or replaced.

## Recovering from a lost MFA device on Nimbus Cloud Platform

### Self-service recovery using a Nimbus Cloud Platform backup code

If you lose your phone or hardware key, click **Use a recovery code instead** on the Nimbus Cloud Platform MFA prompt and enter one of your unused `NMB-XXXX-XXXX` recovery codes. Once signed in, immediately navigate to **User Profile > Security > MFA Devices**, revoke the lost device, enroll a replacement authenticator, and regenerate a fresh set of 10 recovery codes.

### Resetting MFA through a peer Tenant Owner

If a standard user, Infrastructure Operator, or Billing Administrator loses both their primary MFA device and their recovery codes, any **Tenant Owner** within the same Nimbus Cloud Platform organization can reset that user's MFA enrollment:

1. The Tenant Owner navigates to **Organization Settings > Users & Roles**.
2. Selects the locked user account (`<EMAIL_1>`) and clicks **Reset MFA Factors**.
3. Enters their own T2 MFA verification challenge to confirm the reset.
4. The affected user receives an email prompts to enroll a new MFA factor upon their next sign-in.

### What to do if the sole Tenant Owner loses MFA access

For security reasons, Nimbus Support specialists cannot disable or bypass MFA for any user over web chat based solely on an email code (T1 verification). If the sole Tenant Owner of a tenant loses both MFA devices and recovery codes, another verified administrator via corporate SSO (T2) must authorize the reset, or the organization must complete the formal **Notarized Domain & Corporate Officer Recovery Workflow** through the Nimbus Security team (`queue-account-sec`), which takes 2 to 3 business days.
