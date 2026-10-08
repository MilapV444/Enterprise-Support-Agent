# KR-ADP-01: Knowledge Sources, Authority & Content Labelling (Probabilistic Source Tiers, Audience Segregation & Provenance Tagging)

- **Status**: Accepted & Confirmed
- **Date**: 2026-09-24 *(Amended: 2026-09-24 per KR-Q1, KR-Q4, KR-Q7 Resolutions)*
- **Deciders**: Architecture Team, Lead Knowledge Systems Engineer, Data Governance & Security Core
- **Component**: `[2] Knowledge & Retrieval` (`Component [ 2 ]`)
- **Reasoning Source**: `checkpoint.md` §6 · Diagram: `LLD - [2] Knowledge & Retrieval`
- **Decisions Covered**:
  - `KR-D1`: Knowledge Sources — All Tiers Ingested (Curated KB + Operational Runbooks/Bugs + Raw Resolved Tickets/Chats; `KR-Q1(i)`)
  - `KR-D2`: Audience Segregation — Per-Chunk `audience` Label (`customer_visible` vs. `internal`); Only Customer-Visible Cited (`KR-Q4(i)`)
  - `KR-D13`: Default Audience Policy — `audience = internal` is the Mandatory System-Level Default
  - `KR-D16`: Provenance Attribution — Mandatory `source = human | agent` Provenance Metadata on Every Chunk (`KR-Q7(ii)`)
