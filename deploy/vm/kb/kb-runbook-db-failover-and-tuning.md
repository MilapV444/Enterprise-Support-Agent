---
doc_id: kb-runbook-db-failover-and-tuning
title: Nimbus DB runbook: multi-AZ failover, slow queries, backup restore, and tuning
source_system: runbooks
source_kind: operational
audience: internal
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-08-19
intents: [TECHNICAL_OUTAGE]
test_case: conflict
---

# Nimbus DB runbook: multi-AZ failover, slow queries, backup restore, and tuning

## Overview of Nimbus DB operational recovery procedures

This internal engineering runbook covers four critical operational tasks for **Nimbus DB** managed PostgreSQL clusters across the US and EU regions: (1) connection parameter tuning, (2) executing or troubleshooting a Multi-AZ high-availability failover, (3) diagnosing and cancelling slow queries causing CPU/IO saturation, and (4) performing a Point-in-Time Recovery (PITR) restore from backup.

## Connection parameter baseline and memory guardrails

To prevent Linux kernel out-of-memory kills on PostgreSQL backend processes during heavy sorting and hash-join workloads, Nimbus DB enforces conservative default `max_connections` ceilings across instance classes:

| Nimbus DB Instance Class | vCPU / Memory | Default Direct PostgreSQL `max_connections` | Built-in PgBouncer Max Client Connections |
| :--- | :--- | :--- | :--- |
| `db.m6.medium` | 2 vCPU / 4 GB RAM | **125 connections** | **2,500 client connections** |
| **`db.m6.large`** | **4 vCPU / 8 GB RAM** | **250 connections** | **5,000 client connections** |
| **`db.m6.xlarge`** | **8 vCPU / 16 GB RAM** | **500 connections** | **5,000 client connections** |
| `db.m6.2xlarge` | 16 vCPU / 32 GB RAM | **1,000 connections** | **10,000 client connections** |

*(Note: Under this Nimbus DB High-Stability Tuning Baseline, a standard `db.m6.large` 8 GB RAM instance defaults to **250 direct connections** and `db.m6.xlarge` defaults to **500 direct connections**, while PgBouncer supports up to **5,000 client connections**).*

## Procedure 1: Executing or verifying a Multi-AZ failover

### Step-by-step manual or stuck-failover remediation

On Growth and Enterprise multi-AZ clusters, synchronous standby replicas run in a secondary Availability Zone (for example, `eu-central-1b` backing up `eu-central-1a`). Automatic failover typically completes within **25 to 45 seconds**. If a primary node suffers degraded NVMe disk latency without triggering a hard heartbeat loss, a Tier 2 verified operator or SRE can trigger a controlled switchover:

1. Check replication lag and standby readiness before initiating failover:

```bash
nimbus db ha-status --cluster <CLUSTER_NAME> --region <REGION>
```

2. Confirm `replication_state: STREAMING_SYNC` and `replay_lag_bytes: 0`, then execute a controlled switchover:

```bash
# Trigger controlled Multi-AZ switchover to the synchronous standby node
nimbus db failover-cluster \
  --cluster <CLUSTER_NAME> \
  --region <REGION> \
  --mode controlled-switchover
```

## Procedure 2: Diagnosing and cancelling slow queries

1. Query `pg_stat_activity` and `pg_stat_statements` to identify long-running queries holding locks or saturating vCPU:

```bash
nimbus db psql --cluster <CLUSTER_NAME> --region <REGION> --admin-slot << 'EOF'
SELECT pid, now() - query_start AS duration, wait_event_type, state, left(query, 120) AS query_snippet
FROM pg_stat_activity
WHERE state = 'active' AND (now() - query_start) > interval '30 seconds'
ORDER BY duration DESC;
EOF
```

2. Gracefully cancel the offending query with `SELECT pg_cancel_backend(<PID>);` (or use `pg_terminate_backend(<PID>)` if `pg_cancel_backend` does not clear the lock within 10 seconds).

## Procedure 3: Restoring a Nimbus DB cluster from backup (PITR)

Nimbus DB captures daily full snapshots and archives Write-Ahead Log (WAL) segments to regional object storage every 60 seconds, enabling Point-in-Time Recovery (PITR) down to a 1-second granularity within the tenant's retention window (**7 to 35 days**). Restores always create a **new** Nimbus DB cluster and never overwrite the existing source cluster in place:

```bash
# Restore cluster db-prod-west to a specific UTC timestamp into a new cluster
nimbus db restore-pitr \
  --source-cluster db-prod-west \
  --target-cluster db-prod-west-restored-1031 \
  --restore-time "2026-10-30T14:22:00Z" \
  --region us-west-2
```
