# OB-ADP-02: Telemetry Storage Topology, 7-Day Retention & Queryable Erasure (Regional Jaeger/OpenSearch, Correlated JSON Logs & Temporal Deletion Sagas)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-03 *(Confirmed per OB-D2 Regional Jaeger/OpenSearch OB-Q3, OB-D5 7-Day TTL, OB-D6 Queryable Telemetry Erasure & OB-D12 Correlated JSON Logging)*
- **Deciders**: Architecture Team, Principal Data Architect, Lead Observability Engineer, Compliance Officer
- **Component**: `[9] Observability & Monitoring` (`Component [ 9 ]`)
- **Reasoning Source**: `checkpoint.md` §13 · Diagram: `LLD - [9] Observability & Monitoring`
- **Decisions Covered**:
  - `OB-D2`: Regional Tracing Backend Topology — Self-hosted Jaeger backed by OpenSearch clusters deployed independently within each sovereign region (`us-east-1` and `eu-central-1`, `DP-D10`); Grafana Tempo rejected because its immutable Parquet block storage model prohibits single-tenant and single-user deletion queries required for GDPR right-to-be-forgotten compliance (`OB-Q3`)
  - `OB-D5`: Strict 7-Day Telemetry Retention Window — Rolling 7-day time-to-live (TTL) enforced across all trace spans and structured application logs; older telemetry dropped automatically via OpenSearch Index State Management (ISM); eliminates unbounded storage liabilities while bounding privacy risk; long-term compliance preserved via separate 2-year decision and audit records (`SG-D12`, `TA-D12`)
  - `OB-D6`: Queryable Telemetry Erasure Integration — Telemetry stores formally registered in the `MS-D14` erasure inventory; when a user exercises their right to erasure, the `DP-D13` Temporal workflow issues an asynchronous `_delete_by_query` against regional OpenSearch trace and log indices, verifying zero residual records before certification ($KK3$)
  - `OB-D12`: Correlated Structured JSON Logs — Application logs emitted as high-throughput JSON payloads carrying mandatory W3C `trace_id` and `span_id` headers; indexed in regional OpenSearch log clusters with identical 7-day TTL and erasure policies, enabling instantaneous bi-directional pivots between log lines and distributed trace graphs
- **Related Architectural Decision Points**:
  - [`DP-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/07-data-persistence/DP-ADP-01-store-topology-residency.md): Store Topology & Residency *(Regional Sovereign Deployment Boundaries)*
  - [`DP-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/07-data-persistence/DP-ADP-05-erasure-backups-restore.md): Erasure, Backups & Restore *(Temporal Workflow Orchestration)*
  - [`MS-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/03-memory-state/MS-ADP-05-retention-erasure.md): Retention & Erasure *(Full Store Inventory Coverage)*
  - [`SG-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/06-safety-security-governance/SG-ADP-05-governance-retention-providers.md): Governance, Retention & Providers *(Separation from 2-Year Legal Transcripts)*

---

## 1. Context & Problem Statement

Distributed multi-agent systems generate terabytes of operational telemetry. In a high-volume enterprise customer support platform, persisting this data triggers severe architectural tensions between debugging efficiency, storage cost, and statutory privacy mandates:

1. **The Immutable Block vs. Right-to-be-Forgotten Paradox (`OB-Q3`, $KK3$)**:
   - Modern cloud-native tracing backends (such as Grafana Tempo or ClickHouse) achieve high compression by packing spans into massive, immutable columnar chunks (Parquet/blocks) written to object storage (S3/GCS).
   - Under GDPR Art. 17 and CCPA, when an end-user Sarah requests complete data erasure, the platform must purge all personal identifiers associated with her from every persistent store within 30 days (`MS-D14`). Immutable chunk storage engines cannot delete single rows or traces without re-writing entire multi-gigabyte files, making real-time user-targeted erasure impossible ($KK3$).
2. **The Long-Case Horizon vs. Telemetry Lifespan Gap ($UU2$)**:
   - Complex B2B customer support cases involving engineering bug investigations, hardware RMAs, or executive financial disputes can remain open for $14–30\text{ days}$ (`MS-D5`).
   - If operational traces expire after 7 days, debugging a catastrophic failure on Day 12 of a long-running case reveals that the initial diagnostic spans from Day 1 have disappeared.
3. **The Disconnected Log/Trace Island ($KK2$)**:
   - When application logs and distributed traces reside in disconnected silos with disparate query models, investigating an outage requires manual timestamp matching, slowing Mean Time to Detect (MTTD) and Mean Time to Resolve (MTTR).

