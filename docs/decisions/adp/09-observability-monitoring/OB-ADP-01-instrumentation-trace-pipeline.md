# OB-ADP-01: Distributed Instrumentation & Trace Pipeline (OpenTelemetry GenAI Conventions, Collector PII Scrubbing & Tail-Based Sampling)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-03 *(Confirmed per OB-D1 OpenTelemetry + SDK Instrumentation OB-Q1, OB-D3 Content Masking Tiers, OB-D4 Tail-Based Sampling & OB-D14 Collector-Level PII Scrubbing)*
- **Deciders**: Architecture Team, Principal Observability Engineer, Lead Security Architect, Data Governance Lead
- **Component**: `[9] Observability & Monitoring` (`Component [ 9 ]`)
- **Reasoning Source**: `checkpoint.md` §13 · Diagram: `LLD - [9] Observability & Monitoring`
- **Decisions Covered**:
  - `OB-D1`: Distributed Instrumentation Standard — OpenTelemetry (OTel) standard across all microservices and gateways, paired with an LLM-observability SDK (Langfuse/LangSmith) used strictly as in-process instrumentation (`OB-Q1`); the SDK formats internal agent execution graphs into OpenTelemetry GenAI semantic conventions (`gen_ai.*`) and exports directly to the generic regional trace collector; standalone SaaS LLM dashboards rejected to preserve regional data residency and unified tracing
  - `OB-D3`: Trace Content Capture Tiers — Tiered payload logging: Full PII-tokenized prompts and completions (`SG-D4`) are retained exclusively for traces that trigger errors, manual human escalations, fall into the High-Risk Tier (`EV-D5`), or are selected via uniform sampling; routine successful traces record structured metadata only (durations, token counts, model IDs, Jev confidence scores, tool names)
  - `OB-D4`: Tail-Based Trace Sampling — Tail-sampling processor deployed in the regional OTel Collector cluster; buffers complete multi-turn trace graphs until turn completion; deterministically preserves $100\%$ of error traces, escalated turns, slow turns ($> 2.5\text{s}$), and risk-tier actions, while down-sampling routine successful turns to a $5\%$ uniform baseline
  - `OB-D14`: Collector-Level PII Sanitization Pipeline — The regional OpenTelemetry Collector executes active PII scrubbing filters (`SG-D5` recognizers) across all span attributes, event bodies, and error stack traces prior to persistent storage; neutralizes accidental leaks of cleartext emails, credit cards, or account numbers in unhandled exceptions ($KK1$)
