---
doc_id: kb-runbook-net-vpc-subnet-409-conflict
title: Nimbus Net runbook: resolving error 409 Conflict during VPC subnet bind
source_system: runbooks
source_kind: operational
audience: internal
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-09-24
intents: [TECHNICAL_OUTAGE]
test_case: none
---

# Nimbus Net runbook: resolving error 409 Conflict during VPC subnet bind

## Symptom and root cause of HTTP 409 Conflict on VPC subnet bind

### Exact error message during `terraform apply`

Infrastructure operators deploying or scaling a **Nimbus DB** cluster (for example, `db-prod-west`) or a **Nimbus Run** node pool inside a **Nimbus Net** Virtual Private Cloud (VPC) encounter the following failure during `terraform apply`:

```text
Error: Provider produced error on nimbus_db_cluster.db_prod_west:
HTTP 409 Conflict (ERR_VPC_SUBNET_CIDR_LOCKED):
Cannot bind cluster "db-prod-west" to VPC subnet "subnet-prod-west-01" (10.42.16.0/24).
A stale subnet attachment lease (lock_id: cidr-lk-99812a) is still holding the CIDR allocation lock.
```

### Root cause of the stale CIDR lock

When a previous `terraform apply` or cluster replacement operation is interrupted mid-flight (due to a client network drop, CI/CD runner timeout, or aborted blue/green database migration), the Nimbus Net IP Address Management (IPAM) controller retains an orphaned `ORPHANED_PENDING_RELEASE` lease on the target subnet's CIDR block. As long as that stale subnet lease holds the CIDR lock, subsequent `terraform apply` runs attempting to bind `db-prod-west` to the subnet fail immediately with `HTTP 409 Conflict (ERR_VPC_SUBNET_CIDR_LOCKED)`.

## Step-by-step diagnosis and remediation procedure

Before executing any state-mutating CLI command on behalf of a customer, ensure the requester is authenticated at **Tier 2 (T2)** (SSO with MFA and `Tenant Owner` or `Infrastructure Operator` role), or provide the exact `nimbus` CLI commands below for the customer engineer to run directly from their authenticated workstation.

### Step 1: Inspect the subnet CIDR lock table in Nimbus Net

1. Authenticate the `nimbus` CLI against the target regional control plane (`us-west-2`, `us-east-1`, `eu-central-1`, or `eu-west-1`).
2. List all active and stale CIDR locks attached to the target subnet (`subnet-prod-west-01`) or cluster (`db-prod-west`):

```bash
# List CIDR locks on the VPC subnet associated with cluster db-prod-west
nimbus net subnet-locks list \
  --cluster db-prod-west \
  --region us-west-2 \
  --output table
```

3. Verify that the output shows a lock entry with `STATE = ORPHANED_PENDING_RELEASE` (or `STALE_LEASE`) and `ACTIVE_ENI_COUNT = 0`. **Never** force-release a lock whose state is `ACTIVE_ATTACHED` with live ENI interfaces.

### Step 2: Release the stale subnet CIDR lock

1. Run `nimbus net subnet-locks release` passing the cluster name (`db-prod-west`), the stale lock ID (or `--release-stale`), and `--force-cidr-unlock` to purge the orphaned IPAM reservation:

```bash
# Release the stale VPC subnet CIDR lock for cluster db-prod-west
nimbus net subnet-locks release \
  --cluster db-prod-west \
  --subnet subnet-prod-west-01 \
  --lock-id cidr-lk-99812a \
  --force-cidr-unlock
```

2. Confirm that the CLI returns `STATUS: CIDR_LOCK_RELEASED (subnet-prod-west-01 is now READY_FOR_BIND)`.

### Step 3: Refresh Terraform state and re-run `terraform apply`

1. Instruct the operator to refresh the local or remote Terraform state so the Nimbus Terraform provider reconciles the cleared subnet lease, then re-run `terraform apply`:

```bash
# Refresh provider state and re-apply the Nimbus DB cluster configuration
terraform apply -refresh-only -auto-approve
terraform apply -target=nimbus_db_cluster.db_prod_west
```

## Verification after re-applying Terraform

### Confirming healthy VPC subnet binding

Run the following verification command to confirm that `db-prod-west` is bound to `subnet-prod-west-01` with status `AVAILABLE` and that no orphaned CIDR locks remain:

```bash
nimbus db cluster describe db-prod-west \
  --region us-west-2 \
  --query "{Cluster:name,Status:status,Subnet:vpc_subnet_id,CidrLockState:cidr_lock_status}"
```

Expected output is `Status: AVAILABLE` and `CidrLockState: BOUND_HEALTHY`.
