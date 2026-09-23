# Enterprise AI Support Agent — End-to-End Request-Response Lifecycle Walkthrough

> **Companion Document:** [`architecture.md`](./architecture.md)  
> **Visual Diagram Canvas:** [`architecture.tldr`](./architecture.tldr)  
> **Source Capabilities:** [`thoughts.md`](./thoughts.md)  

---

## 1. Concrete Enterprise Scenario

* **Customer:** Sarah Chen, Lead Cloud Architect at **Acme Corp** (Enterprise Platinum Tier).
* **Channel:** Enterprise Web Support Portal (Authenticated chat widget with SSO).
* **User Query:**
  > *"Our production DB replica failed over after yesterday's v4.2 upgrade, and invoice #INV-9821 shows an unexpected $12,400 overage surcharge. Can you check why the failover happened and refund the unauthorized charge?"*

### Why This Scenario Exercises the Entire Architecture:
1. **Dual Domain Complexity:** Combines a deep technical incident (`tech_incident.database_failover`) with a financial dispute (`billing.overage_dispute_and_refund`).
2. **Sensitive & Masked Identifiers:** Carries PII, account tokens, and financial invoice records.
3. **Context Enrichment:** Requires **Memory & State** (SLA tiers, topology, ticket history) and **Knowledge RAG** (v4.2 upgrade release notes, known issue database).
4. **Tools & Enterprise APIs:** Interacts with Cloud Telemetry / CloudWatch and ERP / Billing systems.
5. **Multi-Agent Coordination:** Orchestrates between specialized sub-agents (Tech Ops Specialist + Billing Specialist).
6. **Confidence & HITL Governance:** Technical explanation is high confidence (96%), but the $12,400 refund exceeds the autonomous financial threshold ($1,000 max), triggering the **Human-in-the-Loop (HITL)** specialist review.
7. **Streaming Response & Foundation Telemetry:** Emits real-time SSE chunks back to the user client while asynchronously updating OpenTelemetry traces, PostgreSQL persistence, and evaluation suites.

---

## 2. System Architecture & Topology Map

