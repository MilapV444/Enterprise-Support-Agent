# HL-ADP-01: Multi-Factor Runtime Confidence Gating & Tri-Band Routing (Jev Claim Grounding, Route Calibration & Mandatory Numeric Review)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-05 *(Confirmed per HL-D1 Jev Confidence Gate, HL-D2 Tri-Band Routing HL-Q1, HL-D13 Mandatory Numeric Co-Pilot Band UU1 & EV-D9 Calibration)*
- **Deciders**: Architecture Team, Principal AI Safety Architect, Head of Customer Support Operations, Compliance Director
- **Component**: `[12] Human-in-the-Loop` (`Component [ 12 ]`)
- **Reasoning Source**: `checkpoint.md` §16 · Diagram: `LLD - [12] Human-in-the-Loop`
- **Decisions Covered**:
  - `HL-D1`: Deterministic Runtime Confidence Gate — Every synthesized draft response from the coordinator agent (`MA-D15`) is evaluated prior to delivery by a lightweight Jev classifier operating on PII-masked inputs (`SG-D4`); computes a composite confidence metric: a Jev `Noul` boolean (*"Is every factual claim strictly supported by the cited documentation passages or tool execution results?"*) combined with a Jev `Score` assessing query relevance; agent-generated secondary evidence (`KR-D16`) is statistically discounted
  - `HL-D2`: Tri-Band Operational Routing — Inbound draft responses route across three calibrated confidence bands (`HL-Q1(ii)`):
    - **Automated Send Band** ($c \ge 0.90$): Directly dispatched to the customer delivery stream (`UA-D4`)
    - **Human Co-Pilot Band** ($0.50 \le c < 0.90$): Forwarded to the specialist queue as a pre-populated AI draft for human review and inline editing; on routes lacking a staffed queue, automatically degrades to full handoff
    - **Warm Escalation / Handoff Band** ($c < 0.50$): Bypasses draft delivery and immediately initiates human specialist escalation
  - `HL-D13`: Mandatory Financial & SLA Numeric Review — Resolves mathematical reasoning vulnerabilities in small language models ($UU1$); any draft reply that articulates monetary values, billing adjustments, refund calculations, or service level agreement (SLA) percentages is unconditionally diverted from the automated send band to the Human Co-Pilot band, guaranteeing that no financial figure reaches a customer unverified
