# DL-ADP-03: Progressive Rollout & Rapid Rollback Strategies (Shadow-to-Canary Pipelines, Read-Only Canaries & Manual Rollback Directives)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-06 *(Confirmed per DL-D4 Progressive Rollout Strategy DL-Q2, DL-D5 Manual Rollback Directives & EV-D7/D12 Read-Only Canaries KK1)*
- **Deciders**: Architecture Team, Lead SRE, Principal AI Platform Architect, Incident Commander
- **Component**: `[14] Deployment & LLMOps` (`Component [ 14 ]`)
- **Reasoning Source**: `checkpoint.md` §18 · Diagram: `LLD - [14] Deployment & LLMOps`
- **Decisions Covered**:
  - `DL-D4`: Progressive Cognitive Rollout vs. Instant Code Deployment — Establishes differentiated regional deployment strategies based on risk profile (`DL-Q2(i)`):
    - **Pure Code Releases (Track A)**: Roll out all-at-once per region via zero-downtime Kubernetes rolling updates
    - **Cognitive & Model Releases (Track B)**: Execute strict three-stage progressive delivery: **Stage 1 (Shadow Mode)**: Candidate models evaluate live traffic in parallel; tool mutations are recorded purely as proposals and never executed (`EV-D12`); **Stage 2 (Canary Mode)**: Routes 5–10% of real production traffic on read-only informational routes (`EV-D7`, `EV-D13`); **Stage 3 (Full Promotion)**: Promotes to 100% regional traffic only after canary SLO validation
  - `DL-D5`: Deterministic Manual Rollback Governance — System rollbacks are executed manually by on-call SREs redeploying the previous immutable container image tag ($KK1$); automated rollbacks are intentionally avoided to prevent thrashing and cascading state corruption in multi-system Temporal outer sagas; rapid rollback triggers are tied directly to multi-window burn-rate SLO alerts (`OB-D8`)
- **Related Architectural Decision Points**:
  - [`EV-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/08-evaluation-experimentation/EV-ADP-05-live-evaluation-experiments.md): Live Evaluation & Experiments *(Shadow & Canary Architecture)*
  - [`OB-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/09-observability-monitoring/OB-ADP-03-service-levels-alerting.md): Service Levels & Alerting *(SLO Burn-Rate Alert Triggers)*
  - [`DL-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/14-deployment-llmops/DL-ADP-02-release-tracks-cadence.md): Release Tracks & Cadence *(Dual-Track Deployment)*
  - [`RP-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/10-reliability-performance-scale/RP-ADP-03-bursts-latency-capacity.md): Bursts, Latency & Capacity *(Canary Traffic Sizing)*

---

## 1. Context & Problem Statement

Deploying updates to autonomous agent runtimes introduces acute operational failure modes:
1. **The Behavioral "Flash Crash" ($KK1$)**:
   - If a new model version or updated prompt is deployed to 100% of production traffic simultaneously, an unforeseen conversational bug (such as an over-eager refund policy interpretation or a tool syntax hallucination) impacts thousands of active customer sessions in minutes.
   - If that bad release triggers unauthorized state-mutating tool writes against external enterprise CRMs or billing systems, reverting the code cannot reverse the executed external financial transactions.
2. **The Auto-Rollback Thrashing Hazard**:
   - Complex distributed sagas executed under Temporal (`ADP-02`) manage active compensating transactions and multi-day approval holds (`HL-D9`).
   - If an automated canary monitor triggers an abrupt, automated rollback while hundreds of workflows are midway through multi-step sagas, the sudden worker version flip can cause non-deterministic replay failures, stranded database locks, and double-mutation retries.
3. **The Mutation Risk in Canary Testing (`EV-D12`)**:
   - Canary testing is critical to observe live customer response distributions. However, exposing active financial or destructive tools to an unproven candidate model in canary runs risks executing unauthorized writes against live production accounts ($EV\text{ }UU5$).

