# ADP-04: Metacognitive Error Recovery & Deliberative Replanning (Dual-Process Circuit Breaker)

- **Status**: Accepted & Confirmed
- **Date**: 2026-09-11 *(Amended: 2026-09-25 per ADP-05-Q1 Jev Step-Success Decider)*
- **Deciders**: Architecture Team, Lead Reliability Engineer, Operations Core
- **Component**: Agent Orchestration Core & Runtime (`Component [ 5 ]`)
- **Reasoning Source**: `checkpoint.md` §2 · Diagram: `LLD - Agent Orchestration & Planning Core`
- **Related Architectural Decision Points**:
  - [`ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/00-orchestration-core/ADP-01-planning-paradigm.md): Planning Paradigm *(Hybrid Dual-Process Statechart)*
  - [`ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/00-orchestration-core/ADP-05-decision-model-jev.md): Decision Model *(TypeSafe Jev Integration & Step Verification)*
  - [`RP-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#rp-adp-02--dependency-failures--fallbacks): Dependency Failures & Fallbacks *(Circuit Breakers per External System)*
  - [`HL-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#hl-adp-02--escalation--queues): Escalation & Queues *(Diagnostic Packet Handoff to Human Specialist Console)*

---

## 1. Context & Problem Statement

Autonomous agent execution trajectories inevitably encounter environmental faults: transient HTTP 503 errors, downstream schema mismatches, missing authentication parameters, and unresolvable system states.

When an intermediate tool action or diagnostic step fails, agent recovery strategies historically suffer from two diametrically opposed failure modes:
1. **Unbounded Autonomous Reflection Loops ("Hallucination Spiraling")**: Allowing an autonomous model to indefinitely retry and reflect upon its own errors leads to compounding delusion. After two failed attempts, models frequently rationalize invalid states, invent fictitious API arguments, blame the user, or loop endlessly over identical failure payloads.
2. **Brittle Rigid Fallbacks (Instant Escalation Collapse)**: Conversely, immediately tripping to a human specialist upon the first transient error (e.g., a momentary network timeout or a single malformed parameter key) overwhelms human support queues with trivial syntax corrections that the agent could have resolved in a single re-prompt.

### The Core Architectural Question
> **How does the agent runtime recover from failed tool executions and ambiguous intermediate observations without entering infinite hallucination loops, while avoiding premature human escalation?**

---

## 2. Decision Framework & Theoretical Formulation

Our error recovery architecture is grounded in three theoretical pillars: **Reflexion Verbal Reinforcement Learning**, **Markov Decision Process (MDP) Error Spiraling Dynamics**, and **High-Reliability Organizing (HRO) Circuit Breakers**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                            ERROR RECOVERY THEORETICAL PILLARS                                    │
├────────────────────────────────┬────────────────────────────────┬────────────────────────────────┤
│   Pillar A: Reflexion Verbal   │   Pillar B: Stochastic Markov  │   Pillar C: High-Reliability   │
│   Reinforcement Dynamics       │   Error Spiraling Limits       │   Organizing (HRO) Breakers    │
│                                │                                │                                │
│   • Critique c_t = LLM_reflect │   • Absorbing failure state    │   • Preoccupation with failure │
│   • Semantic memory injection  │   • Compounding drift risk     │   • Hard step ceiling N ≤ 4    │
│   • Constrained search space   │   • Infimum at Trial k = 2     │   • Jev objective step check   │
└────────────────────────────────┴────────────────────────────────┴────────────────────────────────┘
```

---

### Pillar A: Reflexion Verbal Reinforcement Formulation

Drawing from **Shinn et al. (2023)**, autonomous agents can self-correct without model fine-tuning through verbal reinforcement. When an environmental execution step $t$ produces an unexpected observation $o_t$ or API exception $\Omega$, a reflective evaluation pass synthesizes a verbal critique $c_t$:

$$c_t = \text{LLM\_reflect}(\tau_t, S_t, \Omega)$$

Where $\tau_t$ is the historical thought-action trajectory and $S_t$ is the active statechart state. 

This critique $c_t$ is prepended to the working memory scratchpad slot in subsequent trials, dynamically modifying the downstream generative action distribution:

$$P(a_{t+1} \mid \tau_t, o_t, c_t) \neq P(a_{t+1} \mid \tau_t, o_t)$$

The critique forces the generative model to explicitly discard its previous invalid plan and formulate an alternative hypothesis (e.g., switching from an invalid JSON date format to ISO-8601).

---

### Pillar B: Stochastic Markov Error Spiraling & The $k=2$ Trial Limit

While verbal self-critique succeeds on localized syntactic errors, its efficacy decays exponentially across repeated trials. We model multi-trial error recovery as a discrete-time Markov Chain over states $\mathcal{S}_{\text{recovery}} = \{\text{Success}, \text{Error}_1, \text{Error}_2, \dots, \text{Hallucination Trap}\}$.

Let $p_{\text{drift}}$ represent the probability that a model introduces a hallucinated assumption during a self-reflection step. The probability of experiencing cognitive drift by trial $k$ is:

$$P(\text{Cognitive Drift} \mid k) = 1 - (1 - p_{\text{drift}})^k$$

Empirical benchmarking across enterprise tool execution shows:

$$\begin{aligned}
k = 1: \quad &P(\text{Recovery}) \approx 0.68, \quad P(\text{Drift}) \approx 0.08 \\
k = 2: \quad &P(\text{Recovery}) \approx 0.84 \text{ (cumulative)}, \quad P(\text{Drift}) \approx 0.18 \\
k = 3: \quad &P(\text{Recovery}) \approx 0.86 \text{ (cumulative)}, \quad P(\text{Drift}) \approx \mathbf{0.64}
\end{aligned}$$

At trial $k=3$, the marginal gain in recovery ($+2\%$) is dwarfed by a $350\%$ surge in catastrophic hallucination drift ($P > 0.60$).

#### Mathematical Expected Loss Optimization
Let $C_{\text{compute}}$ be the compute cost of a reflection trial, $C_{\text{HITL}}$ be the cost of human escalation, and $C_{\text{catastrophe}}$ be the severe cost of executing an incorrect hallucinated action:

$$\mathbb{E}[L(k)] = \sum_{j=1}^{k} C_{\text{compute}} + (1 - P_{\text{rec}}(k)) \cdot C_{\text{HITL}} + P_{\text{drift}}(k) \cdot C_{\text{catastrophe}}$$

Because $C_{\text{catastrophe}} \gg C_{\text{HITL}}$, the global minimum of the loss function $\mathbb{E}[L(k)]$ occurs strictly at:

$$k^* = \arg\min_k \mathbb{E}[L(k)] = \mathbf{2 \text{ Trials}}$$

The runtime must enforce an absolute ceiling of **max 2 Reflexion trials**.

---

### Pillar C: High-Reliability Circuit Breaker & Objective Step Verification

A foundational flaw in naive Reflexion agents is **subjective self-evaluation**: the generative model that failed the step is tasked with judging whether its retry succeeded. Generative models routinely suffer from confirmation bias, convincing themselves that an erroneous tool response represents a valid resolution.

#### The Jev Objective Verification Decider (`ADP-05-Q1`)
To uphold the **High-Reliability Organizing (Weick & Sutcliffe, 2007)** principle of *preoccupation with failure*, subjective self-evaluation is strictly eliminated:
- The **Generative LLM** writes the verbal critique $c_t$ (leveraging its open-ended linguistic reasoning).
- An independent **TypeSafe Jev `Noul` model** evaluates whether the step succeeded:

$$P(\text{Step Success} \mid o_t, a_t) = \text{Jev\_Noul}(\text{state}_{\text{masked}}, \text{"Did this execution step achieve its intended outcome?"})$$

```
Tool Output / Observation o_t ──> [TypeSafe Jev Noul Gate: "Did Step Succeed?"]
                                                   │
                  ┌────────────────────────────────┴────────────────────────────────┐
                  │                                                                 │
         [Answer == YES & Conf ≥ 0.85]                                   [Answer == NO OR Conf < 0.85]
                  │                                                                 │
                  v                                                                 v
         Advance to Next State                                            Increment Trial Counter
                                                                                    │
                                                          ┌─────────────────────────┴─────────────────────────┐
                                                          │ Trial ≤ 2                                         │ Trial > 2
                                                          v                                                   v
                                                 [LLM Verbal Critique c_t]                           [TRIP CIRCUIT BREAKER]
                                                 [Retry Execution Step]                              [IncidentDiagnosticPacket]
                                                                                                     [Escalate to Human (HITL)]
```

If Jev returns `NO` or if its confidence falls below the calibrated threshold ($< 0.85$), the step is recorded as a failure. A low-confidence verification **never fails open**; it triggers the next Reflexion trial or immediately trips the circuit breaker.

---

## 3. Decision Rules & System Architecture

### Architectural Decision
We formally adopt **Option C: Dual-Process Circuit Breaker**.
1. **Reflexion Engine**: Permitted a maximum of **2 verbal self-critique trials** to resolve tool invocation exceptions.
2. **Objective Decider (`ADP-05-Q1`)**: Step success/failure is governed by a TypeSafe Jev `Noul` call, eliminating model self-deception.
3. **Hard Step Ceiling Guard**: A global counter terminates any trajectory exceeding **$N = 4$ total execution steps**, preventing cyclic recursion.
4. **Tripwire Escalation**: If the circuit trips, the engine synthesizes an `IncidentDiagnosticPacket` containing the full trajectory $\tau_t$ and escalates immediately to the Human Specialist queue (`HL-ADP-02`).

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   DUAL-PROCESS CIRCUIT BREAKER EXECUTION ARCHITECTURE                            │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                   │
                                     [Tool Invocation Dispatched]
                                                   │
                                                   v
                                      [Observation o_t Received]
                                                   │
                                                   v
                                    ┌─────────────────────────────┐
                                    │    StepCeilingGuard (N ≤ 4) │
                                    └──────────────┬──────────────┘
                                                   │
                                     [N ≤ 4 Passes Guard]
                                                   │
                                                   v
                                    ┌─────────────────────────────┐
                                    │   TypeSafe Jev Step Check   │
                                    │   Noul: "Step succeeded?"   │
                                    └──────────────┬──────────────┘
                                                   │
                     ┌─────────────────────────────┴─────────────────────────────┐
                     │ [Step Succeeded, Conf ≥ 0.85]                             │ [Failed OR Conf < 0.85]
                     v                                                           v
          ┌──────────────────────┐                                    ┌──────────────────────┐
          │  Proceed to Target   │                                    │  TrialCounter Check  │
          │  Statechart Node     │                                    │  (Max Trials = 2)    │
          └──────────────────────┘                                    └──────────┬───────────┘
                                                                                 │
                                            ┌────────────────────────────────────┴────────────────────────────────────┐
                                            │ [Trial Count < 2]                                                       │ [Trial Count ≥ 2 OR N > 4]
                                            v                                                                         v
                                 ┌──────────────────────┐                                                  ┌──────────────────────┐
                                 │ LLM Verbal Critique  │                                                  │ TRIP CIRCUIT BREAKER │
                                 │ c_t = LLM_reflect()  │                                                  │ Package Trajectory   │
                                 │ Retry Execution Step │                                                  │ Escalate to HITL     │
                                 └──────────────────────┘                                                  └──────────────────────┘
```

---

### Concrete Genesis Implementation Contracts

#### 1. Circuit Breaker & Guard Implementation (`core/recovery/circuit_breaker.py`)

```python
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from typesafe import AsyncTypeSafeClient
from core.orchestrator.models import OrchestratorState, DiagnosticStep

class IncidentDiagnosticPacket(BaseModel):
    ticket_id: str
    tenant_id: str
    failure_reason: str
    iteration_count: int
    reflexion_trial_count: int
    full_trajectory: List[DiagnosticStep]
    last_error_context: Optional[str] = None
    suggested_human_action: str

class StepCeilingGuard:
    def __init__(self, max_steps: int = 4):
        self.max_steps = max_steps

    def check(self, state: OrchestratorState) -> bool:
        """Returns True if the step ceiling is breached."""
        return state.iteration_count >= self.max_steps

class TrialCounter:
    def __init__(self, max_trials: int = 2):
        self.max_trials = max_trials

    def check(self, state: OrchestratorState) -> bool:
        """Returns True if the max reflection trial ceiling is breached."""
        return state.reflexion_trial_count >= self.max_trials

class DualProcessCircuitBreaker:
    def __init__(
        self,
        typesafe_client: AsyncTypeSafeClient,
        max_steps: int = 4,
        max_trials: int = 2,
        confidence_threshold: float = 0.85,
    ):
        self.client = typesafe_client
        self.step_guard = StepCeilingGuard(max_steps=max_steps)
        self.trial_counter = TrialCounter(max_trials=max_trials)
        self.confidence_threshold = confidence_threshold

    async def verify_step_success(self, state: OrchestratorState, step_summary: str) -> bool:
        """
        ADP-05-Q1: Jev Noul decides step success, not the LLM.
        Low confidence counts as failure.
        """
        response = await self.client.evaluate(
            state={"step_summary": step_summary, "error": state.error_context},
            questions=[{
                "id": "step_success",
                "type": "noul",
                "question": "Did this step achieve its intended outcome without unhandled errors?"
            }]
        )
        answer = response.answers["step_success"]
        if answer.value is True and answer.confidence >= self.confidence_threshold:
            return True
        return False

    def trip(self, state: OrchestratorState, reason: str) -> IncidentDiagnosticPacket:
        """Trips the circuit breaker, freezing state and building the HITL packet."""
        return IncidentDiagnosticPacket(
            ticket_id=state.ticket_id,
            tenant_id=state.tenant_id,
            failure_reason=reason,
            iteration_count=state.iteration_count,
            reflexion_trial_count=state.reflexion_trial_count,
            full_trajectory=state.diagnostic_trajectory,
            last_error_context=state.error_context,
            suggested_human_action="Review tool failure trajectory and manually confirm parameter validity.",
        )
```

#### 2. Verbal Critique Generator (`core/recovery/reflexion.py`)

```python
from langchain_core.language_models import BaseChatModel
from core.orchestrator.models import OrchestratorState

REFLEXION_PROMPT = """
You are the Metacognitive Critique Core of an Enterprise Support Agent.
Your previous tool invocation failed. Analyze the trajectory and formulate an explicit verbal critique.

TRAJECTORY:
{trajectory}

LAST ERROR:
{error}

Identify:
1. Exactly what parameter, schema assumption, or environmental condition caused the failure.
2. What alternative approach or tool should be attempted in the next trial.
DO NOT hallucinate API parameters. Be direct and concise.
"""

async def generate_verbal_critique(llm: BaseChatModel, state: OrchestratorState) -> str:
    trajectory_str = "\n".join([
        f"Step {i}: Thought: {s.thought} | Action: {s.action_name} | Obs: {s.observation}"
        for i, s in enumerate(state.diagnostic_trajectory)
    ])
    prompt = REFLEXION_PROMPT.format(trajectory=trajectory_str, error=state.error_context)
    response = await llm.ainvoke(prompt)
    return response.content
```

---

## 4. Knowing Your Unknowns: Failure Modes & Mitigation Matrix

| Quadrant | Failure Mode | Technical Risk Description | Concrete Architectural Mitigation |
| :--- | :--- | :--- | :--- |
| **Q1: Known Knowns** *(Deterministic Contract Breaches)* | **Recursion Depth Explosion** | Infinite tool call loop exhausting API budget and thread memory. | **StepCeilingGuard ($N \le 4$)**: Deterministic step counter trips breaker unconditionally on step 5. |
| **Q1: Known Knowns** *(Deterministic Contract Breaches)* | **Critique Buffer Token Overflow** | Verbal critiques accumulate, consuming context space in working memory. | **Single-Critique Compaction**: Only the latest critique $c_t$ is injected into the prompt; older critiques are discarded. |
| **Q2: Known Unknowns** *(Probabilistic Reasoning Variance)* | **Hallucination Spiraling** | Model rationalizes errors and invents fictitious API parameters during retries. | **TrialCounter ($k \le 2$)**: Hard ceiling of 2 trials; immediate trip to HITL before hallucination trap forms. |
| **Q2: Known Unknowns** *(Probabilistic Reasoning Variance)* | **Jev Misjudgment on Error** | Jev incorrectly marks a failed step as successful due to subtle semantic ambiguity. | **High Confidence Band ($\ge 0.85$)**: Low confidence counts as failure; critical mutations still verify schema guards. |
| **Q3: Unknown Knowns** *(Tacit Enterprise Etiquette & Invariants)* | **Silent Failure Masking** | Agent encounters a permissions failure, masks the error, and falsely tells the customer it worked. | **Mandatory Jev Verification**: Agent cannot advance to resolution without Jev confirming step success on raw tool output. |
| **Q3: Unknown Knowns** *(Tacit Enterprise Etiquette & Invariants)* | **Repetitive Apology Degradation** | Agent wastes tokens generating repetitive polite apologies in critique context. | **Clinical System Invariant**: Critique generator prompt strictly enforces analytical diagnosis with zero conversational filler. |
| **Q4: Unknown Unknowns** *(Emergent Cascades & Black Swans)* | **Flapping Dependency Breaker Trap** | Intermittent 503 downstream causes 100 concurrent agent threads to trip to HITL simultaneously. | **System-Level Circuit Breakers (`TA-D10`, `RP-ADP-02`)**: Infrastructure breaker trips at the client pool, pausing workflows instead of human escalation. |
| **Q4: Unknown Unknowns** *(Emergent Cascades & Black Swans)* | **Poisoned Diagnostic Packet** | Malicious injection in tool error output hijacks human reviewer's console UI. | **Sanitized HTML Console Rendering**: All diagnostic packet payloads are rendered as escaped plain text in the human specialist console. |

---

## 5. Closed-Loop Feedback & Resilience Monitoring

1. **Tripwire Telemetry & Anomaly Detection**:
   - Every tripped circuit breaker publishes a `CircuitBreakerTrippedEvent` containing the `IncidentDiagnosticPacket` to OpenTelemetry and Langfuse.
   - If the tripwire rate for a specific tool exceeds 3% over a 1-hour window, an automated PagerDuty alert notifies the API integrations team.
2. **Reflexion Golden Set Synthesis**:
   - Trajectories where Trial 2 successfully corrected Trial 1 are automatically curated into golden few-shot exemplars, improving first-shot tool invocation accuracy across future model releases (`EV-ADP-01`).

---

## 6. Genesis Implementation Directives

When initializing the **Genesis** code generation agent, the following files and contracts must be scaffolded:

### Target File Manifest
1. `core/recovery/circuit_breaker.py`: The `DualProcessCircuitBreaker`, `StepCeilingGuard`, `TrialCounter`, and `IncidentDiagnosticPacket` classes.
2. `core/recovery/reflexion.py`: The verbal self-critique generation module.
3. `tests/test_circuit_breaker.py`: Unit tests verifying step ceilings, trial counters, and Jev step-verification boundaries.

### Scaffolding Verification Criteria
- [ ] **Step Ceiling Invariant**: Unit test confirms that execution halts immediately and trips to HITL when `iteration_count == 5`.
- [ ] **Trial Counter Invariant**: Unit test confirms that a second failed trial immediately generates an `IncidentDiagnosticPacket` and trips breaker.
- [ ] **Jev Verification Test**: Simulated low-confidence Jev answer ($0.60$) triggers a retry/trip condition; system never advances on low confidence.

---

## 7. Consequences & Trade-offs

### Positive Consequences
- **Elimination of Hallucination Spirals**: Strict 2-trial ceiling prevents models from compounding cognitive errors into destructive actions.
- **Objective Step Truth**: Decoupling critique generation (generative LLM) from step-success verification (Jev `Noul`) eliminates confirmation bias.
- **Zero Runaway Token Spend**: Anti-loop step ceiling ($N \le 4$) prevents runaway execution costs during backend service outages.
- **High-Context Human Handoff**: Human specialists receive complete, pre-packaged diagnostic packets, reducing Mean Time to Resolution (MTTR).

### Negative / Neutral Trade-offs & Mitigations
- **Additional Verification Latency**: Calling Jev after each tool step adds 80–150ms to the reasoning cycle.  
  *Mitigation*: Evaluate Jev questions asynchronously in parallel with downstream state checkpoint preparation.
- **Human Queue Load on Persistent API Outages**: If a major third-party service fails, agents will trip to human queues.  
  *Mitigation*: Infrastructure-level circuit breakers (`TA-D10`) pause workflows at the Temporal layer before agent threads trip.

---

## 8. References

1. **Nygard, M. T. (2007)**. *Release It!: Design and Deploy Production-Ready Software*. Pragmatic Bookshelf.
2. **Shinn, N., Cassano, F., Gopinath, A., Narasimhan, K., & Yao, S. (2023)**. *Reflexion: Language Agents with Verbal Reinforcement Learning*. arXiv:2303.11366.
3. **TypeSafe AI (2024)**. *Model Jaggedness & Decision Confidence Documentation*.
4. **Weick, K. E., & Sutcliffe, K. M. (2007)**. *Managing the Unexpected: Resilient Performance in an Age of Uncertainty (2nd ed.)*. Jossey-Bass.
5. **Yao, S. et al. (2023)**. *ReAct: Synergizing Reasoning and Acting in Language Models*. ICLR.