### The Core Architectural Question
> **How do we construct a sovereign, queryable telemetry storage engine that enforces a strict 7-day storage lifecycle, guarantees seamless bi-directional log-trace correlation, and allows instantaneous right-to-be-forgotten purges by user ID without corrupting columnar storage integrity?**

---

## 2. Decision Framework & Theoretical Formulation

To solve these challenges, `OB-D2`, `OB-D5`, `OB-D6`, and `OB-D12` establish the **Regional OpenSearch Telemetry Engine with Queryable Erasure and 7-Day Rolling Decay Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│             REGIONAL TELEMETRY PERSISTENCE & ERASURE ARCHITECTURE (OB-D2, OB-D5, OB-D6)          │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                        Application Log & Trace Stream
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ REGIONAL OPENSEARCH LOGICAL CLUSTER (Per Region: us-east-1 / eu-central-1, DP-D10)               │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                  │
│   INDEX PATTERN 1: jaeger-span-YYYY.MM.DD (OB-D2)                                                │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ Documents: Spans carrying trace_id, parent_id, tenant_id, user_id, conversation_id       │   │
│   │ Full text search on attributes, tags, and error logs                                     │   │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                                  │
│   INDEX PATTERN 2: app-logs-YYYY.MM.DD (OB-D12)                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ Documents: JSON logs carrying timestamp, level, trace_id, span_id, tenant_id, message    │   │
│   │ Bi-directional correlation: Jaeger UI links directly to OpenSearch Discover logs         │   │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                                  │
│   LIFECYCLE MANAGEMENT: OpenSearch ISM Policy (OB-D5)                                            │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ Day 0-1: Hot Storage (Fast SSD NVMe write/search)                                        │   │
│   │ Day 2-7: Warm Storage (Compressed read-only indices)                                     │   │
│   │ Day 8:   Automatic Physical Deletion: DELETE jaeger-span-YYYY.MM.DD                      │   │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────┬───────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ASYNCHRONOUS ERASURE INTEGRATION (DP-D13, OB-D6)                                                 │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ When Sarah requests erasure: Temporal Activity executes asynchronous Delete-by-Query:            │
│    POST /jaeger-span-*,app-logs-*/_delete_by_query                                               │
│    { "query": { "term": { "user_id": "usr_98" } } }                                           │
│ ===> All traces and logs purged across all live daily indices within seconds                     │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Pillar 1: Regional Jaeger with OpenSearch Backend (`OB-D2`, `OB-Q3`)

To guarantee full compliance with right-to-be-forgotten mandates, we deploy **Jaeger backed by distributed OpenSearch**:
1. **The Technical Rejection of Grafana Tempo (`OB-Q3`)**:
   - Grafana Tempo stores traces in immutable block archives in object storage. Deleting a single trace requires a full compactor rewrite of the entire block or waiting for block expiration.
   - OpenSearch treats every span as an independently indexed document, supporting near-instantaneous delete-by-query operations:
     ```http
     POST /jaeger-span-*/_delete_by_query
     ```
2. **Strict Sovereign Residency (`DP-D10`)**:
   - Each sovereign deployment region maintains an independent, non-federated OpenSearch cluster.
   - European tenant telemetry resides in `eu-central-1` OpenSearch; US telemetry resides in `us-east-1` OpenSearch. No telemetry is replicated cross-region.

---

### Pillar 2: 7-Day Index State Management (ISM) Retention (`OB-D5`)

To prevent telemetry storage costs from dominating infrastructure spend while minimizing privacy exposure:
1. **Daily Index Rolling**:
   - Spans and logs are partitioned into daily indices: `jaeger-span-YYYY.MM.DD` and `app-logs-YYYY.MM.DD`.
2. **Automated ISM Purge Pipeline**:
   - OpenSearch Index State Management (ISM) executes an automated lifecycle policy:
     $$\text{Age}(\text{Index}) \ge 7 \text{ days} \implies \text{Action: DELETE}$$
   - When an index reaches 7 days of age, OpenSearch drops the entire Lucene index directory atomically from disk. Dropping entire indices incurs zero Lucene segment merging overhead and instantly reclaims disk storage.
3. **The Long-Case Hand-off ($UU2$)**:
   - We accept that debugging spans older than 7 days will expire ($UU2$).
   - Critical case history is not lost because permanent, auditable operational facts are preserved in separate, durable stores:
     - The **Decision Record Store** (`SG-D13`, `DP-D3`): Retains exact model, prompt, and "why" reasoning indefinitely.
     - The **Tool Audit Store** (`TA-D12`, `DP-D3`): Retains financial before/after deltas indefinitely.
     - The **Transcript Legal Archive** (`SG-D12`, `DP-D8`): Retains complete verbatim dialogues for 2 years.

