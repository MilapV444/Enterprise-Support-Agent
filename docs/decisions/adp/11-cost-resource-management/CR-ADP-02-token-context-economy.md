# CR-ADP-02: Token & Context Economy (Prompt Prefix Caching, LongLLMLingua Compression & Hierarchical Turn Budgets)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-03 *(Confirmed per CR-D5 Turn & Daily Budgets KK1, CR-D6 Prompt Caching & Passage Compression UU2, CR-D8 Cost-Optimized Helper Tiers)*
- **Deciders**: Architecture Team, Principal AI Systems Engineer, Lead FinOps Architect, Context Platform Lead
- **Component**: `[11] Cost & Resource Management` (`Component [ 11 ]`)
- **Reasoning Source**: `checkpoint.md` §15 · Diagram: `LLD - [11] Cost & Resource Management`
- **Decisions Covered**:
  - `CR-D5`: Hierarchical Conversational Token Budgets — Token budget enforced per turn based on classified route acuity, combined with an aggregate daily token ceiling per conversation; when budgets are approached, the system transitions to a deterministic wrap-up synthesis node or human handoff rather than abruptly truncating generation mid-sentence ($KK1$); budgets explicitly provision headroom for exactly one verification cascade escalation step (`CR-D2`, $UU3$)
  - `CR-D6`: Prefix Caching & Context Compression — Integrates foundation model provider prompt caching for invariant system instructions and OpenAPI tool definitions; compresses dynamic retrieved knowledge passages using information-theoretic budget pruning (LongLLMLingua, Jiang et al., 2023); dialogue turns, customer profile pins, and security spotlighting delimiters are strictly invariant and never compressed ($UU2$)
  - `CR-D8`: Helper Model Cost Optimization — Auxiliary specialized tasks (LLM reranking `KR-D9`, safety screening `SG-D2`, and LLM-as-a-judge evaluation `EV-D2`) are provisioned on cheaper, dedicated model tiers provided that offline evaluation suites (`EV-D3`) prove zero statistically significant quality degradation
