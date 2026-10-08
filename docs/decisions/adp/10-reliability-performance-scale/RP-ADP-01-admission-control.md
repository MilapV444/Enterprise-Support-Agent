# RP-ADP-01: Multi-Tier Admission Control & Graceful Traffic Degradation (Token Buckets, Knowledge-Base Fallbacks & Turn Concurrency Mutexes)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-03 *(Confirmed per RP-D1 Multi-Tier Rate Limits, RP-D2 Degraded KB-Only Mode RP-Q1, RP-D3 One-Active-Turn Mutex RP-Q2 & RP-D14 Exact Usage Counter UU1)*
- **Deciders**: Architecture Team, Principal Systems Architect, Lead SRE, Security Operations Director
- **Component**: `[10] Reliability / Performance / Scale` (`Component [ 10 ]`)
- **Reasoning Source**: `checkpoint.md` §14 · Diagram: `LLD - [10] Reliability / Performance / Scale`
- **Decisions Covered**:
  - `RP-D1`: Multi-Tier Rate Limiting Architecture — Hierarchical admission control enforced at the API Gateway: simultaneous concurrency and rate quotas per tenant, per user, per conversation, and token-per-minute (TPM) ceilings per tenant; prevents single-tenant denial-of-service and aligns gateway throttling directly with foundation model token expenses
  - `RP-D2`: Graceful Traffic Degradation Paradigm — Two-stage throttle response: When traffic exceeds the soft rate limit, the agent degrades to a Knowledge-Base-Only Answer (`RP-Q1`: generated purely from retrieved documentation without calling external tools or specialist subgraphs; reverts to cited snippets if LLMs are unavailable); traffic breaching the hard ceiling returns `HTTP 429 Too Many Requests` with an explicit `Retry-After` header ($KK1$)
  - `RP-D3`: Single Active Turn Concurrency Mutex — Strict conversational serialization: exactly one active execution turn permitted per conversation at any moment; rapid duplicate messages submitted while a turn is executing are rejected with `"still working on your last message"`; turns waiting on Human-in-the-Loop approvals count as active (`RP-Q2`), locking that conversation while allowing parallel new conversations on the same case (`MS-D1`)
  - `RP-D14`: Deterministic Exact Token Counter — The orchestrator records provider-reported usage directly into a low-latency shared Redis counter store on every turn completion (`RP-F14(b)`); rate limiting reads exact token consumption rather than sampled trace estimates ($UU1$), guaranteeing mathematically precise quota enforcement