---

### Pillar 3: Temporal Saga Erasure Integration (`OB-D6`)

When an end-user exercises their right to erasure, telemetry cannot be left to expire naturally if the statutory deadline is imminent. Telemetry deletion is orchestrated directly within the `DP-D13` Temporal saga:

#### Execution Protocol
1. **Activity Dispatch**:
   Activity 6 of the `DistributedErasureWorkflow` issues a task against the regional OpenSearch cluster:
   ```json
   {
     "query": {
       "bool": {
         "filter": [
           { "term": { "tenant_id": "ten_acme_01" } },
           { "term": { "user_id": "usr_98" } }
         ]
       }
     }
   }
   ```
2. **Asynchronous Polling & Verification**:
   The Temporal worker polls the OpenSearch task API (`_tasks/{task_id}`) with exponential backoff until completion.
3. **Affirmative Verification Gate**:
   A verification query asserts that `_count` of documents matching `user_id == "usr_98"` across all active indices equals exactly 0:
   $$\text{Count}(\text{OpenSearch}, \text{"usr\_98"}) \equiv 0$$

---

### Pillar 4: Trace-Correlated Structured JSON Logging (`OB-D12`)

Application logs and distributed traces are unified via standardized structured formatting:
1. **Mandatory W3C Context Injection**:
   Every log statement emitted by Python's `structlog` or `logging` library injects current trace context into the JSON payload:
   ```json
   {
     "timestamp": "2026-10-03T14:22:01.104Z",
     "level": "INFO",
     "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
     "span_id": "00f067aa0ba902b7",
     "tenant_id": "ten_acme_01",
     "logger": "orchestrator.coordinator",
     "message": "Delegating case INV-9821 to billing specialist"
   }
   ```
2. **Unified Navigation**:
   In the Jaeger UI, every span embeds an external deep-link to OpenSearch Dashboards filtered by `trace_id == {trace_id}`, allowing developers to inspect full application logs corresponding to that exact span with one click.

---

## 3. Data Contracts & Execution Invariants

### 3.1 Telemetry Erasure Request & Result Contracts

```python
from datetime import datetime
from typing import List
from pydantic import BaseModel, Field

class TelemetryErasureTarget(BaseModel):
    """
    Contract for invoking targeted telemetry deletion in OpenSearch (OB-D6).
    """
    erasure_job_id: str = Field(..., regex=r"^ers_[a-zA-Z0-9]{16}$")
    tenant_id: str = Field(..., regex=r"^ten_[a-zA-Z0-9]{16}$")
    user_id: str = Field(..., regex=r"^usr_[a-zA-Z0-9]{16}$")
    target_indices: List[str] = Field(
        default=["jaeger-span-*", "app-logs-*"],
        description="OpenSearch index patterns targeted for purge"
    )

class TelemetryErasureResult(BaseModel):
    erasure_job_id: str
    spans_deleted_count: int = Field(..., ge=0)
    log_lines_deleted_count: int = Field(..., ge=0)
    execution_duration_ms: int = Field(..., ge=0)
    verified_residual_count: int = Field(default=0, description="Invariant: Must be 0")
    completed_at_utc: datetime = Field(default_factory=datetime.utcnow)
```

### 3.2 OpenSearch Index State Management (ISM) Policy (`7-day-telemetry-ttl.json`)

```json
{
  "policy": {
    "description": "Enforces rolling 7-day TTL across telemetry indices (OB-D5)",
    "default_state": "hot",
    "states": [
      {
        "name": "hot",
        "actions": [],
        "transitions": [
          {
            "state_name": "delete",
            "conditions": {
              "min_index_age": "7d"
            }
          }
        ]
      },
      {
        "name": "delete",
        "actions": [
          {
            "delete": {}
          }
        ],
        "transitions": []
      }
    ]
  }
}
```

---

## 4. Quantitative Failure Modes & Operational Risk Bounds

