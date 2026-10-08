# OB-ADP-03: Service Level Objectives & Multi-Burn-Rate Alerting (Internal Error Budgets, Google SRE Burn Rates & Integration Tripwire Monitors)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-03 *(Confirmed per OB-D7 Internal-Only SLOs OB-Q2, OB-D8 Multi-Window Burn-Rate Alerts & OB-D10 Temporal UI Execution Visibility)*
- **Deciders**: Architecture Team, Site Reliability Engineering Lead, Principal Platform Architect, Incident Commander
- **Component**: `[9] Observability & Monitoring` (`Component [ 9 ]`)
- **Reasoning Source**: `checkpoint.md` §13 · Diagram: `LLD - [9] Observability & Monitoring`
- **Decisions Covered**:
  - `OB-D7`: Service Level Objective Architecture — Strictly internal SLOs configured exclusively for SRE alerting and error budget governance (`OB-Q2`); zero tenant-facing contractual SLAs published in commercial agreements to prevent punitive financial penalties during early model iterations; monitors four core Golden Signals: Turn Availability ($\ge 99.9\%$), Time-to-First-Status ($p95 \le 300\text{ms}$), Final Reply Latency ($p95 \le 2500\text{ms}$), and Human Escalation Ceiling ($\le 8.0\%$)
  - `OB-D8`: Multi-Window Multi-Burn-Rate Alerting Engine — Dual-track alerting topology: (1) Google SRE multi-window, multi-burn-rate alerts tracking error budget consumption across short and long lookback windows ($14.4\times$ 1h/5m and $6.0\times$ 6h/30m); (2) Dedicated deterministic tripwire alerts for critical component hand-offs (OAuth token expiry warnings, nightly batch failures, open circuit breakers, reranker fallback spikes, and repeated sub-threshold financial writes)
  - `OB-D10`: Workflow Execution Monitoring — Workflow state visibility managed via native Temporal Web UI integrated with OpenTelemetry trace links; custom orchestration dashboards rejected to eliminate unnecessary build overhead; stuck long-running approval workflows surfaced via Temporal timeout alarms ($UU3$)
- **Related Architectural Decision Points**:
  - [`RP-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#rp-adp-03--latency-profiles--fallbacks): Latency Profiles & Fallbacks *(P95 Latency Budgets & Graceful Degradation)*
  - [`TA-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/04-tools-actions/TA-ADP-04-execution-credentials-isolation.md): Execution Credentials & Isolation *(Circuit Breaker States & Token Expiry)*
  - [`HL-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#hl-adp-02--human-co-pilot-interface--queue): Human Co-Pilot Interface & Queue *(Escalation Rate Telemetry)*
  - [`KR-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/02-knowledge-retrieval/KR-ADP-02-ingestion-freshness.md): Ingestion Freshness *(Nightly Batch Failure Monitoring)*

---

## 1. Context & Problem Statement

Operational alerting for autonomous generative AI systems breaks down under traditional server monitoring paradigms:
1. **The Static Threshold Noise Trap ($UK1$)**:
   - Setting static alerts on raw error counts or instantaneous latency spikes triggers continuous false-alarm paging. A temporary $20\text{s}$ third-party model latency jitter or single network drop pages on-call engineers at 3:00 AM, inducing severe alert fatigue.
2. **The High-Stakes Silent Integration Failure**:
   - In agentic workflows, failures are rarely simple HTTP 500 crashes. A failure manifests as an external circuit breaker opening silently (`TA-D10`), a nightly knowledge ingestion job failing to refresh prices (`KR KK1`), or an OAuth refresh token silently expiring 2 hours before a major sales shift (`TA KK3`). If alerting only monitors API uptime, the agent fails silently for hours.
3. **The Tenant Contractual Penalty Hazard (`OB-D7`)**:
   - Early enterprise AI systems that contractually guarantee $99.99\%$ response quality SLAs or rigid sub-second latencies expose the organization to legal breach-of-contract liabilities when upstream LLM providers (Anthropic, OpenAI) experience widespread platform degradation.

