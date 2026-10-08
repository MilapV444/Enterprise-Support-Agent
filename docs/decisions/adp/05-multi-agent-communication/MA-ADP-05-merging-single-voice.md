# MA-ADP-05: Merging & The Single Voice (Jev Claim Scoring, Deterministic Numeric Gating & Anti-Deflection Unified Persona)

- **Status**: Accepted & Confirmed
- **Date**: 2026-09-29 *(Amended: 2026-09-29 per MA-D7 Jev Conflict Scoring, MA-D12 Unified Voice, MA-D13 Anti-Redirect Noul, MA-D15 Merged Reply, MA-D16 Numeric HITL Gate & MA-D17 Persona Consistency)*
- **Deciders**: Architecture Team, Lead Conversation Designer, AI Safety & Governance Core
- **Component**: `[5] Multi-Agent & Communication` (`Component [ 5 ]`)
- **Reasoning Source**: `checkpoint.md` §9 · Diagram: `LLD - [5] Multi-Agent & Communication`
- **Decisions Covered**:
  - `MA-D7`: Semantic Conflict Resolution — Conflicting specialist findings resolved via Jev `Score` (1–5 scale) measuring claim entailment against cited evidence; ties or low evidence support trip to Human Specialist (HITL)
  - `MA-D16`: Deterministic Numeric Discrepancy Gate — Numeric disagreements between specialists (uptime percentages, financial sums) are strictly detected in code and trip immediately to HITL; Jev is excluded from mathematical conflict adjudication ($UU4$)
  - `MA-D12`: The Single Voice Invariant — Specialists are strictly forbidden from communicating with the customer; the Coordinator alone authors customer-facing responses, eliminating parallel voices ($UU2$) and action hallucinations ($UU1$)
  - `MA-D13`: Anti-Deflection Verification Gate — Jev `Noul` query on draft replies ("does this message redirect the user to another team or department?"); affirmative scores halt delivery and force internal re-delegation ($UK1$)
  - `MA-D15`: Synchronized Join & Single Response — Exactly one consolidated response delivered to the customer socket after all active specialists join and conflict checks pass
  - `MA-D17`: Unified Enterprise Persona — Cohesive brand tone and terminology; the Coordinator drafts responses in one unified voice while transparently citing internal findings (e.g., *"Our billing analysis verified..."*)