| Failure Mode ID | Sub-Component & Severity | Risk Classification | Empirical Trigger Condition | Detection Vector | Automated Mitigation & Architectural Enforcement |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **OB-FM-201** | Telemetry Erasure (`OB-D6`)<br>**CRITICAL** | Q1 Known Known (Compliance Breach) | Delete-by-query fails due to OpenSearch version conflict or cluster timeout ($KK3$). | OpenSearch client returns HTTP 409 Conflict or 504 Gateway Timeout. | **Temporal Activity Retry Sagas (`DP-D13`)**: Activity executes with exponential backoff up to 24 hours until verification query returns zero. |
| **OB-FM-202** | Storage Saturation (`OB-D5`)<br>**HIGH** | Q1 Known Known (Infrastructure Failure) | ISM policy execution daemon stalls, causing indices older than 7 days to accumulate and fill disk. | Prometheus node disk utilization alert exceeds $85\%$. | **Emergency Cron Pruner**: Secondary independent cron container queries OpenSearch cluster for indices older than 8 days and issues hard `DELETE` via REST API. |
| **OB-FM-203** | Long-Case Span Loss (`OB-D5`)<br>**MEDIUM** | Q2 Known Unknown (Operational Blindspot) | Engineer attempts to debug a 10-day-old unresolved ticket, finding that turn 1 traces have expired ($UU2$). | Jaeger UI returns zero trace results for `conversation_id`. | **Fallback to Durable Decision Records**: Engineer runbook directs investigation to `decision_records` table (`SG-D13`), which stores durable "why" reasoning. |
| **OB-FM-204** | Index Mapping Explosion (`OB-D12`)<br>**HIGH** | Q3 Unknown Known (Tacit Convention) | Developers log dynamic user-supplied dictionaries in JSON logs, creating thousands of distinct fields in OpenSearch. | OpenSearch cluster alert on `Limit of total fields [1000] has been exceeded`. | **Dynamic Mapping Disabling**: Index template configures `"dynamic": "runtime"` or `"dynamic": false`, forcing unmapped fields into an unindexed JSON payload. |
| **OB-FM-205** | Regional Storage Drift (`OB-D2`)<br>**CRITICAL** | Q4 Unknown Unknown (Residency Breach) | OpenSearch snapshot repository misconfigured to replicate indices to a US S3 bucket for EU cluster. | CloudTrail / IAM monitor detects cross-region S3 replication on telemetry buckets. | **Regional SCP Hard Blocks (`DP-D10`)**: AWS Service Control Policies forbid cross-region snapshot registration for telemetry OpenSearch clusters. |

---

## 5. Closed-Loop Architectural Feedback

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   TELEMETRY STORAGE & RETENTION HEALTH ENGINE                                    │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Daily OpenSearch ISM Execution
                 │
                 ▼
   ┌─────────────────────────────┐
   │ 7-Day Prune Policy Evaluator│─────► [Metric: telemetry_indices_dropped_total]
   │ (Deletes Indices > 7 Days)  │       Monitors storage reclamation
   └─────────────┬───────────────┘
                 │
                 ▼
   ┌─────────────────────────────┐
   │ Cluster Disk Watermark Check│─────► [Metric: opensearch_disk_used_percent]
   │ (Tracks NVMe Capacity)      │       Alerts at > 75% utilization
   └─────────────┬───────────────┘
                 │
                 ├──────────────────────────────────────────────┐
                 ▼                                              ▼
   ┌─────────────────────────────┐               ┌─────────────────────────────┐
   │ Temporal Erasure Listener   │               │ Index Field Count Monitor   │
   │ (Executes Delete-by-Query)  │               │ (Guards against explosions) │
   └─────────────┬───────────────┘               └──────────────┬──────────────┘
                 │                                              │
                 ▼                                              ▼
   [Metric: telemetry_erasure_tasks_total]       [Metric: opensearch_total_fields_count]
   Asserts 100% success on RTBF tasks            Ceiling: 500 fields max
```

### Telemetry & Operational SLOs
1. **Telemetry Erasure Completion Latency**:
   - Metric: `opensearch_delete_by_query_duration_seconds`
   - SLO: $p95 < 15\text{ seconds}$, $p99 < 45\text{ seconds}$.
2. **Verification Gate Failure Rate**:
   - Residual documents found post-erasure: **Strictly 0**.
3. **Retention Adherence Window**:
   - Oldest index surviving in live cluster: $\le 7.5\text{ days}$.

---

## 6. Genesis Implementation Directive & Verification Protocol

### 6.1 Telemetry Erasure Activity Implementation (Temporal Worker)

```python
import asyncio
from opensearchpy import AsyncOpenSearch
from temporalio import activity