### The Core Architectural Question
> **How do we engineer a progressive delivery pipeline that safely exercises candidate cognitive models on live traffic without endangering external system state, backed by a disciplined, rapid rollback protocol?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `DL-D4` and `DL-D5` establish the **Shadow-to-Canary Progressive Delivery and SRE Manual Rollback Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   PROGRESSIVE COGNITIVE DELIVERY PIPELINE (DL-D4, DL-D5, EV-D7)                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                                    CANDIDATE BEHAVIORAL RELEASE (vNext)
                                                   │
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 1: SHADOW EVALUATION MODE (EV-D7, EV-D12)                                                  │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Asynchronous Mirroring of Live Production Queries (Duration: 24 Hours):                          │
│ • Production Model (vCurrent) serves live user; delivers answers and executes tools.             │
│ • Candidate Model (vNext) receives mirror query:                                                 │
│   - Executes knowledge retrieval and internal reasoning                                          │
│   - TOOL CALLS RECORDED AS PROPOSALS ONLY (Never Executed! EV-D12)                               │
│ • Offline Judge (`EV-D2`) compares vCurrent vs. vNext outputs on accuracy, cost, and safety      │
└──────────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                   │ (Shadow Comparison Quality $\ge$ Baseline)
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 2: READ-ONLY CANARY PROGRESSIVE ROUTING (DL-D4, EV-D7, EV-D13)                             │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Route 10% of Live Production Traffic on READ-ONLY INFORMATIONAL ROUTES ONLY:                     │
│ • Customer FAQ Inquiries, Documentation Navigation, Status Lookups                               │
│ • State-Mutating Financial / Account Tool Routes STRICTLY EXCLUDED from Canary (`EV-D13`)        │
│ • Real-time Monitoring: Internal SLO Burn Rate (`OB-D8`), CSAT/CES Live Metrics (`EV-D5`)       │
└──────────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                   │
           ┌───────────────────────────────────────┴───────────────────────────────────────┐
           ▼ (SLO Burn Rate Normal)                                                        ▼ (SLO Burn Alert Fired!)
┌───────────────────────────────────────────────┐ ┌────────────────────────────────────────────────┐
│ STAGE 3: FULL REGIONAL PROMOTION (DL-D4)      │ │ MANUAL ROLLBACK DIRECTIVE (DL-D5, KK1)         │
├───────────────────────────────────────────────┤ ├────────────────────────────────────────────────┤
│ • Promoted to 100% of Regional Traffic        │ │ • Prometheus `OB-D8` Multi-Burn-Rate Alert Page│
│ • Deployed Region-by-Region (US -> EU)        │ │ • Incident Commander executes rollback:        │
│ • Full Tool & Mutation Access Enabled         │ │   `helm rollback agent-prod-us <prev_rev>`     │
│                                               │ │ • Reverts to immutable vCurrent image tag      │
│                                               │ │ • In-flight Temporal workflows drain cleanly   │
└───────────────────────────────────────────────┘ └────────────────────────────────────────────────┘
```

---

### Pillar 1: Progressive Three-Stage Cognitive Rollout (`DL-D4`)

Track B behavioral and model releases follow a mandatory three-stage deployment envelope:
1. **Stage 1 (Passive Shadow Mode, `EV-D12`)**:
   - Incoming live user messages are copied to candidate pods via asynchronous message queues.
   - Candidate models generate internal plans and tool call proposals. State-mutating tools are intercepted by a dummy mock executor that records parameter diffs without network dispatch.
   - Asserts zero divergence on safety guardrail classifications and verified facts.
2. **Stage 2 (Active Read-Only Canary, `EV-D7`, `EV-D13`)**:
   - The API Gateway shifts $10\%$ of live conversational traffic to the candidate release.
   - **Scope Invariant (`EV-D13`)**: Canary routing is **strictly restricted to read-only routes** (e.g., FAQ navigation, documentation search, status verification). High-risk routes involving billing adjustments or credential updates remain anchored to the stable baseline release.
3. **Stage 3 (Full Regional Promotion)**:
   - If canary metrics demonstrate stable latency, zero safety regressions, and pass the $\le +10\%$ cost increase ceiling (`CR-D12`), traffic scales to $100\%$ across the region.

---

### Pillar 2: Manual Rollback Governance (`DL-D5`, $KK1$)

To maintain operational sanity during live production incidents:
1. **The Rejection of Blind Auto-Rollbacks**:
   - Automated rollback controllers frequently misdiagnose transient external provider latency spikes as code regressions, triggering destructive deployment oscillation.
   - Rollback authority is reserved for human Incident Commanders and on-call SREs.
2. **Paging Triggers (`OB-D8`)**:
   - Rollback investigations are triggered by automated multi-window SLO burn-rate alerts:
     - 1-hour burn-rate alert ($14.4\times$ burn, consuming $2\%$ error budget in 1 hour).
     - 6-hour burn-rate alert ($6\times$ burn, consuming $5\%$ error budget in 6 hours).
3. **Deterministic Rollback Mechanic**:
   - Rollbacks execute via standard Helm revision history:
     ```bash
     helm rollback agent-prod-us-east-1 42
     ```
   - Because all container images are immutable and stamped with semantic release manifests (`DL-D2`), rolling back restores the exact verified code, prompts, and Cedar policies in $<60\text{ seconds}$.

---

## 3. Technical Implementation & Genesis Contracts

```yaml
# infrastructure/helm/templates/canary-traffic-router.yaml
# Istio / Traefik VirtualService governing Read-Only Canary Routing (DL-D4, EV-D7).

apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata:
  name: agent-canary-router
  namespace: agent-prod
spec:
  hosts:
    - "api.agent.enterprise.corp"
  http:
    # Rule 1: High-Risk Mutating Routes STRICTLY PINNED to Stable Baseline (EV-D13)
    - match:
        - uri:
            prefix: "/api/v1/actions/financial"
        - uri:
            prefix: "/api/v1/actions/destructive"
      route:
        - destination:
            host: agent-core-service
            subset: stable-baseline
          weight: 100

    # Rule 2: Read-Only Routes Split: 90% Stable, 10% Candidate Canary (DL-D4)
    - match:
        - uri:
            prefix: "/api/v1/turns"
          headers:
            x-route-type:
              exact: "read_only_faq"
      route:
        - destination:
            host: agent-core-service
            subset: stable-baseline
          weight: 90
        - destination:
            host: agent-core-service
            subset: candidate-canary
          weight: 10
```

```python
"""
scripts/sre/rollback_incident_checker.py
SRE operational script evaluating canary health and emitting rollback recommendations (DL-D5).
"""

from typing import Dict, Any
from pydantic import BaseModel


class CanaryHealthStatus(BaseModel):
    canary_version: str
    error_rate_pct: float
    p95_latency_ms: float
    slo_burn_rate: float
    cost_increase_pct: float
    recommendation: str


def evaluate_canary_health(
    error_rate: float,
    p95_latency: float,
    burn_rate: float,
    cost_delta: float
) -> CanaryHealthStatus:
    """
    Evaluates live telemetry indicators against release criteria (DL-D5, OB-D8, CR-D12).
    """
    # Thresholds: Max 2% error, Max 5000ms FAQ latency, Max 2.0x burn rate, Max 10% cost rise
    is_failing = (
        error_rate > 2.0 or
        p95_latency > 5000.0 or
        burn_rate > 2.0 or
        cost_delta > 10.0
    )

    recommendation = (
        "CRITICAL: TRIGGER MANUAL ROLLBACK (DL-D5). Run: helm rollback agent-prod <prev>"
        if is_failing else
        "CANARY HEALTHY: Proceed with Stage 3 Full Regional Promotion."
    )

    return CanaryHealthStatus(
        canary_version="v2.4.0-rc1",
        error_rate_pct=error_rate,
        p95_latency_ms=p95_latency,
        slo_burn_rate=burn_rate,
        cost_increase_pct=cost_delta,
        recommendation=recommendation
    )
