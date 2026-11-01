---
doc_id: kb-runbook-instance-credential-rotation
title: Instance root and admin credential rotation runbook with mandatory T2 verification
source_system: runbooks
source_kind: operational
audience: internal
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-09-26
intents: [PASSWORD_RESET, TECHNICAL_OUTAGE]
test_case: none
---

# Instance root and admin credential rotation runbook with mandatory T2 verification

## Security policy gate: Mandatory Tier 2 (T2) identity verification

Resetting or rotating the `root` operating-system credentials or primary administrative SSH/database keys on any tenant compute or database instance (for example, `srv-alpha-12`) is a **Tier 2 (T2) privileged security operation**. Under the **Nimbus Internal Identity Verification Policy**:

- **NEVER execute this runbook for a Tier 0 (anonymous) or Tier 1 (email OTP code only) requester.**
- If the requester is currently at **T0** or **T1**, stop immediately and trigger a **T2 Step-Up Verification Challenge** requiring the user to authenticate via their organization's **Corporate SSO (SAML 2.0 / OIDC) with Multi-Factor Authentication (MFA)** (or local console login + FIDO2/TOTP MFA for non-SSO Starter tenants).
- Confirm that the authenticated T2 user holds either the **`Tenant Owner`** or **`Infrastructure Operator`** RBAC role on the exact tenant that owns the target instance (`srv-alpha-12`). Users holding `Billing Administrator`, `POS Store Manager`, or `Read-Only Auditor` roles are not authorized to reset instance root credentials.

## Step-by-step instance root credential rotation procedure

Once `verification_tier: T2` and RBAC authorization (`Tenant Owner` or `Infrastructure Operator`) are verified in the support console, either guide the customer to run the self-service CLI rotation or execute the ephemeral Vault-backed rotation workflow below.

### Step 1: Verify instance ownership, state, and hypervisor agent health

1. Confirm that the target instance (for example, `srv-alpha-12`) belongs to the authenticated `tenant_id` and that the guest host agent (`nimbus-guest-agent`) is online:

```bash
# Verify instance ownership and guest agent heartbeat for srv-alpha-12
nimbus compute instance describe srv-alpha-12 \
  --tenant-id <TENANT_ID> \
  --region <REGION> \
  --query "{Instance:name,Status:status,GuestAgent:guest_agent_status,OwnerTenant:tenant_id}"
```

2. Ensure `Status` is `RUNNING` and `GuestAgent` is `CONNECTED_HEALTHY`.

### Step 2: Trigger ephemeral root credential rotation via `nimbus compute rotate-root-creds`

1. Run the credential rotation command. In accordance with the **Internal Support Data Handling Policy**, **never** generate or paste a plaintext password into the ticket or web chat. Always use the `--delivery-mode vault-one-time-link` flag so the rotated credential or temporary SSH certificate is sealed inside a single-use, 15-minute KMS-encrypted Vault URL delivered directly to the authenticated T2 user's console session:

```bash
# Rotate root credentials on instance srv-alpha-12 and issue a 15-minute one-time Vault secret link
nimbus compute rotate-root-creds \
  --instance srv-alpha-12 \
  --tenant-id <TENANT_ID> \
  --region <REGION> \
  --auth-tier-verified T2 \
  --revoke-existing-ssh-sessions \
  --delivery-mode vault-one-time-link \
  --ttl 15m
```

### Step 3: Customer retrieval and mandatory password/key update

1. Provide the returned `https://vault.nimbuscloud.example.com/v1/secret/once/<TOKEN>` URL to the T2-verified user. That URL can only be opened once by the authenticated T2 session and self-destructs after reading or after **15 minutes**.
2. Instruct the customer to sign in to `srv-alpha-12`, install their updated permanent SSH public key in `/root/.ssh/authorized_keys` (or update their IAM OS-Login binding), and verify access:

```bash
# Customer verification command from their workstation
nimbus compute ssh srv-alpha-12 --region <REGION> -- "id && uptime"
```

## Step 4: Audit logging and post-rotation verification

Confirm that the control-plane security audit log records event `INSTANCE_ROOT_CREDENTIAL_ROTATED` along with the requester's T2 SSO subject ID and support ticket number.
