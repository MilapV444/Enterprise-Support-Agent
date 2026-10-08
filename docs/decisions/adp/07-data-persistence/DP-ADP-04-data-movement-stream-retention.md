# DP-ADP-04: Inter-Component Data Movement & Stream Retention Lifecycles (Direct In-Memory Writes, 7-Day Outbound Event Replay & Versioned Raw Snapshots)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-01 *(Confirmed per DP-D6 Direct Writes, DP-D7 7-Day SSE Event Retention & DP-D11 Versioned Raw Knowledge Snapshots)*
- **Deciders**: Architecture Team, Distributed Systems Lead, Storage & Data Platform Lead
- **Component**: `[7] Data & Persistence` (`Component [ 7 ]`)
- **Reasoning Source**: `checkpoint.md` §11 · Diagram: `LLD - [7] Data & Persistence`
- **Decisions Covered**:
  - `DP-D6`: Inter-Component Communication Architecture — Elimination of enterprise message brokers / event buses (Kafka, RabbitMQ, SQS); services execute direct synchronous writes and in-process function invocations to downstream persistence targets; transactional outbox and Debezium CDC rejected to minimize operational surface area; high-stakes deletion fan-outs offloaded to Temporal (`DP-D13`) to eliminate lost tombstone risks ($UU1$)
  - `DP-D7`: Outbound Event Log Retention — Outbound conversational event stream (`outbound_event_log`) strictly bounded to a 7-day replay window in PostgreSQL; clients reconnecting via Server-Sent Events (SSE) replay lost turns within 7 days via `Last-Event-ID` (`UA-D2`); clients reconnecting after $> 7$ days receive a synthesized history rehydrated from canonical transcripts
  - `DP-D11`: Raw Knowledge Source Snapshots — Object storage (S3/GCS) preserves immutable, versioned raw document snapshots captured during nightly ingestion batches (`KR-D2`); enables auditability and deterministic index rebuilds without re-crawling live source systems; GDPR erasure compliance enforced via snapshot object rewriting (`DP-D15`)
- **Related Architectural Decision Points**:
  - [`UA-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/01-user-application/UA-ADP-01-channels-api-transport.md): Channels & Transport *(SSE Streaming & Last-Event-ID Replay)*
  - [`KR-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/02-knowledge-retrieval/KR-ADP-02-ingestion-freshness.md): Ingestion Freshness *(Nightly Batch Snapshots & Deletion Detection)*
  - [`MS-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/03-memory-state/MS-ADP-04-agent-state-durability.md): Agent State & Durability *(Synchronous Checkpoint Commits)*
  - [`DP-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/07-data-persistence/DP-ADP-05-erasure-backups-restore.md): Erasure, Backups & Restore *(Temporal Deletion Orchestration)*

---

## 1. Context & Problem Statement

Distributed multi-agent architectures frequently fall victim to enterprise event-bus over-engineering. Typical architectures introduce Kafka, Debezium Change-Data-Capture (CDC), and complex outbox relay daemons to propagate events across microservices (e.g., streaming memory writes, tool receipts, and audit updates).

### The Systemic Failures of Broker-Heavy Pipelines
1. **The Distributed Transaction Fallacy & Dual-Write Hazard**:
   - When an agent turn executes, persisting state in PostgreSQL while simultaneously emitting a message to an external message broker (Kafka/RabbitMQ) creates a classic dual-write failure:
     $$\mathbb{P}(\text{PostgreSQL Commit} \land \neg \text{Kafka Publish}) > 0$$
   - Solving this via the Transactional Outbox pattern introduces polling workers or database WAL tailing (Debezium), dramatically multiplying operational complexity, latency jitter, and connection pool consumption.
2. **Unbounded Event Stream Storage Growth ($UA\text{ }KU3$)**:
   - Streaming intermediate token diffs, node progress markers, and tool execution status via Server-Sent Events (SSE) produces millions of fine-grained events per day.
   - Retaining outbound SSE event streams indefinitely turns the operational database into an unscalable event log, bloating table bloat and degrading B-tree index performance.