### The Core Architectural Question
> **How do we construct an intelligent alerting architecture that eliminates false pages through Google SRE multi-burn-rate error budgets while actively monitoring critical component integration tripwires and maintaining strict internal-only service level targets?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `OB-D7`, `OB-D8`, and `OB-D10` establish the **Internal Error Budget and Multi-Burn-Rate Alerting Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│             SERVICE LEVEL OBJECTIVES & DUAL-TRACK ALERTING PIPELINE (OB-D7, OB-D8)               │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                       Continuous Prometheus Telemetry Metrics Stream
                                             │
             ┌───────────────────────────────┴───────────────────────────────┐
             ▼                                                               ▼
┌─────────────────────────────────────────┐     ┌─────────────────────────────────────────┐
│ TRACK 1: INTERNAL SRE SLO ERROR BUDGETS │     │ TRACK 2: COMPONENT INTEGRATION MONITORS │
│ (OB-D7: Never Tenant-Facing, OB-Q2)     │     │ (OB-D8: Specific Deterministic Trips)   │
├─────────────────────────────────────────┤     ├─────────────────────────────────────────┤
│ • Availability: 99.9% (30-day budget)   │     │ • Circuit Breakers: State == OPEN (P2)  │
│ • TTFT (Status Event): p95 ≤ 300ms      │     │ • OAuth Token Expiry: < 2 Hours Left    │
│ • Final Turn Latency:  p95 ≤ 2500ms     │     │ • Nightly KB Ingest: Batch Failed (P2)  │
│ • Escalation Ceiling:  Rate ≤ 8.0%      │     │ • Sub-Threshold Loop: > 3 writes in turn│
└────────────────────┬────────────────────┘     └────────────────────┬────────────────────┘
                     │                                               │
                     ▼                                               ▼
┌─────────────────────────────────────────┐     ┌─────────────────────────────────────────┐
│ MULTI-WINDOW MULTI-BURN-RATE ENGINE     │     │ IMMEDIATE TRIPWIRE ALERTER              │
├─────────────────────────────────────────┤     ├─────────────────────────────────────────┤
│ • P1 Page: Burn Rate 14.4x              │     │ • Evaluates boolean threshold state     │
│   (Consumes 2% budget in 1h AND 5m)     │     │ • Pagers directly to owning subsystem   │
│ • P2 Ticket: Burn Rate 6.0x             │     │   (e.g., Tools team, Ingest team)       │
│   (Consumes 5% budget in 6h AND 30m)    │     └────────────────────┬────────────────────┘
└────────────────────┬────────────────────┘                          │
                     │                                               │
                     └───────────────────────┬───────────────────────┘
                                             ▼
                             PagerDuty / Slack Alert Router
                                             │
                                             ▼
                             On-Call Incident Engineer
                             (Investigates via Temporal Web UI, OB-D10)