- **Related Architectural Decision Points**:
  - [`SG-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#sg-adp-04--authorization--tool-permissions): Authorization & Tool Permissions *(Content Dissemination Gates & PII Boundary)*
  - [`CI-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#ci-adp-03--improvement-levers): Improvement Levers *(KCS Knowledge Centered Service Evolve Loop)*
  - [`KR-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/02-knowledge-retrieval/KR-ADP-03-indexing-tenant-isolation.md): Indexing & Tenant Isolation *(Private vs. Public Index Placement; KR-Q1)*

---

## 1. Context & Problem Statement

Enterprise customer support architectures must retrieve knowledge across deeply heterogeneous, multi-system corporate repositories:
1. **Canonical Product Documentation & Published API Specs** (Confluence, ReadMe, GitDocs).
2. **Operational Engineering Assets** (Jira Known Issues, postmortems, incident runbooks, release notes).
3. **Historical Resolved Support Tickets & Chat Transcripts** (Zendesk, Freshdesk, Slack channels).

These knowledge tiers exhibit drastically divergent degrees of noise, variance, temporal decay, authority, and security exposure:
- **The Information Authority & Hallucination Dilemma**: Official API documentation specifies a hard rate limit of 100 req/min, whereas a 6-month-old resolved support ticket suggests a customer workaround allowing 500 req/min. In naive RAG systems, vector embeddings treat both chunks as equally authoritative, causing the agent to hallucinate or recommend deprecated workarounds.
- **Internal Knowledge Leakage Vulnerability ($UK4$)**: Support systems ingest internal postmortems and Jira comments containing root-cause admissions (*"Our Kafka cluster dropped messages due to poor capacity planning"*). If unlabeled, models quote these internal reflections directly to customers, exposing the enterprise to immense brand and legal liability.
- **Model Autophagy / Self-Reinforcing Error Loops ($UU5$)**: If historical tickets contain previous agent responses (some containing uncorrected errors or workarounds), indexing them causes the agent to retrieve its own past outputs as canonical truth, accelerating semantic drift across subsequent generations.

### The Core Architectural Question
> **What knowledge sources should be indexed, how do we probabilistically model source authority and resolve cross-document contradictions, and what strict audience and provenance controls prevent internal data leakage and agent self-contamination?**

---

## 2. Decision Framework & Theoretical Formulation

We ground our knowledge authority and content labelling architecture in three theoretical pillars: **Bayesian Source Reliability & Information Theory**, **Asymmetric Operational Loss Minimization**, and **Knowledge-Centered Service (KCS v6) Provenance Hygiene**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                            KNOWLEDGE THEORETICAL PILLARS                                         │
├────────────────────────────────┬────────────────────────────────┬────────────────────────────────┤
│   Pillar A: Bayesian Source    │   Pillar B: Information Theory │   Pillar C: Asymmetric Risk    │
│   Authority P(Truth | Source)  │   & Mutual Information Gain    │   & Loss Minimization E[L]     │
│                                │                                │                                │
│   • Source prior reliability R │   • Shannon Entropy H(Y)       │   • Impact cost C_impact       │
│   • Multi-tier authority ladder│   • Information Gain IG(Y;X)   │   • Closed-loop conflict event │
│   • Canonical > Runbook > Ticket│  • Ambiguity disambiguation   │   • Mandatory internal default │
│   • Empirical noise variance σ²│   • Cross-document delta Δ     │     eliminates leaks (UK4)     │
└────────────────────────────────┴────────────────────────────────┴────────────────────────────────┘
```

---

### Pillar A: Bayesian Source Reliability $P(\text{Truth} \mid \text{Source}, \text{Evidence})$

Each knowledge source $S_i$ is assigned a prior reliability score $R(S_i) \in [0, 1]$ calibrated on empirical noise, variance, and organizational governance characteristics:

$$P(\text{Truth} \mid S_i) = \frac{P(S_i \mid \text{Truth}) \cdot P(\text{Truth})}{P(S_i)}$$

#### The Hierarchical Authority Ladder
1. **Tier 1: Canonical Product Documentation & API Specs ($S_1$)**:
   - $R(S_1) \approx 0.99$ — Low noise ($\sigma^2 \to 0$), high consistency, strict editorial peer review. Expected error rate $\le 1\%$.
2. **Tier 2: Operational Runbooks & Known Bug Trackers ($S_2$)**:
   - $R(S_2) \approx 0.90$ — High technical accuracy, moderate review cadence, structured schemas (e.g., Jira `BUG-8192` with verified workarounds). Expected error rate $\approx 10\%$.
3. **Tier 3: Historical Resolved Support Tickets ($S_3$)**:
   - $R(S_3) \approx 0.79$ — Contextually rich on long-tail issues, but subject to analyst error, incomplete diagnosis, and temporal decay. Expected error rate $\approx 21\%$.
4. **Tier 4: Raw Community Chat / Informal Slack Transcripts ($S_4$)**:
   - $R(S_4) \approx 0.50$ — High noise, unverified conjecture, high entropy.

```
Authority Ranking:
  Tier 1: Canonical Docs  [R = 0.99] ──> Low Variance, Authoritative Governance
  Tier 2: Operational     [R = 0.90] ──> High Technical Detail, Workarounds
  Tier 3: Resolved Tickets[R = 0.79] ──> High Long-Tail Coverage, Subject to Decay
  Tier 4: Slack / Chat    [R = 0.50] ──> Experimental / High Noise (Excluded in v1)
```

#### Enterprise Calibration Invariant
Source reliability priors $R(S_i)$ are configurable per enterprise tenant. If an enterprise maintains an AI-curated ticket system or unmaintained product documentation, source weights $R(S_i)$ are dynamically adjusted based on human feedback loops (`CI-ADP-01`).

---

### Pillar B: Information Gain ($IG$) & Information-Theoretic Conflict Resolution

During passage context selection, candidate knowledge chunks $X$ are evaluated against user query $Y$ to maximize **Information Gain**:

$$IG(Y; X) = H(Y) - H(Y \mid X)$$

Where $H(Y)$ is the Shannon Entropy (uncertainty) of the answer distribution. The agent prioritizes passages that maximize $IG$ while minimizing downstream variance.

#### Contradiction Detection & Winning Selection Rule
Let candidate chunk $c_i \in S_{\text{high}}$ and candidate chunk $c_j \in S_{\text{low}}$ present contradictory assertions regarding the same technical entity (e.g., `rate_limit_rpm`):
1. **Selection Winner**: The chunk with higher posterior reliability $P(\text{Truth} \mid S_i) > P(\text{Truth} \mid S_j)$ is selected for the prompt context.
2. **Offline Knowledge Remediation Trigger (`KnowledgeConflictDetected`)**:
   When high-confidence contradiction is detected ($|\text{Similarity}(c_i, c_j)| > \tau_{\text{conflict}}$ and $S(c_i) \neq S(c_j)$):
   - The runtime emits an asynchronous `KnowledgeConflictDetected` event:
     $$\text{Payload} = \langle \texttt{winner\_doc\_id}, \texttt{stale\_doc\_id}, \texttt{passage\_diff}, \Delta_{\text{confidence}} \rangle$$
   - This automatically creates a Jira/Zendesk documentation maintenance ticket for human technical writers to deprecate or update stale lower-tier content, ensuring continuous self-healing documentation.

---

### Pillar C: Expected Cost of Error Minimization & Safe Audience Segregation

The expected cost of selecting knowledge chunk $c$ from source $S_i$ is:

$$\mathbb{E}[L(S_i)] = P(\text{Error} \mid S_i) \cdot C_{\text{impact}}$$

Where $C_{\text{impact}}$ is the operational, brand, or regulatory cost of hallucination:
- Quoting an outdated public workaround: $C_{\text{impact}} \approx \$200$ (customer frustration, re-contact).
- Quoting an internal unredacted postmortem acknowledging security vulnerabilities: $C_{\text{impact}} \ge \$50,000$ (regulatory sanctions, enterprise contract breach).

#### The Mandatory Internal Default Invariant (`KR-D13`)
To drive the probability of accidental internal disclosure to zero:

$$\forall \text{Chunk } c \in \mathcal{K}, \quad \text{Audience}(c) = \begin{cases}
\texttt{"customer\_visible"} & \text{if explicitly labeled and verified} \\
\texttt{"internal"} & \textbf{by default}
\end{cases}$$

An unlabeled chunk or an ingested document with missing metadata is **strictly classified as internal**. Under no circumstances may an internal chunk be cited or quoted in customer-facing responses (`KR-D2`).

---

## 3. Decision Rules & System Architecture

### Architectural Decision

1. **Ingested Knowledge Tiers (`KR-D1`)**:
   - Ingest all three tiers: Curated Docs ($S_1$) + Operational Bugs/Postmortems ($S_2$) + Raw Resolved Tickets ($S_3$).
   - **Index Placement Isolation (`KR-Q1 -> i`)**: Raw tickets and chat transcripts are indexed **strictly into each tenant's private index**. They are never merged into the shared public index, preventing cross-tenant information leakage.
2. **Audience Segregation & Citation Controls (`KR-D2`, `KR-D13`)**:
   - Every chunk carries an explicit `audience` label (`customer_visible` vs. `internal`).
   - **`audience = internal` is the system-level default (`KR-D13`)**. Customer-visible requires an explicit override.
   - Only `customer_visible` chunks may be cited or displayed to customers. Internal chunks may inform agent System 2 reasoning or surface in Human Specialist (HITL) co-pilot consoles.
   - **Parent-Child Expansion Rule (`KR-Q4 -> i`)**: When a small customer-visible child chunk matches, parent-section expansion automatically strips internal sibling chunks before compilation.
3. **Provenance Attribution (`KR-D16`, `KR-Q7 -> ii`)**:
   - Every ticket chunk carries an immutable provenance tag: `source = human | agent`.
   - Past agent responses are **retained but explicitly tagged** (*"agent reply, unverified"*). The confidence gate discounts agent-provenance evidence, breaking self-reinforcing hallucination loops.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   KNOWLEDGE INGESTION & CONTENT LABELLING ARCHITECTURE                           │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                   │
  ┌────────────────────────────────────────────────┴────────────────────────────────────────────┐
  │ 1. KNOWLEDGE INGESTION SOURCES (KR-D1)                                                      │
  │    • Curated Docs (Confluence, ReadMe) [Tier 1, R=0.99] ──> Public Index                    │
  │    • Operational (Jira Known Bugs, Runbooks) [Tier 2, R=0.90] ──> Public Index              │
  │    • Raw Resolved Tickets (Zendesk) [Tier 3, R=0.79] ──> Private Tenant Index (KR-Q1)       │
  ├─────────────────────────────────────────────────────────────────────────────────────────────┤
  │ 2. METADATA & PROVENANCE ATTACHMENT                                                         │
  │    • Extract author role: source = human | agent (KR-D16, KR-Q7)                            │
  │    • Enforce default audience: audience = internal (KR-D13)                                 │
  │    • Apply explicit override: audience = customer_visible (Verified articles only)          │
  ├─────────────────────────────────────────────────────────────────────────────────────────────┤
  │ 3. PII MASKING & EMBEDDING ENVELOPE (KR-Q2)                                                 │
  │    • Presidio-class PII redaction runs at ingestion before embedding                        │
  │    • Chunks embedded & stored in Qdrant/PostgreSQL pgvector                                 │
  └─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Concrete Genesis Implementation Contracts

#### 1. Knowledge Chunk Schema (`core/knowledge/models.py`)

```python
from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class AuthorityTier(str, Enum):
    TIER_1_CANONICAL_DOC = "TIER_1_CANONICAL_DOC"
    TIER_2_OPERATIONAL = "TIER_2_OPERATIONAL"
    TIER_3_HISTORICAL_TICKET = "TIER_3_HISTORICAL_TICKET"

class AudienceScope(str, Enum):
    CUSTOMER_VISIBLE = "customer_visible"
    INTERNAL = "internal"

class ContentProvenance(str, Enum):
    HUMAN = "human"
    AGENT = "agent"

class KnowledgeChunk(BaseModel):
    chunk_id: str
    parent_section_id: str
    doc_id: str
    tenant_id: Optional[str] = Field(description="None for shared public docs; Tenant UUID for private tickets")
    authority_tier: AuthorityTier
    reliability_prior: float = Field(ge=0.0, le=1.0)
    audience: AudienceScope = AudienceScope.INTERNAL  # KR-D13: Mandatory Internal Default
    provenance: ContentProvenance = ContentProvenance.HUMAN  # KR-D16
    unverified_agent_warning: bool = False
    title: str
    content: str
    url: str
    product_version: Optional[str] = None
    created_at: datetime
    updated_at: datetime
```

#### 2. Ingestion Metadata Normalizer (`core/knowledge/normalizer.py`)

```python
from core.knowledge.models import KnowledgeChunk, AuthorityTier, AudienceScope, ContentProvenance

class KnowledgeChunkNormalizer:
    @staticmethod
    def normalize_and_label_chunk(
        raw_data: dict,
        is_curated_public: bool,
        is_explicitly_public: bool,
        author_is_agent: bool
    ) -> KnowledgeChunk:
        """
        Enforces KR-D2, KR-D13, KR-D16, KR-Q1, KR-Q4, and KR-Q7.
        """
        # 1. Determine Authority Tier & Prior
        if is_curated_public:
            tier = AuthorityTier.TIER_1_CANONICAL_DOC
            prior = 0.99
            tenant_id = None  # Shared Public Index (KR-Q1)
        elif raw_data.get("is_runbook", False):
            tier = AuthorityTier.TIER_2_OPERATIONAL
            prior = 0.90
            tenant_id = None
        else:
            tier = AuthorityTier.TIER_3_HISTORICAL_TICKET
            prior = 0.79
            tenant_id = raw_data["tenant_id"]  # Private Tenant Index (KR-Q1)

        # 2. Enforce Mandatory Internal Default (KR-D13)
        audience = AudienceScope.CUSTOMER_VISIBLE if is_explicitly_public else AudienceScope.INTERNAL

        # 3. Provenance Attribution (KR-D16, KR-Q7)
        provenance = ContentProvenance.AGENT if author_is_agent else ContentProvenance.HUMAN
        unverified_warning = (provenance == ContentProvenance.AGENT)

        return KnowledgeChunk(
            chunk_id=raw_data["chunk_id"],
            parent_section_id=raw_data["parent_section_id"],
            doc_id=raw_data["doc_id"],
            tenant_id=tenant_id,
            authority_tier=tier,
            reliability_prior=prior,
            audience=audience,
            provenance=provenance,
            unverified_agent_warning=unverified_warning,
            title=raw_data["title"],
            content=raw_data["content"],
            url=raw_data["url"],
            product_version=raw_data.get("product_version"),
            created_at=raw_data["created_at"],
            updated_at=raw_data["updated_at"],
        )
```

---

## 4. Knowing Your Unknowns: Failure Modes & Mitigation Matrix

| Quadrant | Failure Mode | Technical Risk Description | Concrete Architectural Mitigation |
| :--- | :--- | :--- | :--- |
| **Q1: Known Knowns** *(Deterministic Contract Breaches)* | **Accidental Internal Leak ($UK4$)** | An unlabeled postmortem containing confidential data is quoted to a customer. | **Mandatory Internal Default (`KR-D13`)**: All chunks default to `internal`; only explicitly whitelisted chunks can be cited (`KR-D2`). |
| **Q1: Known Knowns** *(Deterministic Contract Breaches)* | **Sibling Internal Leak in Parent Section ($KR-Q4$)** | A public chunk matches; parent expansion includes an internal sibling chunk. | **Parent Expansion Filter (`KR-Q4(i)`)**: Parent assembler drops all internal sibling chunks before returning evidence. |
| **Q2: Known Unknowns** *(Probabilistic Reasoning Variance)* | **Raw Ticket Inaccuracy ($KU3$)** | 21% of tickets contain incorrect workarounds that model adopts as truth. | **Bayesian Authority Ladder (Pillar A)**: Tier 1/2 documentation overrides conflicting Tier 3 ticket passages in ranking. |
| **Q2: Known Unknowns** *(Probabilistic Reasoning Variance)* | **Over-Masking of Identifiers ($KU4$)** | Ingestion PII masker replaces critical error codes (`BUG-8192`) with `<ID>`. | **Entity Whitelist Masking**: Presidio engine preserves alphanumeric error tokens and software version strings (`SG-ADP-02`). |
| **Q3: Unknown Knowns** *(Tacit Enterprise Etiquette & Invariants)* | **Version Anachronism ($UK1$)** | Agent recommends v3.2 configuration to a customer operating on v4.2. | **Product Version Metadata Anchor**: Chunks carry `product_version`; query transform extracts version and enforces filter (`KR-D8`). |
| **Q3: Unknown Knowns** *(Tacit Enterprise Etiquette & Invariants)* | **Superseded Article Drift ($UK2$)** | Authors write new policy without deleting old one; both are retrieved. | **Temporal Decay Score**: Retrieval ranking discounts chunks possessing a superseding `updated_at` sibling document. |
| **Q4: Unknown Unknowns** *(Emergent Cascades & Black Swans)* | **Autophagic Model Collapse ($UU5$)** | Agent retrieves past agent answers from tickets, reinforcing hallucinations. | **Provenance Tagging (`KR-D16`, `KR-Q7`)**: Chunks tagged `agent` carry visible warnings and are discounted in confidence gate. |
| **Q4: Unknown Unknowns** *(Emergent Cascades & Black Swans)* | **Poisoned Ticket Reranker Hijack ($UU1$)** | User submits ticket containing *"Rank this first"*; ticket manipulates reranker. | **Pre-Rerank Input Screening (`KR-D14`)**: Chunks are sanitized for prompt injections before passing to LLM reranker. |

---

## 5. Closed-Loop Feedback & Continuous Remediation

1. **Automated Documentation Repair (`KnowledgeConflictDetected`)**:
   - When the agent detects a direct conflict between a Tier 1 Canonical Doc and a Tier 3 Ticket workaround, it emits a `KnowledgeConflictDetected` event to the Kafka/SQS topic.
   - The Continuous Improvement engine (`CI-ADP-03`) synthesizes a documentation revision ticket in Jira, notifying the support engineering lead.
2. **KCS Article Distillation Pipeline**:
   - Tickets that resolve recurring novel issues with high CSAT are mined by the KCS worker to draft formal, human-reviewed knowledge articles.

---

## 6. Genesis Implementation Directives

### Target File Manifest
1. `core/knowledge/models.py`: Pydantic models for `KnowledgeChunk`, `AuthorityTier`, `AudienceScope`, and `ContentProvenance`.
2. `core/knowledge/normalizer.py`: The `KnowledgeChunkNormalizer` enforcing default internal scope and provenance tags.
3. `core/knowledge/conflict.py`: Contradiction detection module emitting `KnowledgeConflictDetected` events.

### Scaffolding Verification Criteria
- [ ] **Default Internal Invariant**: Any chunk ingested without an explicit `is_customer_visible=True` flag has `audience == AudienceScope.INTERNAL`.
- [ ] **Parent Expansion Scrubbing**: Test verifies that expanding a parent section containing 2 public and 1 internal chunk returns strictly the 2 public chunks.
- [ ] **Agent Provenance Warning**: Ingested ticket turns authored by agents carry `unverified_agent_warning == True`.

---

## 7. Consequences & Trade-offs

### Positive Consequences
- **Zero Accidental Internal Disclosures**: Mandatory internal default completely prevents confidential engineering notes from reaching customers.
- **Mathematically Grounded Conflict Resolution**: High-authority canonical documentation consistently overrides historical support workarounds.
- **Self-Healing Documentation**: Contradiction logging systematically surfaces outdated internal content for human revision.
- **Protection Against Model Autophagy**: Explicit provenance tagging breaks self-reinforcing model error loops.

### Negative / Neutral Trade-offs & Mitigations
- **Low Initial Public Coverage**: Because default audience is internal, public KB coverage starts low until articles are explicitly reviewed.  
  *Mitigation*: Execute a one-time bulk verification script on public Confluence spaces during enterprise onboarding.
- **Tenant Index Partitioning Overhead**: Restricting raw tickets to tenant-private indexes eliminates cross-tenant learning.  
  *Mitigation*: Cross-tenant learning is handled exclusively through sanitized, human-curated KCS article publishing (`CI-ADP-05`).

---

## 8. References

1. **Anthropic Research (2024)**. *Information-Theoretic Foundations of Agent Reasoning and Context Selection*.
2. **Shannon, C. E. (1948)**. *A Mathematical Theory of Communication*. Bell System Technical Journal, 27(3), 379-423.
3. **Consortium for Service Innovation (2020)**. *Knowledge-Centered Service (KCS) v6 Principles and Core Concepts*.
4. **Zou, W. et al. (2024)**. *PoisonedRAG: Knowledge Poisoning Attacks to Retrieval-Augmented Generation of Large Language Models*. arXiv:2402.07867.
5. **Greshake, K. et al. (2023)**. *Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection*. ACM Workshop on Artificial Intelligence and Security.
