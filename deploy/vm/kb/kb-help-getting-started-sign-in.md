---
doc_id: kb-help-getting-started-sign-in
title: Getting started with Nimbus Cloud Platform and signing in
source_system: helpcenter
source_kind: curated
audience: customer_visible
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-09-10
intents: [GENERAL_INQUIRY, PASSWORD_RESET]
test_case: none
---

# Getting started with Nimbus Cloud Platform and signing in

## Overview of Nimbus Cloud Platform tenant accounts

Nimbus Cloud Platform is a multi-tenant infrastructure platform operated by Nimbus Systems, Inc. for business organizations in the United States (US) and European Union (EU) regions. Every customer organization on Nimbus Cloud Platform is provisioned as an isolated logical tenant identified by a unique Tenant Slug (for example, `acme-retail-us` or `globex-corp-eu`) and an immutable Tenant ID (such as `tnt_01H9X8K2M4P`). Within a Nimbus Cloud Platform tenant, administrators can deploy managed PostgreSQL-compatible relational databases through Nimbus DB, container orchestration clusters through Nimbus Run, isolated virtual private networks through Nimbus Net, and retail store payment gateways through Nimbus POS Gateway.

### Regional console URLs and tenant routing

Nimbus Cloud Platform enforces strict regional control-plane separation between US and EU customer tenants. Administrators and operators must sign in through the regional web console endpoint that matches their assigned Nimbus Cloud Platform residency region, or use the global tenant router at `https://console.nimbuscloud.example.com`:

- **US Region Console (`us-east-1` and `us-west-2`):** `https://us.console.nimbuscloud.example.com`
- **EU Region Console (`eu-central-1` and `eu-west-1`):** `https://eu.console.nimbuscloud.example.com`
- **CLI and Terraform Auth Endpoint:** `https://auth.nimbuscloud.example.com/v2/token`

When signing in at the global Nimbus Cloud Platform login screen, enter your corporate email address (`<EMAIL_1>`) and your organization's Tenant Slug. The Nimbus Cloud Platform router automatically redirects your browser session to the correct regional identity provider or password prompt.

## Signing in to Nimbus Cloud Platform for the first time

### Accepting a Nimbus Cloud Platform administrator invitation

When a new business tenant is provisioned on Nimbus Cloud Platform, the primary technical contact receives an activation email from `no-reply@notifications.nimbuscloud.example.com` with the subject line `Activate your Nimbus Cloud Platform tenant`. That invitation link remains valid for 72 hours from the timestamp of generation.

1. Open the activation link in a modern TLS 1.3-compatible browser.
2. Verify that the displayed Tenant Slug matches your organization identifier.
3. Choose an authentication method: either create a Nimbus Cloud Platform local password (minimum 14 characters, requiring uppercase, lowercase, numeric, and symbol characters) or bind your account to an already configured Enterprise Single Sign-On (SSO) identity provider.
4. Complete mandatory Multi-Factor Authentication (MFA) enrollment using a FIDO2 hardware security key or a Time-based One-Time Password (TOTP) authenticator application before accessing the Nimbus Cloud Platform dashboard.

### Role-based access control (RBAC) roles on Nimbus Cloud Platform

Every user account inside a Nimbus Cloud Platform tenant is assigned one or more pre-defined RBAC roles that govern what resources the user can view or modify and what actions Nimbus Support can perform on their behalf:

- **Tenant Owner:** Full administrative control over Nimbus DB, Nimbus Run, Nimbus Net, Nimbus POS Gateway, IAM policies, billing contracts, and subscription cancellations.
- **Billing Administrator:** Access to invoices, payment methods, tax certificates, usage quotas, and subscription tier upgrades or downgrades under **Organization Settings > Billing & Plan**.
- **Infrastructure Operator:** Full read/write permissions for Nimbus DB clusters, Nimbus Run workloads, Nimbus Net VPC subnets, and Terraform state locks, without access to billing invoices.
- **POS Store Manager:** Scoped operational permissions to view Nimbus POS Gateway terminal status, rotate store pairing tokens, and inspect register connectivity logs.
- **Read-Only Auditor:** View-only access to infrastructure configurations, SLA uptime reports, and audit logs without mutation capabilities.

## Troubleshooting common Nimbus Cloud Platform sign-in errors

### Error `AUTH_TENANT_MISMATCH` during console login

If the Nimbus Cloud Platform sign-in screen displays `Error AUTH_TENANT_MISMATCH: User is not registered in this regional control plane`, verify that you entered the exact Tenant Slug assigned to your organization and that you are not attempting to authenticate an EU-hosted tenant against the US direct portal (`https://us.console.nimbuscloud.example.com`). Users who belong to multiple tenants (such as a staging tenant and a production tenant) must specify the exact target Tenant Slug during sign-in.

### Expired invitation links and session timeouts

If your 72-hour Nimbus Cloud Platform invitation token has expired, an existing Tenant Owner can issue a fresh invitation from **Organization Settings > Users & Roles > Resend Invite**. By default, interactive Nimbus Cloud Platform web console sessions expire after 12 hours of activity or 30 minutes of inactivity. Enterprise tenants can customize idle session timeouts between 15 minutes and 8 hours under **Organization Settings > Security > Session Policy**.