3. **The Knowledge Re-Ingestion Dilemma ($DP\text{ }KU3$, $KR\text{ }D11$)**:
   - When knowledge chunking strategies or embedding models are upgraded, or when a Qdrant index is corrupted, rebuilding the index from scratch by re-crawling live enterprise systems (Zendesk APIs, Confluence, Slack) overwhelms external API rate limits and can take days.
   - However, storing raw snapshots of external enterprise data indefinitely risks accumulating legally deleted documents, violating privacy laws ($UU3$).

### The Core Architectural Question
> **How do we coordinate data movement across components with zero message broker overhead while bounding high-frequency event stream retention to 7 days and maintaining versioned, GDPR-rewritable raw knowledge snapshots for instantaneous disaster recovery and index rebuilding?**

---

## 2. Decision Framework & Theoretical Formulation

To solve these challenges, `DP-D6`, `DP-D7`, and `DP-D11` establish the **Direct-Write Persistence and Dual-Tier Replay Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│             DATA MOVEMENT, EVENT STREAM & RAW SNAPSHOT TOPOLOGY (DP-D6, DP-D7, DP-D11)           │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                       Agent Execution Turn Finishes (Coordinator / Specialist)
                                                  │
            ┌─────────────────────────────────────┴─────────────────────────────────────┐
            ▼                                                                           ▼
┌─────────────────────────────────────────┐                 ┌─────────────────────────────────────────┐
│ SYNCHRONOUS DIRECT WRITES (DP-D6)       │                 │ STREAM REPLAY ENGINE (DP-D7)            │
│ • LangGraph State Checkpoint            │                 │ • Appends SSE events to:                │
│ • Conversation Turn Record              │                 │   outbound_event_log (PostgreSQL)       │
│ • Append-Only Tool Audit (DP-D3)        │                 │ • 7-Day Automatic Expiration Window     │
│ Single ACID Transaction in PostgreSQL   │                 │ • Bounded storage footprint (UA KU3)    │
└─────────────────────────────────────────┘                 └───────────────────┬─────────────────────┘
                                                                                │
                                                    ┌───────────────────────────┴───────────────────────────┐
                                                    ▼                                                       ▼
                                      ┌───────────────────────────┐           ┌───────────────────────────┐
                                      │ Client Reconnects ≤ 7 Days│           │ Client Reconnects > 7 Days│
                                      │ Replays exact SSE events  │           │ Rehydrates conversation   │
                                      │ from outbound_event_log   │           │ summary from transcript   │
                                      └───────────────────────────┘           └───────────────────────────┘

════════════════════════════════════════════════════════════════════════════════════════════════════
KNOWLEDGE DATA MOVEMENT: RAW SNAPSHOT OBJECT REPOSITORY (DP-D11)
════════════════════════════════════════════════════════════════════════════════════════════════════

   Nightly Batch Crawler (KR-D2)
   (Zendesk, Confluence, Jira)
               │
               ▼
   ┌────────────────────────────────────────────────────────┐
   │ Versioned Raw Snapshot Tarballs (S3 / GCS)            │
   │ s3://enterprise-agent-snapshots/us-east-1/{tenant_id}/ │
   │ ├── batch_2026-10-01_v1.tar.zst (Raw JSON/Markdown)    │
   │ └── batch_2026-10-02_v1.tar.zst                        │
   └───────────┬────────────────────────────────────────────┘
               │
               ▼ Enables Rapid Re-Indexing without API hammering
   ┌────────────────────────────────────────────────────────┐
   │ Qdrant Vector / Sparse Hybrid Indexer (KR-D4)          │
   └────────────────────────────────────────────────────────┘
