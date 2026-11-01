---
doc_id: kb-ticket-terraform-409-subnet-lock
title: Resolved ticket: Terraform 409 Conflict on db-prod-west VPC subnet bind
source_system: tickets
source_kind: ticket
audience: internal
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-10-02
intents: [TECHNICAL_OUTAGE]
test_case: none
---

# Resolved ticket: Terraform 409 Conflict on db-prod-west VPC subnet bind

## Case metadata and problem summary

- **Ticket ID:** `TCK-2026-84102`
- **Tenant Organization:** `Initech Logistics` (US Region `us-west-2`, Enterprise Plan)
- **Requester Contact:** `<NAME_1>` (`<EMAIL_1>`, Phone: `<PHONE_1>`, Role: `Infrastructure Operator`, Verified at **Tier 2** via Okta SAML SSO + MFA)
- **Affected Resource:** Nimbus DB cluster `db-prod-west` and Nimbus Net VPC subnet `subnet-prod-west-01` (`10.42.16.0/24`)

### Reported problem description

Lead infrastructure engineer `<NAME_1>` at `Initech Logistics` contacted Nimbus Support after their production GitLab CI pipeline failed during `terraform apply` while scaling `db-prod-west`. The Terraform output returned:

```text
Error: HTTP 409 Conflict (ERR_VPC_SUBNET_CIDR_LOCKED):
Cannot bind cluster "db-prod-west" to VPC subnet "subnet-prod-west-01" (10.42.16.0/24).
A stale subnet attachment lease (lock_id: cidr-lk-99812a) is still holding the CIDR allocation lock.
```

The engineer initially attempted `terraform force-unlock`, which failed because the Terraform `.tfstate` file itself was not locked.

## Root cause investigation

### Why the stale CIDR lock remained on `subnet-prod-west-01`

Support engineer `<NAME_2>` inspected the regional Nimbus Net IPAM lock table for `Initech Logistics` in `us-west-2`. Roughly 22 minutes earlier, an earlier GitLab CI runner had lost network connectivity mid-execution while resizing `db-prod-west`. When the runner died without closing its API session, the Nimbus Net IPAM controller left subnet lease `cidr-lk-99812a` in state `ORPHANED_PENDING_RELEASE` with `ACTIVE_ENI_COUNT = 0`, blocking any subsequent `terraform apply` from binding `db-prod-west` to `subnet-prod-west-01`.

## Resolution steps executed

### Releasing the orphaned CIDR lock and re-applying Terraform

Following engineering runbook `kb-runbook-net-vpc-subnet-409-conflict`, support confirmed `<NAME_1>`'s **Tier 2 (T2)** SSO + MFA authentication and guided `<NAME_1>` through releasing the stale subnet lease and refreshing Terraform state:

```bash
# 1. Verify that lock cidr-lk-99812a is in ORPHANED_PENDING_RELEASE state with 0 active ENIs
nimbus net subnet-locks list --cluster db-prod-west --region us-west-2 --output table

# 2. Release the stale CIDR lock on subnet-prod-west-01
nimbus net subnet-locks release \
  --cluster db-prod-west \
  --subnet subnet-prod-west-01 \
  --lock-id cidr-lk-99812a \
  --force-cidr-unlock

# 3. Reconcile Terraform state and re-apply the cluster modification
terraform apply -refresh-only -auto-approve
terraform apply -target=nimbus_db_cluster.db_prod_west
```

### Verification and closure

Immediately after `cidr-lk-99812a` was released, `terraform apply` completed in 38 seconds. `nimbus db cluster describe db-prod-west` confirmed `Status: AVAILABLE` and `CidrLockState: BOUND_HEALTHY`.
