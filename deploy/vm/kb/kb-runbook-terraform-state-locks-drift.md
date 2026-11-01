---
doc_id: kb-runbook-terraform-state-locks-drift
title: Nimbus Terraform provider troubleshooting: state locks, drift, and terraform state rm
source_system: runbooks
source_kind: operational
audience: internal
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-09-27
intents: [TECHNICAL_OUTAGE, GENERAL_INQUIRY]
test_case: none
---

# Nimbus Terraform provider troubleshooting: state locks, drift, and terraform state rm

## Differentiating Terraform state locks from Nimbus Net VPC subnet locks

When troubleshooting failures with the official **Nimbus Terraform Provider (`registry.terraform.io/nimbus-systems/nimbus`, v2.8+)**, engineers must first distinguish between two different lock types:

1. **Nimbus Net Server-Side Resource Locks (`HTTP 409 Conflict: ERR_VPC_SUBNET_CIDR_LOCKED`):** The Terraform state file itself is unlocked, but the Nimbus Net IPAM API rejects `nimbus_db_cluster` or `nimbus_run_cluster` subnet binding because a stale subnet lease holds the CIDR lock. **Do NOT use `terraform force-unlock` or `terraform state rm` for a 409 VPC subnet bind error**—follow runbook `kb-runbook-net-vpc-subnet-409-conflict` (`nimbus net subnet-locks release`) instead.
2. **Terraform Backend State File Locks (`Error acquiring the state lock`):** A previous CI/CD pipeline crashed while holding the remote state lock in the Nimbus Terraform State Backend (`nimbus://tfstate/<TENANT_ID>/<WORKSPACE>`).

## Step-by-step resolution for stuck Terraform state locks

### Step 1: Verify that no active CI/CD job is currently running `terraform apply`

Before unlocking a Terraform state file, verify with the customer's engineering team and inspect the active lock metadata to confirm that another runner is not actively mutating infrastructure:

```bash
# Inspect the current remote Terraform state lock metadata in Nimbus State Backend
nimbus tfstate lock-info \
  --workspace <WORKSPACE_NAME> \
  --region <REGION>
```

### Step 2: Release the stuck backend state lock using `terraform force-unlock`

Once confirmed that the lock owner process is dead, run `terraform force-unlock` with the `LOCK_ID` displayed in the error output:

```bash
# Release the orphaned Terraform backend state lock
terraform force-unlock <LOCK_ID>
```

## Reconciling infrastructure drift on Nimbus Cloud Platform

If a team member modified a Nimbus DB firewall rule, Nimbus Run node count, or VPC route manually via the web console outside of Terraform, subsequent plans will show unexpected diffs or fail with `ERR_RESOURCE_VERSION_MISMATCH`.

### Step-by-step non-destructive drift reconciliation

1. Run a refresh-only plan to inspect the exact discrepancy between the remote Nimbus Cloud Platform API and the `.tfstate` file:

```bash
terraform plan -refresh-only
```

2. If the console changes are intentional and should be adopted into Terraform state, apply the refresh and update the `.tf` HCL files to match:

```bash
terraform apply -refresh-only
```

## When to use `terraform state rm` and its critical operational risks

### What `terraform state rm` does

The command `terraform state rm <RESOURCE_ADDRESS>` removes a resource record from Terraform's state tracking file **without destroying the underlying live resource on Nimbus Cloud Platform**.

### Risks of running `terraform state rm` in production

- **Orphaned Unmanaged Production Infrastructure:** Once removed from state, Terraform forgets that the cluster or VPC subnet exists. If an engineer leaves the `resource "nimbus_db_cluster" "..."` block inside their `.tf` files and runs `terraform apply` after running `terraform state rm`, Terraform will attempt to create a **duplicate cluster with the same name/CIDR**, failing with `409 Conflict` or accruing double billing charges.
- **Safe Re-Import Pattern:** Only use `terraform state rm` when moving a resource between workspaces or refactoring module paths, and **immediately follow it with `terraform import`** so the live resource remains tracked:

```bash
# Always create a backup of state before removing and re-importing a resource address
terraform state pull > tfstate_backup_$(date +%Y%m%d_%H%M%S).json
terraform state rm nimbus_db_cluster.legacy_name
terraform import nimbus_db_cluster.new_name dbc_01J4K9L2M
```