```

---

### Pillar 1: Direct Writes Without Message Brokers (`DP-D6`)

We explicitly reject Kafka, RabbitMQ, SQS, and transactional outbox engines for inter-component data propagation.
1. **In-Transaction Relational Writes**:
   - The conversational runtime worker connects directly to PostgreSQL. In a single atomic commit, it persists:
     $$\Delta_{\text{turn}} = \{ \text{Checkpoint}, \text{TurnRecord}, \text{AuditTrail}, \text{EventLog} \}$$
   - This eliminates dual-write anomalies entirely: either the turn state, audit trail, and client events commit together, or the entire transaction aborts.
2. **Handling the Asynchronous Tombstone Risk ($UU1$)**:
   - In standard architectures, direct writes risk partial failures (e.g., PostgreSQL deletes a record, but the direct HTTP call to Qdrant or Redis cache fails).
   - Rather than deploying an enterprise event bus to solve this single problem, critical deletion and erasure fan-outs are orchestrated via **Temporal Workflows (`DP-D13`)**. Temporal guarantees durable execution, exponential backoff retries, and compensation without requiring a message broker.

---

### Pillar 2: 7-Day Outbound Event Log Replay Window (`DP-D7`)

To deliver seamless Server-Sent Events (SSE) streaming while bounding database storage growth:
1. **The Replay Contract (`UA-D2`)**:
   - When a client browser or mobile app disconnects during a turn, it reconnects supplying the HTTP header:
     `Last-Event-ID: evt_01JC89A12B34`
   - If the disconnection interval $\Delta t \le 7\text{ days}$:
     The server executes an index scan on `outbound_event_log` and streams all events where `sequence_num > last_seen_sequence_num`. The user experiences an instantaneous, seamless UI rehydration.
2. **Rehydration Beyond 7 Days**:
   - If $\Delta t > 7\text{ days}$:
     The client is informed that the event stream has expired (`HTTP 410 Gone` or event status `STREAM_EXPIRED`). The client initiates a standard conversation fetch (`GET /conversations/{id}`), which reconstructs dialogue state from the canonical `conversation_memory` and `transcripts` table (`MS-D2`).
3. **Partition Pruning Maintenance**:
   - The `outbound_event_log` table is physically partitioned by day using PostgreSQL range partitioning:
     ```sql
     CREATE TABLE outbound_event_log ( ... ) PARTITION BY RANGE (created_at);
     ```
   - Partitions older than 7 days are dropped via automated DDL:
     $$\text{DROP TABLE outbound\_event\_log\_y2026m10d01;}$$
   - Dropping entire partitions eliminates PostgreSQL dead-tuple bloat, avoids heavy `VACUUM` locks, and consumes virtually zero disk I/O.

---

### Pillar 3: Versioned Raw Knowledge Snapshots in Object Storage (`DP-D11`)

To guarantee disaster recovery and index reproducibility for the Knowledge module:
1. **Snapshot Manifest Structure**:
   - At the conclusion of each nightly batch crawl (`KR-D2`), the ingestion pipeline packages raw external API payloads (original JSON articles, Confluence Markdown files, resolved Zendesk tickets) into a compressed, zstandard-encoded snapshot archive:
     $$\text{SnapshotArchive} = \text{zstd}(\{ D_1, D_2, \dots, D_n \})$$
   - Uploaded to regional object storage with immutable version metadata:
     `s3://tenant-snapshots-{region}/{tenant_id}/{batch_date}/raw_v{version}.tar.zst`
2. **Zero Live-API Dependency for Re-Indexing**:
   - If the Qdrant cluster suffers data corruption or the vector embedding dimensionality changes, the re-indexing worker streams raw snapshots directly from object storage at wire speed ($> 500\text{MB/sec}$ S3 throughput), re-generating embeddings without hitting external vendor rate limits.
3. **Erasure Compliance via Object Rewriting (`DP-D15`)**:
   - Because raw snapshots are stored as distinct objects, when an erasure request is executed for a customer ticket or document, `DP-D15` uncompresses the snapshot, purges the designated document ID, and atomically replaces the S3 object under the same key.

---

## 3. Data Contracts & Execution Invariants

### 3.1 Outbound Event Log Schema Contract

