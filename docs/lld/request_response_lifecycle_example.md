# Enterprise AI Support Agent — End-to-End Request-Response Lifecycle Walkthrough

> **Companion Document:** [`architecture.md`](../architecture/architecture.md)  
> **Visual Diagram Canvas:** [`architecture.tldr`](../../diagrams/architecture.tldr)  
> **Source Capabilities:** [`thoughts.md`](../decisions/thoughts.md)  
> **Decisions reflected:** [`checkpoint.md`](../decisions/checkpoint.md) through component 15/15 (UA, KR, MS, TA, MA, SG, DP, EV, OB, RP, CR, HL, TQ, DL, CI, ADP). Components not yet designed (Confidence Gate, HITL, Delivery) are shown as originally sketched.  

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
5. **Multi-Agent Coordination:** A coordinator delegates to specialists (Technical + Billing) and writes the only reply. Specialists make low-risk writes themselves; higher-risk ones, like this credit memo, are proposed (MA-D1, D9, D12).
6. **Confidence & HITL Governance:** Technical explanation is high confidence (96%), but the $12,400 credit memo is at/above Acme's approval threshold (tenant-configurable, platform default $1,000; TA-D5, TA-Q1), so Tools requires **Human-in-the-Loop (HITL)** approval before it runs.
7. **Streaming Response & Foundation Telemetry:** Streams `status` events while the reply is generated and checked, then the checked reply over SSE (EV-D11), while asynchronously updating OpenTelemetry traces, PostgreSQL persistence, and evaluation suites.

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
    "conversation_id": "conv_5f21c0",
    "client_message_id": "msg_01J8Z6",
    "channel": "web_portal",
    "timestamp": "2026-09-09T18:15:00Z",
    "message": "Our production DB replica failed over after yesterday's v4.2 upgrade, and invoice #INV-9821 shows an unexpected $12,400 overage surcharge. Can you check why the failover happened and refund the unauthorized charge?"
  }
  ```
* **Response:** `202 Accepted` with the turn ID. The answer arrives on the conversation's resumable SSE stream as typed events (`status`, `text_delta`, `citation`, `action_card`, `final`), so a reconnect or a later HITL outcome uses the same path (UA-D2, UA-D7). `client_message_id` makes the submit idempotent.

#### `[ 2 ] API Gateway & Identity`
* **Action:** 
  1. Validates the JWT signature against enterprise Auth0 / Okta IdP.
  2. Extracts authenticated tenant context:
     * `tenant_id`: `"acme-corp"`
     * `user_id`: `"usr_sarah_chen"`
     * `roles`: `["cloud_admin", "billing_viewer"]`
  3. Identity tier **T2** (SSO), so account tools are available (UA-D3). Exchanges Sarah's token for a short-lived on-behalf-of token (`sub` = Sarah, `act` = agent) for downstream calls (UA-D4).
  4. The support contract tier (Enterprise Platinum) is read later from the CRM tool when needed, not from the token or memory (MS-D6).

#### `[ 3 ] Reliability & Resilience`
* **Action:**
  1. Checks rate limits for Acme (tenant), Sarah (user) and this conversation, plus Acme's tokens-per-minute counter (RP-D1, D14) → **within limits**.
  2. Checks that no other turn is active in this conversation (RP-D3) → none, so the turn starts. Circuit breakers for billing and monitoring are closed; no incident is declared (RP-D6).
  3. Latency budget for this route (multi-specialist): first `status` ≤ 1 s, final reply p95 45 s, excluding the human approval wait (RP-D8).
  4. Injects OpenTelemetry distributed tracing header:
     `traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01`

#### `[ 4 ] Input Safety Guardrails`
* **Action:**
  1. **Normalize:** Unicode NFKC + confusables check; size OK.
  2. **PII tokenization (SG-D4, D5):** no personal data in this message. `INV-9821`, `v4.2` and `$12,400.00` are technical / business identifiers on the allow-list, so they stay as written (masking them would break search and tools). Had Sarah pasted her email or a card number, it would become a deterministic token (e.g. `<EMAIL_7f3a…>`) held in the vault; models see only the token.
  3. **Screening (SG-D2, D3):** Llama Guard 3 (hazards) and the injection classifier (score 0.01) → **pass** band for a user message.
* **Output:** Screened envelope forwarded to Tier 2. Retrieved passages and tool outputs are screened the same way later, then spotlighted (marked as data) in prompts (SG-D1).

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
  1. **Load state:** LangGraph checkpoint for `conv_5f21c0` from Postgres (MS-D8). Case: none open yet → a Jev `Choice` over Sarah's open cases returns "new case" → case `INV-9821 dispute` created (MS-D1, MS-Q1).
  2. **Triage (one Jev request, ADP-05):** `Choice` intent → technical incident (lead), `Noul` billing needed → yes, `Score` urgency → high; `Noul` missing details → no. Confidence above the act band, so no clarifying question.
  3. **Delegation (Jev, MA-D3):** lead specialist = **Technical**; **Billing** also needed. Billing depends on the technical finding, so they run in sequence (MA-D6). Budget: 2 steps per specialist, 6 per turn (MA-D8).

#### `[ 6 ] Memory & State Engine`
* **Action:** The coordinator loads conversation memory and Sarah's long-term facts.
* **Retrieved State:**
  ```json
  {
    "conversation": {"verbatim_turns": [], "summary": null, "pinned": []},
    "long_term_facts": [
      {"fact": "Prefers CLI steps over console screenshots", "valid_from": "2026-06-02", "valid_to": null},
      {"fact": "Primary DB in us-east-1, replica in us-east-2", "valid_from": "2026-03-14", "valid_to": null}
    ],
    "episodes": [
      {"case": "T-4412", "date": "2026-09-08", "summary": "Scheduled v4.2 maintenance window executed"}
    ]
  }
  ```
* **Not from memory:** the account tier (Enterprise Platinum) and SLA target come from the CRM tool when needed (MS-D6).

#### `[ 7 ] Knowledge & RAG Retrieval`
* **Action:** Standalone rewrite + identifier extraction (`v4.2`, `INV-9821`, `Err 504`), then BM25 + dense over the public index and Acme's private index, fused with RRF. Candidates are screened as untrusted text, then an LLM reranks them to the top-10 parent sections; internal-only chunks are dropped (KR-D7, D8, D9, D10, D14):
  * Query: `v4.2 upgrade release notes database failover known issues replication bandwidth`
* **Top passages (of 10) returned:**
  * **Passage 1 (Relevance 0.94):**
    > *"Release v4.2 introduces dynamic connection pooling. Under spike loads during schema migration, standby replicas may trigger transient heartbeat timeouts (Err 504), causing an automatic failover to the secondary zone."*
  * **Passage 2 (Relevance 0.89):**
    > *"Known Bug BUG-8192: Cross-region data synchronization during transient failover incorrectly logged temporary ingress replication as unmetered bandwidth surcharge."*

#### `[ Cap 12 ] Cost & Resource Router`
* **Action:**
  1. **Answer cache:** a Jev `Noul` says this needs account data (invoice, cluster), so it is not cache-eligible (CR-D3).
  2. **Model tier:** a Jev `Score` rates the turn as hard (incident + billing dispute), so the coordinator and specialists use the frontier tier; easy turns would go to the self-hosted model (CR-D1, CR-Q1).
  3. **Budgets:** the multi-specialist route's token budget per turn applies (with room for one cascade step); Acme is at 34 % of its monthly budget, so no soft cap (CR-D4, D5). Usage is added to Acme's exact counter (RP-D14).

#### `[ 8 ] Model Runtime & LLM`
* **Action:** Each specialist gets a typed task brief (goal, IDs, pinned constraints, evidence references; MA-D4, D5). For each step, code filters the tools to those Sarah's tier and role allow, Jev shortlists and picks the tool and closed-set arguments, and the LLM writes the plan and free-text fields (TA-D1, ADP-05):
  1. Technical specialist: `query_cloud_monitoring(cluster_id="db-acme-prod", timerange="24h")`. `cluster_id` traces to Sarah's long-term fact, a valid source (TA-D3).
  2. Billing specialist: `get_invoice_breakdown(invoice_id="INV-9821")`. `invoice_id` traces to Sarah's own words.

#### `[ 9 ] Tools & Enterprise APIs`
* **Action:** Both calls are reads, so they run automatically; the Jev gate returns "allow" (TA-D5, D6). Each runs as a Temporal activity in its system's worker pool (monitoring, billing) with an outbound allow-list, using the on-behalf-of token (TA-D4, D11, Q2). Outputs are screened before any LLM reads them; the full ledger is stored by reference with a summary (TA-D9, MS-D7). Each call writes an audit record (TA-D12).
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
* **Technical specialist result (typed, MA-D4):** `status: done` · finding: failover caused by a heartbeat timeout during the v4.2 schema migration (BUG-8192); resync generated cross-region traffic · evidence: monitoring event + Passage 1 and 2.
* **Billing specialist (own identity; reads + low-risk writes; MA-D9):**
  * Links the `NET-DATA-INGRESS` $12,400 line to the resync described in BUG-8192 (Passage 2).
  * Adds a case note ("$12,400 line linked to BUG-8192 resync") directly: a low-risk write, run through Tools and read back.
  * A $12,400 credit is financial and above low-risk, so it can't do that itself. Returns `status: done` with a **proposed action** `apply_credit_memo(invoice_id="INV-9821", amount=12400.00)`; the amount traces to the `get_invoice_breakdown` result, an allow-listed field (TA-D3, D13). It describes the credit as proposed, not done (MA-D14).
* **Coordinator:**
  * Merge: no conflicting claims and no numeric disagreement, so no Jev claim scoring or HITL needed at this point (MA-D7, D16).
  * Sends the proposed write through Tools: financial write, $12,400 ≥ Acme's threshold (default $1,000, per call) → **human approval required** (TA-D5, D14, Q1). The billing API supports a dry run, so the preview goes on the approval card (TA-D7). Checkpoint before the call (MS-D9); Temporal waits for the approval signal.
* **Output:** Draft reply (technical explanation + "credit requested, awaiting approval") and the pending approval → Tier 3.

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
  * Jev gate on the draft (HL-D1): claims supported by BUG-8192, the monitoring event and the invoice line → `0.96`; relevance high.
  * The draft states a money figure ($12,400), so it goes to the **co-pilot band** for a human check regardless of the score (HL-D13).
  * Reads the approval flag set by Tools: the `$12,400.00` credit memo is at/above Acme's threshold (TA-D5), so it is pending human approval; $12,400 is also above the senior amount (default $5,000, HL-D4).
  * **Decision:** one escalation packet (HL-D12) to the **billing senior queue** (SLA 1 h, HL-D3). Sarah sees status, a wait estimate and a "cancel" option (HL-D8).

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
  2. Senior Support Specialist *Alex* (not the conversation's handler) validates the log correlation and the dry-run preview, confirms amount, account and target one by one (HL-D5), checks the draft's figures (co-pilot), and clicks **[Approve $12,400 Credit Memo]**.
  3. **On approval (Temporal signal):** the wait was under 1 h, so no re-fetch is needed (MS-D18). Tools runs `apply_credit_memo` with idempotency key `checkpoint_id + tool_call_id`, checkpoints after the call, and **reads back** the credit memo (`CM-4109`) before anyone tells Sarah it is done (MS-D9, TA-D10, MA-D14). Audit record includes before/after invoice state (TA-D12).

#### `[ 12 ] Output Safety Guardrails`
* **Action:**
  1. **Leakage check (SG-D6):** no PII, secrets, internal IPs / hostnames or system-prompt text in the reply.
  2. **URL / markdown sanitization (SG-D6):** citations are structured `citation` events; no remote images or unlisted links.
  3. **Promise check (SG-D15):** "credited $12,400" matches a commitment phrase, and it is backed by the verified credit memo `CM-4109` (MA-D14), so the reply passes. Before approval, the same sentence would have been held and rewritten as "requested, awaiting approval".
  4. **Redirect check (MA-D13):** the reply doesn't send Sarah to another team.
  5. *Factual grounding (claims vs. logs and passages) is Confidence Boundaries (Comp 13), not output safety.* Tone is not checked (SG-D6).

#### `[ 13 ] Response Delivery Engine`
* **Action:**
  1. While the reply was being generated and checked, only `status` events were streamed ("Checking your invoice…", "Waiting for specialist approval…"); the reply itself is held until every check passes (EV-D11, resolves UA-D8). It then sends typed events on the conversation's SSE stream (UA-D2, D7): `text_delta` for the explanation, `citation` for BUG-8192 and the release note, an `action_card` for the verified credit memo, then `final`. If Sarah's tab had closed, the same events wait in the conversation inbox (UA-Q2).
  2. Appends the turn and delivered reply to conversation memory; the audit record for `CM-4109` is already written by Tools.

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
| **`Data & Persistence`** | Cap 8 | Everything stays in Acme's region (DP-D10). Stored the conversation transcript and LangGraph checkpoints in PostgreSQL under row-level security, the ledger blob by reference in object storage, and the append-only audit record for `#CM-4109` (Sarah's personal fields encrypted with her own data key, wrapped by Acme's KMS key). Long-term facts are extracted later, when the case resolves (MS-D5). |
| **`Observability & Tracing`** | Cap 9 | One OpenTelemetry trace for the turn (Jev answers + confidence on the spans), PII-scrubbed by the collector and **kept in full** because it contains an escalation (tail sampling). Stored in Acme's regional Jaeger for 7 days. Total execution latency = 1,420 ms (LLM & Tools) + 34 s (Specialist HITL review). Total tokens: 3,140 ($0.042 cost). |
| **`Evaluation & Benchmarks`** | Cap 10 | Acme has opted in (EV-D15), so this conversation is a candidate production sample: PII-tokenized, kept in Acme's region, and erasable. It may be scored by the sampled LLM judge (EV-D8) and curated as a risk-tier end-to-end episode (financial write with approval). |
| **`Continuous Improve`** | Cap 16 | Sarah clicks **[ 👍 Yes ]** and answers the one-question survey (CI-D1). Because Acme opted in and Alex approved the outcome, the conversation is eligible (tokenized) as a curated Billing few-shot example, kept out of test sets (CI-D5), and for the next quarterly EU fine-tuning run (CI-D4, CI-Q2). |
| **`Testing & LLMOps`** | Caps 14, 15 | The rules this turn relied on are covered by property-based invariant tests with mocked model outputs (TQ-D2): no financial write at/above the threshold without approval, approver ≠ handler, success reported only after read-back, one active turn. These run without retries (TQ-D13). Scenario 3 has its own E2E test on staging (TQ-D6). The triage wording and thresholds this turn used shipped in last week's scheduled behaviour release, which passed the gate and a canary on read-only routes (DL-D10, DL-Q2). If a release lands while the $12,400 approval waits, the workflow drains its signals and continues-as-new on the new code (DL-D6). |