```

---

### Pillar 1: Internal Service Level Objectives (SLOs) (`OB-D7`, `OB-Q2`)

We establish four foundational Golden Signal SLOs managed strictly internally by SRE teams:

| SLO Metric Name | Service Level Indicator (SLI) Formulation | Target Objective (30-Day Window) | Error Budget ($1 - \text{SLO}$) |
| :--- | :--- | :--- | :--- |
| **Turn Availability** | $\frac{\text{Successful Turns (HTTP 200/Done)}}{\text{Total Valid Turn Requests}}$ | **$\ge 99.90\%$** | $0.10\%$ ($43.2\text{ minutes/month}$) |
| **Perceived Responsiveness** | $\frac{\text{Turns with First Status Event } \le 300\text{ms}}{\text{Total Valid Turn Requests}}$ | **$\ge 95.00\%$** | $5.00\%$ |
| **Turn Generation Latency** | $\frac{\text{Turns with Final Checked Reply } \le 2500\text{ms}}{\text{Total Valid Turn Requests}}$ | **$\ge 95.00\%$** | $5.00\%$ |
| **Escalation Stability** | $\frac{\text{Turns Resolved Without Escalation}}{\text{Total Valid Turn Requests}}$ | **$\ge 92.00\%$** | $8.00\%$ (Escalations $\le 8.0\%$) |

#### The Legal Shield Invariant (`OB-D7`)
No commercial contract, SLA addendum, or marketing material may incorporate these operational targets. They function purely as engineering error budgets to control release velocity (`DL-ADP-03`).

---

### Pillar 2: Google SRE Multi-Window Multi-Burn-Rate Alerting (`OB-D8`)

To eliminate alert noise and false positives, alerts do not trigger on instantaneous error spikes. They evaluate the rate of error budget consumption (**Burn Rate $B$**):

#### Mathematical Burn Rate Formulation
Let $E = 1 - \text{SLOTarget}$ be the total 30-day error budget. The burn rate $B$ is defined as:
$$B = \frac{\text{Observed Error Rate}}{E}$$
A burn rate of $B = 1.0$ consumes exactly $100\%$ of the budget over 30 days ($720\text{ hours}$).
A burn rate of $B = 14.4$ consumes $2\%$ of the total monthly error budget in exactly 1 hour.

#### Multi-Window Dual-Condition Alerting Matrix
To ensure an alert pages only when an incident is both severe AND currently ongoing, alerts mandate that both a long lookback window AND a short lookback window exceed the burn rate threshold simultaneously:

```
┌─────────┬────────────┬─────────────┬──────────────┬──────────────────────────────────────────┐
│ Severity│ Burn Rate  │ Long Window │ Short Window │ Budget Consumed & Operational Response   │
├─────────┼────────────┼─────────────┼──────────────┼──────────────────────────────────────────┤
│ **P1**  │ **14.4x**  │ 1 Hour      │ 5 Minutes    │ Consumes 2% in 1 hour. PAGERDUTY WAKE-UP.│
│ **P1**  │ **6.0x**   │ 6 Hours     │ 30 Minutes   │ Consumes 5% in 6 hours. PAGERDUTY ON-CALL│
│ **P2**  │ **3.0x**   │ 1 Day (24h) │ 2 Hours      │ Consumes 10% in 3 days. TICKET CREATED.  │
│ **P3**  │ **1.0x**   │ 3 Days (72h)│ 6 Hours      │ Consumes 10% in 30 days. TEAM DASHBOARD. │
└─────────┴────────────┴─────────────┴──────────────┴──────────────────────────────────────────┘
```

---

### Pillar 3: Hand-Off Integration Tripwire Monitors (`OB-D8`)

In addition to SLO burn rates, the alerting engine monitors deterministic subsystem tripwires derived from upstream component loops:

1. **Downstream OAuth Token Expiry Warning (`TA KK3`, `TA-D4`)**:
   - Condition: Dedicated worker OAuth refresh token valid lifetime $\tau_{\text{remain}} < 2\text{ hours}$.
   - Severity: **P2 Alert** (Warns integration administrator before workers fail).
2. **Nightly Knowledge Ingestion Batch Failure (`KR KK1`, `KR-D2`)**:
   - Condition: Batch cron terminates with non-zero exit code or $< 90\%$ corpus parity.
   - Severity: **P2 Alert** (Paging Knowledge on-call at 04:00 UTC before business hours).
3. **External System Circuit Breaker Tripped (`TA-D10`)**:
   - Condition: Circuit breaker transitions to `OPEN` state for system $S$ (e.g., Stripe, Jira).
   - Severity: **P1/P2 Alert** (Pages immediately; agent degrades to read-only for system $S$).
4. **Reranker Fallback Spike (`KR-D12`)**:
   - Condition: Cross-encoder reranker timeout/fallback rate $> 5.0\%$ over 15 minutes.
   - Severity: **P2 Alert** (Indicates GPU worker exhaustion in retrieval cluster).
5. **Repeated Sub-Threshold Write Anomaly (`TA-D14`, `TA UU4`)**:
   - Condition: Single case executes $> 3$ financial writes below the $\$1,000$ approval threshold within 1 hour.
   - Severity: **P1 Security Alert** (Indicates potential structuring fraud attempt; freezes case).

---

### Pillar 4: Workflow Visibility via Temporal UI (`OB-D10`)

We explicitly reject building custom agent execution visualization dashboards:
1. **Temporal Web UI Integration**:
   - Every agent saga and tool activity executes within Temporal (`ADP-02`).
   - On-call engineers use the native Temporal Web UI to inspect running workflows, activity retry stacks, and compensation histories.
2. **Stuck Workflow Protection ($UU3$)**:
   - To prevent workflows waiting on Human-in-the-Loop approvals (`HL-ADP-04`) from being forgotten indefinitely:
     - Temporal workflows configure an explicit activity timeout:
       $$\tau_{\text{approval\_wait}} \le 24\text{ hours}$$
     - If an approval remains unacknowledged after 12 hours, a warning notification is routed to the customer support supervisor queue.

---

## 3. Data Contracts & Execution Invariants

### 3.1 Prometheus Alerting Rules Definition (`prometheus_alerts.yaml`)

```yaml
groups:
  - name: enterprise_agent_slo_alerts
    rules:
      # P1 Critical: 14.4x Burn Rate on Availability (1h and 5m windows)
      - alert: AgentAvailabilityCriticalBurnRate
        expr: |
          (
            sum(rate(http_turn_requests_total{status="error"}[1h])) 
            / sum(rate(http_turn_requests_total[1h]))
          ) > (14.4 * 0.001)
          and
          (
            sum(rate(http_turn_requests_total{status="error"}[5m])) 
            / sum(rate(http_turn_requests_total[5m]))
          ) > (14.4 * 0.001)
        for: 2m
        labels:
          severity: p1
          component: orchestrator
        annotations:
          summary: "Agent Turn Availability Error Budget consuming at 14.4x normal rate"
          description: "Current error rate exceeds 1.44%. Over 2% of monthly budget consumed in past hour."

      # P1/P2 Component Tripwire: Circuit Breaker Open (TA-D10)
      - alert: ExternalSystemCircuitBreakerOpen
        expr: circuit_breaker_state == 2 # 2 = OPEN state
        for: 30s
        labels:
          severity: p1
          component: tools
        annotations:
          summary: "Circuit Breaker OPEN for external integration {{ $labels.system_name }}"
          description: "All tool mutations to {{ $labels.system_name }} are failing fast or disabled."

      # P2 Component Tripwire: OAuth Token Expiry Imminent (TA-D4)
      - alert: OAuthCredentialExpiryImminent
        expr: oauth_token_seconds_until_expiry < 7200 # < 2 hours
        for: 5m
        labels:
          severity: p2
          component: auth
        annotations:
          summary: "OAuth refresh token for {{ $labels.system_name }} expires in < 2 hours"
