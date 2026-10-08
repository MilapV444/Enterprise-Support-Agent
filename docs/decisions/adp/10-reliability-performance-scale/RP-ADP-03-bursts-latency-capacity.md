# RP-ADP-03: Burst Absorption, Route Latency Budgets & Elastic Capacity Management (Single-Flight Coalescing, Incident Triage Mode & Pre-Warmed Autoscaling)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-03 *(Confirmed per RP-D6 Request Coalescing & Incident Mode, RP-D8 Route Latency Budgets RP-Q5 & RP-D9 Pre-Warmed Autoscaling KK2)*
- **Deciders**: Architecture Team, Lead Site Reliability Engineer, Distributed Systems Architect, Front-End Experience Lead
- **Component**: `[10] Reliability / Performance / Scale` (`Component [ 10 ]`)
- **Reasoning Source**: `checkpoint.md` §14 · Diagram: `LLD - [10] Reliability / Performance / Scale`
- **Decisions Covered**:
  - `RP-D6`: Thundering-Herd Mitigation & Incident Triage Mode — Dual burst protection: (1) In-flight request coalescing (single-flight) merging concurrent identical retrieval and tool read queries within a 200ms window into a single execution; (2) Platform Incident Mode activated by on-call during widespread service disruptions, using a fast TypeSafe Jev `Noul` question ("is this about the ongoing incident?", Use #4, #8) to divert matching user inquiries to pre-approved canonical status answers, neutralizing downstream thundering herds ($UK1$)
  - `RP-D8`: Route-Specific Latency Budgets — Formal latency performance envelopes under EV-D11's buffered streaming contract: First interactive `status` progress event delivered within $\le 1.0\text{ second}$ ($p95$); final checked response $p95$ latency ceilings partitioned by conversational complexity (`RP-Q5`): **FAQ Routes $\le 5\text{ seconds}$**, **Diagnostic Routes $\le 20\text{ seconds}$**, and **Multi-Specialist Routes $\le 45\text{ seconds}$**; sub-step timeouts strictly sum within the route ceiling
  - `RP-D9`: Elastic Autoscaling with Pre-Warmed Minimums — Kubernetes Horizontal Pod Autoscaling (HPA) driven by queue depth and CPU utilization across stateless API gateways, LangGraph orchestrator workers, and Temporal task-queue worker pools; backed by strict pre-warmed minimum pod allocations per sovereign region ($N_{\min} \ge 5$) to permanently eliminate cold-start latency spikes that trigger false circuit breaker trips ($KK2$)
- **Related Architectural Decision Points**:
  - [`OB-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/09-observability-monitoring/OB-ADP-03-service-levels-alerting.md): Service Levels & Alerting *(Internal SLO Burn-Rate Targets)*
  - [`UA-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/01-user-application/UA-ADP-04-response-contract-delivery.md): Response Contract & Delivery *(SSE Progress Status Streaming)*
  - [`KR-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/02-knowledge-retrieval/KR-ADP-04-retrieval-ranking-pipeline.md): Retrieval & Ranking Pipeline *(Read Coalescing on Qdrant)*
  - [`CR-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/11-cost-resource-management/CR-ADP-03-answer-cache.md): Answer Cache *(Semantic Cache vs. In-Flight Coalescing)*

---

## 1. Context & Problem Statement

Autonomous conversational agents experience extreme, non-linear traffic dynamics. When an enterprise software product experiences an unplanned outage or network degradation, thousands of end-users rush simultaneously to the customer support interface to ask identical questions ("Is the service down?", "Why can't I log in?").

### The Systemic Failure Modes of Traffic Surges
1. **The Thundering Herd Collapse (Failure Matrix Q4, `RP-D6`)**:
   - In a severe incident, 500 users submit identical questions within a 60-second window. Naive systems spin up 500 concurrent multi-agent graphs, executing 500 redundant vector searches, 500 CRM lookups, and 1,500 LLM generation calls.
   - Downstream databases and LLM APIs saturate immediately, circuit breakers trip (`TA-D10`), turns fail, and all 500 users furiously click "Retry", initiating a fatal positive feedback loop that completely paralyzes the support platform.
2. **The Cold-Start Breaker Cascade ($KK2$)**:
   - Autoscaling based solely on CPU metrics experiences a $60–120\text{ second}$ pod provisioning lag (container image pull, Python interpreter initialization, LangGraph graph compilation).
   - During a sudden traffic surge, incoming requests queue up on unscaled workers. Request durations balloon past timeouts, tripping client and gateway circuit breakers before newly scaled pods become ready ($KK2$).
3. **The Blank Screen Cognitive Stall (`RP-D8`, $KU4$)**:
   - Under `EV-D11`, responses are buffered until output safety checks pass. If a diagnostic inquiry takes $18\text{ seconds}$ to retrieve logs and generate analysis, a user staring at a static loading bar will assume the system crashed and abandon the session.

### The Core Architectural Question
> **How do we engineer an execution harness that collapses 500 concurrent identical requests into a single execution, shunts incident traffic instantly via dedicated Jev classifiers, maintains strict route-specific latency budgets, and guarantees zero cold-start latency spikes?**

---

## 2. Decision Framework & Theoretical Formulation

To solve these challenges, `RP-D6`, `RP-D8`, and `RP-D9` establish the **Single-Flight Coalescing, Incident Triage Mode, and Pre-Warmed Elastic Capacity Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│             BURST ABSORPTION, COALESCING & INCIDENT TRIAGE PIPELINE (RP-D6, RP-D8)               │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                       Inbound Customer Turn Stream (Surge: 500 req/sec)
                                              │
             ┌────────────────────────────────┴────────────────────────────────┐
             ▼                                                                 ▼
┌─────────────────────────────────────────┐     ┌─────────────────────────────────────────┐
│ NORMAL OPERATION: SINGLE-FLIGHT         │     │ PLATFORM INCIDENT DECLARED:             │
│ REQUEST COALESCING (RP-D6)              │     │ JEV INCIDENT TRIAGE MODE (RP-D6, UK1)   │
├─────────────────────────────────────────┤     ├─────────────────────────────────────────┤
│ Intercepts Identical Concurrent Reads   │     │ On-Call Declares Active Incident:       │
│ Window: Δt = 200ms                      │     │ "EU Billing Database Degradation"       │
│                                         │     │                                         │
│ In-Flight Promise Map:                  │     │ Fast Jev Noul Check (< 120ms):          │
│ • Request 1: Executes Live Read         │     │ "Is message about ongoing incident?"    │
│ • Requests 2-50: Await Promise 1        │     │                                         │
│ ===> 50 queries collapsed into 1 call   │     │ Matching Traffic: Diverts to Prepared   │
│      Zero duplicate tool / vector load  │     │ Canonical Status Answer (Skips Graph!)  │
└────────────────────┬────────────────────┘     └────────────────────┬────────────────────┘
                     │                                               │
                     └───────────────────────┬───────────────────────┘
                                             ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ROUTE LATENCY ENVELOPE CONTROLLER (RP-D8, RP-Q5)                                                 │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 1. Time-to-First-Status Ticker:  ≤ 1.0s (p95) ===> Emits "Reviewing documentation..."            │
│ 2. Final Reply p95 Budget:                                                                       │
│    • FAQ / General Inquiry:      ≤ 5.0s (p95)                                                    │
│    • Diagnostic Technical Turn:  ≤ 20.0s (p95)                                                   │
│    • Multi-Specialist Sagas:     ≤ 45.0s (p95)                                                   │
│ Invariant: Step timeouts sum within total route budget; overrunning triggers early fallback      │
└────────────────────────────────────┬─────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ELASTIC INFRASTRUCTURE: PRE-WARMED AUTOSCALER (RP-D9, KK2)                                       │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ • Pre-Warmed Sovereign Floor: N_min ≥ 5 Pods per Region (Zero Cold-Start Breaker Trips)          │
│ • HPA Trigger Metric: Temporal Queue Depth + LangGraph In-Flight Turn Concurrency                │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Pillar 1: Single-Flight Request Coalescing (`RP-D6`)

To absorb micro-bursts of identical queries without hammering downstream systems:
1. **The In-Flight Promise Multiplexer**:
   - The Gateway and Tool Coordinator maintain an in-memory single-flight coalescing registry.
   - For any read-only operation (e.g., Qdrant hybrid retrieval or external status check), an idempotency hash is computed:
     $$\mathcal{H} = \text{SHA256}(\text{tenant\_id} \parallel \text{action\_name} \parallel \text{normalized\_query})$$
2. **Execution Merging Protocol**:
   - If a request arrives with hash $\mathcal{H}$ while an execution with identical hash $\mathcal{H}$ is currently in-flight (within a $\Delta t = 200\text{ms}$ execution window):
     - Request 2 does not invoke the database or tool API.
     - It subscribes directly to the in-memory `asyncio.Future` of Request 1.
     - When Request 1 completes, the identical return payload is dispatched to all awaiting callers simultaneously.
   - **Throughput Reduction**: In a sudden surge of 50 identical queries, physical backend executions collapse from $50 \to 1$.

---

### Pillar 2: Platform Incident Triage Mode (`RP-D6`, `Use #4`, `#8`)

During a major corporate service disruption, customers demand immediate confirmation rather than generic support dialogue ($UK1$):
1. **Incident Declaration Protocol**:
   - When an incident is active, the incident commander sets an incident banner and brief via the administrative API:
     $$\text{IncidentBrief} = \text{"AWS EU-West network degradation causing login timeouts."}$$
     $$\text{StatusAnswer} = \text{"We are actively investigating login failures in EU. Engineers are deploying a fix..."}$$
2. **TypeSafe Jev Fast-Triage (`Noul`)**:
   - Inbound turns pass through a lightweight, ultra-fast TypeSafe Jev classifier ($< 120\text{ms}$ latency):
     ```python
     is_incident_related: bool = await jev.evaluate_noul(
         question="Is this customer asking about or experiencing the active service disruption?",
         context=f"Incident: {IncidentBrief}\nCustomer: {user_message}"
     )
     ```
3. **Short-Circuit Status Delivery**:
   - If `is_incident_related == TRUE`:
     The turn completely bypasses specialist graphs, tool calls, and LangGraph multi-agent loops.
     The verified status answer is delivered immediately, passing through standard output safety sanitization (`SG-D6`).
   - This breaks the thundering-herd loop completely, shielding the foundation models and databases from thousands of redundant queries.

---

### Pillar 3: Route-Specific Latency Budgets (`RP-D8`, `RP-Q5`)

We establish strict, route-partitioned performance budgets governing execution time under buffered streaming (`EV-D11`):

| Conversational Route Scope | First Status Event ($p95$) | Final Reply Target ($p95$) | Hard Absolute Timeout | Fallback Behavior on Timeout |
| :--- | :--- | :--- | :--- | :--- |
| **FAQ / Documentation** | $\le 1.0\text{s}$ | **$\le 5.0\text{s}$** | $8.0\text{s}$ | Serve raw top-1 retrieved snippet without LLM generation |
| **Technical Diagnostic** | $\le 1.0\text{s}$ | **$\le 20.0\text{s}$** | $28.0\text{s}$ | Truncate log analysis; summarize current diagnostic findings |
| **Multi-Specialist Saga** | $\le 1.0\text{s}$ | **$\le 45.0\text{s}$** | $60.0\text{s}$ | Terminate specialist loop; route case to Human Co-Pilot (`HL-02`) |

#### Sub-Step Timeout Partitioning
Within a route's total budget, individual step timeouts are strictly bounded:
$$\sum \tau_{\text{step}} = \tau_{\text{screening}} + \tau_{\text{triage}} + \tau_{\text{retrieval}} + \tau_{\text{generation}} + \tau_{\text{safety}} \le \tau_{\text{route\_target}}$$
If retrieval takes $3.5\text{s}$ on an FAQ turn ($> 2.0\text{s}$ allocated), the orchestrator skips optional cross-encoder reranking (`KR-D12`) to keep total turn latency under the $5.0\text{s}$ ceiling.

---

### Pillar 4: Pre-Warmed Elastic Capacity (`RP-D9`, $KK2$)

To eradicate cold-start spikes during sudden bursts ($KK2$):
1. **The Pre-Warmed Regional Floor**:
   - Kubernetes deployments for stateless gateways, LangGraph orchestrator workers, and Temporal task-queue workers enforce strict replica floors:
     $$N_{\text{min}} \ge 5 \text{ pods per region at all times (24/7)}$$
   - Ensures that an instantaneous $10\times$ traffic burst is absorbed by immediately available compute without waiting for container boot.
2. **Queue-Depth Driven Autoscaling**:
   - Autoscaling does not rely purely on lagging CPU utilization.
   - The Horizontal Pod Autoscaler (HPA) evaluates custom Prometheus metrics tracking active in-flight turns and Temporal task queue backlog depth:
     $$N_{\text{desired}} = \max\left( N_{\min}, \left\lceil \frac{\text{QueueBacklog}}{\text{TargetThroughputPerPod}} \right\rceil \right)$$

---

## 3. Data Contracts & Execution Invariants

### 3.1 Incident Mode & Latency Budget Contracts

```python
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class ConversationalRouteType(str, Enum):
    FAQ_LOOKUP = "faq_lookup"
    TECHNICAL_DIAGNOSTIC = "technical_diagnostic"
    MULTI_SPECIALIST_SAGA = "multi_specialist_saga"

class RouteLatencyConfig(BaseModel):
    route_type: ConversationalRouteType
    first_status_target_seconds: float = Field(default=1.0)
    final_reply_p95_seconds: float
    hard_timeout_seconds: float

class ActiveIncidentState(BaseModel):
    """
    Contract governing active platform incident triage mode (RP-D6).
    """
    is_active: bool = Field(default=False)
    incident_id: Optional[str] = Field(None, regex=r"^inc_[a-zA-Z0-9]{16}$")
    incident_title: Optional[str] = None
    incident_brief: Optional[str] = None
    prepared_status_answer: Optional[str] = None
    declared_by_email: Optional[str] = None
    declared_at_utc: Optional[datetime] = None
```

### 3.2 Single-Flight Coalescing Invariant

$$\forall \text{ Hash } \mathcal{H}, \quad \text{ConcurrentInFlightExecutions}(\mathcal{H}) \le 1$$
Multiple concurrent read calls with identical parameters must share a single physical execution promise.

---

## 4. Quantitative Failure Modes & Operational Risk Bounds

| Failure Mode ID | Sub-Component & Severity | Risk Classification | Empirical Trigger Condition | Detection Vector | Automated Mitigation & Architectural Enforcement |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **RP-FM-301** | Cold-Start Spikes (`RP-D9`)<br>**HIGH** | Q1 Known Known (Latency Breach) | Traffic spikes during scheduled worker scale-down, causing request queues to exceed timeouts ($KK2$). | Gateway logs p95 turn latency exceeding route budget during scale-up events. | **Pre-Warmed Capacity Floor Enforcement**: Terraform HPA minimum pod setting strictly locked to $N_{\min} \ge 5$ pods. |
| **RP-FM-302** | Incident Stale State (`RP-D6`)<br>**HIGH** | Q1 Known Known (Process Drift) | On-call resolves production incident but forgets to disable Incident Mode, causing users to receive outage messages ($UK1$). | Anomaly detector reports $100\%$ incident triage match while production error rate is zero. | **Incident Mode Auto-Expire Timer**: Incident mode automatically deactivates after 4 hours unless explicitly renewed by the incident commander. |
| **RP-FM-303** | Coalescing Memory Leak (`RP-D6`)<br>**MEDIUM** | Q2 Known Unknown (Memory Bloat) | In-flight promise map fails to evict completed futures under high turn concurrency. | Worker process memory utilization increases monotonically over time. | **WeakRef & TTL Promise Eviction**: Promise registry utilizes Python `weakref` and an explicit 5-second TTL eviction per future. |
| **RP-FM-304** | Route Budget Overrun (`RP-D8`)<br>**MEDIUM** | Q2 Known Unknown (UX Degradation) | Multi-specialist saga executes 4 steps, exceeding 45s p95 latency budget ($RP\text{-}Q5$). | Tracing duration alert `turn_duration_seconds > 45` fires. | **Aggressive Step Cut-Off**: At $t = 38\text{s}$, the orchestrator halts remaining specialist sub-graphs and immediately formats best-effort response. |
| **RP-FM-305** | Incident Misclassification (`RP-D6`)<br>**HIGH** | Q3 Unknown Known (Tacit Convention) | Customer asking unrelated billing question during an incident gets incorrectly triaged into the incident response. | Jev Noul confidence score drops below 0.85 on incident classification. | **High-Confidence Gate**: Traffic only diverted if Jev Noul confidence $\ge 0.90$; ambiguous queries route to standard coordinator. |

---

## 5. Closed-Loop Architectural Feedback

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   BURST, LATENCY & CAPACITY HEALTH OBSERVABILITY ENGINE                          │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Ingress Turn Execution Stream
                 │
                 ▼
   ┌─────────────────────────────┐
   │ Single-Flight Coalescer     │─────► [Metric: coalesced_requests_merged_total]
   │ (Tracks Request Merges)     │       Measures backend queries saved
   └─────────────┬───────────────┘
                 │
                 ▼
   ┌─────────────────────────────┐
   │ Route Latency Profiler      │─────► [Metric: turn_latency_p95_seconds]
   │ (Tracks FAQ vs. Diagnostics)│       Evaluates against 5s, 20s, 45s targets
   └─────────────┬───────────────┘
                 │
                 ├──────────────────────────────────────────────┐
                 ▼ (Incident Mode Active)                       ▼ (Autoscaler Feedback)
   ┌─────────────────────────────┐               ┌─────────────────────────────┐
   │ Jev Incident Diverter       │               │ Temporal Queue Depth Gauge  │
   │ [Metric: incident_diverts]  │               │ Drives Kubernetes HPA pods  │
   └─────────────────────────────┘               └─────────────────────────────┘
```

### Telemetry & Operational SLOs
1. **Time-to-First-Status Latency**:
   - Metric: `first_status_event_duration_ms`
   - SLO: $p95 \le 1000\text{ms}$ (Target: $\le 300\text{ms}$).
2. **Route Latency Budget Compliance**:
   - FAQ Turns: $p95 \le 5.0\text{ seconds}$.
   - Diagnostic Turns: $p95 \le 20.0\text{ seconds}$.
   - Multi-Specialist Sagas: $p95 \le 45.0\text{ seconds}$.
3. **Single-Flight Coalescing Efficiency**:
   - Ratio of merged requests during peak bursts: $\ge 40\%$ reduction in duplicate queries.

---

## 6. Genesis Implementation Directive & Verification Protocol

### 6.1 Single-Flight Coalescing Implementation

```python
import asyncio
from typing import Dict, Any, Callable

class SingleFlightCoalescer:
    def __init__(self):
        self._in_flight: Dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    async def execute_or_coalesce(self, cache_key: str, action: Callable[[], Any]) -> Any:
        """
        Executes action or coalesces with existing in-flight future for identical key (RP-D6).
        """
        async with self._lock:
            if cache_key in self._in_flight:
                # Concurrent identical request detected: Subscribe to existing in-flight future
                future = self._in_flight[cache_key]
                return await future

            # First request: Create future and register in registry
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            self._in_flight[cache_key] = future

        try:
            # Execute physical action
            result = await action()
            future.set_result(result)
            return result
        except Exception as exc:
            future.set_exception(exc)
            raise
        finally:
            async with self._lock:
                self._in_flight.pop(cache_key, None)
```

### 6.2 Verification Checklist & Integration Tests

```bash
# 1. Verify Single-Flight Coalescing Efficiency
pytest tests/reliability/test_coalescing.py -k "test_concurrent_reads_collapse_to_one"

# Expected Output:
# PASS: 50 concurrent identical vector searches trigger exactly 1 underlying Qdrant query.
# PASS: All 50 callers receive bitwise identical return payload within 250ms.

# 2. Verify Incident Mode Triage Short-Circuit
pytest tests/reliability/test_incident_mode.py -k "test_outage_message_diverts_to_status"

# Expected Output:
# PASS: During active incident, customer query 'Why is EU down?' returns status answer in < 200ms.
# PASS: Underlying specialist graphs and tool APIs receive 0 invocations.
```

---

## 7. Trade-Off Analysis & Rejected Alternatives

| Dimension | Selected Paradigm (`RP-D6`, `RP-D8`, `RP-D9`) | Rejected Alternative A: Static Capacity Provisioning | Rejected Alternative B: Unconstrained Generation Latencies |
| :--- | :--- | :--- | :--- |
| **Burst & Thundering Herd Resilience** | **Absolute**: Coalescing collapses micro-bursts; incident mode diverts mass inquiries ($UK1$). | **Vulnerable**: Surges instantly saturate fixed worker limits, dropping users into 504 errors. | **N/A**: Relates to latency budgets. |
| **Cold-Start Elimination** | **Guaranteed**: $N_{\min} \ge 5$ pre-warmed pods per region absorb surges with zero boot lag ($KK2$). | **Guaranteed**: If over-provisioned, but idle compute costs are unsustainable ($KU1$). | **N/A**: Relates to capacity. |
| **User Experience & Responsiveness** | **Predictable**: Route budgets guarantee first status in $\le 1\text{s}$ and enforce hard ceilings. | **Unpredictable**: Latencies fluctuate wildly from 2s to 90s depending on load. | **Hostile**: Users endure 30+ seconds of silence before knowing if agent is working ($KU4$). |
| **Infrastructure Compute Cost** | **Optimized**: Coalescing saves up to $40\%$ of redundant queries; autoscales back down off-peak. | **Extreme**: Provisioning for 10x peak permanently wastes tens of thousands in idle server bills. | **Uncontrolled**: Long-running loops consume excessive GPU tokens. |

---

## 8. Formal References & Literature Grounding

1. **Beyer, B., Jones, C., Petoff, J., & Murphy, N. R. (2016).** *Site Reliability Engineering: How Google Runs Production Systems*. O'Reilly Media. Chapter 21: Handling Overload (Load shedding and single-flight request patterns). *(Foundational architecture for request coalescing).*
2. **Nygard, M. T. (2018).** *Release It!: Design and Deploy Production-Ready Software*. Pragmatic Bookshelf. Chapter 4: Capacity & Chapter 5: Stability Patterns. *(Principles of pre-warmed capacity and thundering herd mitigations).*
3. **Little, J. D. (1961).** *A Proof for the Queuing Formula: $L = \lambda W$*. Operations Research, 9(3), 383–387. *(Mathematical formula governing queue-depth based capacity scaling).*
4. **W3C Recommendation. (2015).** *Server-Sent Events*. World Wide Web Consortium. *(Standards governing progress event streaming under buffered execution).*
5. **NIST. (2020).** *Security and Privacy Controls for Information Systems and Organizations*. NIST SP 800-53, Rev 5. Control SC-5 (Denial of Service Protection) & Control PE-17 (Alternate Work Site). *(Standards governing burst absorption and incident contingency modes).*
