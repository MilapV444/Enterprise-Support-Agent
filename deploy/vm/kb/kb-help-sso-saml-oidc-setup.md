---
doc_id: kb-help-sso-saml-oidc-setup
title: Configuring Enterprise Single Sign-On (SAML 2.0 and OIDC)
source_system: helpcenter
source_kind: curated
audience: customer_visible
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-09-12
intents: [PASSWORD_RESET, GENERAL_INQUIRY]
test_case: none
---

# Configuring Enterprise Single Sign-On (SAML 2.0 and OIDC)

## Overview of Single Sign-On on Nimbus Cloud Platform

Nimbus Cloud Platform supports federated Single Sign-On (SSO) using both SAML 2.0 and OpenID Connect (OIDC) standards. SSO integration is included on the Growth and Enterprise subscription plans and enables business tenants to authenticate users through their corporate Identity Provider (IdP) and enforce centralized Multi-Factor Authentication (MFA) for T2-verified administrative actions.Starter plan tenants use local Nimbus Cloud Platform credentials with mandatory TOTP or WebAuthn MFA, and can upgrade to the Growth or Enterprise plan at any time to unlock SAML 2.0 and OIDC federation.

### Supported Identity Providers and protocols

Nimbus Cloud Platform validates standard SAML 2.0 assertions (signed with RSA-SHA256) and OIDC Authorization Code flows with PKCE. Before configuring SSO on Nimbus Cloud Platform, confirm that your Tenant Owner has verified ownership of your corporate email domain under **Organization Settings > Domains** by adding the generated `_nimbus-domain-verification` TXT record to your DNS zone.

## Configuring SAML 2.0 federation on Nimbus Cloud Platform

### Nimbus Cloud Platform Service Provider (SP) metadata values

When creating a SAML 2.0 application in your corporate Identity Provider for Nimbus Cloud Platform, configure the following Service Provider endpoints (replace `<TENANT_SLUG>` with your organization's Nimbus Cloud Platform Tenant Slug):

- **Assertion Consumer Service (ACS) URL:** `https://auth.nimbuscloud.example.com/saml2/acs/<TENANT_SLUG>`
- **Service Provider Entity ID / Audience URI:** `urn:nimbuscloud:sp:<TENANT_SLUG>`
- **Single Logout (SLO) URL:** `https://auth.nimbuscloud.example.com/saml2/slo/<TENANT_SLUG>`
- **NameID Format:** `urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress`

### Required SAML 2.0 attribute mappings

Nimbus Cloud Platform requires three SAML attributes in every assertion response to provision and map user accounts accurately:

1. `email` (mapped to the user's primary corporate email address, such as `<EMAIL_1>`).
2. `display_name` (mapped to the user's full name or given/surname combination, such as `<NAME_1>`).
3. `nimbus_groups` (optional multi-value attribute used to map corporate directory groups to Nimbus Cloud Platform RBAC roles such as `Tenant Owner`, `Billing Administrator`, or `Infrastructure Operator`).

To require MFA verification status in the SAML assertion for Nimbus Support T2 step-up authentication, ensure your Identity Provider includes `<AuthnContextClassRef>urn:oasis:names:tc:SAML:2.0:ac:classes:TimeSyncToken</AuthnContextClassRef>` or `urn:oasis:names:tc:SAML:2.0:ac:classes:MultiFactor` in the SAML `AuthnStatement`.

## Configuring OpenID Connect (OIDC) on Nimbus Cloud Platform

### OIDC client registration and discovery URL

To configure OIDC SSO on Nimbus Cloud Platform, navigate to **Organization Settings > Security > Single Sign-On**, select **OpenID Connect (OIDC)**, and supply your Identity Provider's `.well-known/openid-configuration` issuer URL along with the Client ID and Client Secret:

- **Redirect Callback URI:** `https://auth.nimbuscloud.example.com/oidc/callback/<TENANT_SLUG>`
- **Required Scopes:** `openid email profile groups`
- **Expected Claims:** `sub`, `email`, `email_verified: true`, and `amr` (Authentication Methods References containing `mfa`, `otp`, or `hwk` to satisfy Nimbus Cloud Platform T2 verification requirements).

## Enforcing SSO-only login and break-glass recovery

### Enabling strict SSO enforcement for a Nimbus Cloud Platform tenant

Once you have tested your SAML 2.0 or OIDC connection using the **Test SSO Connection** button in the Nimbus Cloud Platform console, you can toggle **Enforce SSO-Only Login**. When SSO-Only Login is active, password-based authentication is disabled for all standard users in your tenant, and all CLI sessions (`nimbus auth login --sso`) redirect through your Identity Provider.

### Break-glass Tenant Owner recovery when an IdP certificate expires

If your corporate SAML signing certificate expires or your OIDC client secret rotates without updating Nimbus Cloud Platform, users will receive `Error SSO_SIGNATURE_INVALID` or `Error OIDC_TOKEN_EXCHANGE_FAILED`. Designated Tenant Owners can bypass a misconfigured IdP using the break-glass login path at `https://auth.nimbuscloud.example.com/recovery/owner-login` by providing their local recovery password and a valid hardware FIDO2 key or TOTP code.