```

### 3.2 Integration Tripwire Invariants

1. **Circuit Breaker Paging Invariant**:
   $$\text{State}(\text{Breaker}_S) == \text{OPEN} \implies \text{DispatchAlert}(\text{P1}, S) \le 60\text{ seconds}$$
2. **Structuring Fraud Freeze Invariant**:
   $$\sum_{t \in \text{Case}} \mathbf{1}(\text{ToolCall} == \text{"write"} \land \text{Amount} < \tau_{\text{threshold}}) > 3 \implies \text{FreezeCase}() \land \text{AlertSecOps}()$$

---

## 4. Quantitative Failure Modes & Operational Risk Bounds

| Failure Mode ID | Sub-Component & Severity | Risk Classification | Empirical Trigger Condition | Detection Vector | Automated Mitigation & Architectural Enforcement |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **OB-FM-301** | Alert Fatigue (`OB-D8`)<br>**HIGH** | Q1 Known Known (Operational Noise) | Single momentary API blip causes instantaneous threshold alert to page on-call at midnight ($UK1$). | SRE post-mortem review detects $> 20$ un-actionable pages per week. | **Multi-Window Burn-Rate Enforcement**: Alerts strictly require dual 1h AND 5m window confirmation before paging. |
| **OB-FM-302** | Stuck Workflow (`OB-D10`)<br>**HIGH** | Q2 Known Unknown (Workflow Stall) | Case waiting on human approval sits in Temporal queue for 5 days because operator was on leave ($UU3$). | Temporal workflow duration timer exceeds 24 hours. | **Automated Workflow Timeout Escalate**: Temporal workflow timer fires at 24h, auto-reassigning case to secondary supervisor tier. |
| **OB-FM-303** | Reranker Fallback Storm (`OB-D8`)<br>**MEDIUM** | Q2 Known Unknown (Degraded Quality) | Cross-encoder GPU pod crash causes $100\%$ of retrieval queries to fall back to un-reranked BM25/vector search. | Prometheus alert `retrieval_reranker_fallback_rate > 0.05` fires. | **Auto-Scaling GPU Replica Group**: Alert triggers horizontal pod autoscaler (HPA) to spin up additional inference workers. |
| **OB-FM-304** | Missing Runbook Link (`OB-D8`)<br>**MEDIUM** | Q3 Unknown Known (Tacit Convention) | PagerDuty alert fires without diagnostic dashboard or runbook link, causing 45-minute MTTR delay. | SRE incident retro notes missing operational guidance. | **CI Prometheus Alert Linter**: CI lint rules mandate that every alert rule YAML contains valid `runbook_url` and `dashboard_url` annotations. |
| **OB-FM-305** | Metric Cardinality Burst (`OB-D7`)<br>**HIGH** | Q4 Unknown Unknown (Prometheus Crash) | Developer adds `conversation_id` as a Prometheus metric label, causing timeseries count to explode past $10\text{ million}$. | Prometheus server CPU exceeds $100\%$; scrape targets drop. | **Label Whitelist Linter**: CI blocks metric registration containing dynamic unbounded identifiers; forces high-cardinality data to OpenSearch traces. |

---

## 5. Closed-Loop Architectural Feedback

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   ALERTING & ERROR BUDGET GOVERNANCE ENGINE                                      │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

     Prometheus Scrape Interval (15s)
                    │
                    ▼
     ┌──────────────────────────────┐
     │ Error Budget Burn Engine     │─────► [Metric: slo_error_budget_consumed_ratio]
     │ (1h, 6h, 24h, 72h Windows)   │       Tracks percentage of monthly budget spent
     └──────────────┬───────────────┘
                    │
                    ▼
     ┌──────────────────────────────┐
     │ Hand-Off Tripwire Evaluator  │─────► [Metric: active_integration_alerts_count]
     │ (Breakers, Tokens, Batches)  │
     └──────────────┬───────────────┘
                    │
                    ├──────────────────────────────────────────────┐
                    ▼                                              ▼
     ┌──────────────────────────────┐               ┌──────────────────────────────┐
     │ P1 Critical Pager Dispatch   │               │ P2/P3 Ticket Creator         │
     │ (PagerDuty Escalation Policy)│               │ (Jira / Linear Issue Sync)   │
     └──────────────┬───────────────┘               └──────────────────────────────┘
                    │
                    ▼
     [Metric: oncall_pager_incidents_total]
     Target: < 3 actionable pages per on-call shift
```