- **Related Architectural Decision Points**:
  - [`ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/00-orchestration-core/ADP-05-decision-model-jev.md): Decision Model (Jev) *(Scoring & Noul Query Paradigms)*
  - [`HL-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#hl-adp-01--confidence-gate): Confidence Gate *(Downstream Grounding & Hallucination Checks)*
  - [`SG-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#sg-adp-03--output-safety): Output Safety *(Leakage, Promise, and Markdown Checks)*
  - [`UA-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/01-user-application/UA-ADP-04-response-contract-delivery.md): Response Contract & Delivery *(CloudEvents Response Envelope)*

---

## 1. Context & Problem Statement

When multiple domain specialists analyze a complex enterprise incident, they frequently arrive at divergent conclusions or generate conflicting recommendations. For example, during an outage review:
- The Technical specialist reports: *"Service degraded due to downstream AWS regional network failure; uptime was 99.92%"*.
- The Account & Ops specialist reports: *"Service degraded due to customer misconfiguring their VPC peering; uptime was 99.85%"*.
- The Billing specialist reports: *"Customer is entitled to a $450 credit based on 99.85% uptime, but $0 credit based on 99.92% uptime"*.

In this multi-agent setting, naive response assembly triggers severe systemic failures:

1. **The Parallel Voices & Cacophony Exploit ($UU2$)**: If sub-agents communicate directly with the user over web sockets as their tasks complete, the customer receives multiple conflicting messages in real time. The Technical agent says *"We are looking into it"*, while Billing simultaneously messages *"Your ticket is resolved"*, completely shattering customer trust.
2. **The Numeric Hallucination Trap ($UU4$)**: Large Language Models are notoriously unreliable at arithmetic comparisons and financial boundary checks (jagged intelligence; Bubeck et al., 2023). Relying on an LLM to "reconcile" two conflicting numbers results in hallucinated intermediate values that contradict contractual SLAs.
3. **The Bureaucratic Ping-Pong Runaround ($UK1$)**: Specialists operating in domain silos frequently attempt to deflect responsibility: *"This is a billing issue; please call our accounting desk"*. Customers are forced to navigate internal enterprise bureaucracy instead of receiving autonomous support.
4. **Premature Action Promises ($UU1$)**: A specialist states *"I have applied a $1,240 refund to your account"*, but the refund requires two-person human approval and has not yet been authorized.

### The Core Architectural Question
> **How do we adjudicate factual and numeric conflicts between specialists, prevent bureaucratic customer deflections, and synthesize multi-agent findings into a single, cohesive, authoritative voice?**

---

## 2. Decision Framework & Theoretical Formulation

To solve these challenges, we establish the **Two-Tier Conflict Adjudication & Single Voice Synthesis Pipeline**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             TWO-TIER CONFLICT RESOLUTION (MA-D7, MA-D16)                         │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

Specialist Results Joined at Barrier: [Technical Result] + [Billing Result] + [Ops Result]
                                                │
                                                ▼
                             ┌──────────────────────────────────────┐
                             │ Tier 1: Deterministic Numeric Gate   │
                             │ (MA-D16, Code Check)                 │
                             │ Do numerical values disagree?        │
                             └──────────────────────────────────────┘
                                                │
                       ┌────────────────────────┴────────────────────────┐
                       │ YES (e.g., $450 vs $0)                          │ NO (Numbers Match)
                       ▼                                                 ▼
        ┌─────────────────────────────┐                   ┌─────────────────────────────┐
        │ TRIP TO HUMAN SPECIALIST    │                   │ Tier 2: Jev Claim Scoring   │
        │ (HITL Escalation, UU4 Fixed)│                   │ (MA-D7, TypeSafe NLI)       │
        │ Prevents numeric confusion  │                   │ Score: Entailment vs Evidence│
        └─────────────────────────────┘                   └─────────────────────────────┘
                                                                         │
                                                ┌────────────────────────┴────────────────────────┐
                                                │ Score Tie or Low Support (<3)                   │ Clear Winner (ΔScore ≥ 2)
                                                ▼                                                 ▼
                                 ┌─────────────────────────────┐                   ┌─────────────────────────────┐
                                 │ TRIP TO HUMAN SPECIALIST    │                   │ Adopt High-Scoring Claim    │
                                 │ Ambiguity requires human    │                   │ Synthetic Deliverable Formed│
                                 └─────────────────────────────┘                   └─────────────────────────────┘
                                                                                                  │
                                                                                                  ▼
                                                                                   ┌─────────────────────────────┐
                                                                                   │ Tier 3: Coordinator Single  │
                                                                                   │ Voice & Anti-Redirect Gate  │
                                                                                   │ (MA-D12, MA-D13, MA-D17)    │
                                                                                   └─────────────────────────────┘
```

---

### Pillar A: Deterministic Numeric Gating in Code (`MA-D16` / $UU4$)

We enforce an absolute architectural boundary: **Models do not adjudicate numeric disputes**.
All numbers (uptime metrics, invoice currency totals, latency thresholds) are extracted into typed Pydantic fields.

$$\text{Discrepancy}(A, B) \iff \exists k \in \text{NumericKeys}, \quad |v_A(k) - v_B(k)| > \epsilon$$

If two specialists emit conflicting numerical values for the same business metric:
$$\text{Action} = \text{TripToHumanSpecialist}(\text{ERR\_NUMERIC\_DISCREPANCY}, \text{Payload} = \{A: v_A, B: v_B\})$$
The system immediately halts automated generation and routes the conflict to a Human Specialist with a pre-populated discrepancy card.

---

### Pillar B: Semantic Conflict Scoring via Jev Natural Language Entailment (`MA-D7`)

For non-numeric factual disagreements (e.g., Root Cause A vs. Root Cause B), Jev evaluates each claim $c_i$ against its cited evidence $\mathcal{E}_i$ using an ordered 5-point Likert `Score` query (TypeSafe Model Evaluation Use 6):

$$s(c_i) = \text{Jev.Score}\left(
\text{State} = \{\text{Claim}: c_i, \text{Evidence}: \mathcal{E}_i\},
\text{Question} = \text{"How strongly does the cited evidence support this factual claim?"},
\text{Levels} = [1: \text{"Unsupported"}, 2: \text{"Weak"}, 3: \text{"Plausible"}, 4: \text{"Strong"}, 5: \text{"Definitive"}]
\right)$$

#### Adjudication Decision Rules
Let $c_A$ and $c_B$ be conflicting claims, with scores $s_A, s_B \in [1, 5]$:
$$\text{Adjudication} = \begin{cases}
c_A & \text{if } s_A \ge 4 \land s_B \le 2 \quad (\text{Clear Win for A}) \\
c_B & \text{if } s_B \ge 4 \land s_A \le 2 \quad (\text{Clear Win for B}) \\
\text{TripToHITL}(\text{EVIDENCE\_AMBIGUITY}) & \text{otherwise (Ties, Weak Support, or Close Contests)}
\end{cases}$$
The agent never gambles on ambiguous evidence; any contest within $\Delta s < 2$ escalates to human review.

---

### Pillar C: The Single Voice & Anti-Deflection Verification Gate (`MA-D12`, `MA-D13`, `MA-D17`)

#### 1. The Single Voice Invariant (`MA-D12`, `MA-D15`)
Specialist subgraphs possess zero socket dispatch authority. Only the Coordinator generates customer-facing text:
$$\text{CustomerSocket.write}(m) \implies \text{Author}(m) = \text{Coordinator}$$
This eliminates parallel voice cacophony ($UU2$) and ensures that the customer experiences a single unified paired-programming session.

#### 2. Jev Anti-Deflection Gate (`MA-D13` / $UK1$)
Before the Coordinator's draft response is transmitted over the SSE stream, Jev evaluates an adversarial anti-redirect `Noul` query:
$$\mathbb{P}(\text{is\_redirect}) = \text{Jev.Noul}\left(
\text{State} = \tilde{m}_{\text{draft}},
\text{Question} = \text{"Does this message instruct or advise the customer to reach out to another internal team, department, or specialist rather than resolving it here?"}
\right)$$

Execution gate:
$$\text{DispatchRule} = \begin{cases}
\text{DeliverToCustomer}(\tilde{m}_{\text{draft}}) & \text{if } \mathbb{P}(\text{is\_redirect}) < 0.20 \\
\text{HaltAndRedelegate}(\text{ERR\_BUREAUCRATIC\_DEFLECTION}) & \text{if } \mathbb{P}(\text{is\_redirect}) \ge 0.20
\end{cases}$$
If an affirmative redirect is detected, the draft is held; the Coordinator either activates the missing specialist subgraph internally or trips to HITL.

#### 3. Transparent Attribution Persona (`MA-D17`)
The Coordinator authors replies using a shared enterprise persona, integrating specialist findings seamlessly:
> *"I investigated your invoice discrepancy with our engineering and billing records. Our technical diagnostics confirmed that BUG-8192 caused the database resync traffic on September 24. Consequently, I have prepared a $12,400 credit memo for your review."*

---

## 3. Decision Rules, Structural Invariants & Code Contracts

### Decision Invariants
1. **Invariant 1 (Strict Single-Writer Socket Architecture)**: Only the Coordinator LangGraph node may append messages to the customer turn envelope.
2. **Invariant 2 (Zero Numeric Hallucination Tolerance)**: Numerical fields that disagree across specialist outputs must trigger an immediate HITL escalation in code.
3. **Invariant 3 (Anti-Redirect Failsafe)**: Draft replies exhibiting $\mathbb{P}(\text{is\_redirect}) \ge 0.20$ must never reach customer channels.
4. **Invariant 4 (Verified Action Wording)**: Proposed actions must be phrased using prospective modal verbs (*"I have requested"*, *"I have prepared"*); only actions confirmed via read-back (`MA-D14`) may use past-tense completion verbs (*"I have processed"*).

---

### Python & Pydantic Data Contracts

```python
"""
Data contracts for Conflict Resolution, Response Merging, and Single Voice Synthesis.
Module: core/multiagent/synthesis.py
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class ConflictType(str, Enum):
    NUMERIC_DISCREPANCY = "numeric_discrepancy"
    FACTUAL_CONTRADICTION = "factual_contradiction"
    ACTION_INCOMPATIBILITY = "action_incompatibility"


class JevClaimScoreResult(BaseModel):
    """Output of Jev Score natural language evidence entailment check (MA-D7)."""
    claim: str
    source_role: str
    score: int = Field(..., ge=1, le=5, description="1=Unsupported, 5=Definitive")
    confidence: float = Field(..., ge=0.0, le=1.0)
    entailment_explanation: Optional[str] = None


class ConflictAdjudicationResult(BaseModel):
    """Result of multi-specialist join conflict analysis."""
    has_conflicts: bool
    conflict_type: Optional[ConflictType] = None
    requires_human_escalation: bool = Field(default=False)
    escalation_reason: Optional[str] = None
    
    # Adjudicated conclusions
    winning_claims: List[str] = Field(default_factory=list)
    adjudication_timestamp: datetime = Field(default_factory=datetime.utcnow)


class AntiRedirectCheckResult(BaseModel):
    """Output contract for Jev Noul anti-deflection verification (MA-D13)."""
    draft_response: str
    is_redirect_detected: bool
    redirect_probability: float = Field(..., ge=0.0, le=1.0)
    passed_gate: bool


class FinalSynthesizedResponse(BaseModel):
    """Consolidated single-voice customer response deliverable (MA-D15, MA-D17)."""
    case_id: str
    conversation_id: str
    response_text: str = Field(..., description="Unified single-voice prose written by Coordinator")
    
    # Traceability
    participating_specialists: List[str]
    citations_included: List[str]
    proposed_action_card_ids: List[str] = Field(default_factory=list)
    
    passed_anti_redirect_gate: bool = Field(default=True)
    synthesized_at: datetime = Field(default_factory=datetime.utcnow)
```

---

## 4. Failure Modes Matrix & Resilience Invariants

| Quadrant | Failure Scenario | Detection Mechanism | Systemic Mitigation & Recovery |
| :--- | :--- | :--- | :--- |
| **Q1: Known Knowns** | **Bureaucratic Redirect Deflection ($UK1$)**: Coordinator draft tells the customer: *"Please contact our sales desk for credit questions"*. | Jev Anti-Redirect Gate (`MA-D13`) evaluates draft response. | If $\mathbb{P}(\text{is\_redirect}) \ge 0.20$, draft delivery is halted; Coordinator re-delegates internally or routes to HITL. |
| **Q2: Known Unknowns** | **Jev Claim Scoring Tie / Weakness ($KU2$)**: Two specialists offer plausible, equally supported explanations for a network failure. | Score difference evaluator detects $\Delta s < 2$ or scores $\le 3$. | Engine refuses to gamble; trips immediately to Human Specialist (`MA-D7`) with both specialists' evidence packets. |
| **Q3: Unknown Knowns** | **Parallel Voice Cacophony ($UU2$)**: Two specialists send concurrent SSE chunks, producing garbled user interfaces. | Single-writer socket invariant enforces Coordinator-only delivery. | Structural barrier: Specialists do not hold socket references (`MA-D12`); exactly one message emitted after the join barrier (`MA-D15`). |
| **Q4: Unknown Unknowns** | **Numeric Discrepancy Hallucination ($UU4$)**: LLM attempts to split the difference between conflicting $450 and $0 refund recommendations. | Deterministic numeric code evaluator catches value divergence. | Code-level assertion trips immediately to HITL (`MA-D16`); LLMs are strictly excluded from numeric dispute resolution. |

---

## 5. Closed-Loop Feedback & Verification Signals

1. **System Health Telemetry**:
   - `Conflict_Resolution_HITL_Escalation_Rate`: Tracks percentage of multi-specialist turns requiring human tie-breaking.
   - `Anti_Redirect_Violation_Rate`: Monitored per route; alerts if draft replies contain bureaucratic deflections (alerts if $> 1\%$).
   - `Numeric_Discrepancy_Trigger_Count`: Monitored across billing and SLA audit turns.
2. **Weekly Tone and Consistency Audit**:
   - Sample $100$ synthesized cross-domain responses. Run automated semantic consistency evaluators in CI (`EV-ADP-02`) asserting a unified persona and zero customer-facing attribution fragmentation.

---

## 6. Genesis Implementation Directives

1. **Code Locations**:
   - Implement numeric conflict detection in `core/multiagent/numeric_gate.py`.
   - Implement Jev claim scoring in `core/multiagent/claim_adjudicator.py`.
   - Implement the Coordinator synthesis compiler in `core/multiagent/synthesizer.py`.
   - Implement the Jev anti-redirect gate in `core/multiagent/anti_redirect.py`.
2. **Testing Directives**:
   - Implement CI test cases in `tests/multiagent/test_synthesis.py` asserting that numerical discrepancies ($450 vs $0) trigger deterministic HITL exceptions without invoking LLM synthesis.

---

## 7. Consequences & Trade-offs

### Positive Consequences
- **Total Elimination of Cacophony**: Single-voice synthesis guarantees the customer experiences a cohesive, premium conversational partner.
- **Mathematical Safety on Numbers**: Excluding models from numeric dispute arbitration eliminates hallucinated settlement figures and financial liability.
- **Eradication of Bureaucratic Deflection**: Jev anti-redirect gating ensures customer problems are solved autonomously rather than passed between teams.

### Negative Consequences & Trade-offs
- **Elevated Specialist Escalation Rate**: Escalating all numeric discrepancies and evidence ties increases the volume of tickets routed to human specialists.
- **Synthesis Inference Latency**: Running Jev claim scoring and subsequent Coordinator synthesis adds $\approx 350\text{ms}$ to turn response delivery.
- **Loss of Specialist Conversational Color**: Suppressing individual specialist direct communication prevents unique specialist personas from emerging.

---

## 8. References & Cross-Disciplinary Grounding

1. **Sparks of Artificial General Intelligence: Early Experiments with GPT-4**: Bubeck, S., et al. (2023). arXiv:2303.12712. (Analysis of jagged intelligence and mathematical reasoning limits).
2. **Natural Language Inference and Fact Verification**: Thorne, J., et al. (2018). *FEVER: A Large-scale Dataset for Fact Extraction and VERification*. NAACL.
3. **Customer Effort Score (CES) and Service Friction**: Dixon, M., et al. (2010). *Stop Trying to Delight Your Customers*. Harvard Business Review.
4. **Moffatt v. Air Canada (2024 BCCRT 149)**: Legal precedent on unverified representations and promises made by automated chat interfaces.