```python
from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, UUID7, field_validator

class OutboundEventType(str):
    TOKEN_DELTA = "token_delta"
    NODE_PROGRESS = "node_progress"
    TOOL_START = "tool_start"
    TOOL_COMPLETE = "tool_complete"
    INTERVENTION_REQUIRED = "intervention_required"
    FINAL_RESPONSE = "final_response"

class OutboundStreamEvent(BaseModel):
    """
    Contract for real-time SSE stream events persisted in the 7-day replay log (DP-D7).
    """
    event_id: str = Field(..., regex=r"^evt_[a-zA-Z0-9]{16}$", description="Monotonically increasing event ID")
    conversation_id: str = Field(..., regex=r"^conv_[a-zA-Z0-9]{16}$")
    turn_id: str = Field(..., regex=r"^turn_[a-zA-Z0-9]{16}$")
    sequence_number: int = Field(..., ge=0, description="Strict sequence order within turn")
    event_type: str = Field(..., description="Canonical event classification")
    payload: Dict[str, Any] = Field(..., description="JSON event payload delivered to client")
    created_at_utc: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("event_id")
    @classmethod
    def validate_monotonic_order(cls, v: str) -> str:
        # Guarantees time-sortable lexicographical property (e.g., ULID or UUIDv7 prefix)
        return v
```

### 3.2 SQL Invariant: 7-Day Range-Partitioned Event Log

```sql
CREATE TABLE IF NOT EXISTS outbound_event_log (
    event_id VARCHAR(64) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    conversation_id VARCHAR(64) NOT NULL,
    turn_id VARCHAR(64) NOT NULL,
    sequence_number INT NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP(),
    PRIMARY KEY (created_at, conversation_id, sequence_number)
) PARTITION BY RANGE (created_at);

-- Forced Row Level Security
ALTER TABLE outbound_event_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE outbound_event_log FORCE ROW LEVEL SECURITY;

CREATE POLICY event_log_tenant_isolation ON outbound_event_log
FOR ALL
USING (tenant_id = current_setting('app.current_tenant_id', true));

-- Create daily partition helper
CREATE OR REPLACE PROCEDURE create_event_log_daily_partition(partition_date DATE)
LANGUAGE plpgsql AS $$
DECLARE
    partition_name TEXT := 'outbound_event_log_' || to_char(partition_date, 'YYYY_MM_DD');
    start_ts TEXT := to_char(partition_date, 'YYYY-MM-DD 00:00:00');
    end_ts TEXT := to_char(partition_date + INTERVAL '1 day', 'YYYY-MM-DD 00:00:00');
BEGIN
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF outbound_event_log FOR VALUES FROM (%L) TO (%L);',
        partition_name, start_ts, end_ts
    );
END;
$$;
```

---

## 4. Quantitative Failure Modes & Operational Risk Bounds

| Failure Mode ID | Sub-Component & Severity | Risk Classification | Empirical Trigger Condition | Detection Vector | Automated Mitigation & Architectural Enforcement |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **DP-FM-401** | Direct Writes (`DP-D6`)<br>**HIGH** | Q1 Known Known (Network Failure) | Direct call from agent worker to external monitoring API fails during turn write. | Exception handler catches socket timeout / connection refusal. | **Non-Blocking Best-Effort Logging**: Secondary observability writes wrapped in non-blocking async tasks; critical state committed directly to PostgreSQL. |
| **DP-FM-402** | Event Replay (`DP-D7`)<br>**MEDIUM** | Q1 Known Known (Client Reconnection) | Client reconnects with `Last-Event-ID` pointing to an event older than 7 days that has been dropped. | SQL query on `outbound_event_log` returns 0 records for specified ID. | **HTTP 410 Gone / Fallback Rehydrate**: Gateway responds with `X-Stream-Expired: true`, prompting client to request full conversation JSON rehydration. |
| **DP-FM-403** | Snapshot Growth (`DP-D11`)<br>**MEDIUM** | Q2 Known Unknown (Storage Growth) | Nightly snapshots stored without lifecycle rules accumulate terabytes of unpruned data ($KU3$). | CloudWatch / Cloud Storage metric alarms on bucket size exceeding $10\text{TB}$. | **S3 Intelligent-Tiering & Archival**: Objects transitioned to Glacier Instant Retrieval after 60 days; deduplication hash checks avoid saving unchanged docs. |
| **DP-FM-404** | Lost Tombstone (`DP-D6`)<br>**CRITICAL** | Q4 Unknown Unknown (Silent Inconsistency) | Operator or direct code path deletes a ticket in PostgreSQL, but direct write to Qdrant fails silently ($UU1$). | Periodic consistency audit crawler detects Qdrant vectors whose parent document is missing in PostgreSQL. | **Temporal Workflow Quarantine (`DP-D13`)**: All document deletions are forbidden from direct writes; must route through durable Temporal deletion workflows. |
| **DP-FM-405** | Erased Docs in Snapshots (`DP-D11`)<br>**HIGH** | Q4 Unknown Unknown (Privacy Resurrect) | Index rebuild re-ingests historical raw snapshots, accidentally restoring a customer ticket that was legally erased ($UU3$). | Re-ingestion pipeline flag detects presence of erased document IDs in source stream. | **Pre-Ingestion Deletion Filter (`KR-D15`)**: Index rebuild workers cross-reference document IDs against durable PostgreSQL deletion tombstones before indexing. |