### Telemetry & Operational SLOs
1. **Mean Time to Detect (MTTD)**:
   - For severe ongoing outages ($14.4\times$ burn rate): $\le 5\text{ minutes}$.
2. **Alert Actionability Ratio**:
   - $\frac{\text{Actionable Incidents}}{\text{Total PagerDuty Pages}} \ge 0.90$ (Zero alert fatigue).
3. **Tripwire Dispatch Latency**:
   - Circuit breaker transition to PagerDuty trigger: $< 60\text{ seconds}$.

---

## 6. Genesis Implementation Directive & Verification Protocol

### 6.1 Multi-Window Burn-Rate Calculator Function

```python
import numpy as np

class SLOBurnRateEvaluator:
    def __init__(self, target_slo: float = 0.999):
        self.error_budget = 1.0 - target_slo  # e.g., 0.001 for 99.9%

    def evaluate_p1_alert(self, error_rate_1h: float, error_rate_5m: float) -> bool:
        """
        Evaluates Google SRE 14.4x burn rate condition across 1-hour and 5-minute windows.
        Consumes 2% of the monthly error budget in 1 hour.
        """
        burn_threshold = 14.4 * self.error_budget  # 0.0144 (1.44% error rate)
        
        # Dual-window requirement: Must be elevated over both windows to eliminate blips
        is_burning_1h = error_rate_1h > burn_threshold
        is_burning_5m = error_rate_5m > burn_threshold
        
        return is_burning_1h and is_burning_5m
```