```
  ┌───────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │ TIER 1: INGRESS & EDGE SECURITY (Left-to-Right Flow)                                                  │
  │ [1] User Channels ──► [2] API Gateway ──► [3] Reliability & Resilience ──► [4] Input Safety Guardrails│
  └────────────────────────────────────────────────────────────────────────────────────────┬──────────────┘
                                                                                           │ Sanitized Query
  ┌────────────────────────────────────────────────────────────────────────────────────────▼──────────────┐
  │ TIER 2: COGNITIVE REASONING & EXECUTION CORE                                                          │
  │   [6] Memory & State ◄──► [5] AGENT ORCHESTRATION CORE ──► [8] Model Runtime ◄──► [9] Tools & APIs   │
  │   [7] Knowledge RAG  ◄──► [Cap 12] Cost/Token Router         ▲                                       │
  │                                                              └──► [10] Multi-Agent Sub-Agents         │
  └────────────────────────────────────────────────────────────────────────┬──────────────────────────────┘
                                                                           │ Candidate Draft
  ┌────────────────────────────────────────────────────────────────────────▼──────────────────────────────┐
  │ TIER 3: GOVERNANCE, HITL & RESPONSE DELIVERY (Right-to-Left Return Flow)                              │
  │   [14] User Served ◄── [13] Response Engine ◄── [12] Output Safety ◄── [11] Confidence Gate          │
  │       ▲                                                                       ▲         │ <$1k Auto   │
  │       │                                                       Specialist Appr │         ▼ >=$1k       │
  │       │                                                                       └─ [HITL] Specialist    │
  │       └──────── Lifecycle Completed (Session Open for Follow-up) ─────────────────────────────────────┤
  └───────────────────────────────────────────────────────────────────────────────────────────────────────┘
  ┌───────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │ TIER 4: ENTERPRISE FOUNDATION PLATFORM (Continuous Telemetry, State & LLMOps)                         │
  │ Testing & CI/CD (14,15) │ Data & Persistence (8) │ Evaluation (10) │ Observability (9) │ Continuous (16) │
  └───────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Detailed Component-by-Component Trace

### Tier 1 — Ingress & Edge Security Tier (Capabilities 1, 7, 11)

#### `[ 1 ] User Channels & Ingress`
* **Action:** Sarah enters her query into the authenticated web portal and submits.
* **Payload Dispatched:**
  ```http
  POST /api/v1/support/chat/message HTTP/1.1
  Host: support.enterprise-cloud.io
  Authorization: Bearer eyJhbGciOi... (Sarah's JWT)
  Content-Type: application/json

  {
    "session_id": "sess_88429b",
    "channel": "web_portal",
    "timestamp": "2026-09-09T18:15:00Z",
    "message": "Our production DB replica failed over after yesterday's v4.2 upgrade, and invoice #INV-9821 shows an unexpected $12,400 overage surcharge. Can you check why the failover happened and refund the unauthorized charge?"
  }
  ```

#### `[ 2 ] API Gateway & Identity`
* **Action:** 
  1. Validates the JWT signature against enterprise Auth0 / Okta IdP.
  2. Extracts authenticated tenant context:
     * `tenant_id`: `"acme-corp"`
     * `user_id`: `"usr_sarah_chen"`
     * `roles`: `["cloud_admin", "billing_viewer"]`
  3. Verifies active enterprise support contract (Enterprise Platinum tier).

#### `[ 3 ] Reliability & Resilience`
* **Action:**
  1. Checks **Token Bucket Rate Limiting** for `tenant:acme-corp` (Tenant limit: 120 req/min; Current usage: 8 req/min → **Approved**).
  2. Evaluates downstream **Circuit Breakers** (All systems green).
  3. Injects OpenTelemetry distributed tracing header:
     `traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01`

#### `[ 4 ] Input Safety Guardrails`
* **Action:**
  1. **Prompt Injection Shield:** Inspects text for jailbreaks, prompt override commands, or system prompt exfiltration (Injection score: 0.01 → Passed).
  2. **PII Masking & Sanitization:** Verifies query does not leak raw credentials or unencrypted secret keys. Identifies and tokenizes entities:
     * `[INVOICE_ID: #INV-9821]`
     * `[VERSION_TAG: v4.2]`
     * `[AMOUNT: $12,400.00]`
* **Output:** Sanitized query envelope forwarded to Tier 2.

---

### Tier 2 — Cognitive Reasoning & Execution Core (Capabilities 2, 3, 4, 5, 6, 12)

```
             ┌─────────────────────────────────────────────────────────────┐
             │            [ 5 ] AGENT ORCHESTRATION CORE                   │
             │  • Intent: Composite (Incident Triage + Billing Dispute)    │
             │  • Execution Plan: Sub-agent Fan-out & Tool Execution       │
             └──────┬───────────────────────┬───────────────────────┬──────┘
                    │ Load Profile          │ Fetch Runbooks        │ Model Routing
                    ▼                       ▼                       ▼
            ┌───────────────┐       ┌───────────────┐       ┌───────────────┐
            │ [ 6 ] Memory  │       │ [ 7 ] RAG     │       │ [Cap 12] Cost │
            │   & State     │       │   Retrieval   │       │   Router      │
            └───────────────┘       └───────────────┘       └───────┬───────┘
                                                                    │ Prompt
                                                                    ▼
                                                            ┌───────────────┐
                                                            │ [ 8 ] LLM     │
                                                            │   Runtime     │
                                                            └───┬───────┬───┘
                                              Tool Call (ERP)   │       │ Delegate
                                                                ▼       ▼
                                                        ┌────────┐   ┌─────────────┐
                                                        │[9]Tools│   │[10]SubAgents│
                                                        └────────┘   └─────────────┘
```

#### `[ 5 ] AGENT ORCHESTRATION CORE` (The Brain)
* **Action:**
  1. **Intent Classification:** Classifies the request as a **Composite Multi-Domain Intent**:
     * Intent A: `tech_incident.database_failover_investigation`
     * Intent B: `billing.overage_dispute_and_refund`
  2. **Plan Synthesis:**
     * Step 1: Query Memory for customer cluster details and past maintenance tickets.
     * Step 2: Query Knowledge Base (RAG) for v4.2 upgrade notes and failover incident reports.
     * Step 3: Call Monitoring API for database metrics and replica failover logs.
     * Step 4: Delegate refund handling to Billing Specialist Sub-Agent.

#### `[ 6 ] Memory & State Engine`
* **Action:** Orchestrator queries `fetch_session_and_profile(tenant_id="acme-corp", user_id="usr_sarah_chen")`.
* **Retrieved State:**
  ```json
  {
    "tenant_name": "Acme Corp",
    "tier": "Enterprise Platinum",
    "sla_uptime_target": "99.99%",
    "infrastructure": {
      "cluster_id": "db-acme-prod",
      "primary_region": "us-east-1",
      "secondary_replica": "us-east-2"
    },
    "recent_history": [
      {
        "ticket_id": "T-4412",
        "date": "2026-09-08",
        "title": "Scheduled v4.2 maintenance window executed"
      }
    ]
  }
  ```

#### `[ 7 ] Knowledge & RAG Retrieval`
* **Action:** Hybrid vector embedding + BM25 search over enterprise technical documentation, followed by cross-encoder reranking:
  * Query: `v4.2 upgrade release notes database failover known issues replication bandwidth`
* **Top-k Passages Retrieved:**
  * **Passage 1 (Relevance 0.94):**
    > *"Release v4.2 introduces dynamic connection pooling. Under spike loads during schema migration, standby replicas may trigger transient heartbeat timeouts (Err 504), causing an automatic failover to the secondary zone."*
  * **Passage 2 (Relevance 0.89):**
    > *"Known Bug BUG-8192: Cross-region data synchronization during transient failover incorrectly logged temporary ingress replication as unmetered bandwidth surcharge."*

#### `[ Cap 12 ] Cost & Resource Router`
* **Action:**
  1. Evaluates reasoning complexity: Composite multi-turn incident + cross-domain financial delegation.
  2. **Model Tier Selection:** Routes to Frontier Reasoning Model (e.g. Claude 3.5 Sonnet / GPT-4o) rather than lightweight SLM.
  3. **Token Budgeting:** Allocates 4,000 completion tokens. Semantic cache checked (Miss: unique invoice ID).

#### `[ 8 ] Model Runtime & LLM`
* **Action:** The LLM receives the compiled context window (System prompt + Acme profile + RAG excerpts + Tool schemas + User query) and produces structured function calls:
  1. Tool Call 1: `query_cloud_monitoring(cluster_id="db-acme-prod", timerange="24h")`
  2. Tool Call 2: `get_invoice_breakdown(invoice_id="INV-9821")`
  3. Sub-Agent Delegation: `delegate_to_subagent(agent="billing_specialist", ...)`

#### `[ 9 ] Tools & Enterprise APIs`
* **Action:** Executes external API calls in a secure sandbox:
  1. **Cloud Monitoring Tool Response:**
     ```json
     {
       "cluster_id": "db-acme-prod",
       "event": "FAILOVER_TRIGGERED",
       "timestamp": "2026-09-08T22:14:02Z",
       "primary": "db-prod-primary-01",
       "secondary": "db-prod-secondary-01",
       "root_cause": "Heartbeat timeout during v4.2 schema migration (BUG-8192)",
       "current_status": "Healthy (Active on db-prod-secondary-01)"
     }
     ```
  2. **ERP Billing System Response:**
     ```json
     {
       "invoice_id": "INV-9821",
       "total_amount": 34800.00,
       "line_items": [
         {
           "code": "NET-DATA-INGRESS",
           "description": "Cross-region sync replication bandwidth",
           "amount": 12400.00
         }
       ]
     }
     ```

#### `[ 10 ] Multi-Agent Sub-Agents`
* **Billing Specialist Sub-Agent Execution:**
  * Analyzes invoice line item against the telemetry root cause (`BUG-8192`).
  * Determines that the $12,400 bandwidth surcharge was an erroneous billing bug caused by the failover resync.
  * Checks Autonomous Authority Limits:
    * *Autonomous refund ceiling:* **$1,000.00**
    * *Requested refund:* **$12,400.00** → Exceeds autonomous limit!
  * Prepares action proposal: `apply_credit_memo(tenant="acme-corp", amount=12400.00)` with `requires_human_approval: true`.
* **Output:** Candidate draft and action payload returned to the Orchestrator.

---

### Tier 3 — Governance, Human-in-the-Loop & Response Delivery Tier (Capabilities 7, 13, 1)

```
  Candidate Draft from Execution Core
            │
            ▼
 ┌───────────────────────────────────────┐
 │ [ 11 ] Confidence Gate & Eval         │
 │ • Technical Explanation: 96% Conf     │
 │ • Financial Action: Exceeds $1,000    │──► [Escalate: Amount >= $1,000] ──┐
 └──────────────────┬────────────────────┘                                   │
                    │                                                        ▼
                    │ Approved (<$1,000 or post-HITL)             ┌──────────────────────┐
                    │                                             │ [HITL] Human Support │
                    ▼                                             │ Specialist Console   │
 ┌───────────────────────────────────────┐                        │  • Reviews Evidence  │
 │ [ 12 ] Output Safety Guardrails       │                        │  • One-Click Approve │
 │ • Hallucination Shield: 100% Grounded │◄─── [Specialist Approves] ┘
 │ • Corporate Policy & Tone: Compliant  │
 └──────────────────┬────────────────────┘
                    │ Verified Safe
                    ▼
 ┌───────────────────────────────────────┐
 │ [ 13 ] Response Delivery Engine       │
 │ • SSE Token Streaming                 │
 │ • Session State Commit to PostgreSQL  │
 └──────────────────┬────────────────────┘
                    │ Stream to User
                    ▼
 ┌───────────────────────────────────────┐
 │ [ 14 ] User Client (Served)           │
 │ • Message rendered in UI              │
 │ • Feedback Thumbs Up / Down Enabled   │
 └──────────────────┬────────────────────┘
                    │ Return Loop
                    ▼
           Lifecycle Completed (Session Open for follow-up)
```

#### `[ 11 ] Confidence Gate & Eval`
* **Action:**
  * Evaluates factual groundedness score: `0.96` (High confidence).
  * Evaluates financial risk policy: The proposed action is a financial refund of `$12,400.00`.
  * **Gate Rule:** Any financial action exceeding `$1,000.00` must be routed to a human specialist.
  * **Decision:** Route to **[HITL] Human Support Specialist Console**.

#### `[ HITL ] Human Support Specialist (Escalation Review)`
* **Action:**
  1. A review card is dispatched to the enterprise support specialist console:
     ```yaml
     Customer: Acme Corp (Enterprise Platinum)
     User: Sarah Chen (Cloud Architect)
     Incident: Production database failover following v4.2 upgrade
     Root Cause: Known bug BUG-8192 (heartbeat timeout during schema migration)
     Current Cluster Status: Healthy on secondary replica
     Proposed Financial Action: Issue $12,400 Credit Memo for bandwidth surcharge
     Supporting Evidence:
       - AWS CloudWatch failover event at 2026-09-08 22:14:02 UTC
       - ERP Line Item: NET-DATA-INGRESS ($12,400.00)
     ```
  2. Senior Support Specialist *Alex* validates the log correlation and clicks **[Approve $12,400 Refund & Release Response]**.

#### `[ 12 ] Output Safety Guardrails`
* **Action:**
  1. **Hallucination & Factuality Shield:** Asserts that all factual claims match the verified logs and RAG passages.
  2. **Corporate Policy & Tone:** Confirms tone is apologetic, transparent, and authoritative.
  3. **Credential & Privacy Check:** Verifies no internal IP addresses, backend hostnames, or auth tokens leaked into output.

#### `[ 13 ] Response Delivery Engine`
* **Action:**
  1. Establishes Server-Sent Events (SSE) stream back to Sarah's active browser connection.
  2. Commits updated session history and financial action record (`CreditMemo #CM-4109`) to persistence.

#### `[ 14 ] User Client (Served)`
* **What Sarah Chen Receives in Her Web UI:**
  > **Resolution Summary:**
  > 
  > 1. **Root Cause of Failover:**  
  > During yesterday's v4.2 maintenance, cross-region schema synchronization experienced transient connection timeouts (identified under **BUG-8192**). Your database safely executed an automated failover to your secondary replica (`db-prod-secondary-01`), which is currently healthy and serving traffic with zero data loss.
  > 
  > 2. **Invoice Adjustment & Refund:**  
  > The $12,400 surcharge on invoice `#INV-9821` was an erroneous bandwidth metering anomaly caused by the cross-region data resync during the failover.
  > 
  > **Action Taken:**  
  > Our enterprise billing team has approved and credited **$12,400.00** back to your account under **Credit Memo #CM-4109**. Your revised invoice balance is **$22,400.00**.
  > 
  > *Was this resolution helpful? [ 👍 Yes ] [ 👎 No ]*

* **Return Loop:** The session remains open for any follow-up questions Sarah might have (`Lifecycle Completed (Session Open)`).

---

### Tier 4 — Enterprise Foundation Platform (Capabilities 8, 9, 10, 14, 15, 16)

While the request moved through Tiers 1–3, the Foundation layer captured telemetry and updated persistence asynchronously:

| Foundation Component | Capability | Action Performed During This Lifecycle |
| :--- | :--- | :--- |
| **`Data & Persistence`** | Cap 8 | Stored conversation transcript, updated session state in Redis/PostgreSQL, and committed immutable audit log `#CM-4109`. |
| **`Observability & Tracing`** | Cap 9 | Emitted distributed OpenTelemetry trace: Total execution latency = 1,420 ms (LLM & Tools) + 34 s (Specialist HITL review). Total tokens: 3,140 ($0.042 cost). |
| **`Evaluation & Benchmarks`** | Cap 10 | Evaluated interaction with Ragas/Trulens; logged as a "Golden Multi-Intent Reference" for technical incident + billing resolution. |
| **`Continuous Improve`** | Cap 16 | Sarah clicks **[ 👍 Yes ]**. Feedback is tagged with `BUG-8192` to enhance few-shot prompt examples for the Billing Sub-Agent. |
| **`Testing & LLMOps`** | Caps 14, 15 | Added test case to the CI/CD regression suite verifying that refund requests > $1,000 always block on HITL approval. |

---

## 4. End-to-End Hop Sequence Summary Table

| Hop | Source Component | Destination Component | Protocol / Interface | Data / Purpose |
| :---: | :--- | :--- | :--- | :--- |
| **1** | [ 1 ] User Channels | [ 2 ] API Gateway | HTTPS / WSS | User query with JWT and session token |
| **2** | [ 2 ] API Gateway | [ 3 ] Reliability | Internal Middleware | Authenticated tenant context (`acme-corp`) |
| **3** | [ 3 ] Reliability | [ 4 ] Input Safety | Internal Middleware | Rate limit & circuit breaker verified |
| **4** | [ 4 ] Input Safety | [ 5 ] Orchestrator | Internal Event Bus | Sanitized query & masked entity tokens |
| **5** | [ 5 ] Orchestrator | [ 6 ] Memory & State | Redis / Cache | Load customer SLA, DB topology & past tickets |
| **6** | [ 5 ] Orchestrator | [ 7 ] RAG Retrieval | Vector DB / Search | Retrieve v4.2 upgrade runbooks & `BUG-8192` |
| **7** | [ 5 ] Orchestrator | [Cap 12] Cost Router | Routing Engine | Frontier model selected within 4k token budget |
| **8** | [ 5 ] Orchestrator | [ 8 ] Model Runtime | LLM Inference API | Context assembled; model reasons & plans actions |
| **9** | [ 8 ] Model Runtime | [ 9 ] Tools & APIs | Secure API Sandbox | Queries CloudWatch metrics & ERP invoice breakdown |
| **10** | [ 8 ] Model Runtime | [ 10 ] Sub-Agents | Agent Messaging Bus | Delegates refund evaluation to Billing Sub-Agent |
| **11** | [ 10 ] Sub-Agents | [ 11 ] Confidence Gate | Policy Engine | Candidate draft flagged: refund > $1k requires HITL |
| **12** | [ 11 ] Confidence Gate | [ HITL ] Specialist | Support Dashboard | Human specialist reviews evidence & approves $12.4k credit |
| **13** | [ 11 ] Confidence Gate | [ 12 ] Output Safety | Guardrail Pipeline | Factuality & corporate policy checks verify response |
| **14** | [ 12 ] Output Safety | [ 13 ] Response Engine | Internal Streamer | Verified markdown response committed to state |
| **15** | [ 13 ] Response Engine | [ 14 ] User Client | SSE Stream | Resolution rendered in Sarah's UI; session stays open |