```

---

## 4. Failure Modes & Mitigation Matrix

| Failure ID | Sub-Component | Failure Mode Description | Root Cause | Effect on System | Architectural Mitigation (`DL-D4`, `DL-D5`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **$KK1$** | Deployment | Bad release breaks all regional sessions simultaneously | 100% traffic shift without canary phase | Massive multi-tenant service outage across region | `DL-D4` mandates shadow evaluation followed by 10% read-only canary before full promotion |
| **$EV\text{ }UU5$** | Deployment | Canary release executes unauthorized financial writes | Untested model allowed to mutate production CRM | Accidental credit memos or balance changes issued | `DL-D4` and `EV-D13` strictly quarantine canary traffic to read-only informational routes |
| **$DL-D5$** | Rollback | Rollback delayed while incident escalates | On-call SRE unaware of canary degradation | Lingering customer impact during outage | `OB-D8` multi-window SLO burn-rate alerts immediately page Incident Commander |
| **$UU1$** | Rollback | Rollback corrupts in-flight Temporal workflows | Container rolled back without checkpoint compatibility | Deserialization crashes on resuming paused cases | Checkpoint migrations verified in CI (`TQ-D14`); workflows continue-as-new safely (`DL-D6`) |

---

## 5. Closed-Loop Telemetry & Verification Directives

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   CANARY & ROLLBACK OBSERVABILITY PIPELINE                                       │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Canary Traffic ──► [ Istio Telemetry Router ] ──► Metric: `canary.traffic.weight_pct`
                             │
                             ├──► [ Multi-Window Burn Alert ] ──► Prometheus: `slo.error_budget.burn_rate`
                             │
                             └──► [ Manual Rollback Audit ]  ──► Audit Log: `deploy.rollback.executed`
```

### 1. Prometheus Telemetry Indicators
- `deploy.canary.traffic_percentage`: Gauge tracking current percentage of traffic routed to canary pods.
- `deploy.canary.slo_burn_rate`: Multi-burn-rate metric tracking error budget consumption in canary subset.
- `deploy.rollback.events_total`: Counter tracking total manual rollbacks executed by SRE team.

---

## 6. Alternatives Considered & Trade-Off Analysis

| Architectural Alternative | Technical Mechanism | Why Rejected / Trade-Off Analysis |
| :--- | :--- | :--- |
| **Instant 100% Promotion for All Releases (DL-F4(a))** | Deploy all cognitive and model changes directly to 100% traffic | **Rejected ($KK1$)**: Unacceptable blast radius; any prompt defect or hallucination immediately damages all regional customers. |
| **Fully Automated Machine Rollback (DL-F5(b))** | Algorithmic daemon executes automated rollback on any metric blip | **Rejected**: High risk of deployment thrashing; transient third-party API hiccups trigger unnecessary rolling crashes across Temporal sagas. |
| **Canary on All Routes Including Writes** | Route 10% of financial refund traffic to unproven canary model | **Rejected ($EV\text{ }UU5$)**: High financial liability; canary testing should never risk unauthorized real-world database mutations. |

---

## 7. References & Academic Foundations

1. **Beyer, B. et al.** (2016). *Site Reliability Engineering: How Google Runs Production Systems.* O'Reilly Media. Chapter 27: Reliable Product Launching.
2. **Argo Project.** (2024). *Argo Rollouts: Progressive Delivery for Kubernetes.* Technical Documentation.
3. **NIST SP 800-53, Rev. 5.** (2020). *Security and Privacy Controls for Information Systems and Organizations.* Control CP-10: Information System Recovery and Reconstitution.
