# MS-ADP-01: Conversation & Case Model (Three-Tier Scope Hierarchy, Jev-Governed Case Linking & Resilient Dialogue Compaction)

- **Status**: Accepted & Confirmed
- **Date**: 2026-09-26 *(Amended: 2026-09-26 per MS-Q1 Jev Case Linking & MS-Q2 Jev Pinning/Unpinning Guards)*
- **Deciders**: Architecture Team, Lead Conversation & State Engineer, AI Orchestration Core
- **Component**: `[3] Memory & State` (`Component [ 3 ]`)
- **Reasoning Source**: `checkpoint.md` §7 · Diagram: `LLD - [3] Memory & State`
- **Decisions Covered**:
  - `MS-D1`: Conversation Scoping Hierarchy — Three-tier lifecycle (`Session` $\to$ `Conversation` $\to$ `Case`); automatic case resolution linking via Jev `Choice` with user confirmation below high confidence (`MS-Q1`, resolves `UA-D5`)
  - `MS-D2`: Dialogue Compaction & Context Preservation — Last $N$ turns verbatim + rolling recursive summary + immutable pinned items (rules + Jev `Noul` constraint detection with unpinning sweep, `MS-Q2`)
- **Related Architectural Decision Points**:
  - [`UA-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/01-user-application/UA-ADP-03-sessions-conversation-scope.md): Sessions & Conversation Scope *(Transport-level 30m/12h Session Bounds)*
  - [`ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/00-orchestration-core/ADP-03-context-engineering.md): Working Memory & Context Engineering *(25% Dialogue Slot Budget)*
  - [`ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/00-orchestration-core/ADP-05-decision-model-jev.md): Decision Model (Jev) *(Structured Categorical Selection)*
  - [`HL-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#hl-adp-04--action-approval--presentation): Action Approval & Presentation *(Case Confirmation Action Cards)*

---

## 1. Context & Problem Statement

Customer support interactions are inherently asynchronous and stateful. A single enterprise incident (e.g., investigating an unexpected invoice discrepancy `INV-9821` or debugging a multi-region database latency spike) rarely completes in a single browser session. Under `UA-ADP-03`, transport sessions expire strictly after $30$ minutes of inactivity or $12$ hours maximum lifetime. 

When a customer returns the following day or reconnects after an approval wait:
1. **The Context Cliff & Amnesia Dilemma**: If the agent treats each connection as an isolated thread, the customer must re-explain complex architectural context, triggering acute customer friction (Dixon et al., 2010). Conversely, if the agent naively appends all historical turns across weeks into a single flat buffer, the prompt blows past the allocated $25\%$ dialogue budget (`ADP-03`), triggering token truncation and LLM attention degradation.
2. **Compaction Loss of Negative Constraints ($KK2 / Q2$)**: Standard rolling summarizers compress older turns into concise prose. In doing so, summarization LLMs consistently drop critical negative constraints (e.g., *"Do NOT reboot the production cluster under any circumstances"*, *"We cannot modify the legacy VPC peering"*). If the agent subsequently recommends a reboot because the constraint was discarded during compaction, the operational blast radius is catastrophic.
3. **Case Fragmentation vs. Conflation**: An enterprise user may report a billing issue today and an API authentication issue tomorrow. If all conversations blindly attach to the user's latest open issue, billing context contaminates technical debugging. If every interaction forces a brand new ticket, customer issues fragment into duplicate Jira/Zendesk tickets.

### The Core Architectural Question
> **How do we structure the conversational lifecycle across transport sessions, threads, and underlying customer issues, while compressing long-running dialogue within a strict 25% token budget without ever dropping safety-critical operational constraints?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve this challenge, `MS-D1` and `MS-D2` establish two complementary structural pillars: **The Three-Tier Scoping Hierarchy** and **The Tripartite Compaction Substrate with Dynamic Pinning**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             THREE-TIER SCOPING HIERARCHY (MS-D1)                                 │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                  │
│  CASE: Canonical Business Incident (e.g., case_inv9821, lasts days/weeks until RESOLVED)         │
│  │                                                                                               │
│  ├── CONVERSATION 1: Initial web chat (conv_01) ──────────────┐                                  │
│  │   ├── Session A (T2 SSO, 10:00 - 10:30)                    │ Managed under                    │
│  │   └── Session B (Reconnected SSE, 11:00 - 11:45)           │ 25% Dialogue Slot Budget         │
│  │                                                            │ (Last N Verbatim + Rolling       │
│  └── CONVERSATION 2: Follow-up next day (conv_02) ───────────┘  Summary + Pinned Constraints)    │
│      └── Session C (T2 SSO, next day 09:00 - 09:30)                                              │
│                                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Pillar A: Three-Tier Scoping & Jev Categorical Case Linking

We formalize conversational entities into three nested tiers:
1. **Session ($\mathcal{S}$)**: The transport-level ephemeral connection envelope governed by `UA-ADP-03`. Bound to a validated token, expires at $30$m idle / $12$h max.
2. **Conversation ($\mathcal{C}$)**: A continuous, ordered sequence of dialogue turns between customer and agent. Outlives sessions; represents a specific chat thread.
3. **Case ($\mathcal{K}$)**: The overarching enterprise issue or business objective (e.g., refund authorization, ticket resolution). A Case spans multiple conversations over days or weeks until reaching terminal state (`RESOLVED` / `CLOSED`).

#### Jev-Governed Case Linking Algorithm (`MS-Q1`)
When a user initiates turn $t=1$ in a new conversation $\mathcal{C}_{\text{new}}$, the system inspects the set of currently active open cases for the authenticated principal:
$$\mathcal{K}_{\text{open}} = \{k_1, k_2, \dots, k_m\} \cup \{\text{NEW\_CASE}\}$$

We submit a masked state vector $\vec{x}_{\text{turn}}$ (`ADP-05-Q3`) to Jev via a structured `Choice` query:
$$\mathbb{P}(k_i \mid \vec{x}_{\text{turn}}) = \text{Jev.Choice}(\text{Question} = \text{"Which case does this inquiry pertain to?"}, \text{Options} = \mathcal{K}_{\text{open}})$$

Let $k^* = \arg\max_{k \in \mathcal{K}_{\text{open}}} \mathbb{P}(k \mid \vec{x}_{\text{turn}})$ and $\gamma^* = \text{Confidence}(k^*)$.

The linkage is governed by calibrated decision bounds (`ADP-05-Q2`):
$$\text{Action} = \begin{cases} 
\text{LinkDirectly}(k^*) & \text{if } \gamma^* \ge 0.90 \\
\text{PresentConfirmationCard}(k^*) & \text{if } 0.50 \le \gamma^* < 0.90 \\
\text{CreateNewCase}() & \text{if } \gamma^* < 0.50 \text{ or } k^* = \text{NEW\_CASE}
\end{cases}$$

If $\gamma^* \in [0.50, 0.90)$, the agent emits a lightweight action card: *"Are you following up on your invoice dispute (INV-9821), or is this a new issue?"* The user's explicit selection binds the conversation.

---

### Pillar B: Mathematical Formulation of Compaction & Constraint Pinning

Under `ADP-03`, the dialogue slot budget is strictly capped:
$$\text{Budget}(\text{Dialogue}) \le 0.25 \times \mathcal{B}_{\text{total}}$$
For a standard $128\text{k}$ context envelope, $\mathcal{B}_{\text{dialogue}} \approx 32,000$ tokens.

Naive FIFO turn dropping creates catastrophic amnesia. We formulate the dialogue buffer as a tripartite partitioned set:
$$\mathcal{D}_t = \mathcal{P}_t \cup \mathcal{S}_t \cup \mathcal{V}_t$$
Where:
- $\mathcal{V}_t = \{\tau_{n-N+1}, \dots, \tau_n\}$ represents the **Verbatim Window** of the most recent $N$ turns (empirically $N \in [6, 10]$).
- $\mathcal{S}_t$ is the **Rolling Recursive Summary** of all evicted turns $\tau_1 \dots \tau_{n-N}$.
- $\mathcal{P}_t$ is the set of **Immutable Pinned Items** (constraints, technical identifiers, explicit customer commitments).

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                               DIALOGUE COMPACTION ARCHITECTURE                                   │
├────────────────────────────────┬────────────────────────────────┬────────────────────────────────┤
│   1. Pinned Items (𝒫_t)        │   2. Rolling Summary (𝒮_t)     │   3. Verbatim Window (𝒱_t)     │
│   Immutable Constraint Set     │   Recursive Semantic Prose     │   High-Fidelity Recent Turns   │
│                                │                                │                                │
│   • "Do NOT reboot production" │   • "Customer reported 504     │   • Turn n-3 (User query)      │
│   • "Target VPC: vpc-9021a"    │     gateway timeout on billing │   • Turn n-2 (Agent action)    │
│   • Governed by Jev Noul checks│     endpoint at 10:14 UTC..."  │   • Turn n-1 (Tool result)     │
│   • Unpinned only on reversal  │   • Compacted every K turns    │   • Turn n   (Current turn)    │
└────────────────────────────────┴────────────────────────────────┴────────────────────────────────┘
```

#### Recursive Summary Evolution
When turn count $|\mathcal{V}_t| > N$, the oldest turn $\tau_{\text{evicted}}$ is removed from $\mathcal{V}_t$ and folded into the summary:
$$\mathcal{S}_{t} = \text{Summarize}(\mathcal{S}_{t-1}, \tau_{\text{evicted}})$$
The summarizer operates under strict prompt instructions to preserve chronology, issue causality, and entity IDs while dropping conversational pleasantries.

#### Dual-Gate Pinning & Dynamic Unpinning Protocol (`MS-Q2`)
Every incoming user utterance $u_i$ is evaluated for operational constraints via a hybrid regex and Jev decision gate:

1. **Gate 1: Deterministic Syntax Regex**:
   Matches explicit identifiers (`/[A-Z]{3,4}-[0-9]{4,8}/`) and strict modal negation patterns (`/(do not|never|must not|cannot|refuse to)\s+([a-z\s]+)/i`).
2. **Gate 2: Jev Constraint Verification**:
   For any detected candidate clause $c \in u_i$, Jev evaluates a parallel `Noul` query:
   $$\mathbb{P}(\text{is\_hard\_constraint} \mid c) = \text{Jev.Noul}(\text{"Is this statement an operational constraint or non-negotiable directive that must never be violated?"})$$
   If $\mathbb{P} \ge 0.85$, $c$ is permanently appended to $\mathcal{P}_t$.

3. **Dynamic Unpinning & Revocation Protocol (`UK4`)**:
   To prevent stale constraints from trapping the agent when the user changes their mind (*"Actually, go ahead and restart the node now"*), every new utterance $u_i$ is evaluated against all active pinned constraints $\{p_j \in \mathcal{P}_t\}$:
   $$\mathbb{P}(\text{withdraws\_pin}_j \mid u_i, p_j) = \text{Jev.Noul}(\text{f"Does the user's latest statement revoke, withdraw, or contradict the previous constraint: '{p_j.content}'?"})$$
   If $\mathbb{P} \ge 0.80$, pin $p_j$ is transitioned to `REVOKED` state and archived with an audit trail, immediately freeing the agent to act.

---

## 3. Decision Rules, Structural Invariants & Code Contracts

### System Structural Invariants
1. **Invariant 1 (Pin Immutability under Compaction)**: The rolling summarizer MUST NEVER consume, alter, or evict items in $\mathcal{P}_t$. Pinned items are evaluated in every turn assembly regardless of dialogue length.
2. **Invariant 2 (Token Budget Ceiling)**: The sum of tokens across $\text{Tokens}(\mathcal{P}_t) + \text{Tokens}(\mathcal{S}_t) + \text{Tokens}(\mathcal{V}_t)$ must satisfy:
   $$\text{Tokens}(\mathcal{D}_t) \le 0.25 \times \mathcal{B}_{\text{total}}$$
   If $\text{Tokens}(\mathcal{P}_t)$ exceeds $10\%$ of $\mathcal{B}_{\text{dialogue}}$ (over-accumulation of constraints), a P2 alert is raised, and the user is prompted to clarify priorities.
3. **Invariant 3 (Optimistic Concurrency & Lock Sequencing, $KK3$)**: Multiple browser tabs belonging to the same user writing to the same conversation thread MUST acquire a Redis distributed mutex with monotonic turn sequencing ($\text{seq}_{t+1} = \text{seq}_t + 1$). Conflicting concurrent turns reject the stale submit with HTTP `409 Conflict`.
4. **Invariant 4 (Tenancy Containment)**: Cases and Conversations are strictly keyed by `(tenant_id, principal_id)`. Cross-principal case access is forbidden at the storage layer.

---

### Python & Pydantic Data Contracts

```python
"""
Data contracts for Conversation, Case, and Dialogue Compaction.
Module: core/memory/dialogue.py
"""

from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class CaseStatus(str, Enum):
    OPEN = "open"
    AWAITING_CUSTOMER = "awaiting_customer"
    AWAITING_SPECIALIST = "awaiting_specialist"
    RESOLVED = "resolved"
    CLOSED = "closed"


class PinStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class PinnedConstraint(BaseModel):
    """An immutable operational constraint preserved across compaction."""
    pin_id: str = Field(..., description="Unique pin UUID")
    content: str = Field(..., description="Exact constraint text extracted from user turn")
    source_turn_id: str
    pinned_at: datetime = Field(default_factory=datetime.utcnow)
    confidence: float = Field(..., ge=0.0, le=1.0, description="Jev Noul confidence score")
    status: PinStatus = Field(default=PinStatus.ACTIVE)
    revocation_reason: Optional[str] = None
    revoked_at: Optional[datetime] = None


class Turn(BaseModel):
    """A single atomic dialogue turn."""
    turn_id: str
    sequence_num: int = Field(..., description="Monotonically increasing turn sequence")
    role: str = Field(..., regex="^(user|assistant|system|tool)$")
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    token_count: int


class DialogueBuffer(BaseModel):
    """The 25% dialogue slot representation assembled for orchestrator context."""
    conversation_id: str
    case_id: Optional[str] = None
    
    # Tripartite compaction partitions
    pinned_items: List[PinnedConstraint] = Field(default_factory=list)
    rolling_summary: Optional[str] = Field(None, description="Recursive prose summary of older turns")
    verbatim_turns: List[Turn] = Field(..., description="Last N turns preserved verbatim")
    
    total_tokens: int = Field(..., description="Aggregate token count across all three partitions")


class CaseLinkResult(BaseModel):
    """Output contract for Jev case-linking evaluation."""
    target_case_id: Optional[str] = None
    is_new_case: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    requires_user_confirmation: bool = Field(
        default=False, 
        description="True if confidence is between 0.50 and 0.90"
    )
    suggested_confirmation_prompt: Optional[str] = None
```

---

## 4. Failure Modes Matrix & Resilience Invariants

| Quadrant | Failure Scenario | Detection Mechanism | Systemic Mitigation & Recovery |
| :--- | :--- | :--- | :--- |
| **Q1: Known Knowns** | **Concurrent Tab Collision ($KK3$)**: Two browser tabs for the same customer submit turns simultaneously, causing race conditions in Postgres turn sequencing. | Optimistic concurrency check detects stale `sequence_num` collision. | Postgres row-level locking + Redis turn sequence mutex; stale turn receives HTTP `409 Conflict` with client auto-refresh. |
| **Q2: Known Unknowns** | **Summary Degradation / Hallucination ($KU1$)**: Over a 40-turn dispute, recursive summarization subtly alters numerical values (e.g., changes $\$1,240$ into $\$12,400$). | Discrepancy detector compares summary numbers against pinned entity allow-list. | Critical numbers and alphanumeric entities are automatically added to `pinned_items`; summarizer prompt forbids altering pinned entities. |
| **Q3: Unknown Knowns** | **Withdrawn Constraint Zombie Persistence ($UK4$)**: Customer previously stated *"Never reboot server"*, but later says *"Go ahead and restart now"*; the agent still refuses. | Jev Revocation Sweep fails to trigger on indirect colloquial phrasing. | Explicit Jev `Noul` revocation query run on every turn across all active pins; agent can ask clarifying question if ambiguity $\ge 0.50$. |
| **Q4: Unknown Unknowns** | **Adversarial Pin Inflation Exploit ($UU1$)**: Malicious user submits prompt injection generating $50$ artificial constraints, exhausting the dialogue token budget. | Budget guard detects `Tokens(PinnedItems) > 0.10 * Budget(Dialogue)`. | Hard ceiling of $10$ active pinned items; surplus triggers automatic HITL review and disables automated pinning for the session. |

---

## 5. Closed-Loop Feedback & Verification Signals

1. **Online Telemetry Alerts**:
   - `Dialogue_Compaction_Token_Overshoot`: Emitted if assembled dialogue slot exceeds $25\%$ of context ceiling.
   - `Jev_Case_Link_Disagreement_Rate`: Tracks how often users reject the suggested case confirmation card (alerts if $>15\%$, signaling intent classification drift).
   - `Stale_Pin_Revocation_Latency`: Emitted when an unpin operation succeeds, measuring the turn delta between constraint declaration and withdrawal.
2. **Weekly Quality Audit**:
   - Sample $100$ closed multi-session cases. Execute an offline evaluation comparing the original raw conversation turns against the final rolling summary. Calculate BERTScore and entity preservation recall to verify zero constraint amnesia.

---

## 6. Genesis Implementation Directives

1. **Code Locations**:
   - Implement data contracts and entities in `core/memory/dialogue.py`.
   - Implement the case linking and routing coordinator in `core/memory/case_manager.py`.
   - Implement the compaction engine and recursive summarizer in `core/memory/compaction.py`.
   - Implement the Jev pinning and revocation rules in `core/memory/pins.py`.
2. **Database & Persistence Integration**:
   - Persist cases, conversations, turns, and pinned items in Postgres (`cases`, `conversations`, `turns`, `conversation_pins`) with foreign key cascading.
   - Enforce row-level tenant security (`tenant_id = current_setting('app.current_tenant')`).
3. **Orchestrator Integration**:
   - Orchestration context assembler (`core/context/assembler.py`) calls `DialogueBuffer.assemble()` to populate the $25\%$ dialogue slot.

---

## 7. Consequences & Trade-offs

### Positive Consequences
- **Elimination of Cross-Session Amnesia**: Customers returning days later to resume complex billing or technical investigations experience seamless continuity.
- **Absolute Constraint Safety**: Moving operational constraints and negative instructions outside the lossy rolling summarizer guarantees the agent never violates safety invariants.
- **Bounded Token Expenditures**: Strict tripartite budgeting prevents dialogue context bloat, preserving $35\%$ of the window for high-precision RAG chunks (`ADP-03`).

### Negative Consequences & Trade-offs
- **Additional Jev API Calls per Turn**: Running parallel Jev `Noul` queries for pin detection and pin revocation adds $\approx 35\text{ms}$ to turn processing latency.
- **User Confirmation Overhead**: Ambiguous case linkages ($0.50 \le \gamma < 0.90$) introduce conversational friction by asking the customer to disambiguate their ticket.
- **Storage Amplification**: Storing raw turns, rolling summaries, and structured pins across multi-week cases increases database write volume in high-traffic enterprise deployments.

---

## 8. References & Cross-Disciplinary Grounding

1. **Stop Trying to Delight Your Customers**: Dixon, M., Toman, N., & DeLisi, R. (2010). *Harvard Business Review*. (Foundational research demonstrating that forcing customers to repeat context drives defection).
2. **Recursive Dialogue Summarization**: Wang, Z., et al. (2023). *A Survey on Dialogue Summarization in the Era of Large Language Models*. arXiv:2308.00404.
3. **Dual-Process Working Memory in Autonomous Agents**: Baddeley, A. (2000). *The Episodic Buffer: A New Component of Working Memory?* Trends in Cognitive Sciences.
4. **OWASP Top 10 for LLM Applications & Agentic AI (2025)**: Threat T1 — Memory Poisoning and Indirect Injection.