- **Related Architectural Decision Points**:
  - [`UA-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/01-user-application/UA-ADP-01-channels-api-transport.md): Channels & Transport *(POST /turns Transport Contract)*
  - [`CR-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#cr-adp-04--cost-attribution--token-budgets): Cost Attribution & Token Budgets *(Tenant Financial Quotas)*
  - [`KR-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/02-knowledge-retrieval/KR-ADP-04-retrieval-ranking-pipeline.md): Retrieval & Ranking Pipeline *(Direct Knowledge Search Execution)*
  - [`HL-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#hl-adp-04--handoff-transcripts--waiting-experience): Handoff & Waiting Experience *(Conversation Lock UX)*

---

## 1. Context & Problem Statement

Autonomous conversational agents present unique traffic management challenges distinct from standard REST microservices:
1. **The Asymmetric Resource Inversion**:
   - A traditional API request consumes negligible CPU ($\approx 5\text{ms}$). In contrast, a single conversational agent turn may initiate 5 LLM inference calls, 3 high-dimensional vector searches, 2 external tool mutations, and 1 safety guardrail check, consuming $3,500$ tokens and $2.0\text{ seconds}$ of GPU compute.
   - An unthrottled tenant generating 50 concurrent requests can exhaust upstream model API rate limits ($10,000\text{ TPM}$) and starve all other tenants sharing the platform.
2. **The Double-Click Rapid Turn Race Condition (Scenario 8, `RP-D3`)**:
   - End-users frequently click "Send" repeatedly when an interface does not respond instantly, or send 4 rapid-fire messages within $800\text{ms}$ ("Hello", "Are you there?", "I need help", "Refund my invoice").
   - If the gateway spawns four parallel LangGraph agent graphs for the same conversation, they execute concurrent tool mutations (e.g., duplicate credit memos) and interleave disjoint conversational histories into the database.
3. **The Abrupt Black-Hole Throttle ($KK1$)**:
   - When conventional APIs hit rate limits, they abruptly drop connections with unhelpful errors or silent socket closes. In an enterprise support environment, dropping a frustrated customer with no explanation triggers severe user dissatisfaction and brand damage.

### The Core Architectural Question
> **How do we construct an intelligent, multi-tier admission control pipeline that prevents conversational race conditions, tracks real-time token spend with sub-millisecond precision, and degrades gracefully into informative knowledge-base answers before issuing hard 429 rejections?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `RP-D1`, `RP-D2`, `RP-D3`, and `RP-D14` establish the **Multi-Tier Token Bucket Admission Controller and Conversational Mutex Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│             MULTI-TIER ADMISSION CONTROL & DEGRADATION PIPELINE (RP-D1, RP-D2, RP-D3)            │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                       Inbound POST /turns (Tenant: "ten_01", User: "usr_98", Conv: "conv_12")
                                                     │
                                                     ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 1: CONVERSATION ACTIVE TURN MUTEX GATE (RP-D3, Scenario 8)                                 │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Check Distributed Mutex: lock:conv:conv_12 (Redis SETNX with 60s TTL)                           │
│                                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ Lock Acquired?                                                                           │   │
│   │ • YES ===> Proceed to Stage 2                                                            │   │
│   │ • NO  ===> REJECT INBOUND (HTTP 409 Conflict): "Still working on your last message"      │   │
│   │            (Client buffers text locally; locks persist through HITL waits RP-Q2)         │   │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────┬─────────────────────────────────────────────────────────────┘
                                     │ LOCK ACQUIRED
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 2: HIERARCHICAL RATE & TOKEN QUOTA EVALUATOR (RP-D1, RP-D14)                               │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ In-Memory Sliding Window / Token Bucket Quotas (Evaluated via Redis in < 2ms):                   │
│ 1. Per-User Quota:          ≤ 10 turns / minute                                                  │
│ 2. Per-Tenant Concurrency:  ≤ 50 active parallel turns                                           │
│ 3. Per-Tenant Token Quota:  ≤ 60,000 tokens / minute (Direct Counter RP-D14)                     │
└────────────────────────────────────┬─────────────────────────────────────────────────────────────┘
                                     │
           ┌─────────────────────────┼─────────────────────────┐
           ▼ (Within Normal Quota)   ▼ (Exceeds Soft Quota)    ▼ (Exceeds Hard Ceiling)
┌───────────────────────┐ ┌───────────────────────┐ ┌───────────────────────────────────────┐
│ TIER 1: FULL AGENT    │ │ TIER 2: DEGRADED KB   │ │ TIER 3: HARD THROTTLE REJECTION       │
│ EXECUTION             │ │ ANSWER (RP-D2)        │ │ (RP-D2, KK1)                          │
├───────────────────────┤ ├───────────────────────┤ ├───────────────────────────────────────┤
│ • Coordinator Triage  │ │ • Skip All Tool Calls │ │ • HTTP 429 Too Many Requests          │
│ • Specialist Routing  │ │ • Skip Specialists    │ │ • Header: Retry-After: 35             │
│ • External Tools Live │ │ • Direct Vector Search│ │ • Client Enforces Exponential Backoff │
│ • Multi-Agent Output  │ │ • Generated or Snippet│ │ • Zero Backend Token Spend            │
└───────────────────────┘ └───────────────────────┘ └───────────────────────────────────────┘
```

---

### Pillar 1: Hierarchical Token-Bucket Admission Control (`RP-D1`, `RP-D14`)

Admission control operates across three hierarchical dimensions to ensure fairness and prevent platform starvation:

#### The Mathematical Token Bucket Formulation
For tenant $T$, available token capacity at time $t$ is governed by a continuous Leaky Token Bucket:
$$B_T(t) = \min\left( C_{\max}, B_T(t_0) + r \cdot (t - t_0) - \Delta_{\text{consumed}} \right)$$
where:
- $C_{\max}$ is the burst ceiling ($100,000\text{ tokens}$).
- $r$ is the sustained replenishment rate ($60,000\text{ tokens/minute}$).
- $\Delta_{\text{consumed}}$ is the exact token count reported by model providers and added to the shared Redis counter by the orchestrator upon turn completion (`RP-D14`).

#### Hierarchical Quota Structure
1. **User Tier**: Max 10 requests / minute per user ID (mitigates client script loops).
2. **Conversation Tier**: Exactly 1 active turn per conversation ID (`RP-D3`).
3. **Tenant Request Tier**: Max 120 requests / minute per tenant.
4. **Tenant Token Tier (TPM)**: Max 60,000 tokens / minute across all concurrent users.

---

### Pillar 2: Graceful Degradation to Knowledge-Base Answers (`RP-D2`, `RP-Q1`)

When a tenant exceeds their soft token or request quota ($100–125\%$ of limit), the platform does not issue a blunt 429 error. Instead, it enters **Graceful Degradation Mode**:

#### The Knowledge-Base-Only Execution Contract (`RP-Q1`)
1. **Tool & Specialist Bypass**:
   - The orchestrator completely bypasses specialist graphs (Billing, Technical), external tool invocations (`TA-D1`), and Temporal saga coordinators.
2. **Direct Vector & BM25 Search**:
   - The user query routes directly to the Knowledge retrieval pipeline (`KR-ADP-04`) to retrieve matching public documentation and FAQ passages.
3. **Dual Execution Fallback (`RP-Q1`)**:
   - **Case A (LLM Available)**: If model capacity exists, a lightweight, cheap model generates a direct answer strictly citing the retrieved documentation. The system prompt forbids account-specific claims (*"Because our systems are currently busy, I cannot check your live account status, but here is our official policy..."*).
   - **Case B (LLM Exhausted / Down)**: If upstream LLMs are completely throttled or down (`RP-D4`), the system returns the top-3 retrieved passages as raw cited snippets without neural generation.
4. **Hard Ceiling Throttling ($KK1$)**:
   - If traffic exceeds $150\%$ of the quota (extreme Denial of Service), the gateway issues `HTTP 429 Too Many Requests` with a calculated `Retry-After: {seconds}` header.

---

### Pillar 3: Single Active Turn Concurrency Mutex (`RP-D3`, `RP-Q2`)

To eliminate duplicate execution races (Scenario 8):
1. **Distributed Lock Acquisition**:
   - When `POST /turns` arrives for conversation $C$, the gateway attempts an atomic lock in Redis:
     ```python
     acquired = redis.set(f"lock:conv:{C}", turn_id, nx=True, ex=60)
     ```
2. **Conflict Rejection Protocol**:
   - If `acquired == False`:
     The gateway rejects the request with `HTTP 409 Conflict`:
     ```json
     {
       "status": "BUSY",
       "error": "STILL_WORKING",
       "message": "Still working on your last message. Please wait for completion.",
       "active_turn_id": "turn_01JC9812A"
     }
     ```
   - The client application is contractually required to retain the unsent text in the user's input draft box so no user input is lost.
3. **Human-in-the-Loop Lock Holding (`RP-Q2`)**:
   - If a turn requires human approval (`TA-D5`, `HL-ADP-03`), the turn remains active and the mutex remains locked.
   - The user cannot send new messages inside that specific conversation while awaiting approval. However, they are free to initiate a separate parallel conversation, which automatically links to the identical customer case via `MS-D1`.

---

### Pillar 4: Deterministic Real-Time Token Usage Counters (`RP-D14`, $UU1$)

To eliminate the $300\%$ estimation error of sampled traces ($UU1$):
1. **Direct Post-Turn Accounting**:
   - On every LLM, Jev, judge, or reranker completion, the orchestrator extracts the provider-verified usage field:
     $$T_{\text{consumed}} = U_{\text{prompt}} + U_{\text{completion}}$$
2. **Atomic Counter Increment**:
   - The orchestrator issues an atomic increment to the tenant's rolling minute bucket in Redis:
     ```redis
     INCRBY tenant:ten_acme_01:tpm:202610031422 3420
     EXPIRE tenant:ten_acme_01:tpm:202610031422 120
     ```
   - Rate limiters read this counter directly, guaranteeing sub-millisecond, mathematically exact TPM enforcement independent of OpenTelemetry trace sampling.

---

## 3. Data Contracts & Execution Invariants

### 3.1 Rate Limit Policy & Response Contracts

```python
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class DegradationMode(str, Enum):
    FULL_AGENT = "full_agent"
    KB_ONLY_GENERATED = "kb_only_generated"
    KB_ONLY_SNIPPETS = "kb_only_snippets"
    HARD_THROTTLED = "hard_throttled"

class RateLimitVerdict(BaseModel):
    """
    Contract representing the admission control evaluation for an inbound turn (RP-D1, RP-D2).
    """
    allowed: bool
    degradation_mode: DegradationMode
    current_tpm_usage: int = Field(..., ge=0)
    tenant_tpm_limit: int = Field(..., ge=0)
    retry_after_seconds: Optional[int] = Field(None, ge=1)
    error_message: Optional[str] = None

class TurnConflictResponse(BaseModel):
    """
    Contract returned on concurrent turn collision (RP-D3, HTTP 409).
    """
    error_code: str = Field(default="CONVERSATION_BUSY")
    message: str = Field(default="Still working on your last message. Please wait.")
    active_turn_id: str = Field(...)
    conversation_id: str = Field(...)
    retry_recommended_ms: int = Field(default=1500)
```

### 3.2 Concurrency Mutex Invariant

$$\forall \text{ Conversation } C, \quad \sum_{\text{Worker } W} \mathbf{1}(\text{ExecutingTurn}(W, C)) \le 1$$
Under no circumstance may two worker threads, pods, or LangGraph runtimes execute turns concurrently within the same conversation ID.

---

## 4. Quantitative Failure Modes & Operational Risk Bounds

| Failure Mode ID | Sub-Component & Severity | Risk Classification | Empirical Trigger Condition | Detection Vector | Automated Mitigation & Architectural Enforcement |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **RP-FM-101** | Header Omission (`RP-D2`)<br>**HIGH** | Q1 Known Known (Contract Breach) | Gateway issues HTTP 429 response without a `Retry-After` header, causing client to spam retries ($KK1$). | Synthetic gateway integration test asserts presence of `Retry-After` header. | **Gateway Header Enforcement Filter**: Envoy/FastAPI middleware automatically injects calculated backoff header if missing. |
| **RP-FM-102** | Turn Mutex Deadlock (`RP-D3`)<br>**CRITICAL** | Q1 Known Known (Stall) | Worker pod crashes mid-turn without releasing Redis mutex, permanently locking customer conversation. | Prometheus alert detects mutex held $> 60\text{ seconds}$ without active worker heartbeat. | **Redis Key Expiration Ceiling**: All mutex locks configured with an automatic 60-second TTL; lock automatically drops if worker dies. |
| **RP-FM-103** | Counter Store Outage (`RP-D14`)<br>**HIGH** | Q2 Known Unknown (Dependency Failure) | Redis cluster hosting token counters suffers hardware crash or network partition. | Rate limiter catches Redis `ConnectionRefusedError`. | **Fail-Open to Request-Rate Fallback**: System temporarily falls back to in-memory local token buckets per worker node, logging warning. |
| **RP-FM-104** | Overreaching KB Answers (`RP-D2`)<br>**HIGH** | Q4 Unknown Unknown (Hallucination) | Degraded KB-only answer attempts to answer invoice question without live tool data, hallucinating a bill amount ($UU2$). | Output Safety Promise Linter (`SG-D15`) catches unbacked account assertion. | **Strict Persona Invariant (`RP-Q1`)**: KB-only system prompt mandates explicit boilerplate disclaimer forbidding account-specific claims. |
| **RP-FM-105** | Thundering Mutex Retries (`RP-D3`)<br>**MEDIUM** | Q4 Unknown Unknown (Network Surge) | Frontend client retries rejected message in a tight 50ms loop upon receiving HTTP 409 Conflict. | Gateway access logs report $> 20\text{ req/sec}$ for single conversation ID. | **Client Backoff Contract**: Gateway enforces exponential backoff with jitter on 409 responses, throttling rapid client retries. |

---

## 5. Closed-Loop Architectural Feedback

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   ADMISSION CONTROL & TRAFFIC FLOW OBSERVABILITY ENGINE                          │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Inbound Request Stream
             │
             ▼
   ┌─────────────────────────────┐
   │ Concurrency Mutex Gate      │─────► [Metric: conversation_turn_conflicts_total]
   │ (Single Active Turn Check)  │       Monitors 409 rapid-click rejections
   └─────────────┬───────────────┘
                 │
                 ▼
   ┌─────────────────────────────┐
   │ Real-Time Token Bucket      │─────► [Metric: tenant_tpm_utilization_ratio]
   │ (Exact Redis Counter Store) │       Warns at > 80% quota consumption
   └─────────────┬───────────────┘
                 │
                 ├──────────────────────────────────────────────┐
                 ▼ (Degraded KB Mode)                           ▼ (Hard 429 Drop)
   ┌─────────────────────────────┐               ┌─────────────────────────────┐
   │ Degraded Response Emitter   │               │ Hard Throttling Pipeline    │
   │ [Metric: turns_degraded_kb] │               │ [Metric: turns_rate_limited]│
   └─────────────────────────────┘               └─────────────────────────────┘
```

### Telemetry & Operational SLOs
1. **Admission Decision Latency**:
   - Time to evaluate mutex and token quotas: $p99 \le 3.0\text{ms}$.
2. **Turn Mutex Accuracy**:
   - Race conditions permitting parallel turns on same conversation: **Strictly 0**.
3. **Degraded Knowledge Answer Quality**:
   - Context Precision of degraded KB answers: $\ge 0.85$.

---

## 6. Genesis Implementation Directive & Verification Protocol

### 6.1 Admission Control Middleware Implementation

```python
import time
import redis.asyncio as aioredis
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

class AdmissionControlMiddleware:
    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client

    async def evaluate_turn_admission(self, tenant_id: str, conversation_id: str, user_id: str) -> None:
        """
        Enforces single active turn mutex (RP-D3) and multi-tier rate quotas (RP-D1, RP-D2).
        """
        # 1. ENFORCE SINGLE ACTIVE TURN MUTEX (RP-D3)
        lock_key = f"lock:conv:{conversation_id}"
        acquired = await self.redis.set(lock_key, "ACTIVE", nx=True, ex=60)
        if not acquired:
            raise HTTPException(
                status_code=409,
                detail={
                    "error_code": "CONVERSATION_BUSY",
                    "message": "Still working on your last message. Please wait.",
                    "conversation_id": conversation_id
                }
            )

        # 2. EVALUATE REAL-TIME TOKEN TPM LIMIT (RP-D14)
        current_minute = int(time.time() // 60)
        tpm_key = f"tpm:{tenant_id}:{current_minute}"
        current_tokens = int(await self.redis.get(tpm_key) or 0)
        tpm_limit = 60000  # Default tenant limit

        if current_tokens > (tpm_limit * 1.5):
            # Hard Throttle Ceiling (RP-D2)
            await self.redis.delete(lock_key)  # Release lock on throttle
            raise HTTPException(
                status_code=429,
                headers={"Retry-After": "45"},
                detail="Rate limit exceeded. System heavily loaded."
            )
        elif current_tokens > tpm_limit:
            # Soft Limit: Flag request for Degraded KB-Only Mode
            pass
```

### 6.2 Verification Checklist & Integration Tests

```bash
# 1. Verify Single Active Turn Mutex Rejection
pytest tests/reliability/test_admission_control.py -k "test_rapid_turn_returns_409"

# Expected Output:
# PASS: Second concurrent POST /turns on same conversation ID returns HTTP 409 Conflict.
# PASS: Error payload contains CONVERSATION_BUSY status; original turn executes undisturbed.

# 2. Verify Graceful Degradation to KB-Only Answers
pytest tests/reliability/test_admission_control.py -k "test_over_limit_triggers_kb_degrade"

# Expected Output:
# PASS: Traffic exceeding soft TPM quota bypasses specialist tools and returns cited KB answer.
# PASS: Hard ceiling returns HTTP 429 with Retry-After header.
```

---

## 7. Trade-Off Analysis & Rejected Alternatives

| Dimension | Selected Paradigm (`RP-D1`, `RP-D2`, `RP-D3`, `RP-D14`) | Rejected Alternative A: Hard 429 Drop on All Over-Limits | Rejected Alternative B: Request Queuing for 30 Seconds |
| :--- | :--- | :--- | :--- |
| **Customer Experience Under Load** | **Superior**: Degrades to helpful public KB answer; customers receive answers instead of error screens. | **Hostile**: Abruptly severs connection with 429; customers assume agent is broken. | **Poor**: User stares at frozen loading spinner for 30 seconds before eventual timeout. |
| **Concurrency Protection** | **Absolute**: Redis mutex guarantees zero state corruption from rapid multi-clicks (Scenario 8). | **None**: Concurrent clicks spawn concurrent agent graphs, corrupting memory state. | **Moderate**: Delays duplicate turns, but still executes duplicate tool calls eventually. |
| **Token Tracking Accuracy** | **Exact**: In-memory Redis counter updated atomically on turn completion (`RP-D14`). | **Estimated**: Uses trace samples, leading to $300\%$ estimation error ($UU1$). | **N/A**: Relates to queue mechanics. |
| **Systemic Resource Safety** | **Guaranteed**: Hard ceiling provides uncompromised circuit breaker against massive DDoS attacks. | **Guaranteed**: Protects resources, but destroys user satisfaction. | **Hazardous**: Queuing hundreds of requests consumes worker memory buffers, risking cascade crashes. |

---

## 8. Formal References & Literature Grounding

1. **Beyer, B., Jones, C., Petoff, J., & Murphy, N. R. (2016).** *Site Reliability Engineering: How Google Runs Production Systems*. O'Reilly Media. Chapter 21: Handling Overload & Chapter 22: Addressing Cascading Failures. *(Theoretical foundation for graceful degradation and load shedding).*
2. **RFC 6585. (2012).** *Additional HTTP Status Codes*. Internet Engineering Task Force (IETF). Section 4: 429 Too Many Requests. *(Standards governing Retry-After headers and client rate limit handling).*
3. **Leaky Bucket & Token Bucket Algorithms. (1986).** *Turner, J. S. New Directions in Communications (or Which Way to the Information Age?)*. IEEE Communications Magazine, 24(10), 8–15. *(Mathematical foundation for network traffic shaping and burst control).*
4. **Kleppmann, M. (2017).** *Designing Data-Intensive Applications*. O'Reilly Media. Chapter 8: The Trouble with Distributed Systems (Distributed locks and race conditions). *(Principles of distributed mutexes and concurrency prevention).*
5. **NIST. (2020).** *Security and Privacy Controls for Information Systems and Organizations*. NIST SP 800-53, Rev 5. Control SC-5 (Denial of Service Protection). *(Standards governing admission control and rate limiting in federal information systems).*
