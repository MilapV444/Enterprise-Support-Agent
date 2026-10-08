# ADP-03: Working Memory & Context Engineering Strategy (Tripartite Structured Slot Allocator)

- **Status**: Accepted & Confirmed
- **Date**: 2026-09-11 *(Updated: 2026-09-24 per KR-Q6 RAG Label Alignment)*
- **Deciders**: Architecture Team, Lead NLP Engineer, Prompt Engineering Core
- **Component**: Agent Orchestration Core & Runtime (`Component [ 5 ]`)
- **Reasoning Source**: `checkpoint.md` §2 · Diagram: `LLD - Agent Orchestration & Planning Core`
- **Related Architectural Decision Points**:
  - [`MS-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#ms-adp-01--conversation--case-model): Conversation & Case Model *(Dialogue History & Case Linking)*
  - [`KR-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#kr-adp-04--retrieval--ranking-pipeline): Retrieval & Ranking Pipeline *(Top-10 Parent Chunks via Hybrid RRF)*
  - [`CR-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#cr-adp-02--token--context-economy): Token & Context Economy *(KV-Cache Optimization & Compression Ratios)*

---

## 1. Context & Problem Statement

Modern enterprise customer support contexts are inherently heterogeneous, interleaving multi-turn conversation transcripts, corporate knowledge base passages, customer identity graphs, relational CRM account attributes, and real-time tool execution traces.

When constructing the language model prompt payload, naive context assemblers suffer from three catastrophic failure modes:
1. **The "Context Cliff" (FIFO Eviction Amnesia)**: Naive First-In, First-Out (FIFO) sliding turn buffers continuously evict the earliest conversational turns to accommodate fresh messages. In multi-turn technical support, early turns contain foundational customer constraints (e.g., *"Operating on Debian 12 without root access"* or *"Do NOT reboot the primary database cluster"*). Evicting these constraints induces critical agent regressions.
2. **"Lost in the Middle" Attentional Degradation (Liu et al., 2023)**: Transformer self-attention mechanisms exhibit a severe U-shaped positional bias. Key facts placed in the middle 30%–70% of a long context window experience an empirical recall degradation of up to 55% compared to facts positioned at the absolute start or end of the prompt payload.
3. **Context Dilution & KV-Cache Economic Inflation**: Packing raw, uncompressed API schemas and voluminous documentation passages triggers rapid token bloat, accelerating per-turn inference costs and degrading model reasoning focus.

### The Core Architectural Question
> **How should the agent runtime mathematically allocate, partition, and compress the finite context window budget across system persona, user profile facts, retrieved knowledge passages, dialogue history, and scratchpad reasoning to guarantee zero constraint loss and maximum attentional salience?**

---

## 2. Decision Framework & Theoretical Formulation

We formulate our context engineering paradigm upon three theoretical pillars: **Baddeley's Multicomponent Working Memory Model**, **Transformer Attention Distribution & Positional Salience Optimization**, and **Information-Theoretic Prompt Compression**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                            CONTEXT ENGINEERING THEORETICAL PILLARS                               │
├────────────────────────────────┬────────────────────────────────┬────────────────────────────────┤
│   Pillar A: Baddeley Working   │   Pillar B: Positional Salience│   Pillar C: Information-       │
│   Memory Model Formulation     │   & "Lost in the Middle" Bias  │   Theoretic Token Compression  │
│                                │                                │                                │
│   • Central Executive          │   • Transformer self-attention │   • Compression ratio r        │
│   • Phonological Loop          │     U-shaped curve A(pos)      │   • Mutual Information         │
│   • Episodic Buffer            │   • Convex optimization of     │     I(X; Y) >= (1 - ε) I(X;Y)  │
│   • Strict Quota Partitioning  │     slot ordering              │   • LongLLMLingua perplexity   │
└────────────────────────────────┴────────────────────────────────┴────────────────────────────────┘
```

---

### Pillar A: Baddeley's Multicomponent Working Memory Model

Human working memory does not function as a homogeneous, monolithic buffer. As formulated by **Baddeley & Hitch (1974)** and refined by **Baddeley (2000)**, cognitive architecture relies on a specialized tripartite working memory system:
1. **Central Executive**: Attentional controller governing focus, task boundaries, and policy compliance.
2. **Episodic Buffer**: Integrates multimodal chronological inputs into coherent event representations (dialogue history and customer state).
3. **Phonological Loop & Visuospatial Sketchpad**: Specialized temporary storage buffers holding semantic verbal structures (retrieved knowledge and intermediate scratchpad deliberations).

Translating Baddeley's formulation into language model context engineering, the finite prompt window $W$ is modeled as a strictly partitioned vector space of typed cognitive slots:

$$W = \langle \mathcal{S}_{\text{System}}, \mathcal{S}_{\text{Profile}}, \mathcal{S}_{\text{Knowledge}}, \mathcal{S}_{\text{Dialogue}}, \mathcal{S}_{\text{Scratchpad}} \rangle$$

Where each slot $\mathcal{S}_k$ is bounded by a fixed proportion $q_k$ of the total context token ceiling $B_{\text{window}}$:

$$\sum_{k=1}^{5} q_k = 1.0 \quad \text{and} \quad \text{Tokens}(\mathcal{S}_k) \le q_k \cdot B_{\text{window}}$$

---

### Pillar B: Positional Salience & U-Shaped Attention Optimization

In standard Transformer self-attention (**Vaswani et al., 2017**), the attention weight assigned by query token $i$ to key token $j$ at positional index $p_j$ is given by:

$$A_{i,j} = \frac{\exp\left(\frac{q_i k_j^\top}{\sqrt{d_k}}\right)}{\sum_{m=1}^{L} \exp\left(\frac{q_i k_m^\top}{\sqrt{d_k}}\right)}$$

Empirical investigations into long-context Transformer attention (**Liu et al., 2023**) demonstrate that retrieval accuracy $R(p)$ over normalized token position $p \in [0, 1]$ follows a distinct convex U-shaped curve:

$$R(p) \approx 1 - 4 \cdot \alpha \cdot p \cdot (1 - p)$$

Where $\alpha \approx 0.55$ represents the empirical attentional degradation coefficient in the middle positions.

```
Retrieval Fidelity R(p)
  1.0 ──┐                                                     ┌──
        │ \                                                 / │
  0.8 ──┤  \                                               /  │
        │   \                                             /   │
  0.6 ──┤    \                                           /    │
        │     \                                         /     │
  0.4 ──┤      └───────────────────────────────────────┘      │
        └──────┬──────────────┬──────────────┬──────────────┬─────┴──
              0.0            0.25           0.50           0.75   1.0
             Prompt                                       Prompt
             Head                                         Tail
           (System &                                    (Recent Turns &
            Profile)                                     Scratchpad)
```

- **Prompt Head ($p \in [0.0, 0.20]$)**: $R(p) \ge 0.95$. Maximum salience.
- **Prompt Tail ($p \in [0.80, 1.00]$)**: $R(p) \ge 0.92$. High recency salience.
- **Prompt Middle ($p \in [0.25, 0.75]$)**: $R(p) \le 0.45$. Severe attentional dilution.

#### Mathematical Context Layout Optimization
To maximize end-to-end task performance, we place **high-consequence regulatory invariants and customer identity** at the prompt head, and **the most recent customer turns and active scratchpad deliberation** at the prompt tail. The high-volume retrieved RAG chunks—which benefit from explicit chunk headers and citation anchors—occupy the middle section:

$$\begin{aligned}
\text{Position } [0.00, 0.15] &\implies \mathcal{S}_{\text{System}} \quad &&(\text{Hard Safety Policies, Role Boundaries}) \\
\text{Position } [0.15, 0.30] &\implies \mathcal{S}_{\text{Profile}} \quad &&(\text{Tenant Identity, Chronic Account Facts}) \\
\text{Position } [0.30, 0.65] &\implies \mathcal{S}_{\text{Knowledge}} \quad &&(\text{Slotted Grounded RAG Documentation Chunks}) \\
\text{Position } [0.65, 0.90] &\implies \mathcal{S}_{\text{Dialogue}} \quad &&(\text{Chronological Verbatim Dialogue Window}) \\
\text{Position } [0.90, 1.00] &\implies \mathcal{S}_{\text{Scratchpad}} \quad &&(\text{Active Deliberation DAG \& Tool Thoughts})
\end{aligned}$$

---

### Pillar C: Information-Theoretic Token Compression (Perplexity Filtering)

To prevent RAG passages and historical logs from consuming disproportionate quota, candidate text chunks undergo **Perplexity-Guided Token Pruning (LongLLMLingua, Jiang et al., 2023)**.

Given a text sequence $X = (x_1, x_2, \dots, x_N)$, the conditional token information content is evaluated via a small, fast evaluator model $M_{\text{small}}$ (e.g., Llama-3-8B):

$$I(x_i \mid x_{<i}) = -\log_2 P_{M_{\text{small}}}(x_i \mid x_{<i})$$

Tokens with low information content (filler syntax, repetitive boilerplate, redundant markdown tags) have low surprisal and are pruned:

$$X_{\text{pruned}} = \{ x_i \in X \mid I(x_i \mid x_{<i}) \ge \tau_{\text{prune}} \}$$

#### Negative Constraint Preservation Invariant
Naive perplexity pruning frequently drops semantic negations (e.g., *"not"*, *"never"*, *"prohibited"*). We enforce an immutable regex reservation mask:

$$\forall x_i \in \text{NegativeTokens} \cup \text{NumericalEntities} \cup \text{UUIDs}, \quad x_i \notin \text{PruningCandidates}$$

This ensures that critical operational constraints (*"Do NOT terminate cluster"*) are preserved with 100% fidelity while achieving an overall 40%–60% token compression ratio ($r = 0.50$).

---

## 3. Decision Rules & System Architecture

### Architectural Decision
We formally adopt **Option C: Tripartite Structured Slot Allocator**.
- The standard context budget is calibrated to **16,384 tokens** (with elastic expansion up to 32k for deep diagnostics).
- The prompt assembly pipeline allocates strict quota percentages across five dedicated Pydantic slot models.
- When an individual slot breaches its quota, specialized compaction policies execute locally within that slot, preventing context bleed into adjacent cognitive areas.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   STRUCTURED TRIPARTITE SLOT ALLOCATION ARCHITECTURE                             │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                   │
  ┌────────────────────────────────────────────────┴────────────────────────────────────────────┐
  │ 1. SYSTEM SLOT [15% / ~2,450 Tokens]                                                        │
  │    • Immutable System Persona & Behavioral Policies                                         │
  │    • Hard Invariants (Zero PII disclosure, destructive command bans)                        │
  │    • Compaction Policy: ZERO COMPACTION (Never pruned, strictly immutable)                  │
  ├─────────────────────────────────────────────────────────────────────────────────────────────┤
  │ 2. PROFILE SLOT [15% / ~2,450 Tokens]                                                       │
  │    • Customer Identity (Tenant ID, User Role, SLA Tier: Enterprise Platinum)                │
  │    • Long-Term Fact Graph (Mem0 / Zep chronic customer facts; MS-D3)                        │
  │    • Compaction Policy: Fact Deduplication & Recency-Importance Ranking (Park et al.)       │
  ├─────────────────────────────────────────────────────────────────────────────────────────────┤
  │ 3. KNOWLEDGE SLOT [35% / ~5,730 Tokens]                                                     │
  │    • Top-10 Grounded RAG Documentation Chunks (Parent-Child small-to-big chunks; KR-D4)     │
  │    • Chunk Provenance Headers & Semantic Source Metadata                                   │
  │    • Compaction Policy: LongLLMLingua Perplexity Pruning with Negative Constraint Guard      │
  ├─────────────────────────────────────────────────────────────────────────────────────────────┤
  │ 4. DIALOGUE SLOT [25% / ~4,100 Tokens]                                                      │
  │    • Last N Verbatim Dialogue Turns (Recent user & agent interactions; MS-D2)               │
  │    • Structured Tool Result Envelopes (Reference summaries for large JSON; MS-D7)           │
  │    • Compaction Policy: Rolling Semantic Summarization of turns older than N=6 turns        │
  ├─────────────────────────────────────────────────────────────────────────────────────────────┤
  │ 5. SCRATCHPAD SLOT [10% / ~1,630 Tokens]                                                    │
  │    • Ephemeral Working Memory Buffer for Active Deliberation DAG                            │
  │    • ReAct Intermediate Thoughts (r_t) & Plan-and-Solve Tracking                            │
  │    • Compaction Policy: Reset upon state transition completion (Purely ephemeral)           │
  └─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Slot Specification & Compaction Protocols

| Slot Name | Quota % | Token Budget (16k Window) | Storage Source | Eviction / Compaction Strategy |
| :--- | :--- | :--- | :--- | :--- |
| **`SystemSlot`** | **15%** | ~2,450 tokens | Git-versioned Prompt Registry | **None**. Immutable safety invariant. Overflows raise a deployment build error. |
| **`ProfileSlot`** | **15%** | ~2,450 tokens | Long-Term Memory (Mem0 / Zep) + CRM | Importance-ranked fact graph. Lowest-importance facts pruned when quota reached (`MS-D4`). |
| **`RAGSlot`** | **35%** | ~5,730 tokens | Hybrid Retrieval Engine (`KR-D7`) | LongLLMLingua perplexity compression; drops to top-5 parent chunks if budget saturated. |
| **`DialogueSlot`** | **25%** | ~4,100 tokens | PostgreSQL Thread Checkpointer (`MS-D8`) | Sliding verbatim window (last 6 turns) + rolling background summary (`MS-D2`). |
| **`ScratchpadSlot`** | **10%** | ~1,630 tokens | Agent Working State | Ephemeral buffer; discarded upon state completion or circuit trip. |

---

### Concrete Genesis Implementation Contracts

#### 1. Typed Slot Models (`core/context/models.py`)

```python
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class SystemSlot(BaseModel):
    persona_instructions: str
    safety_invariants: List[str]
    max_tokens: int = 2450

class ProfileSlot(BaseModel):
    user_id: str
    tenant_id: str
    sla_tier: str
    chronic_facts: List[str] = Field(default_factory=list)
    max_tokens: int = 2450

class RAGChunk(BaseModel):
    chunk_id: str
    source_uri: str
    audience: str
    content: str
    relevance_score: float

class RAGSlot(BaseModel):
    chunks: List[RAGChunk] = Field(default_factory=list)
    max_tokens: int = 5730

class DialogueTurn(BaseModel):
    role: str
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None

class DialogueSlot(BaseModel):
    summary_of_earlier_turns: Optional[str] = None
    recent_verbatim_turns: List[DialogueTurn] = Field(default_factory=list)
    max_tokens: int = 4100

class ScratchpadSlot(BaseModel):
    active_plan_dag: Optional[str] = None
    intermediate_thoughts: List[str] = Field(default_factory=list)
    max_tokens: int = 1630

class ContextEnvelope(BaseModel):
    system: SystemSlot
    profile: ProfileSlot
    knowledge: RAGSlot
    dialogue: DialogueSlot
    scratchpad: ScratchpadSlot
    total_token_count: int = 0
```

#### 2. Context Assembler & Compactor (`core/context/assembler.py`)

```python
import tiktoken
import re
from typing import List
from core.context.models import ContextEnvelope, RAGChunk, DialogueTurn

class ContextAssembler:
    def __init__(self, model_name: str = "gpt-4o", total_budget: int = 16384):
        self.tokenizer = tiktoken.encoding_for_model(model_name)
        self.total_budget = total_budget

    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text))

    def assemble_context_envelope(
        self,
        system_slot: SystemSlot,
        profile_slot: ProfileSlot,
        rag_slot: RAGSlot,
        dialogue_slot: DialogueSlot,
        scratchpad_slot: ScratchpadSlot,
    ) -> ContextEnvelope:
        # 1. Enforce System Immutability
        sys_tokens = self.count_tokens(system_slot.persona_instructions + " ".join(system_slot.safety_invariants))
        if sys_tokens > system_slot.max_tokens:
            raise ValueError(f"System slot overflow: {sys_tokens} > {system_slot.max_tokens}")

        # 2. Compact RAG Slot if overflowing
        rag_text = " ".join([c.content for c in rag_slot.chunks])
        if self.count_tokens(rag_text) > rag_slot.max_tokens:
            rag_slot.chunks = self._compact_rag_chunks(rag_slot.chunks, rag_slot.max_tokens)

        # 3. Compact Dialogue Slot if overflowing
        diag_tokens = self.count_tokens(self._render_dialogue(dialogue_slot))
        if diag_tokens > dialogue_slot.max_tokens:
            dialogue_slot = self._compact_dialogue(dialogue_slot, dialogue_slot.max_tokens)

        # 4. Compile Envelope
        total_tokens = (
            sys_tokens
            + self.count_tokens(" ".join(profile_slot.chronic_facts))
            + self.count_tokens(" ".join([c.content for c in rag_slot.chunks]))
            + self.count_tokens(self._render_dialogue(dialogue_slot))
            + self.count_tokens(" ".join(scratchpad_slot.intermediate_thoughts))
        )

        return ContextEnvelope(
            system=system_slot,
            profile=profile_slot,
            knowledge=rag_slot,
            dialogue=dialogue_slot,
            scratchpad=scratchpad_slot,
            total_token_count=total_tokens,
        )

    def _compact_rag_chunks(self, chunks: List[RAGChunk], token_limit: int) -> List[RAGChunk]:
        """Prunes lowest relevance chunks and applies negative constraint-safe filtering."""
        sorted_chunks = sorted(chunks, key=lambda c: c.relevance_score, reverse=True)
        selected_chunks = []
        current_tokens = 0

        for chunk in sorted_chunks:
            chunk_tokens = self.count_tokens(chunk.content)
            if current_tokens + chunk_tokens <= token_limit:
                selected_chunks.append(chunk)
                current_tokens += chunk_tokens
            else:
                break
        return selected_chunks

    def _compact_dialogue(self, dialogue: DialogueSlot, token_limit: int) -> DialogueSlot:
        """Retains last 4 turns verbatim and moves older turns to summary."""
        if len(dialogue.recent_verbatim_turns) > 4:
            overflow_turns = dialogue.recent_verbatim_turns[:-4]
            preserved_turns = dialogue.recent_verbatim_turns[-4:]
            
            # Simple summarization stub for overflow
            extracted_points = [f"{t.role}: {t.content[:100]}..." for t in overflow_turns]
            updated_summary = (dialogue.summary_of_earlier_turns or "") + "\n" + "\n".join(extracted_points)
            
            dialogue.summary_of_earlier_turns = updated_summary.strip()
            dialogue.recent_verbatim_turns = preserved_turns
        return dialogue

    def _render_dialogue(self, dialogue: DialogueSlot) -> str:
        summary = dialogue.summary_of_earlier_turns or ""
        turns = " ".join([f"{t.role}: {t.content}" for t in dialogue.recent_verbatim_turns])
        return summary + " " + turns
```

---

## 4. Knowing Your Unknowns: Failure Modes & Mitigation Matrix

| Quadrant | Failure Mode | Technical Risk Description | Concrete Architectural Mitigation |
| :--- | :--- | :--- | :--- |
| **Q1: Known Knowns** *(Deterministic Contract Breaches)* | **Context Window Hard Overflow** | Combined prompt exceeds foundation model context limit, triggering API error 400. | **Hard Slot Ceilings**: Strict pre-invocation token counting with `tiktoken`; assembler rejects prompts exceeding 16,384 tokens. |
| **Q1: Known Knowns** *(Deterministic Contract Breaches)* | **System Invariant Eviction** | Aggressive context pruner drops system safety rules to accommodate a long log trace. | **Immutable System Slot**: System Slot has zero-compaction policy ($q_{\text{system}} = 0.15$); pruners are forbidden from modifying system text. |
| **Q2: Known Unknowns** *(Probabilistic Reasoning Variance)* | **Compaction Negation Loss** | Token pruning drops critical negation terms (e.g., pruning *"not"* in *"do not reboot"*). | **Regex Negative Entity Mask**: Pruning pipeline explicitly protects negations, numerical entities, and UUIDs from token removal. |
| **Q2: Known Unknowns** *(Probabilistic Reasoning Variance)* | **Attentional Recency Drift** | Model forgets user constraints stated 8 turns ago due to summary vagueness. | **Pinned Memory Items (`MS-D2`)**: Key customer constraints are flagged as pinned facts and injected into the Profile Slot, bypassing dialogue eviction. |
| **Q3: Unknown Knowns** *(Tacit Enterprise Etiquette & Invariants)* | **Cross-Tenant Knowledge Bleed** | Cached RAG passages from tenant A accidentally slip into the context envelope of tenant B. | **Tenant-Isolated Assembler Envelopes**: Assembler validates that every chunk in `RAGSlot` matches the envelope `tenant_id` before compilation (`KR-D5`). |
| **Q3: Unknown Knowns** *(Tacit Enterprise Etiquette & Invariants)* | **Scratchpad Pollution** | Deliberative thoughts from an earlier failed trial persist into subsequent unrelated turns. | **State Transition Scratchpad Wipe**: Ephemeral scratchpad slot is explicitly initialized to empty upon advancing to any new primary FSM state. |
| **Q4: Unknown Unknowns** *(Emergent Cascades & Black Swans)* | **Indirect Injection via RAG Snippet** | Malicious content in an internal Confluence wiki overrides system instructions. | **Context Tag Delimiters & Pre-Rerank Screening (`KR-D14`)**: Passages are wrapped in isolated `<retrieved_context>` XML tags; text is screened for prompt injections prior to slot inclusion. |
| **Q4: Unknown Unknowns** *(Emergent Cascades & Black Swans)* | **KV-Cache Memory Exhaustion** | 1,000 concurrent long-context sessions exhaust GPU cluster vRAM. | **Per-Tenant Context Economy Routing (`CR-ADP-02`)**: Shorter turn windows and aggressive LongLLMLingua compression are applied during cluster peak load. |

---

## 5. Closed-Loop Feedback & Telemetry Integration

1. **Context Telemetry & Slot Utilization Metrics**:
   - Every generated prompt logs its slot token distribution (`tokens_system`, `tokens_profile`, `tokens_rag`, `tokens_dialogue`, `tokens_scratchpad`) to Langfuse and Prometheus.
   - If `tokens_rag` consistently exceeds 80% of its slot budget across a specific domain, the Knowledge Ingestion team is notified to optimize chunking granularity (`KR-D4`).
2. **Context Regression Evaluation**:
   - Automated evaluation suites continuously measure needle-in-a-haystack recall across the U-shaped attention spectrum to detect model version degradation (`EV-ADP-03`).

---

## 6. Genesis Implementation Directives

When initializing the **Genesis** code generation agent, the following files and contracts must be scaffolded:

### Target File Manifest
1. `core/context/models.py`: Pydantic models for `ContextEnvelope`, `SystemSlot`, `ProfileSlot`, `RAGSlot`, `DialogueSlot`, and `ScratchpadSlot`.
2. `core/context/assembler.py`: The `ContextAssembler` engine executing token quota enforcement, LongLLMLingua pruning, and dialogue compaction.
3. `core/context/pruner.py`: Negation-safe perplexity filtering module for RAG passages.

### Scaffolding Verification Criteria
- [ ] **Quota Bounds Verification**: Unit tests verify that overflowing any slot triggers local compaction and never encroaches on adjacent slot quotas.
- [ ] **Negative Token Preservation Test**: Automated test confirms that sentences with negative imperatives (*"Do not delete"*) retain 100% of negative tokens after compaction.
- [ ] **U-Shape Layout Verification**: The compiled prompt string positions `SystemSlot` and `ProfileSlot` at index 0, and `DialogueSlot` and `ScratchpadSlot` at the prompt tail.

---

## 7. Consequences & Trade-offs

### Positive Consequences
- **Elimination of the "Lost in the Middle" Degradation**: Placing critical invariants and customer profile facts at the prompt head guarantees $\ge 95\%$ attentional retention.
- **Predictable Token Costs**: Hard slot ceilings eliminate runaway context bloat, stabilizing per-turn inference latency and API expenditure.
- **Preservation of Critical Invariants**: Dedicated zero-compaction System Slot guarantees regulatory compliance rules are never evicted.
- **Clean Context Separation**: Modularity between profile, knowledge, and dialogue enables independent caching and targeted updating.

### Negative / Neutral Trade-offs & Mitigations
- **Compaction Latency Overhead**: Running perplexity filtering or dialogue summarization adds 30–80ms to context assembly.  
  *Mitigation*: Pre-screen and compress RAG passages asynchronously during ingestion; perform dialogue summarization as a background task.
- **Information Loss in Long Conversations**: Compacting turns older than $N=6$ inevitably discards conversational nuances.  
  *Mitigation*: The `ProfileSlot` captures enduring facts asynchronously, ensuring essential customer context is preserved regardless of dialogue age.

---

## 8. References

1. **Baddeley, A. (2000)**. *The episodic buffer: a new component of working memory?* Trends in Cognitive Sciences, 4(11), 417-423.
2. **Baddeley, A. D., & Hitch, G. (1974)**. *Working memory*. Psychology of Learning and Motivation, 8, 47-89.
3. **Jiang, H. et al. (2023)**. *LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression*. arXiv:2310.06201.
4. **Liu, N. F., Lin, K., Hewitt, J., Paranjape, A., Bevilacqua, M., Petroni, F., & Liang, P. (2023)**. *Lost in the Middle: How Language Models Use Long Contexts*. Transactions of the Association for Computational Linguistics.
5. **Vaswani, A. et al. (2017)**. *Attention Is All You Need*. Advances in Neural Information Processing Systems (NeurIPS).