---

## 5. Closed-Loop Architectural Feedback

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   STREAM REPLAY & SNAPSHOT HEALTH OBSERVABILITY ENGINE                           │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Client SSE Reconnection
              │
              ▼
   ┌───────────────────────┐
   │ Check Reconnect Age:  │
   │ Last-Event-ID Δt      │
   └──────────┬────────────┘
              │
              ├──────────────────────────────────────────────┐
              ▼ (Δt ≤ 7 Days)                                ▼ (Δt > 7 Days)
   ┌───────────────────────┐                      ┌───────────────────────┐
   │ Replay Stream Events  │                      │ Fallback Transcript   │
   │ from PostgreSQL       │                      │ Rehydration Protocol  │
   └──────────┬────────────┘                      └──────────┬────────────┘
              │                                              │
              ▼                                              ▼
   [Metric: sse_stream_replays_total]             [Metric: sse_stream_expired_fallbacks_total]
   Target: > 98% replayed successfully            Monitors long disconnection frequencies

════════════════════════════════════════════════════════════════════════════════════════════════════
RAW SNAPSHOT PARTITION & PURGE TELEMETRY
════════════════════════════════════════════════════════════════════════════════════════════════════
   Partition Maintenance Cron ──► [Metric: event_log_partitions_dropped_total]
   Nightly Ingest Archiver   ──► [Metric: raw_snapshot_bytes_persisted_total]
```

### Telemetry & Operational SLOs
1. **Event Replay Latency**:
   - Metric: `sse_replay_duration_seconds`
   - Target: $p95 < 15\text{ms}$ (instant stream resume).
2. **Direct Write Transaction Commit Duration**:
   - Metric: `direct_write_turn_commit_seconds`
   - Target: $p95 < 20\text{ms}$, $p99 < 45\text{ms}$.
3. **Partition Pruning Execution Delay**:
   - Time elapsed past 7-day threshold before partition drop: $< 2\text{ hours}$.

---

## 6. Genesis Implementation Directive & Verification Protocol

### 6.1 Event Stream Replay Dispatcher Implementation

```python
from typing import AsyncGenerator
import asyncpg

class EventStreamReplayService:
    def __init__(self, db_pool: asyncpg.Pool):
        self.pool = db_pool

    async def stream_reconnection_events(
        self,
        tenant_id: str,
        conversation_id: str,
        last_event_id: str
    ) -> AsyncGenerator[dict, None]:
        """
        Replays lost SSE events within the 7-day retention window.
        Yields events in strictly ascending sequence order.
        """
        query = """
            SELECT event_id, event_type, sequence_number, payload
            FROM outbound_event_log
            WHERE conversation_id = $1
              AND sequence_number > (
                  SELECT sequence_number FROM outbound_event_log WHERE event_id = $2
              )
            ORDER BY sequence_number ASC;
        """
        async with self.pool.acquire() as conn:
            # Enforce RLS context
            await conn.execute("SELECT set_config('app.current_tenant_id', $1, true);", tenant_id)
            records = await conn.fetch(query, conversation_id, last_event_id)
            
            if not records:
                # Check if last_event_id exists at all to distinguish between up-to-date and expired
                exists = await conn.fetchval(
                    "SELECT 1 FROM outbound_event_log WHERE event_id = $1;", last_event_id
                )
                if not exists:
                    raise StopAsyncIteration("STREAM_EXPIRED")

            for record in records:
                yield {
                    "id": record["event_id"],
                    "event": record["event_type"],
                    "data": record["payload"]
                }