- **Related Architectural Decision Points**:
  - [`SG-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/06-safety-security-governance/SG-ADP-02-pii-protection.md): PII Protection *(Reversible Tokenization & Salted Hashes)*
  - [`ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/00-orchestration-core/ADP-05-decision-model-jev.md): Decision Model (Jev) *(Trace Context Logging Mandate)*
  - [`OB-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/09-observability-monitoring/OB-ADP-02-telemetry-storage-retention-erasure.md): Telemetry Storage, Retention & Erasure *(Regional Jaeger / OpenSearch Backend)*
  - [`TQ-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#tq-adp-02--contract-testing--isolation-verification): Contract Testing & Isolation Verification *(W3C Traceparent Propagation Tests)*

---

## 1. Context & Problem Statement

Autonomous multi-agent customer support systems exhibit non-linear, multi-branching execution graphs. A single customer turn traverses the API Gateway, Input Screening classifiers, Coordinator graph, Specialist subgraphs, Temporal durable sagas, external tool APIs, and Output Sanitization guardrails.

### The Observability Dilemmas
1. **The Distributed Context Disconnect ($KK2$)**:
   - Modern conversational agents execute across asynchronous execution boundaries (FastAPI event loops, Celery task workers, Temporal workflow activities, and Server-Sent Event streaming generators).
   - Without unified context propagation, traceparent headers are lost across asynchronous thread boundaries or Temporal activity hops, fracturing single turn executions into un-correlatable trace fragments.
2. **The PII Telemetry Ingestion Leak ($KK1$)**:
   - Application developers diligently tokenize customer prompts via PII vaults (`SG-D4`). However, when an external billing API returns an unhandled 500 error containing a raw customer credit card number or physical address inside an error stack trace, naive OpenTelemetry auto-instrumentation serializes the cleartext exception into span attributes, violating GDPR Art. 5 ($KK1$).
3. **The High-Cost, Low-Value Storage Trap ($KU1$, $KU2$)**:
   - Generating full text spans (prompts, retrieved chunks, tool JSON responses) for $100\%$ of production turns generates tens of gigabytes of trace data daily. $90\%$ of these traces represent routine, uneventful FAQ lookups that are never inspected by engineers.
   - Conversely, head-based random sampling at turn ingress drops the very traces engineers need most: anomalous $3.5\text{s}$ timeouts, catastrophic hallucinations, and edge financial errors.

### The Core Architectural Question
> **How do we engineer an OpenTelemetry tracing pipeline that maintains unbroken context across asynchronous agent boundaries, guarantees zero cleartext PII leakage in error traces, and utilizes intelligent tail sampling to preserve 100% of anomalies while discarding 95% of routine storage bloat?**

---

## 2. Decision Framework & Theoretical Formulation

To solve these challenges, `OB-D1`, `OB-D3`, `OB-D4`, and `OB-D14` establish the **OpenTelemetry GenAI Pipeline with In-Collector Scrubbing and Tail-Sampling Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│             DISTRIBUTED TRACING & SANITIZATION PIPELINE (OB-D1, OB-D3, OB-D4, OB-D14)            │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

 Inbound Request (HTTP Header: traceparent: 00-4bf92f3577b...-00f067aa0ba902b7-01)
                          │
                          ▼
 ┌───────────────────────────────────────────────────────────────────────────────────────────────┐
 │ APPLICATION RUNTIME INSTRUMENTATION (OB-D1)                                                   │
 │ • FastAPI Middleware: Binds Trace Context & Injects W3C Context into LangGraph State          │
 │ • LLM SDK Wrapper: Emits OTel GenAI Semantics (gen_ai.request.model, gen_ai.usage.*)         │
 │ • Temporal Interceptors: Propagates traceparent across Workflow & Activity boundaries (KK2)  │
 │ • Emits Spans to Local Regional OpenTelemetry Collector DaemonSet                             │
 └───────────────────────────────┬───────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
 ┌───────────────────────────────────────────────────────────────────────────────────────────────┐
 │ REGIONAL OPENTELEMETRY COLLECTOR PIPELINE                                                     │
 ├───────────────────────────────────────────────────────────────────────────────────────────────┤
 │                                                                                               │
 │   Stage 1: In-Flight Memory Buffering (Max Duration: 30 Seconds)                              │
 │   ┌───────────────────────────────────────────────────────────────────────────────────────┐   │
 │   │ Buffers completed spans per trace_id pending turn completion decision                 │   │
 │   └───────────────────────────────────┬───────────────────────────────────────────────────┘   │
 │                                       │                                                       │
 │                                       ▼                                                       │
 │   Stage 2: Active PII Recognizer & Scrubber Filter (OB-D14, KK1)                              │
 │   ┌───────────────────────────────────────────────────────────────────────────────────────┐   │
 │   │ Regex & Microsoft Presidio Filters inspect all span attributes, events, and errors    │   │
 │   │ Replaces: SSNs, CC numbers, emails, phone numbers with [REDACTED_TELEMETRY_PII]       │   │
 │   └───────────────────────────────────┬───────────────────────────────────────────────────┘   │
 │                                       │                                                       │
 │                                       ▼                                                       │
 │   Stage 3: Multi-Criteria Tail-Based Sampling Policy (OB-D4)                                  │
 │   ┌───────────────────────────────────────────────────────────────────────────────────────┐   │
 │   │ IF (HasError == True)                ===> KEEP TRACE (100% Sampling)                  │   │
 │   │ IF (HumanEscalation == True)         ===> KEEP TRACE (100% Sampling)                  │   │
 │   │ IF (IsRiskTierAction == True)        ===> KEEP TRACE (100% Sampling)                  │   │
 │   │ IF (Duration > 2.50s)                ===> KEEP TRACE (100% Sampling)                  │   │
 │   │ ELSE (Routine Successful Turn)       ===> UNIFORM SAMPLE (5% Sampling Rate)           │   │
 │   └───────────────────────────────────┬───────────────────────────────────────────────────┘   │
 │                                       │                                                       │
 │                                       ▼                                                       │
 │   Stage 4: Content Payload Stripping (OB-D3)                                                  │
 │   ┌───────────────────────────────────────────────────────────────────────────────────────┐   │
 │   │ IF Kept via Error / Escalation / Risk / 5% Sample ===> Retain Tokenized Prompt & Text │   │
 │   │ IF Sampled-Out / Routine                           ===> Strip Text; Retain Metadata    │   │
 │   └───────────────────────────────────┬───────────────────────────────────────────────────┘   │
 └───────────────────────────────────────┼───────────────────────────────────────────────────────┘
                                         │
                                         ▼
                 Export to Regional Jaeger / OpenSearch Backend (OB-D2)
```

---

### Pillar 1: OpenTelemetry GenAI Semantic Conventions (`OB-D1`, `OB-Q1`)

We reject proprietary SaaS tracing agents. All application components standardize on OpenTelemetry Python SDK with native GenAI semantic conventions:
1. **Span Attribute Specification**:
   - `gen_ai.system`: Provider identifier (`"anthropic"`, `"openai"`, `"self-hosted"`).
   - `gen_ai.request.model`: Target model ID (`"claude-3-5-sonnet-20241022"`).
   - `gen_ai.response.model`: Actual model instance returned.
   - `gen_ai.usage.input_tokens`: Measured input prompt token count.
   - `gen_ai.usage.output_tokens`: Measured completion token count.
   - `gen_ai.operation.name`: Subsystem phase (`"chat"`, `"text_completion"`, `"embeddings"`).
2. **Context Propagation Across Temporal Sagas ($KK2$)**:
   - Standard OTel context propagation works over synchronous HTTP. To maintain trace continuity across asynchronous Temporal workflows and LangGraph nodes, we deploy a **Temporal Inbound/Outbound OpenTelemetry Interceptor**:
     ```python
     workflow_header["traceparent"] = format_traceparent(trace.get_current_span().get_span_context())
     ```
   - When a Temporal worker picks up a tool activity, the interceptor re-hydrates the parent span context, binding the tool activity as a child span of the original conversational turn.

---

### Pillar 2: Collector-Level PII Scrubbing (`OB-D14`, $KK1$)

To eliminate the danger of cleartext PII entering log or trace stores via unhandled exceptions:
1. **The In-Collector Scrubber Pipeline**:
   - The OTel Collector runs an inline transform processor prior to exporting:
     ```yaml
     processors:
       transform/pii_scrub:
         error_mode: ignore
         trace_statements:
           - set(attributes["exception.message"], replace_all_patterns(attributes["exception.message"], "value", "\\b[0-9]{3}-[0-9]{2}-[0-9]{4}\\b", "[REDACTED_SSN]"))
           - set(attributes["exception.stacktrace"], replace_all_patterns(attributes["exception.stacktrace"], "value", "\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{2,}\\b", "[REDACTED_EMAIL]"))
     ```
2. **Defense-in-Depth Guarantee**:
   - Upstream code masks intentional inputs via the vault (`SG-D4`).
   - The collector scrubber acts as an automated safety backstop, intercepting accidental leakage in unhandled database errors, third-party REST client error payloads, and stack traces.

---

### Pillar 3: Multi-Criteria Tail-Based Sampling (`OB-D4`, `OB-D3`)

Head-based sampling (deciding whether to trace when a request arrives) is strictly rejected. We deploy the **Tail-Sampling Processor** inside the regional collector daemon:

#### Mathematical Tail-Sampling Decision Function
Let $T$ be a trace spanning execution interval $[t_0, t_1]$. The retention decision $\mathcal{D}(T) \in \{0, 1\}$ evaluates:
$$\mathcal{D}(T) = \mathbf{1}\left( \text{HasError}(T) \lor \text{IsEscalated}(T) \lor \text{IsRiskTier}(T) \lor (\text{Duration}(T) > \tau_{\text{slow}}) \lor (U_T \le \rho) \right)$$
where:
- $\text{HasError}(T) \equiv \exists \text{ span } s \in T \text{ s.t. } s.\text{status} == \text{ERROR}$
- $\text{IsEscalated}(T) \equiv \text{attributes}[\text{"support.escalated"}] == \text{TRUE}$
- $\text{IsRiskTier}(T) \equiv \text{attributes}[\text{"agent.risk\_tier"}] == \text{"risk"}$
- $\tau_{\text{slow}} = 2.50\text{ seconds}$ (SLO violation threshold)
- $U_T \sim \text{Uniform}(0, 1)$ is a pseudo-random hash of $T.\text{trace\_id}$
- $\rho = 0.05$ (5% uniform baseline sampling for non-anomalous turns)

#### Content Payload Tiering (`OB-D3`)
- For traces where $\mathcal{D}(T) = 1$ triggered by error, escalation, or risk tier: Full prompt and completion text (PII-tokenized) are stored.
- For traces preserved purely via the $5\%$ uniform baseline: Prompts and completions are stripped, preserving only numerical token counts, latency profiles, and routing decisions.

---

## 3. Data Contracts & Execution Invariants

### 3.1 Trace Span Schema Contract

```python
from typing import Dict, Optional
from pydantic import BaseModel, Field

class OpenTelemetryGenAISpan(BaseModel):
    """
    Contract governing structured span attributes emitted by agent runtime (OB-D1).
    """
    trace_id: str = Field(..., regex=r"^[a-f0-9]{32}$")
    span_id: str = Field(..., regex=r"^[a-f0-9]{16}$")
    parent_span_id: Optional[str] = Field(None, regex=r"^[a-f0-9]{16}$")
    name: str = Field(..., description="e.g., 'coordinator.triage', 'tools.billing.issue_refund'")
    
    # OTel GenAI Attributes
    gen_ai_system: str = Field(..., description="anthropic, openai, self_hosted")
    gen_ai_request_model: str = Field(...)
    gen_ai_usage_input_tokens: int = Field(..., ge=0)
    gen_ai_usage_output_tokens: int = Field(..., ge=0)
    
    # Context & Routing Attributes
    tenant_id: str = Field(...)
    conversation_id: str = Field(...)
    turn_id: str = Field(...)
    jev_confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    risk_tier: str = Field(..., regex=r"^(routine|edge|risk)$")
    is_escalated: bool = Field(default=False)
    
    # Sanitized Content (Present only if kept under OB-D3)
    tokenized_prompt: Optional[str] = None
    tokenized_response: Optional[str] = None
```

### 3.2 Trace Context Invariant

$$\forall \text{ ActivitySpan } A \in \text{Turn}, \quad A.\text{trace\_id} \equiv \text{GatewaySpan}.\text{trace\_id}$$
Every database query, Jev evaluation, LLM call, and Temporal activity executed in furtherance of turn $k$ must share an unbroken, bitwise identical 128-bit `trace_id`.

---

## 4. Quantitative Failure Modes & Operational Risk Bounds

| Failure Mode ID | Sub-Component & Severity | Risk Classification | Empirical Trigger Condition | Detection Vector | Automated Mitigation & Architectural Enforcement |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **OB-FM-101** | Trace Propagation (`OB-D1`)<br>**HIGH** | Q1 Known Known (Broken Context) | Temporal workflow worker fails to extract `traceparent` from payload, starting a new disconnected trace ($KK2$). | Trace correlation monitor detects orphan root spans with `parent_id = NULL` on internal workers. | **Temporal OTel Interceptor Suite (`TQ-ADP-02`)**: Interceptor unit tests assert trace context survival across serialization boundaries. |
| **OB-FM-102** | Collector Memory Spill (`OB-D4`)<br>**HIGH** | Q2 Known Unknown (Resource Contention) | Traffic surge of long-running turns ($> 20\text{s}$) causes tail-sampling buffer to exhaust collector RAM ($KU2$). | Collector container memory usage exceeds $85\%$; container OOMKilled restarts. | **Emergency Fallback to Head-Sampling**: Memory limiter processor automatically drops uniform sampling rate to $1\%$ when buffer exceeds $1.5\text{GB}$. |
| **OB-FM-103** | PII Scrubber Bleed (`OB-D14`)<br>**CRITICAL** | Q3 Unknown Known (Tacit Convention) | Unusual proprietary error string escapes standard regex patterns, writing customer tax ID to OpenSearch ($KK1$). | Automated weekly telemetry PII scanner detects entropy/regex match in OpenSearch index. | **Query-Based Index Purge (`OB-D6`)**: Targeted Elasticsearch delete-by-query purges infected document; regex pattern updated in OTel collector config. |
| **OB-FM-104** | Skewed Cost Estimation (`OB-D4`, `OB-D9`)<br>**MEDIUM** | Q4 Unknown Unknown (Sampling Distortion) | Engineers calculate total tenant spend by summing kept traces, forgetting that tail-sampling is non-uniform ($UU1$). | Reported monthly infrastructure spend exceeds trace-based estimate by $300\%$. | **Dedicated Unsampled Metrics Counter (`CR-ADP-04`)**: Token spend calculated from unsampled lightweight OTel counter metrics, not sampled trace spans. |
| **OB-FM-105** | Trace Buffer Latency (`OB-D4`)<br>**LOW** | Q2 Known Unknown (Export Lag) | Tail-sampling buffer delays trace availability in Jaeger UI by up to $30\text{ seconds}$ after turn concludes. | Real-time debugging engineer observes delay before trace appears in Jaeger search. | **Documented Operational Delay**: Operator runbooks document that completed traces become visible within a bounded 30-second window. |

---

## 5. Closed-Loop Architectural Feedback

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   TRACE PIPELINE HEALTH & SAMPLING OBSERVABILITY ENGINE                          │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Ingress Span Stream
            │
            ▼
   ┌─────────────────────────────┐
   │ Collector Memory Limiter    │─────► [Metric: otel_collector_buffer_memory_bytes]
   │ (Monitors Tail Buffer Pool) │       Alerts at > 80% capacity
   └────────────┬────────────────┘
                │
                ▼
   ┌─────────────────────────────┐
   │ Active PII Scrubber Engine  │─────► [Metric: telemetry_pii_entities_scrubbed_total]
   │ (Presidio Regex Processor)  │       Monitors active leaks neutralized in collector
   └────────────┬────────────────┘
                │
                ▼
   ┌─────────────────────────────┐
   │ Tail-Sampling Decision Gate │
   └────────────┬────────────────┘
                │
                ├──────────────────────────────────────────────┐
                ▼ (Kept: Error, Slow, Risk, 5% Uniform)        ▼ (Sampled-Out: Routine)
   ┌─────────────────────────────┐               ┌─────────────────────────────┐
   │ Export to Regional Jaeger   │               │ Discard Payload             │
   └────────────┬────────────────┘               └─────────────────────────────┘
                │
                ▼
   [Metric: trace_sampling_ratio]
   Target: Overall ~12-18% of global volume kept; 100% of errors kept
```

### Telemetry & Operational SLOs
1. **Error Trace Capture Completeness**:
   - $\mathbb{P}(\text{KeepTrace} \mid \text{Status} == \text{ERROR}) \equiv 1.000$ (100% guaranteed).
2. **Collector Processing Overhead**:
   - PII Scrubbing + Sampling CPU overhead: $\le 5\%$ CPU utilization on node collector.
3. **Trace Ingestion Latency**:
   - Time from turn completion to availability in Jaeger: $p95 \le 20\text{ seconds}$.

---

## 6. Genesis Implementation Directive & Verification Protocol

### 6.1 OpenTelemetry Tail-Sampling Collector Configuration (`otel-collector-config.yaml`)

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

processors:
  memory_limiter:
    check_interval: 1s
    limit_percentage: 80
    spike_limit_percentage: 20

  tail_sampling:
    decision_wait: 10s
    num_traces: 10000
    expected_new_traces_per_sec: 200
    policies:
      # 1. Keep 100% of Errors (OB-D4)
      - name: errors-policy
        type: status_code
        status_code: { status_codes: [ ERROR ] }
      # 2. Keep 100% of Escalations & Risk-Tier Turns
      - name: risk-tier-policy
        type: string_attribute
        string_attribute:
          key: agent.risk_tier
          values: [ risk ]
      # 3. Keep 100% of Turns exceeding Latency SLO (2.5s)
      - name: latency-policy
        type: numeric_attribute
        numeric_attribute:
          key: duration_ms
          value_condition: { greater_than: 2500 }
      # 4. Uniform 5% Baseline on remainder
      - name: probabilistic-policy
        type: probabilistic
        probabilistic: { sampling_percentage: 5.0 }

  # Collector PII Scrubber (OB-D14)
  transform/pii_scrubber:
    error_mode: ignore
    trace_statements:
      - set(attributes["error.stacktrace"], replace_all_patterns(attributes["error.stacktrace"], "value", "\\b[0-9]{3}-[0-9]{2}-[0-9]{4}\\b", "[REDACTED_SSN]"))

exporters:
  otlp/jaeger:
    endpoint: jaeger-collector.telemetry.svc.cluster.local:4317
    tls:
      insecure: true

service:
  pipelines:
    traces:
      receivers: [ otlp ]
      processors: [ memory_limiter, tail_sampling, transform/pii_scrubber ]
      exporters: [ otlp/jaeger ]
```

### 6.2 Verification Checklist & Integration Tests

```bash
# 1. Verify 100% Capture of Error Spans
pytest tests/observability/test_tail_sampling.py -k "test_error_traces_never_dropped"

# Expected Output:
# PASS: 100 out of 100 generated error turns successfully ingested by Jaeger.
# PASS: Routine successful turns sampled at 5.0% (+/- 0.8%).

# 2. Verify Collector PII Scrubbing Functionality
pytest tests/observability/test_pii_scrubbing.py -k "test_stacktrace_email_redacted"

# Expected Output:
# PASS: Exception message containing 'user@company.com' stored in Jaeger as '[REDACTED_EMAIL]'.
```

---

## 7. Trade-Off Analysis & Rejected Alternatives

| Dimension | Selected Paradigm (`OB-D1`, `OB-D3`, `OB-D4`, `OB-D14`) | Rejected Alternative A: Proprietary SaaS APM (Datadog/LangSmith SaaS) | Rejected Alternative B: Head-Based 10% Uniform Sampling |
| :--- | :--- | :--- | :--- |
| **Data Sovereignty & Compliance** | **Absolute**: Runs entirely within tenant's sovereign VPC (`DP-D10`); zero data shared with third-party APMs. | **Fatal Non-Compliance**: Streaming production prompts to US SaaS clouds violates EU residency laws (`DP-D10`). | **Compliant**: If self-hosted, but drops critical failure data. |
| **Debugging Power on Failures** | **Maximum**: $100\%$ of errors, escalations, and slow turns captured with full tokenized prompts. | **Maximum**: Rich specialized UI, but at extreme vendor subscription expense. | **Abysmal**: Drops $90\%$ of rare, catastrophic errors; impossible to troubleshoot edge failures. |
| **Infrastructure Cost & Storage** | **Minimal**: Discarding $95\%$ of routine traces reduces OpenSearch storage costs by $> 80\%$. | **Prohibitive**: SaaS APM per-token ingestion costs exceed $\$15,000/\text{month}$ at enterprise scale. | **Minimal**: Low storage, but yields useless telemetry. |
| **PII Leakage Resilience** | **Double Shield**: App tokenization (`SG-D4`) + Collector regex scrubbing (`OB-D14`) catches uncaught errors ($KK1$). | **Single Shield**: Relies entirely on developer discipline; unhandled exception leaks cleartext to SaaS. | **Unprotected**: No active scrubbing in collector. |

---

## 8. Formal References & Literature Grounding

1. **OpenTelemetry Project. (2024).** *Semantic Conventions for Generative AI Operations*. OpenTelemetry Specification, Cloud Native Computing Foundation (CNCF). *(Standardized definitions for gen_ai.* span attributes and model metrics).*
2. **W3C Recommendation. (2021).** *Trace Context: W3C Recommendation 23 November 2021*. World Wide Web Consortium. *(Protocol specification for traceparent and tracestate header propagation across distributed systems).*
3. **Sigelman, B. H., et al. (2010).** *Dapper, a Large-Scale Distributed Systems Tracing Infrastructure*. Google Technical Report. *(Foundational architecture for tail-based sampling and trace context propagation).*
4. **European Union General Data Protection Regulation (GDPR). (2016).** *Regulation (EU) 2016/679: Article 25 (Data protection by design and by default)*. *(Mandate for active telemetry scrubbing preventing cleartext personal data ingress).*
5. **NIST. (2020).** *Security and Privacy Controls for Information Systems and Organizations*. NIST SP 800-53, Rev 5. Control AU-3 (Content of Audit Records) & Control AU-9 (Protection of Audit Information). *(Standards governing trace retention, scrubbing, and sanitization).*