---

## 4. End-to-End Hop Sequence Summary Table

| Hop | Source Component | Destination Component | Protocol / Interface | Data / Purpose |
| :---: | :--- | :--- | :--- | :--- |
| **1** | [ 1 ] User Channels | [ 2 ] API Gateway | HTTPS / WSS | User query with JWT and session token |
| **2** | [ 2 ] API Gateway | [ 3 ] Reliability | Internal Middleware | Authenticated tenant context (`acme-corp`) |
| **3** | [ 3 ] Reliability | [ 4 ] Input Safety | Internal Middleware | Rate limit & circuit breaker verified |
| **4** | [ 4 ] Input Safety | [ 5 ] Orchestrator | Internal Event Bus | Sanitized query & masked entity tokens |
| **5** | [ 5 ] Orchestrator | [ 6 ] Memory & State | PostgreSQL (checkpointer + facts) | Load checkpoint, conversation memory, Sarah's facts; link case (Jev) |
| **6** | [ 5 ] Orchestrator | [ 7 ] RAG Retrieval | Hybrid search + screened LLM rerank | Top-10 sections incl. v4.2 notes & `BUG-8192` |
| **7** | [ 5 ] Orchestrator | [Cap 12] Cost Router | Routing Engine | Jev difficulty score → frontier tier; not cache-eligible; within turn budget |
| **8** | [ 5 ] Orchestrator | [ 10 ] Sub-Agents | LangGraph subgraphs, typed contracts | Jev delegation: Technical, then Billing |
| **9** | [ 10 ] Sub-Agents | [ 9 ] Tools & APIs | Temporal activities, pool per system | Jev-picked reads: monitoring event, invoice breakdown |
| **10** | [ 10 ] Sub-Agents | [ 5 ] Coordinator | Typed result | Billing adds a case note (low-risk, direct) and proposes `apply_credit_memo` (financial) |
| **11** | [ 5 ] Coordinator | [ 9 ] Tools & APIs | Action validation | $12,400 ≥ tenant threshold → approval required, dry-run preview |
| **12** | [ 9 ] Tools / [ 11 ] Gate | [ HITL ] Specialist | Support Dashboard + Temporal signal | Specialist approves; Tools executes, reads back `CM-4109` |
| **13** | [ 11 ] Confidence Gate | [ 12 ] Output Safety | Guardrail Pipeline | Factuality & corporate policy checks verify response |
| **14** | [ 12 ] Output Safety | [ 13 ] Response Engine | Internal Streamer | Verified markdown response committed to state |
| **15** | [ 13 ] Response Engine | [ 14 ] User Client | SSE Stream | Resolution rendered in Sarah's UI; session stays open |
