---
doc_id: kb-runbook-db-connection-limits
title: Nimbus DB runbook: diagnosing connection limit exhaustion and PgBouncer pooling
source_system: runbooks
source_kind: operational
audience: internal
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-08-14
intents: [TECHNICAL_OUTAGE]
test_case: conflict
---

# Nimbus DB runbook: diagnosing connection limit exhaustion and PgBouncer pooling

## Symptoms of connection exhaustion on Nimbus DB

When a **Nimbus DB** managed PostgreSQL cluster reaches its configured backend connection ceiling, client applications and **Nimbus Run** microservices fail to establish new database sessions and log the following PostgreSQL error:

```text
FATAL: remaining connection slots are reserved for non-replication superuser connections (SQLSTATE 53300)
```

Because connection exhaustion caused by unpooled client connections or idle transaction leaks is a customer workload configuration issue, downtime resulting from `SQLSTATE 53300` is excluded from monthly SLA uptime credit calculations unless caused by an underlying Nimbus control-plane proxy defect.

## Default `max_connections` limits by Nimbus DB instance class

Nimbus DB provisions PostgreSQL clusters with pre-tuned `max_connections` settings scaled to the instance RAM tier, reserving 15 connection slots for internal `nimbus_admin` health probes and replication streams. Under the **Nimbus DB Standard Memory Allocation Profile**, the default limits are:

| Nimbus DB Instance Class | vCPU / Memory | Default Direct PostgreSQL `max_connections` | Built-in PgBouncer Max Client Connections |
| :--- | :--- | :--- | :--- |
| `db.m6.medium` | 2 vCPU / 4 GB RAM | **200 connections** | **1,000 client connections** |
| **`db.m6.large`** | **4 vCPU / 8 GB RAM** | **400 connections** | **2,000 client connections** |
| **`db.m6.xlarge`** | **8 vCPU / 16 GB RAM** | **800 connections** | **2,000 client connections** |
| `db.m6.2xlarge` | 16 vCPU / 32 GB RAM | **1,600 connections** | **4,000 client connections** |

*(Note: On a standard `db.m6.large` 8 GB RAM instance, the direct PostgreSQL `max_connections` ceiling is strictly **400 connections**, and the managed PgBouncer connection pooler accepts up to **2,000 client connections**).*

## Step-by-step diagnosis and mitigation runbook

### Step 1: Inspect active and idle-in-transaction connections

1. Connect to the Nimbus DB cluster over the reserved administrative diagnostic channel (`port 5432`) using `nimbus db psql`:

```bash
# Open an administrative psql diagnostic session and group connections by state and application
nimbus db psql --cluster <CLUSTER_NAME> --region <REGION> --admin-slot << 'EOF'
SELECT state, application_name, usename, count(*)
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
GROUP BY state, application_name, usename
ORDER BY count(*) DESC;
EOF
```

2. Check whether connections are piling up in `idle in transaction` (indicating uncommitted application transactions) or `idle` (indicating unpooled serverless functions or excessive ORM pool sizes across Nimbus Run replicas).

### Step 2: Terminate leaked `idle in transaction` backends

1. After confirming with a **Tier 2 (T2)** verified `Infrastructure Operator` or `Tenant Owner`, terminate leaked sessions that have been stuck in `idle in transaction` for more than 5 minutes:

```bash
nimbus db psql --cluster <CLUSTER_NAME> --region <REGION> --admin-slot << 'EOF'
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle in transaction'
  AND state_change < now() - interval '5 minutes'
  AND usename <> 'nimbus_admin';
EOF
```

### Step 3: Enable and route traffic through managed PgBouncer (`port 6432`)

1. Enable the built-in Nimbus DB PgBouncer proxy in `transaction` pooling mode so up to **2,000 client connections** on `db.m6.large` are multiplexed over a default pool size of 60 backend PostgreSQL connections:

```bash
# Enable managed PgBouncer transaction pooling on the Nimbus DB cluster
nimbus db pooler update \
  --cluster <CLUSTER_NAME> \
  --mode transaction \
  --default-pool-size 60 \
  --max-client-conn 2000
```

2. Instruct the customer to update their application connection URI from direct PostgreSQL port `5432` to the PgBouncer endpoint port **`6432`**.