class OpenSearchTelemetryErasureActivity:
    def __init__(self, opensearch_client: AsyncOpenSearch):
        self.client = opensearch_client

    @activity.defn
    async def purge_telemetry_by_user_id(self, target: TelemetryErasureTarget) -> TelemetryErasureResult:
        """
        Executes queryable right-to-be-forgotten erasure across OpenSearch spans and logs (OB-D6).
        """
        query = {
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"tenant_id": target.tenant_id}},
                        {"term": {"user_id": target.user_id}}
                    ]
                }
            }
        }

        # 1. Dispatch Asynchronous Delete-by-Query
        response = await self.client.delete_by_query(
            index=",".join(target.target_indices),
            body=query,
            wait_for_completion=True,
            conflicts="proceed"
        )
        total_deleted = response.get("deleted", 0)

        # 2. Affirmative Verification Gate (Assert Count == 0)
        verify_response = await self.client.count(
            index=",".join(target.target_indices),
            body=query
        )
        residual_count = verify_response.get("count", 0)
        if residual_count > 0:
            raise RuntimeError(f"CRITICAL COMPLIANCE FAILURE: {residual_count} residual telemetry records found for user {target.user_id}")

        return TelemetryErasureResult(
            erasure_job_id=target.erasure_job_id,
            spans_deleted_count=total_deleted,
            log_lines_deleted_count=0,
            execution_duration_ms=response.get("took", 0),
            verified_residual_count=0
        )
```

### 6.2 Verification Checklist & Integration Tests

```bash
# 1. Verify Delete-by-Query Erasure on OpenSearch Telemetry
pytest tests/observability/test_telemetry_erasure.py -k "test_delete_by_query_purges_user_traces"

# Expected Output:
# PASS: OpenSearch documents matching user_id='usr_98' deleted across jaeger-span indices.
# PASS: Post-deletion verification count returns 0 records.

# 2. Verify 7-Day ISM Policy Configuration
pytest tests/observability/test_ism_lifecycle.py -k "test_indices_older_than_7d_dropped"

# Expected Output:
# PASS: Mock indices older than 7 days successfully transitioned to 'delete' state.
```

---

## 7. Trade-Off Analysis & Rejected Alternatives

| Dimension | Selected Paradigm (`OB-D2`, `OB-D5`, `OB-D6`, `OB-D12`) | Rejected Alternative A: Grafana Tempo on S3 Block Storage | Rejected Alternative B: 30-Day Long-Term Telemetry Retention |
| :--- | :--- | :--- | :--- |
| **Right-to-be-Forgotten Compliance** | **Absolute**: OpenSearch allows fine-grained, instantaneous delete-by-query by user and conversation ID ($KK3$). | **Fatal Non-Compliance**: Tempo's immutable Parquet blocks cannot delete individual user spans without rewriting petabytes. | **Compliant**: If using OpenSearch, but data liability window expands by $400\%$. |
| **Storage & Infrastructure Cost** | **Minimal**: Rolling 7-day TTL automatically drops old indices, bounding SSD disk requirements. | **Lowest Cost**: S3 storage is cheaper than OpenSearch NVMe SSDs, but lacks compliance controls. | **High**: Multiplies OpenSearch cluster size and SSD volume provisioning by $4.3\times$. |
| **Log-Trace Correlation** | **Seamless**: Shared W3C `trace_id` allows instantaneous one-click pivots between Jaeger and OpenSearch. | **Fragmented**: Requires external Grafana Loki instance with custom logQL link configurations. | **Identical**: If correlated logging is implemented. |
| **Long-Case Investigation Depth** | **Bounded**: Traces expire after 7 days; relies on permanent `decision_records` table for deep audits ($UU2$). | **High**: S3 block storage can retain traces for 30+ days economically. | **High**: Full diagnostic traces preserved for 30 days. |

---

## 8. Formal References & Literature Grounding

1. **European Union General Data Protection Regulation (GDPR). (2016).** *Regulation (EU) 2016/679: Article 17 (Right to erasure) & Article 5(1)(e) (Storage limitation)*. *(Legal mandates requiring prompt, queryable deletion of telemetry and rolling data expiration).*
2. **OpenSearch Project. (2023).** *Index State Management: Automated Index Lifecycle Policies*. OpenSearch Documentation, Linux Foundation. *(Mechanisms for deterministic daily index rollover and atomic directory-level deletion).*
3. **Jaeger Authors. (2023).** *Jaeger: Open Source, End-to-End Distributed Tracing Architecture*. Cloud Native Computing Foundation. *(Design of distributed tracing collectors and Elasticsearch/OpenSearch storage plugins).*
4. **Kleppmann, M. (2017).** *Designing Data-Intensive Applications*. O'Reilly Media. *(Analysis of append-only immutable storage versus mutable document search engines under deletion constraints).*
5. **NIST. (2020).** *Security and Privacy Controls for Information Systems and Organizations*. NIST SP 800-53, Rev 5. Control AU-4 (Audit Storage Capacity) & Control AU-11 (Audit Record Retention). *(Standards governing finite audit log retention windows and automated purging).*