- **Related Architectural Decision Points**:
  - [`ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/00-orchestration-core/ADP-05-decision-model-jev.md): Decision Model (Jev) *(Structured Scoring & Confidence)*
  - [`EV-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/08-evaluation-experimentation/EV-ADP-02-scoring-calibration.md): Scoring & Calibration *(Expected Calibration Error on Route Cutoffs)*
  - [`MA-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/05-multi-agent-communication/MA-ADP-05-merging-single-voice.md): Merging & Single Voice *(Coordinator Merged Draft)*
  - [`SG-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/06-safety-security-governance/SG-ADP-03-output-safety.md): Output Safety *(Pre-Delivery Sanitization Pipeline)*
  - [`HL-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/12-human-in-the-loop/HL-ADP-02-escalation-queues.md): Escalation & Queues *(Specialist Routing)*

---

## 1. Context & Problem Statement

Autonomous conversational models in enterprise support are prone to subtle hallucinations that cannot be intercepted by simple regex filters:
1. **The Semantic Grounding Failure**:
   - An LLM may synthesize a fluent, authoritative-sounding response that subtly misrepresents company policy (e.g., claiming *"Enterprise customers receive 99.995% SLA credits automatically after 10 minutes of downtime"*, when the contract requires manual claim filing and a 99.9% threshold).
   - If an agent auto-dispatches ungrounded commitments to customers, the enterprise incurs legally binding liabilities and SLA breach disputes.
2. **The High-Latency Semantic Entropy Bottleneck**:
   - Academic approaches propose measuring model uncertainty via *Semantic Entropy* (Kuhn et al., 2023), generating 5 to 10 parallel samples per turn and clustering meanings. However, this approach adds $2.0–4.0\text{ seconds}$ of generation latency and multiplies inference costs by $500\%$, violating interactive p95 SLAs (`RP-D8`).
3. **The Small Model Numeric Blind Spot ($UU1$)**:
   - Small language models (such as Jev TypeSafe classifiers) excel at semantic classification but exhibit poor numeric grounding. A small model may assess the sentence *"Your credit is \$1,240"* as supported by a passage stating *"Customer balance is \$124.00"*, misinterpreting magnitude ($UU1$). Without explicit deterministic guardrails, erroneous billing claims escape into production.

### The Core Architectural Question
> **How do we construct a low-latency, multi-factor confidence boundary that validates claim grounding on PII-masked inputs, routes drafts across three operational bands, and mandates human verification on all financial and SLA claims?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `HL-D1`, `HL-D2`, and `HL-D13` establish the **Runtime Multi-Factor Confidence Gate Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   RUNTIME CONFIDENCE GATE & TRI-BAND ROUTING (HL-D1, HL-D2, HL-D13)              │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                       Coordinator Merged Draft Reply $Y$ (MA-D15, SG-D6 Sanitized)
                                                      │
                                                      ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 1. DETERMINISTIC NUMERIC & FINANCIAL FILTER (HL-D13, UU1)                                        │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Regex & AST Parser: Does draft $Y$ contain Currency (\$, €, £), SLA Percentages, or Credits?     │
│                                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ Numeric Flag Status:                                                                     │   │
│   │ • DETECTED ===> HARD OVERRIDE: Divert directly to HUMAN CO-PILOT BAND (HL-D13)           │   │
│   │                 (Bypasses auto-send; prevents small-model numeric miscalculations)        │   │
│   │ • NONE     ===> Proceed to Jev Confidence Scorer                                         │   │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┬────────────────────────────────────────────────┘
                                                  │ (No Sensitive Numerics)
                                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 2. JEV MULTI-FACTOR CONFIDENCE SCORER (HL-D1, ADP-05 Uses 6 & 9)                                 │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 1. Claim Grounding: $g = \text{Jev}_{\text{Noul}}(\text{"Every claim strictly supported by KB/tools?"})│
│ 2. Query Relevance: $r = \text{Jev}_{\text{Score}}(\text{"Draft directly answers user query?"}) \in [0, 1]│
│ 3. Discount Agent-Generated Chunks: Weight $w = 0.5$ if evidence provenance = agent (`KR-D16`)  │
│ Composite Score: $c = g \cdot r \cdot \prod w_i$                                                 │
└─────────────────────────────────────────────────┬────────────────────────────────────────────────┘
                                                  │
           ┌──────────────────────────────────────┼──────────────────────────────────────┐
           ▼ High Confidence ($c \ge 0.90$)        ▼ Moderate ($0.50 \le c < 0.90$)       ▼ Low ($c < 0.50$)
┌───────────────────────────────┐ ┌───────────────────────────────┐ ┌───────────────────────────────┐
│ BAND 1: AUTOMATED SEND        │ │ BAND 2: HUMAN CO-PILOT        │ │ BAND 3: WARM ESCALATION /     │
│ (HL-D2)                       │ │ (HL-D2, HL-D13)               │ │ HANDOFF (HL-D2)               │
├───────────────────────────────┤ ├───────────────────────────────┤ ├───────────────────────────────┤
│ • Auto-deliver via SSE stream │ │ • AI Draft sent to Retool UI  │ │ • Suppress draft delivery     │
│ • Zero human intervention     │ │ • Specialist edits & approves │ │ • Immediate human queue dispatch│
│ • Full trace logged (OB-D1)   │ │ • If route unstaffed -> Hand- │ │ • Escalation packet generated │
│ • Latency < 100ms over gen    │ │   off immediately to Queue    │ │   with diagnostic state       │
└───────────────────────────────┘ └───────────────────────────────┘ └───────────────────────────────┘
```

---

### Pillar 1: Jev Claim Grounding & Evidence Discounting (`HL-D1`)

Rather than relying on expensive multi-sample semantic entropy, confidence is determined via a dual-predicate Jev invocation:
1. **Fact Grounding Predicate ($g \in \{0, 1\}$)**:
   - A specialized Jev `Noul` classifier evaluates the draft $Y$ against the retrieved context passages $C$ and tool execution outputs $T$:
     $$g = \mathbb{I}\left( \forall \text{claim } k \in Y, \exists c \in (C \cup T) \text{ s.t. } c \models k \right)$$
2. **Relevance Score ($r \in [0.0, 1.0]$)**:
   - Evaluates whether the draft directly addresses the customer's core intent rather than providing an evasive or irrelevant factual deflection.
3. **Agent Evidence Discounting (`KR-D16`)**:
   - In accordance with `KR-ADP-01`, if a supporting passage is flagged with provenance `origin: "agent"` (e.g., an agent-summarized case note), its evidential weight is discounted by $50\%$ ($w_i = 0.5$).
4. **Composite Formulation**:
   $$c = g \cdot r \cdot \min_{i}(w_i)$$

---

### Pillar 2: Calibrated Tri-Band Routing (`HL-D2`, `EV-D9`)

Draft delivery routes across three explicit bands based on route-specific thresholds calibrated by the evaluation harness:
- **Send Band ($c \ge 0.90$)**: High-certainty responses delivered directly to the user.
- **Co-Pilot Band ($0.50 \le c < 0.90$)**: Semi-automated assistance. The draft appears in the Retool specialist console (`HL-D11`). The human agent can accept with one click, modify parameters, or rewrite before sending.
  - *Staffing Invariant*: If the route does not have a designated active human queue (e.g., off-hours or unstaffed tier), the system automatically treats the co-pilot band as a full handoff to prevent customer stall.
- **Handoff Band ($c < 0.50$)**: The draft is deemed unreliable. The orchestrator transitions the case to human queue dispatch (`HL-ADP-02`), displaying a graceful waiting estimate to the user (`HL-D8`).

---

### Pillar 3: Mandatory Financial & SLA Numeric Review (`HL-D13`, $UU1$)

To eliminate the small-model numeric blind spot ($UU1$), all drafts undergo deterministic lexical scanning:
$$\text{HasSensitiveNumerics}(Y) = \text{Regex}_{\text{currency}}(Y) \lor \text{Regex}_{\text{percentage}}(Y) \lor \text{Regex}_{\text{sla}}(Y)$$

If `HasSensitiveNumerics(Y)` evaluates to `True`:
- The draft is **unconditionally barred** from the Automated Send Band ($c \leftarrow \min(c, 0.89)$).
- The draft routes to the Human Co-Pilot queue with the detected numeric entities visually highlighted.
- The specialist must actively confirm that the proposed financial figure matches the underlying tool invoice data before authorization.

---

## 3. Technical Implementation & Genesis Contracts

```python
"""
core/hitl/confidence_gate.py
Pydantic v2 schemas and runtime manager for Multi-Factor Confidence Gating.
"""

import re
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class ConfidenceBand(str, Enum):
    SEND = "send"          # Composite score >= 0.90
    CO_PILOT = "co_pilot"  # 0.50 <= Composite score < 0.90
    HANDOFF = "handoff"    # Composite score < 0.50


class ConfidenceVerdict(BaseModel):
    composite_score: float = Field(ge=0.0, le=1.0)
    assigned_band: ConfidenceBand
    grounding_passed: bool
    relevance_score: float
    numeric_override_triggered: bool
    requires_staffed_queue: bool
    route_name: str


class ConfidenceGateConfig(BaseModel):
    route_name: str
    send_threshold: float = Field(default=0.90, ge=0.80, le=0.99)
    handoff_threshold: float = Field(default=0.50, ge=0.10, le=0.70)
    is_queue_staffed: bool = True


class RuntimeConfidenceGate:
    """
    Evaluates draft grounding, relevance, and numeric safety (HL-D1, HL-D2, HL-D13).
    """

    NUMERIC_PATTERN = re.compile(
        r"(\$\s*[0-9]+(\.[0-9]{2})?|\b[0-9]+(\.[0-9]+)?\s*\%|\bSLA\b|\bcredit\b|\brefund\b)",
        re.IGNORECASE
    )

    def __init__(self, route_configs: Dict[str, ConfidenceGateConfig]):
        self.route_configs = route_configs

    def evaluate_draft(
        self,
        route_name: str,
        draft_text: str,
        jev_grounding_passed: bool,   # Output from Jev Noul (HL-D1)
        jev_relevance_score: float,   # Output from Jev Score (HL-D1)
        evidence_provenance_types: List[str]  # e.g., ['curated', 'agent']
    ) -> ConfidenceVerdict:
        """
        Executes confidence scoring and enforces tri-band routing invariants.
        """
        cfg = self.route_configs.get(
            route_name,
            ConfidenceGateConfig(route_name="default")
        )

        # Check for mandatory numeric / financial review (HL-D13, UU1)
        has_sensitive_numerics = bool(self.NUMERIC_PATTERN.search(draft_text))

        # Apply agent-evidence discount (KR-D16)
        provenance_discount = 0.5 if "agent" in evidence_provenance_types else 1.0

        # Calculate composite score
        grounding_factor = 1.0 if jev_grounding_passed else 0.0
        composite_score = grounding_factor * jev_relevance_score * provenance_discount

        # Determine target operational band
        numeric_override = False
        if has_sensitive_numerics and composite_score >= cfg.send_threshold:
            # Force into Co-Pilot band (HL-D13)
            assigned_band = ConfidenceBand.CO_PILOT
            numeric_override = True
        elif composite_score >= cfg.send_threshold:
            assigned_band = ConfidenceBand.SEND
        elif composite_score >= cfg.handoff_threshold:
            # If route is unstaffed, degrade co-pilot to handoff (HL-D2)
            if not cfg.is_queue_staffed:
                assigned_band = ConfidenceBand.HANDOFF
            else:
                assigned_band = ConfidenceBand.CO_PILOT
        else:
            assigned_band = ConfidenceBand.HANDOFF

        return ConfidenceVerdict(
            composite_score=round(composite_score, 4),
            assigned_band=assigned_band,
            grounding_passed=jev_grounding_passed,
            relevance_score=jev_relevance_score,
            numeric_override_triggered=numeric_override,
            requires_staffed_queue=(assigned_band == ConfidenceBand.CO_PILOT),
            route_name=route_name
        )
```

---

## 4. Failure Modes & Mitigation Matrix

| Failure ID | Sub-Component | Failure Mode Description | Root Cause | Effect on System | Architectural Mitigation (`HL-D1`, `HL-D2`, `HL-D13`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **$UU1$** | Confidence Boundaries | Erroneous numeric claim escapes gate | Small model cannot reliably verify numeric magnitudes | Incorrect refund amount or invalid SLA credit committed to customer | `HL-D13` mandates regex financial/SLA scan; unconditionally diverts all numeric drafts to Human Co-Pilot |
| **$KU1$** | Confidence Boundaries | Gate inaccuracy (false positives / negatives) | Jev grounding misclassifies nuanced natural language | Bad draft sent to user, or high-quality draft unnecessarily handed off | `EV-D9` recalibrates thresholds per route against human golden labels prior to release |
| **$UU4$** | Confidence Boundaries | Queue flooding on unstaffed routes | Co-pilot band triggers on routes without specialists | Massive backlog of blocked conversations | `HL-D2` automatically degrades co-pilot drafts to immediate cold handoff on unstaffed routes |
| **$UK1$** | Confidence Boundaries | Citation presence mistaken for true relevance | Model cites irrelevant documentation passage | Customer receives factual but non-responsive deflection | `HL-D1` pairs factual grounding ($g$) with explicit query relevance scoring ($r$) |
| **$KU2$** | Escalation | Specialist burnout from financial review load | High volume of billing questions diverts to co-pilot | Human queue SLA breaches and lengthened customer wait times | `RP-D6` incident mode coalesces duplicate queries; staffing monitored via `OB-D8` |

---

## 5. Closed-Loop Telemetry & Verification Directives

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   CONFIDENCE GATE TELEMETRY & OBSERVABILITY PIPELINE                             │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Draft Evaluation ──► [ Confidence Gate Verdict ] ──► Prometheus: `hitl.confidence.score`
                               │
                               ├──► [ Operational Band Metric ] ──► Metric: `hitl.gate.band_total`
                               │
                               └──► [ Numeric Overrides ] ──► Metric: `hitl.override.numeric_total`
```

### 1. Prometheus Telemetry Indicators
- `hitl.gate.evaluations_total`: Total drafts evaluated by confidence gate.
- `hitl.gate.band_distribution`: Histogram of drafts by band (`send`, `co_pilot`, `handoff`). (Target: $\ge 75\%$ Send, $\le 15\%$ Co-Pilot, $\le 10\%$ Handoff).
- `hitl.override.numeric_total`: Counter tracking drafts diverted to Co-Pilot strictly due to `HL-D13` financial rules.
- `hitl.calibration.ece_score`: Expected Calibration Error of Jev confidence classifier across live audited traces.

### 2. OpenTelemetry Attributes
- `hitl.confidence.composite_score`: Float between $0.0$ and $1.0$.
- `hitl.confidence.band`: `"send"` | `"co_pilot"` | `"handoff"`
- `hitl.confidence.numeric_flag`: `boolean`

---

## 6. Alternatives Considered & Trade-Off Analysis

| Architectural Alternative | Technical Mechanism | Why Rejected / Trade-Off Analysis |
| :--- | :--- | :--- |
| **Semantic Entropy Sampling (Option B)** | Generate 10 samples per draft and measure cluster entropy (Kuhn et al.) | **Rejected**: Incurs $3–5\text{s}$ latency overhead and $5\times$ token expense; fails interactive turn SLAs (`RP-D8`). |
| **Binary Gate (Send or Handoff Only, HL-F2(a))** | Eliminate co-pilot band; route directly to send or full human handoff | **Rejected**: Creates an abrupt operational cliff. Forcing human agents to take over entire conversations for minor draft edits increases human labor by $>40\%$. |
| **Small-Model Number Verification (HL-F13(a))** | Allow Jev to verify numbers without regex override | **Rejected ($UU1$)**: Small language models consistently fail numeric comparisons, allowing severe financial hallucination escapes. |
| **Universal Co-Pilot on All Routes** | Enforce co-pilot band even when no human specialists are rostered | **Rejected ($UU4$)**: Causes customer conversations to stall indefinitely in unmonitored queues during night shifts. |

---

## 7. References & Academic Foundations

1. **Kuhn, L., Gal, Y., & Farquhar, S.** (2023). *Semantic Uncertainty: Linguistic Invariances for Uncertainty Estimation in Large Language Models.* International Conference on Learning Representations (ICLR).
2. **Guo, C. et al.** (2017). *On Calibration of Modern Neural Networks.* International Conference on Machine Learning (ICML).
3. **Parasuraman, R., & Manzey, D. H.** (2010). *Complacency and Bias in Human Use of Automation: An Attentional Integration.* Human Factors, 52(3), 381-410.
4. **GDPR Article 22.** (2016). *Automated Individual Decision-Making, Including Profiling.* Human Review Mandates.