### 6.2 Verification Checklist & Integration Tests

```bash
# 1. Verify Multi-Window Burn-Rate Calculation
pytest tests/observability/test_burn_rate_alerts.py -k "test_momentary_blip_does_not_page"

# Expected Output:
# PASS: 2-minute error spike exceeding 5% DOES NOT trigger P1 page (5m window passes, 1h window below).
# PASS: Sustained 1.5% error rate across both 1h and 5m triggers P1 PagerDuty dispatch.

# 2. Verify Circuit Breaker Tripwire Alerting
pytest tests/observability/test_tripwire_alerts.py -k "test_breaker_open_fires_alert"

# Expected Output:
# PASS: Setting circuit_breaker_state=2 immediately triggers ExternalSystemCircuitBreakerOpen alert.
```

---

## 7. Trade-Off Analysis & Rejected Alternatives

| Dimension | Selected Paradigm (`OB-D7`, `OB-D8`, `OB-D10`) | Rejected Alternative A: Contractual Tenant SLAs | Rejected Alternative B: Instantaneous Threshold Alerts |
| :--- | :--- | :--- | :--- |
| **Legal & Financial Exposure** | **Zero Risk**: Internal SLOs guide engineering without creating breach-of-contract liabilities (`OB-D7`). | **Severe Risk**: Third-party LLM outages trigger multi-million dollar customer SLA penalty payouts. | **Zero Risk**: But operationally useless due to alert noise. |
| **Alert Actionability & Signal-to-Noise** | **Optimal**: Multi-window burn rates filter transient network blips; pages only on sustained outages. | **N/A**: Relates to commercial terms. | **Abysmal**: Instantaneous threshold alerts wake up on-call engineers for self-healing 10-second blips ($UK1$). |
| **Integration Coverage** | **Comprehensive**: Specific tripwires catch silent breaker openings, token expirations, and fraud loops. | **N/A**: Relates to commercial terms. | **Blind**: Focuses exclusively on HTTP status codes; misses degraded internal agent states. |
| **Workflow Tooling Maintenance** | **Minimal**: Reuses native Temporal Web UI (`OB-D10`); zero custom dashboard code to maintain. | **N/A**: Relates to commercial terms. | **High**: Building bespoke state visualizers wastes engineering cycles. |

---

## 8. Formal References & Literature Grounding

1. **Beyer, B., Jones, C., Petoff, J., & Murphy, N. R. (2016).** *Site Reliability Engineering: How Google Runs Production Systems*. O'Reilly Media. Chapter 4: Service Level Objectives & Chapter 5: Eliminating Toil. *(Mathematical foundation for error budgets and multi-window multi-burn-rate alerting).*
2. **Murphy, N. R., Beyer, B., Blank-Edelman, D., et al. (2020).** *The Site Reliability Workbook: Practical Ways to Implement SRE*. O'Reilly Media. Chapter 5: Alerting on SLOs. *(Detailed mathematical specification for short- and long-window burn rate alerts).*
3. **Nygard, M. T. (2018).** *Release It!: Design and Deploy Production-Ready Software*. Pragmatic Bookshelf. *(Engineering standards for circuit breaker state observability and fail-fast alerting).*
4. **NIST. (2020).** *Security and Privacy Controls for Information Systems and Organizations*. NIST SP 800-53, Rev 5. Control SI-4 (Information System Monitoring) & Control CA-7 (Continuous Monitoring). *(Standards governing active tripwire monitoring and service stability).*