```

### 6.2 Verification Checklist & Integration Tests

```bash
# 1. Verify 7-Day Event Log Replay & Boundary
pytest tests/persistence/test_stream_replay.py -k "test_reconnect_within_7_days_replays_events"

# Expected Output:
# PASS: Events with sequence_num > last_seen successfully streamed in exact chronological order.
# PASS: Reconnection with event older than 7 days raises STREAM_EXPIRED and triggers fallback.

# 2. Verify Atomic Direct Writes Without Broker
pytest tests/persistence/test_direct_writes.py -k "test_atomic_checkpoint_audit_commit"

# Expected Output:
# PASS: Simulated failure during turn aborts entire transaction; zero orphaned audit/event records.
```

---

## 7. Trade-Off Analysis & Rejected Alternatives

| Dimension | Selected Paradigm (`DP-D6`, `DP-D7`, `DP-D11`) | Rejected Alternative A: Kafka Event Bus + CDC (Debezium) | Rejected Alternative B: Permanent Unbounded Event Stream |
| :--- | :--- | :--- | :--- |
| **Systemic Complexity & Maintenance** | **Minimal**: PostgreSQL connection pool only; zero distributed broker clusters to operate. | **Extreme**: Requires managing ZooKeeper/KRaft, Kafka brokers, Kafka Connect, and Debezium schema registries. | **Low**: Simple database tables, but leads to massive disk bloat and performance degradation. |
| **Consistency Guarantees** | **ACID In-Transaction**: Checkpoints, audit trails, and event records commit atomically. | **Eventual Consistency**: Outbox relay workers introduce latency jitter ($50–500\text{ms}$) and duplicate delivery risks. | **ACID**: But vacuuming costs and index degradation cripple operational transactions. |
| **Client Disconnection Recovery** | **Dual-Tier**: Fast binary replay for 7 days; robust transcript rehydration for long-term reconnects. | **Stream Replay**: Kafka offset replay, but requires exposing Kafka offsets to public web clients. | **Infinite Replay**: Capable of replaying 2-year-old streams, but at massive database storage expense. |
| **Disaster Recovery from Raw Snapshots** | **Fast & Isolated**: S3 zstandard archives enable wire-speed re-indexing without crawling live APIs. | **CDC Log Compaction**: Kafka topic compaction, but topic retention costs are significantly higher than S3. | **None**: Live re-crawl required if indexes corrupted. |

---

## 8. Formal References & Literature Grounding

1. **Richardson, C. (2018).** *Microservices Patterns: With Examples in Java*. Manning Publications. Chapter 3: Inter-process Communication & Chapter 4: Transactional Messaging. *(Theoretical foundation for evaluating transactional outbox patterns versus direct database writes).*
2. **W3C Recommendation. (2015).** *Server-Sent Events: Reconnecting and the Last-Event-ID Header*. World Wide Web Consortium. *(Standard defining client event reconnection protocols and replay contracts).*
3. **Kleppmann, M. (2017).** *Designing Data-Intensive Applications*. O'Reilly Media. Chapter 11: Stream Processing & Chapter 3: Storage and Retrieval. *(Comparative analysis of log compaction, range partitioning, and direct relational commits).*
4. **European Union General Data Protection Regulation (GDPR). (2016).** *Regulation (EU) 2016/679: Article 5(1)(e) (Storage limitation)*. *(Legal principle mandating that personal data in streaming logs be kept in a form permitting identification for no longer than necessary).*
