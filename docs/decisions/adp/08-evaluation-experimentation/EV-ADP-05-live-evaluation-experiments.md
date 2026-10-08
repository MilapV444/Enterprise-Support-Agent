# EV-ADP-05: Live Traffic Evaluation & Experimentation Architecture (Shadow Execution Sagas, Read-Only Canaries & Buffered Output Delivery)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-02 *(Confirmed per EV-D7 Read-Only Canaries EV-Q4, EV-D8 Sampled Live Scoring, EV-D11 Buffered Output Streaming UA-D8 & EV-D12 Shadow Tool Execution UU5)*
- **Deciders**: Architecture Team, Lead AI Evaluation Scientist, Principal Systems Architect, User Experience Lead
- **Component**: `[8] Evaluation & Experimentation` (`Component [ 8 ]`)
- **Reasoning Source**: `checkpoint.md` §12 · Diagram: `LLD - [8] Evaluation & Experimentation`
- **Decisions Covered**:
  - `EV-D7`: Live Experimentation Topology — Multi-stage traffic experimentation: Shadow-mode deployment on live traffic paired with selective Canary / A/B routing strictly restricted to Low-Risk Read-Only Routes (`EV-Q4`: FAQ queries, status checks, documentation lookups); production write traffic is completely excluded from live canary routing
  - `EV-D8`: Continuous Live Quality Telemetry — Dual-vector real-time quality observation: Continuous ingestion of implicit customer signals (thumbs up/down, prompt re-asks, manual human escalations, step-up MFA abandonment) combined with automated sampled scoring ($5\%$ production sample) via the cross-family LLM judge (`EV-D2`); samples adhere strictly to tokenization and sovereign regional boundaries (`EV-D10`)
  - `EV-D11`: Buffered Response Delivery & Progress Streaming — Final resolution of `UA-D8` (`UA-F8(c)`): Agent responses are completely buffered until 100% of safety checks (leakage, Markdown/URL sanitization `SG-D6`, unbacked promises `SG-D15`) pass; to prevent user perceived latency degradation ($KU4$), interactive `status` progress events ("Checking account status…", "Scanning knowledge base…") stream continuously via Server-Sent Events (SSE)
  - `EV-D12`: Shadow Mode Write-Containment Contract — When release candidates execute in shadow mode on live customer turns, read-only tools execute against live systems; write actions (financial debits, cancellations, status mutations) are recorded exclusively as hypothetical proposals and NEVER executed ($UU5$), completely eliminating duplicate write hazards