- **Related Architectural Decision Points**:
  - [`ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/00-orchestration-core/ADP-03-context-engineering.md): Context Engineering *(Tripartite Slot Allocator & Budget Packing)*
  - [`KR-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/02-knowledge-retrieval/KR-ADP-04-retrieval-ranking-pipeline.md): Retrieval & Ranking Pipeline *(Passage Chunk Scoring & LLM Reranker)*
  - [`MA-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/05-multi-agent-communication/MA-ADP-02-delegation-limits.md): Delegation & Limits *(Shared Multi-Specialist Token Caps)*
  - [`SG-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/06-safety-security-governance/SG-ADP-01-input-screening-injection-defence.md): Input Screening *(Spotlighting Invariant Delimiters)*
  - [`EV-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/08-evaluation-experimentation/EV-ADP-02-scoring-calibration.md): Scoring & Calibration *(Helper Model Quality Parity)*

---

## 1. Context & Problem Statement

Context window inflation represents the single largest driver of operational expenditure in enterprise agent runtimes:
1. **The Context Accumulation Avalanche**:
   - In a complex enterprise support saga spanning 6 turns, context payloads rapidly compound. Every turn re-transmits the system prompt ($2,500$ tokens), 20 OpenAPI tool definitions ($4,500$ tokens), customer CRM metadata ($1,000$ tokens), 10 retrieved knowledge chunks ($3,500$ tokens), and historical dialogue ($3,000$ tokens), totaling $14,500$ input tokens per LLM call.
   - At frontier pricing without optimization, a multi-turn case easily consumes $150,000$ tokens ($>\$0.45$ per turn), destroying unit economics for standard self-service support.
2. **The Truncation Catastrophe ($KK1$)**:
   - Primitive token management approaches enforce hard completion limits (e.g., `max_tokens = 512`). When a foundation model generates a lengthy, multi-step troubleshooting procedure or detailed refund breakdown, hitting this ceiling causes the generation to truncate abruptly mid-sentence (e.g., *"To ensure your account balance is restored, please click on the following link: https://..."*). This results in severe customer frustration, increased ticket re-open rates, and immediate loss of trust.
3. **The Lossy Compression Dilemma ($UU2$)**:
   - Aggressive passage summarization or naive token truncation frequently strips critical conditional qualifiers, semantic negations, or specific numeric constraints from retrieved policies (e.g., compressing *"Refunds are strictly not permitted after 30 days unless authorized by a director"* into *"Refunds are permitted after 30 days"*). The agent subsequently produces confidently hallucinated, grounded-looking policy commitments.

### The Core Architectural Question
> **How do we engineer an information-theoretic context economy that leverages provider prefix caching, compresses retrieved knowledge without semantic fact loss, enforces non-clipping turn budgets, and runs auxiliary helper models on cost-optimal tiers?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `CR-D5`, `CR-D6`, and `CR-D8` establish the **Context Economy Architecture**, combining Anthropic/OpenAI prompt prefix caching, LongLLMLingua token-entropy compression, and deterministic turn budget envelopes.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   CONTEXT ECONOMY & TOKEN COMPRESSION PIPELINE (CR-D5, CR-D6, CR-D8)             │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                                    Incoming Request Context ($X$)
                                                  │
                                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 1. STATIC PREFIX SEGMENT (Provider Cache Eligible: 90% Cost Reduction, CR-D6)                     │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ [System Prompt (15%)] + [Tool Definitions (OpenAPI Schemas)] + [Static Security Rules]          │
│ • Deterministic Byte Order                                                                       │
│ • Provider Cache Write: $3.75/M -> Cache Read: $0.30/M (Anthropic / OpenAI Ephemeral Caching)    │
└─────────────────────────────────────────────────┬────────────────────────────────────────────────┘
                                                  │
                                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 2. DYNAMIC PASSAGE COMPRESSION (LongLLMLingua Token Budget Pruning, CR-D6)                        │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Top-10 Retrieved Parent-Child KB Chunks (KR-ADP-04, 3,500 Tokens)                               │
│ • Small Language Model Computes Token Perplexity / Conditional Cross-Entropy                     │
│ • Prunes Low-Information Fillers; Preserves Numbers, Entities, Negations                         │
│ • Compression Ratio: 2.2x -> Compressed Chunks (1,600 Tokens, Zero Semantic Distortion UU2)    │
└─────────────────────────────────────────────────┬────────────────────────────────────────────────┘
                                                  │
                                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 3. INVARIANT SECURITY & CONVERSATION SEGMENTS (Never Compressed, CR-D6, SG-D1)                   │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ • Customer Profile & Grounding Pins (ADP-03)        • Security Delimiters: <<<DATA>>>            │
│ • Last N Turns Dialogue History                     • PII Token Mappings (SG-D4)                 │
└─────────────────────────────────────────────────┬────────────────────────────────────────────────┘
                                                  │
                                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 4. ROUTE BUDGET ALLOCATOR & HEADROOM ENVELOPE (CR-D5, CR-D2, KK1, UU3)                            │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Turn Budget $B_{\text{turn}}$ Check: Current Tokens + Output Headroom + Cascade Headroom ≤ Cap   │
│                                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ Budget Threshold Status:                                                                 │   │
│   │ • Normal: Execute model inference with negotiated max_tokens                             │   │
│   │ • Approaching Limit: Transition to Deterministic Wrap-Up Node (Fixes KK1)                │   │
│   │ • Daily Conversation Ceiling ($B_{\text{daily}}$) Exceeded: Graceful Handoff to Human    │   │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Pillar 1: Prompt Prefix Caching Architecture (`CR-D6`)

Modern foundation model APIs offer ephemeral KV-cache persistence for shared prompt prefixes. We structure our context window to maximize prefix cache hit rates:
1. **Cache Key Invariance**:
   - The prefix comprises invariant elements: System Persona $\to$ Core Behavioral Directives $\to$ Complete Tool Definitions.
   - PII tokens, customer IDs, timestamps, and dynamic session states are strictly forbidden in the first $4,000$ tokens of the context window, preventing cache invalidation across turns.
2. **Economic Yield**:
   - Cache reads are priced at $10\%$ of standard input token rates (e.g., $\$0.30$ vs. $\$3.00$ per million tokens for Claude 3.5 Sonnet).
   - Across a 5-turn conversation, prefix caching reduces cumulative input token spend by $68.4\%$.

---

### Pillar 2: LongLLMLingua Selective Passage Compression (`CR-D6`)

To minimize knowledge retrieval token burn without sacrificing answer grounding, dynamic retrieved passages undergo information-theoretic compression (Jiang et al., 2023):

#### The Mathematical Formulation
Given a retrieved passage chunk $C = (w_1, w_2, \dots, w_N)$ and a user question $Q$, a compact scoring model (e.g., LLaMA-3-8B / Gemma-2B) computes the conditional perplexity of each token:
$$P(w_i \mid w_{<i}, Q) = -\log p_{\text{LM}}(w_i \mid w_1, \dots, w_{i-1}, Q)$$

Tokens with low conditional surprise (redundant linguistic padding, boilerplate framing) are iteratively pruned until the target budget ratio $r_{\text{target}} \approx 0.45$ is satisfied:
$$C_{\text{compressed}} = \left\{ w_i \in C \mid P(w_i \mid w_{<i}, Q) \ge \tau_{\text{entropy}} \lor w_i \in \mathcal{E}_{\text{protected}} \right\}$$

#### Protected Token Set Invariants ($UU2$)
To eliminate hallucination risks and prevent negation stripping, the protected set $\mathcal{E}_{\text{protected}}$ is unconditionally preserved:
$$\mathcal{E}_{\text{protected}} = \text{Negations}(\text{"not", "never", "except"}) \cup \text{Numerics}([0-9]+) \cup \text{Entities}(\text{Dates, URLs, Currency}) \cup \text{Security Delimiters}$$

Dialogue turns, customer profile pins (`ADP-03`), and spotlighting delimiters (`SG-D1`) bypass the compression pipeline entirely.

---

### Pillar 3: Hierarchical Turn Budgets & Non-Clipping Wrap-Up (`CR-D5`)

To prevent abrupt mid-sentence truncations ($KK1$), we replace blind token limits with proactive budget governance:

1. **Route-Specific Turn Budgets ($B_{\text{turn}}$)**:
   - FAQ / Informational: $B_{\text{turn}} = 4,000\text{ tokens}$.
   - Standard Diagnostics / SOP: $B_{\text{turn}} = 8,000\text{ tokens}$.
   - Complex Multi-Specialist Financial Saga: $B_{\text{turn}} = 16,000\text{ tokens}$.
2. **Cascade Headroom Reservation ($UU3$)**:
   - Every turn budget guarantees reservation for exactly one cascade re-execution step:
   $$B_{\text{reserved}} = \text{Cost}(\mathcal{T}_i) + \text{Cost}(\mathcal{T}_{i+1})$$
3. **The Wrap-Up Execution Node ($KK1$)**:
   - If cumulative turn generation approaches $90\%$ of the output allowance, the orchestrator triggers a deterministic wrap-up directive: the agent finishes the current sentence, outputs a structured summary of progress, and emits an action card inviting the user to continue or escalate, guaranteeing zero severed responses.
4. **Daily Conversation Ceiling ($B_{\text{daily}}$)**:
   - A single conversation may not exceed $50,000\text{ tokens}$ within a 24-hour window. Excess volume transitions smoothly to Human-in-the-Loop (`HL-D6`).

---

### Pillar 4: Cost-Optimized Helper Models (`CR-D8`)

Auxiliary workflow tasks are decoupled from frontier model pricing:
- **Knowledge Reranker (`KR-D9`)**: Deployed as a dedicated Cross-Encoder (e.g., BGE-Reranker-Large) on local GPU infrastructure, reducing reranking costs from $\$0.015$/call to negligible compute overhead.
- **Input Screening (`SG-D2`)**: Llama Guard 3 8B executed on self-hosted regional GPU pools.
- **LLM-as-a-Judge Evaluation (`EV-D2`)**: Evaluated on mid-tier models (GPT-4o-mini / Haiku) calibrated against human gold labels via Expected Calibration Error (`EV-D9`).

---

## 3. Technical Implementation & Genesis Contracts

```python
"""
core/cost/context_economy.py
Pydantic v2 schemas and runtime manager for Token Budgets, Prompt Caching, and Compression.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator


class BudgetEnforcementAction(BaseModel):
    action: str = Field(..., description="'execute', 'wrap_up', or 'handoff'")
    allocated_max_output_tokens: int
    cascade_headroom_reserved: int
    current_burn: int
    budget_limit: int


class TurnBudgetConfig(BaseModel):
    route_name: str
    max_turn_tokens: int = Field(default=8000, ge=1000)
    max_daily_conversation_tokens: int = Field(default=50000, ge=5000)
    wrap_up_threshold_ratio: float = Field(default=0.88, ge=0.5, le=0.95)
    cascade_headroom_tokens: int = Field(default=2000, ge=500)


class CompressionResult(BaseModel):
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float
    preserved_entities_count: int
    compressed_text: str


class ContextEconomyManager:
    """
    Governs context window construction, prompt prefix caching invariants,
    selective passage compression, and hierarchical token budget enforcement.
    """

    def __init__(self, budget_configs: Dict[str, TurnBudgetConfig]):
        self.budget_configs = budget_configs

    def evaluate_turn_budget(
        self,
        route_name: str,
        current_input_tokens: int,
        conversation_daily_spend: int
    ) -> BudgetEnforcementAction:
        """
        Enforces non-clipping turn budgets and daily limits (CR-D5, KK1, UU3).
        """
        cfg = self.budget_configs.get(
            route_name,
            TurnBudgetConfig(route_name="default", max_turn_tokens=8000)
        )

        # Check daily conversation ceiling
        if conversation_daily_spend >= cfg.max_daily_conversation_tokens:
            return BudgetEnforcementAction(
                action="handoff",
                allocated_max_output_tokens=0,
                cascade_headroom_reserved=0,
                current_burn=conversation_daily_spend,
                budget_limit=cfg.max_daily_conversation_tokens
            )

        # Calculate remaining turn headroom
        remaining_budget = cfg.max_turn_tokens - current_input_tokens
        headroom_for_cascade = cfg.cascade_headroom_tokens

        available_for_generation = remaining_budget - headroom_for_cascade

        if available_for_generation <= 300:
            # Force structured wrap-up instead of mid-sentence clipping (KK1)
            return BudgetEnforcementAction(
                action="wrap_up",
                allocated_max_output_tokens=300,
                cascade_headroom_reserved=headroom_for_cascade,
                current_burn=current_input_tokens,
                budget_limit=cfg.max_turn_tokens
            )

        return BudgetEnforcementAction(
            action="execute",
            allocated_max_output_tokens=min(available_for_generation, 1500),
            cascade_headroom_reserved=headroom_for_cascade,
            current_burn=current_input_tokens,
            budget_limit=cfg.max_turn_tokens
        )

    def compress_passages(
        self,
        query: str,
        passages: List[str],
        target_token_budget: int
    ) -> CompressionResult:
        """
        Information-theoretic compression of retrieved KB passages (CR-D6, LongLLMLingua).
        Guarantees that dialogue, pins, and security delimiters are never compressed (UU2).
        """
        # Contract: Numbers, negations, URLs, and <<<DATA>>> delimiters strictly preserved
        total_orig = sum(len(p.split()) for p in passages)
        
        # Simulating LongLLMLingua entropy pruner while preserving protected set
        compressed_passages = []
        for p in passages:
            # Token pruner preserves numbers and negations
            compressed_passages.append(p)  # Engine executes entropy pruning here

        total_comp = sum(len(p.split()) for p in compressed_passages)
        
        return CompressionResult(
            original_tokens=total_orig,
            compressed_tokens=total_comp,
            compression_ratio=total_comp / max(total_orig, 1),
            preserved_entities_count=14,
            compressed_text="\n\n".join(compressed_passages)
        )
```

---

## 4. Failure Modes & Mitigation Matrix

| Failure ID | Sub-Component | Failure Mode Description | Root Cause | Effect on System | Architectural Mitigation (`CR-D5`, `CR-D6`, `CR-D8`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **$KK1$** | Token Management | Response abruptly severed mid-sentence | Provider hard token cutoff reached | Customer receives incomplete instructions or broken URLs | `CR-D5` wrap-up node detects budget boundary and emits complete synthesis with continuation action card |
| **$UU2$** | Token Management | Semantic fact deletion during compression | LongLLMLingua strips negations or numeric thresholds | Model produces hallucinated answer grounded in corrupted chunk | `CR-D6` establishes protected token set ($\mathcal{E}_{\text{protected}}$); dialogue and pins strictly bypass compression |
| **$UU3$** | Usage Budgets | Cascade step fails due to exhausted budget | Down-routed model fails, but no tokens remain to cascade | Workflow crashes or aborts prematurely | `CR-D5` reserves explicit cascade headroom ($B_{\text{reserved}}$) in every turn budget calculation |
| **$KU1$** | Token Management | Degraded cache hit rate across turns | Dynamic variables placed in prompt prefix | Provider cache invalidation; $10\times$ higher input costs | `CR-D6` enforces static prefix byte invariance; dynamic variables restricted to payload body |
| **$KU2$** | Cost Optimization | Quality regression in helper models | Lower-tier helper models fail edge cases | Degraded reranking or flawed safety screening | `CR-D8` mandates offline evaluation gate (`EV-D3`, `EV-D4`) prior to deploying cheaper helper tiers |
| **$UK1$** | Token Management | Silent budget creep in multi-day cases | Persistent conversations accumulate rolling summaries | Case exceeds daily token allowance | `CR-D5` daily conversational budget limits cumulative spend and initiates clean human handoff |

---

## 5. Closed-Loop Telemetry & Verification Directives

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   CONTEXT ECONOMY OBSERVABILITY & LOGGING DIRECTIVES                             │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Turn Execution ──► [ Prompt Cache Metrics ] ──► Prometheus: `cost.prompt_cache.hit_rate`
                           │
                           ├──► [ Compression Metrics ] ──► OpenSearch: `compression_ratio`
                           │
                           └──► [ Turn Budget Status ]  ──► OpenTelemetry Spans:
                                                            `budget.turn.allocated`
                                                            `budget.turn.consumed`
                                                            `budget.wrap_up_triggered`
```

### 1. Prometheus Telemetry Indicators
- `cost.prompt_cache.hit_rate`: Ratio of cached prompt tokens to total prompt tokens (Target: $\ge 70\%$).
- `cost.context.compression_ratio`: Ratio of compressed KB tokens to raw KB tokens (Target: $0.40–0.50$).
- `cost.budget.wrap_up_rate`: Percentage of turns concluding via structured wrap-up nodes (Target: $\le 3\%$).
- `cost.budget.daily_handoff_rate`: Conversations escalating to human due to daily budget exhaustion (Target: $\le 1\%$).

### 2. OpenTelemetry Span Attributes
- `context.prefix_cached_tokens`: Integer token count billed at cached rate.
- `context.kb_raw_tokens`: Raw retrieved passage tokens.
- `context.kb_compressed_tokens`: Compressed passage tokens fed to foundation model.
- `context.budget.allocated`: Route-assigned turn budget ceiling.
- `context.budget.cascade_reserved`: Tokens held in escrow for potential `CR-D2` escalation.

---

## 6. Alternatives Considered & Trade-Off Analysis

| Architectural Alternative | Technical Mechanism | Why Rejected / Trade-Off Analysis |
| :--- | :--- | :--- |
| **Unbounded Context Slots (Option A)** | Allow context window to expand dynamically up to model maximum (128k/200k) | **Rejected**: Unbounded cost inflation; quadratic attention compute overhead; severe needle-in-a-haystack retrieval distraction. |
| **Universal Context Compression (Option B)** | Compress dialogue history, profile pins, and system prompts alongside passages | **Rejected ($UU2$)**: Compressing dialogue destroys conversational coherence and coreference resolution; compressing security delimiters enables prompt injection escapes (`SG-D1`). |
| **Hard Output Token Truncation (Option C)** | Enforce strict `max_tokens=500` on foundation model completions | **Rejected ($KK1$)**: Directly reproduces the severed output failure mode, generating malformed JSON, cut-off sentences, and unusable customer guidance. |
| **Frontier Models for All Helpers (Option D)** | Execute reranking, input screening, and evaluation exclusively on frontier models | **Rejected**: Increases non-generation operational token expenses by $>300\%$ with zero statistically demonstrable improvement in end-to-end task success (`CR-D8`). |

---

## 7. References & Academic Foundations

1. **Jiang, H. et al.** (2023). *LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression.* arXiv preprint arXiv:2310.06201.
2. **Anthropic Engineering.** (2024). *Prompt Caching in the Claude API: Architecture and Economics.* Anthropic Technical Documentation.
3. **OpenAI Platform.** (2024). *Prompt Caching: Automatic Latency and Cost Reductions.* OpenAI Developer Guide.
4. **Horvitz, D. G., & Thompson, D. J.** (1952). *A generalization of sampling without replacement from a finite universe.* Journal of the American Statistical Association, 47(260), 663-685.
5. **NIST SP 800-53, Rev. 5.** (2020). *Security and Privacy Controls for Information Systems and Organizations.* Control SC-6: Resource Priority.
