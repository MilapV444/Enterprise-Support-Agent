---
doc_id: kb-ticket-root-credential-reset-t2
title: Resolved ticket: Emergency root credential rotation on srv-alpha-12 after T2 step-up
source_system: tickets
source_kind: ticket
audience: internal
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-10-10
intents: [PASSWORD_RESET]
test_case: none
---

# Resolved ticket: Emergency root credential rotation on srv-alpha-12 after T2 step-up

## Case metadata and problem summary

- **Ticket ID:** `TCK-2026-86915`
- **Tenant Organization:** `Acme Retail` (US Region `us-east-1`, Enterprise Plan)
- **Requester Contact:** `<NAME_1>` (`<EMAIL_1>`, Phone: `<PHONE_1>`, Role: `Infrastructure Operator`)
- **Affected Resource:** Managed compute instance `srv-alpha-12` (`us-east-1a`)

### Reported problem description

Systems engineer `<NAME_1>` initiated a web chat stating: *"Please reset the root credentials on instance srv-alpha-12 right away—our former lead admin left the company yesterday and rotated the SSH authorized_keys before departing."* At the start of the chat session, `<NAME_1>` had only completed **Tier 1 (T1)** verification using a 6-digit one-time email code sent to `<EMAIL_1>`.

## Root cause and security policy enforcement

### Why the request was blocked at Tier 1 (T1)

In accordance with `kb-policy-internal-identity-verification` and `kb-runbook-instance-credential-rotation`:

1. Tier 1 (T1) email OTP verification only authorizes reading one's own tickets and basic non-sensitive account metadata.
2. Support must **never** reset instance root credentials or modify billing for a T0 or T1 user.
3. Resetting root credentials on `srv-alpha-12` strictly requires **Tier 2 (T2)** authentication (Corporate SSO with Multi-Factor Authentication enforced) plus confirmation of the `Tenant Owner` or `Infrastructure Operator` RBAC role.

## Resolution steps executed

### Step-up authentication from T1 to T2 and Vault one-time link delivery

1. Cloud Support Engineer `<NAME_2>` explained the Tier 2 security requirement to `<NAME_1>` and triggered an in-chat **T2 Step-Up Verification Challenge**:

```bash
nimbus-support-cli auth step-up --target-tier T2 --tenant acme-retail-us
```

2. `<NAME_1>` completed the SAML 2.0 SSO login with a hardware FIDO2 security key (`amr: ["hwk", "mfa"]`). The support console confirmed `verification_tier: T2` and verified `<NAME_1>`'s RBAC role as `Infrastructure Operator` on tenant `acme-retail-us`.
3. Following `kb-runbook-instance-credential-rotation` and `kb-policy-internal-support-data-handling`, `<NAME_2>` executed the root credential rotation on `srv-alpha-12` using a 15-minute one-time Vault link (never pasting plaintext credentials into the ticket):

```bash
# Verify guest agent status on srv-alpha-12
nimbus compute instance describe srv-alpha-12 \
  --tenant-id tnt_01H9ACMERETAIL \
  --region us-east-1 \
  --query "{Instance:name,Status:status,GuestAgent:guest_agent_status}"

# Rotate root credentials and revoke any lingering SSH sessions from the departed admin
nimbus compute rotate-root-creds \
  --instance srv-alpha-12 \
  --tenant-id tnt_01H9ACMERETAIL \
  --region us-east-1 \
  --auth-tier-verified T2 \
  --revoke-existing-ssh-sessions \
  --delivery-mode vault-one-time-link \
  --ttl 15m
```

4. `<NAME_1>` opened the single-use Vault URL, signed in to `srv-alpha-12`, installed the team's new SSH certificate authority key, and confirmed full administrative restoration.