- **Related Architectural Decision Points**:
  - [`UA-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/01-user-application/UA-ADP-04-response-contract-delivery.md): Response Contract & Delivery *(Status Event Delivery Mechanics)*
  - [`SG-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/06-safety-security-governance/SG-ADP-03-output-safety.md): Output Safety *(Pre-Delivery Gate Invariants)*
  - [`DL-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#dl-adp-03--deployment-validation--rollback-triggers): Deployment Validation & Rollback Triggers *(Canary Health Tripwires)*
  - [`CI-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#ci-adp-01--production-signals--feedback-loops): Production Signals & Feedback Loops *(Continuous Improvement Pipeline)*

---

## 1. Context & Problem Statement

Evaluating autonomous multi-agent systems purely on offline test suites creates an inevitable reality gap:
1. **The Synthetic Blindspot**:
   - Real customers formulate inquiries with typos, incomplete thoughts, shifting intents, and unprecedented edge cases that synthetic suites fail to anticipate. Full evaluation requires testing new prompts, models, and retrieval strategies against live traffic.
2. **The Shadow Execution Side-Effect Hazard ($UU5$)**:
   - In traditional web services, "shadow mode" duplicates inbound HTTP requests to a secondary service and discards the response. In an autonomous agent system with external tool access, naive shadow execution is catastrophic: if the production agent issues a $\$50$ refund, and the shadow candidate agent also calls the live `issue_refund` tool, the customer receives a duplicate refund.
3. **The Streaming vs. Safety Dilemma (`UA-D8`, $KU4$)**:
   - Real-time token streaming provides superior Time-to-First-Token (TTFT) metrics, but exposes customers to catastrophic model outputs: if an agent streams a toxic hallucination, unauthorized prompt leak, or unbacked contractual promise token-by-token, the damage is done before an output guardrail can cancel the turn.
   - Conversely, buffering the full response until generation finishes introduces a $1.5–3.0\text{s}$ blank silence that frustrates users.

### The Core Architectural Question
> **How do we evaluate candidate agent versions against live production traffic without risking duplicate real-world side effects, and how do we enforce rigorous 100% pre-delivery output safety verification without creating a dead-air user experience?**

---

## 2. Decision Framework & Theoretical Formulation

To solve these dual challenges, `EV-D7`, `EV-D8`, `EV-D11`, and `EV-D12` establish the **Live Traffic Experimentation, Proposal-Only Shadow Engine, and Buffered SSE Status Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│             LIVE TRAFFIC EXPERIMENTATION & BUFFERED DELIVERY PIPELINE (EV-D7, EV-D11)            │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                       Live Inbound Customer Turn (User Sarah)
                                          │
            ┌─────────────────────────────┴─────────────────────────────┐
            ▼                                                           ▼
┌─────────────────────────────────────────┐                 ┌─────────────────────────────────────────┐
│ PRODUCTION ACTIVE WORKER (Release v2.3) │                 │ SHADOW EXPERIMENT WORKER (Release v2.4) │
├─────────────────────────────────────────┤                 ├─────────────────────────────────────────┤
│ • Full Tool Execution                   │                 │ • Tool Interceptor (EV-D12):            │
│ • Streams SSE Status Events (EV-D11)    │                 │   - Read Tools: Executed Live           │
│ • Buffers Output for Safety (SG-D6)     │                 │   - Write Tools: Recorded as PROPOSAL   │
│ • Delivers Checked Final Reply          │                 │ • Output Divergence Evaluator           │
└────────────────────┬────────────────────┘                 └────────────────────┬────────────────────┘
                     │                                                           │
                     ▼                                                           ▼
┌─────────────────────────────────────────┐                 ┌─────────────────────────────────────────┐
│ Client Browser / Mobile UI              │                 │ Offline Telemetry & Divergence Log      │
│ 1. Receives "Checking invoice..."       │                 │ Logs: Δ(Action_prod, Action_shadow)     │
│ 2. Receives Clean, Checked Reply        │                 │ Emits Shadow Equivalence Metric         │
└─────────────────────────────────────────┘                 └─────────────────────────────────────────┘

════════════════════════════════════════════════════════════════════════════════════════════════════
LIVE QUALITY MONITORING & CANARY GATING ENGINE (EV-D7, EV-D8)
════════════════════════════════════════════════════════════════════════════════════════════════════

   Canary Traffic Router (Strictly Read-Only Routes: FAQs, Documentation, Order Lookups)
               │
               ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │ Real-Time Signal Aggregator (EV-D8)                                    │
   │ • Implicit: Thumbs Down Rate, Re-Ask Frequency, Human Escalation Rate  │
   │ • Sampled Live Scoring: 5% of Turns Evaluated by GPT-4o Judge (EV-D2)  │
   └───────────────────────────────────┬────────────────────────────────────┘
                                       │
                                       ▼
                       ┌───────────────────────────────┐
                       │ Canary Tripwire Controller    │
                       │ Escalation > 8.0% ===> ROLLBACK│
                       │ CSAT Drop > 0.05  ===> ROLLBACK│
                       └───────────────────────────────┘
```

---

### Pillar 1: Proposal-Only Shadow Mode Execution (`EV-D12`, $UU5$)

To evaluate candidate models on complex multi-step reasoning without risking external side effects, the execution engine deploys a **Tool Execution Interceptor**:

#### The Shadow Interception Protocol
Let $T$ be a tool invoked by the shadow candidate agent with arguments $\alpha$. Let $\text{IsReadOnly}(T)$ be the immutable risk classification metadata registered in the Tool Registry (`TA-D1`):
$$\text{Execute}(T, \alpha) = \begin{cases} \text{ExecuteLive}(T, \alpha) & \text{if } \text{IsReadOnly}(T) == \text{TRUE} \\ \text{RecordProposalOnly}(T, \alpha) & \text{if } \text{IsReadOnly}(T) == \text{FALSE} \end{cases}$$

1. **Live Read Execution**:
   - Tools that read state (e.g., `get_customer_billing_history`, `search_knowledge_base`) execute live against production APIs. This provides the shadow agent with genuine, up-to-date context identical to the live production worker.
2. **Write Action Suppression & Proposal Logging**:
   - Tools that mutate external state (e.g., `issue_refund`, `cancel_subscription`, `update_email`) are intercepted before network dispatch.
   - The interceptor injects a simulated synthetic success return into the shadow agent's LangGraph scratchpad:
     ```python
     return {"status": "SHADOW_SIMULATED_SUCCESS", "action_id": "sim_act_99"}
     ```
   - Simultaneously, an append-only proposal event is emitted to the shadow audit log:
     $$\text{Proposal} = \{ \text{candidate\_version}, \text{turn\_id}, T.\text{name}, \text{args\_hash}, \alpha \}$$
3. **Divergence Metric Calculation**:
   Offline analytics compare the shadow agent's proposed action $\alpha_{\text{shadow}}$ against the actual action executed by the production agent $\alpha_{\text{prod}}$:
   $$\text{AgreementRatio} = \frac{1}{N} \sum_{i=1}^{N} \mathbf{1}\left( \alpha_{\text{shadow}}^{(i)} == \alpha_{\text{prod}}^{(i)} \right)$$

---

### Pillar 2: Read-Only Canary Experimentation (`EV-D7`, `EV-Q4`)

Canary releases test candidates on real end-users, but must strictly bound the blast radius:
1. **The Read-Only Invariant (`EV-Q4`)**:
   - Only conversational routes classified as strictly read-only are eligible for canary routing (e.g., general inquiries, navigation assistance, documentation lookups).
   - Any turn in which the intent classifier detects write intent (e.g., "cancel my account", "refund my payment") is pinned unconditionally to the stable production release (`v_current`).
2. **Automated Canary Rollback Tripwires (`DL-ADP-03`)**:
   The canary routing gateway continuously evaluates real-time telemetry over a sliding 1-hour window:
   - **Escalation Tripwire**: If the human escalation rate on canary traffic exceeds $1.25 \times \text{Baseline}$, canary traffic resets to $0\%$.
   - **Safety Tripwire**: If any output screening check triggers on canary traffic, canary routing terminates immediately.

---

### Pillar 3: Buffered Output Streaming & Real-Time Status Ticker (`EV-D11`)

We resolve `UA-D8` by adopting the **Buffered Final Reply with Streaming Status Ticker** architecture:

#### Perception & Safety Trade-Off Formulation
Let $T_{\text{gen}}$ be the generation latency of the model ($\approx 1200\text{ms}$), and $T_{\text{checks}}$ be the latency of deterministic leakage, URL, and promise checks ($\approx 80\text{ms}$).
- Direct token streaming yields perceived latency $\approx 250\text{ms}$, but safety leak risk is catastrophic:
  $$\mathbb{P}(\text{Safety Breach Reaches User}) > 0$$
- Completely buffering the response keeps safety breach risk at **strictly $0$**, but perceived latency equals $T_{\text{gen}} + T_{\text{checks}} \approx 1280\text{ms}$.

#### The Streaming Status Mitigation
To eliminate the dead-air sensation during the $1280\text{ms}$ buffering interval:
1. **Interactive Status Ticker**:
   - As the agent graph transitions across nodes, lightweight SSE status events are emitted to the client:
     - $t = 100\text{ms}$: `event: status`, `data: {"text": "Searching knowledge base..."}`
     - $t = 450\text{ms}$: `event: status`, `data: {"text": "Reviewing invoice history..."}`
     - $t = 900\text{ms}$: `event: status`, `data: {"text": "Formulating resolution..."}`
2. **Atomic Final Delivery**:
   - The full response text is buffered in worker memory.
   - The output safety pipeline (`SG-D6`, `SG-D15`) executes synchronously against the buffered text.
   - Upon verification approval, the complete checked markdown response is delivered as a final atomic SSE payload (`event: final_response`).
   - The user experiences active, continuous feedback without exposure to unchecked raw tokens.

---

## 3. Data Contracts & Execution Invariants

### 3.1 Shadow Execution & Proposal Schema Contract

```python
from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

class ShadowActionProposal(BaseModel):
    """
    Contract logging a simulated tool execution in shadow mode (EV-D12).
    """
    shadow_run_id: str = Field(..., regex=r"^shd_[a-zA-Z0-9]{16}$")
    candidate_version: str = Field(..., description="Release tag of shadow candidate")
    conversation_id: str = Field(...)
    turn_id: str = Field(...)
    tool_name: str = Field(..., min_length=2, max_length=64)
    proposed_arguments: Dict[str, Any] = Field(..., description="Arguments that would have been executed")
    is_write_action: bool = Field(..., description="Must be True for intercepted writes")
    intercepted_and_suppressed: bool = Field(default=True, description="Invariant: True for all writes")
    created_at_utc: datetime = Field(default_factory=datetime.utcnow)

class LiveQualitySignal(BaseModel):
    """
    Contract capturing real-time implicit and sampled quality metrics (EV-D8).
    """
    turn_id: str = Field(...)
    tenant_id: str = Field(...)
    version: str = Field(...)
    thumbs_feedback: Optional[int] = Field(None, ge=-1, le=1, description="+1 for up, -1 for down")
    user_re_ask_detected: bool = Field(default=False)
    human_escalation_triggered: bool = Field(default=False)
    sampled_for_judge: bool = Field(default=False)
    judge_faithfulness_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    created_at_utc: datetime = Field(default_factory=datetime.utcnow)
```

### 3.2 Shadow Write-Immunity Invariant

$$\forall \text{ ToolInvocation } T \in \text{ShadowWorker}, \quad \text{IsWrite}(T) \implies \text{NetworkEgressBytes}(T) \equiv 0$$
Under no circumstance may a shadow worker process transmit network packets to external write endpoints.

---

## 4. Quantitative Failure Modes & Operational Risk Bounds

| Failure Mode ID | Sub-Component & Severity | Risk Classification | Empirical Trigger Condition | Detection Vector | Automated Mitigation & Architectural Enforcement |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **EV-FM-501** | Shadow Containment (`EV-D12`)<br>**CRITICAL** | Q1 Known Known (Security Leak) | Developer registers a new write tool but misclassifies it as `read_only = True` in tool metadata. | Tool execution audit catches shadow worker modifying live CRM state ($UU5$). | **Tool Registry Security Review (`TA-D16`)**: CI fails build if any tool making POST/PUT/DELETE HTTP calls is tagged read-only. |
| **EV-FM-502** | User Latency Perceived (`EV-D11`)<br>**MEDIUM** | Q2 Known Unknown (UX Degradation) | Output check takes longer than expected ($> 600\text{ms}$), causing user to abandon chat before response appears ($KU4$). | Frontend telemetry reports turn abandonment during status display phase. | **Strict Output Check Timeout**: If output safety check exceeds $200\text{ms}$, regex fast-path is used; complex LLM rewrites aborted. |
| **EV-FM-503** | Canary Blast Bleed (`EV-D7`)<br>**HIGH** | Q3 Unknown Known (Tacit Convention) | Gateway routing error directs customer intending to cancel account to canary worker. | Canary router audit logs write-intent classification on canary node. | **Dynamic Gateway Fallback**: If user utterance in canary session scores $> 0.50$ write probability, turn immediately reroutes to production cluster. |
| **EV-FM-504** | Judge Sampling Cost (`EV-D8`)<br>**MEDIUM** | Q2 Known Unknown (Token Budget) | High production traffic surge causes 5% judge sampling to incur thousands of dollars in external API fees ($KU1$). | Judge rate limiter detects $> 100\text{ judge calls/minute}$. | **Adaptive Dynamic Sampling**: Sampling rate dynamically throttles from $5\%$ down to $1\%$ when global traffic exceeds $10,000\text{ turns/hour}$. |
| **EV-FM-505** | Shadow Read Load (`EV-D12`)<br>**HIGH** | Q4 Unknown Unknown (Capacity Spike) | Shadow workers running on $100\%$ of production traffic double the read load on internal database replicas. | Database read replica CPU utilization exceeds $85\%$; query latency spikes. | **Shadow Sample Throttling**: Shadow mode worker execution capped at $25\%$ of production traffic volume via hash partitioning. |

---

## 5. Closed-Loop Architectural Feedback

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   LIVE EXPERIMENTATION & CANARY HEALTH ENGINE                                    │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Live Inbound Turn Traffic
               │
               ▼
   ┌───────────────────────────────┐
   │ Route Classifier & Router     │─────► [Metric: canary_traffic_share_ratio]
   │ (Only Read Routes to Canary)  │       Target: 5% (Monitors route isolation)
   └──────────────┬────────────────┘
               │
               ├──────────────────────────────────────────────┐
               ▼                                              ▼
   ┌───────────────────────────────┐              ┌───────────────────────────────┐
   │ Canary Signal Aggregator      │              │ Shadow Mode Worker Pool       │
   │ (Tracks Thumbs & Escalations) │              │ (Executes Reads; Logs Writes) │
   └──────────────┬────────────────┘              └──────────────┬────────────────┘
               │                                              │
               ▼                                              ▼
   [Metric: canary_escalation_rate]               [Metric: shadow_write_attempts_suppressed]
   Tripwire: > 1.25x Baseline triggers            Verifies 100% write suppression (Target: 0 executed)
   Automated Canary Rollback (DL-03)
```

### Telemetry & Operational SLOs
1. **Shadow Mode Write Leakage**:
   - Metric: `shadow_unauthorized_writes_executed_total`
   - Hard Target: **Strictly 0**.
2. **Canary Escalation Delta**:
   - $\Delta\text{EscalationRate} = \text{Escalation}_{\text{canary}} - \text{Escalation}_{\text{prod}} \le 0.015$.
3. **Buffered Delivery TTFT (First Status Event)**:
   - Metric: `time_to_first_status_event_ms`
   - Target: $p95 < 200\text{ms}$.
4. **Final Checked Output Delivery Delay**:
   - Metric: `output_safety_check_duration_ms`
   - Target: $p95 < 60\text{ms}$, $p99 < 150\text{ms}$.

---

## 6. Genesis Implementation Directive & Verification Protocol

### 6.1 Shadow Tool Interceptor Implementation

```python
from typing import Any, Dict
from pydantic import BaseModel

class ShadowExecutionInterceptor:
    def __init__(self, shadow_audit_writer, is_shadow_mode: bool = True):
        self.shadow_audit = shadow_audit_writer
        self.is_shadow_mode = is_shadow_mode

    async def execute_tool_call(
        self,
        tool_definition,
        tool_args: Dict[str, Any],
        turn_context: dict
    ) -> Dict[str, Any]:
        """
        Guarantees that shadow workers execute live reads but strictly suppress writes.
        """
        if not self.is_shadow_mode:
            # Active production worker: execute tool normally
            return await tool_definition.execute(**tool_args)

        if tool_definition.is_read_only:
            # Read-only tool: safe to execute against live production systems (EV-D12)
            return await tool_definition.execute(**tool_args)

        # WRITE TOOL DETECTED IN SHADOW WORKER: INTERCEPT & SUPPRESS
        proposal = {
            "candidate_version": turn_context["version"],
            "conversation_id": turn_context["conversation_id"],
            "turn_id": turn_context["turn_id"],
            "tool_name": tool_definition.name,
            "proposed_arguments": tool_args,
            "is_write_action": True,
            "intercepted_and_suppressed": True
        }
        await self.shadow_audit.record_proposal(proposal)

        # Return simulated synthetic response to allow shadow LangGraph execution to continue
        return {
            "status": "SIMULATED_SHADOW_SUCCESS",
            "message": f"Tool '{tool_definition.name}' simulated in shadow mode. Zero side effects."
        }
```

### 6.2 Verification Checklist & Integration Tests

```bash
# 1. Verify Shadow Mode Write Suppression
pytest tests/evaluation/test_shadow_mode.py -k "test_shadow_write_tools_never_execute"

# Expected Output:
# PASS: Shadow worker calling issue_refund records proposal in audit log.
# PASS: External payment API reports 0 network requests from shadow worker IP.

# 2. Verify Buffered Output SSE Delivery
pytest tests/evaluation/test_buffered_streaming.py -k "test_status_events_stream_before_final"

# Expected Output:
# PASS: Client receives 'status' SSE event within 150ms of turn start.
# PASS: Final checked response delivered only after SG-D6 leakage checks pass.
```

---

## 7. Trade-Off Analysis & Rejected Alternatives

| Dimension | Selected Paradigm (`EV-D7`, `EV-D8`, `EV-D11`, `EV-D12`) | Rejected Alternative A: Full Live Write Canary | Rejected Alternative B: Unbuffered Real-Time Token Streaming |
| :--- | :--- | :--- | :--- |
| **Operational Safety & Side Effects** | **Absolute**: Shadow writes strictly suppressed ($UU5$); canaries restricted to read-only traffic. | **High Risk**: Canary candidate making live financial writes risks real customer financial loss. | **Zero Safety**: Raw tokens delivered instantly; cannot retract leaked prompt or unbacked promises. |
| **User Experience & Perceived Speed** | **High**: Continuous streaming status events eliminate dead-air silence during buffering ($KU4$). | **High**: Standard streaming, but risk of confusing hallucinations. | **Fastest TTFT**: User sees tokens in $250\text{ms}$, but experiences awkward retract/delete flashes on safety trip. |
| **Real-Traffic Evaluation Depth** | **High**: Shadow mode tests full reasoning and proposal accuracy against real customer distributions. | **Maximum**: Full real traffic, but blast radius is unacceptably high for enterprise banking/support. | **N/A**: Relates purely to delivery mechanics. |
| **Systemic Complexity** | **Moderate**: Requires tool interceptor and status event emission pipeline. | **Lowest**: Standard routing, but requires expensive disaster recovery runbooks. | **Lowest**: Raw pass-through, but fails compliance output safety standards. |

---

## 8. Formal References & Literature Grounding

1. **Nygard, M. T. (2018).** *Release It!: Design and Deploy Production-Ready Software*. Pragmatic Bookshelf. Chapter 9: Canary Deployments & Chapter 10: Shadow Testing. *(Engineering patterns for safe production traffic shadowing and side-effect containment).*
2. **W3C Recommendation. (2015).** *Server-Sent Events*. World Wide Web Consortium. *(Protocol specification for real-time progress event streaming and reconnection semantics).*
3. **Es, S., et al. (2023).** *RAGAS: Automated Evaluation of Retrieval Augmented Generation*. arXiv preprint arXiv:2309.15217. *(Standard metrics for automated sampled live quality monitoring).*
4. **NIST. (2023).** *Artificial Intelligence Risk Management Framework (AI RMF 1.0)*. National Institute of Standards and Technology. Section 3.4: Safe and Resilient AI. *(Guidelines for continuous production AI monitoring, canary gating, and rapid rollback triggers).*
5. **Kleppmann, M. (2017).** *Designing Data-Intensive Applications*. O'Reilly Media. *(Principles of read/write operational segregation in distributed microservice architectures).*
