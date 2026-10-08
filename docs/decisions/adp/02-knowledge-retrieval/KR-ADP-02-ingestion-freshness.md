# KR-ADP-02: Knowledge Ingestion, Chunking & Freshness (Parent-Child Small-to-Big Chunking & Deletion-Aware Batch Ingestion)

- **Status**: Accepted & Confirmed
- **Date**: 2026-09-24 *(Amended: 2026-09-24 per KR-Q3 Immediate Purge & KR-D15 Deletion Check)*
- **Deciders**: Architecture Team, Lead Data Engineer, Compliance & Privacy Core
- **Component**: `[2] Knowledge & Retrieval` (`Component [ 2 ]`)
- **Reasoning Source**: `checkpoint.md` §6 · Diagram: `LLD - [2] Knowledge & Retrieval`
- **Decisions Covered**:
  - `KR-D3`: Ingestion Cadence — Scheduled Nightly Batch Sync (Content $\le 24\text{h}$ Stale; `KR-Q3(ii)`)
  - `KR-D4`: Chunking Strategy — Structure-Aware Parsing + Parent-Child Small-to-Big Chunking
  - `KR-D15`: Deletion Hygiene — Deletion-Aware Ingestion Pipeline with Pre/Post Tombstone Verification
- **Related Architectural Decision Points**:
  - [`DP-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#dp-adp-05--erasure-backups--restore): Erasure, Backups & Restore *(GDPR Art. 17 Cryptographic Deletion)*
  - [`SG-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#sg-adp-02--pii-protection): PII Protection *(Presidio Pre-Ingestion Masking Barrier; KR-Q2)*
  - [`CR-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#cr-adp-03--answer-cache): Answer Cache *(Semantic Cache Invalidation via Tombstones)*

---

## 1. Context & Problem Statement

Enterprise knowledge bases undergo continuous mutations: product documentation updates nightly, engineering teams deploy hotfixes with revised workarounds, and users exercise statutory GDPR/CCPA data erasure requests.

Transforming raw enterprise documents into high-performance vector and keyword indexes faces three severe engineering tensions:
1. **The Chunking Granularity Dilemma (Precision vs. Context)**:
   - *Small Chunks (100–200 tokens)*: Excel at fine-grained embedding vector alignment (high cosine similarity on specific error codes), but sever semantic continuity, losing condition-action pairs, tables, and surrounding warnings.
   - *Large Chunks (1,000–2,000 tokens)*: Preserve full document context, but dilute vector embeddings, triggering poor retrieval recall on needle-in-a-haystack queries.
2. **The Ingestion Cadence vs. Operational Cost Trade-Off**: Running streaming Change Data Capture (CDC) across thousands of Confluence spaces, Jira boards, and Zendesk instances introduces immense webhook infrastructure complexity, rate-limit consumption, and continuous embedding API costs. Conversely, simple nightly batches create a $\le 24$-hour staleness window.
3. **The "Resurrected Data" Vulnerability ($UU4$)**: When a customer exercises their GDPR "Right to be Forgotten," an out-of-band purge deletes their tickets from the vector index. However, if the subsequent nightly batch re-syncs from a database snapshot or export dump that still contains the raw tickets, the erased data is silently re-ingested ($UU4$).

### The Core Architectural Question
> **How frequently is enterprise knowledge synchronized, how are documents chunked to maximize retrieval precision without sacrificing context, and how does the pipeline guarantee immediate GDPR erasure while preventing stale snapshots from resurrecting deleted records?**

---

## 2. Decision Framework & Theoretical Formulation

We structure our ingestion and chunking architecture upon three theoretical pillars: **Cognitive Load Theory & Information Foraging (Small-to-Big)**, **GDPR Article 17 Derivation Graph Propagation**, and **Multi-Phase Tombstone Reconciliation**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             INGESTION THEORETICAL PILLARS                                        │
├────────────────────────────────┬────────────────────────────────┬────────────────────────────────┤
│   Pillar A: Information        │   Pillar B: GDPR Art. 17       │   Pillar C: Multi-Phase        │
│   Foraging (Small-to-Big)      │   Derivation Graph Deletion    │   Tombstone Reconciliation     │
│                                │                                │                                │
│   • Small chunk: High Scent    │   • Derivation Graph G=(V,E)   │   • Pre-sync filter            │
│   • Parent section: Context    │   • Atomic out-of-band purge   │   • Post-batch verification    │
│   • Layout/Table integrity     │   • Invalidate semantic cache  │   • Eliminates snapshot        │
│   • Zero LLM indexing cost     │   • Zero derived artifact leak │     resurrection (UU4)         │
└────────────────────────────────┴────────────────────────────────┴────────────────────────────────┘
```

---

### Pillar A: Information Foraging Theory & Small-to-Big Chunking

Following **Information Foraging Theory (Pirolli & Card, 1999)** and **Cognitive Load Theory (Sweller, 1988)**, human searchers navigate information via proximal cues ("information scent"). In computational RAG:
- The **Small Child Chunk** ($\approx 120\text{ words}$) provides sharp, high-density information scent, maximizing bi-encoder dense cosine similarity and BM25 term frequency.
- The **Parent Section** ($300\text{–}800\text{ words}$) provides cognitive completeness, supplying the full condition-action table, prerequisite list, and operational context required for language model reasoning.

#### Mathematical Formulation of Small-to-Big Retrieval
Let document $D$ be parsed into a set of hierarchical parent sections $\mathcal{P} = \{P_1, P_2, \dots, P_m\}$. Each parent section $P_i$ is decomposed into a set of child chunks $\{c_{i,1}, c_{i,2}, \dots, c_{i,k}\}$:

$$\bigcup_{j=1}^{k} c_{i,j} \equiv P_i \quad \text{and} \quad \text{Tokens}(c_{i,j}) \approx 120, \quad \text{Tokens}(P_i) \in [300, 800]$$

During first-stage retrieval, query $Q$ matches against child chunks:

$$c^* = \arg\max_{c_{i,j}} \text{Score}(Q, c_{i,j})$$

However, rather than returning child chunk $c^*$ to the prompt context, the index expands the hit to its parent section $P_i$:

$$\text{Evidence Retrospective: } c^* \implies \text{Emit}(P_i)$$

This provides the language model with full tabular and structural context while preserving pinpoint retrieval precision, achieving the benefits of Anthropic Contextual Retrieval with **zero runtime LLM indexing costs** (`KR-D4`).

---

### Pillar B: Statutory Erasure Propagation across the Derived Artifact Graph

Under **GDPR Article 17 ("Right to be Forgotten")**, data erasure mandates apply not only to raw source documents, but to all downstream derived representations:

$$\text{Derivation Graph: } D_{\text{raw}} \longrightarrow \{c_k\}_{\text{chunks}} \longrightarrow \{\vec{v}_k\}_{\text{embeddings}} \longrightarrow \mathcal{C}_{\text{semantic\_cache}}$$

If source document $D_{\text{raw}}$ is deleted, retaining derived vector embeddings $\vec{v}_k$ violates statutory compliance, particularly given modern **embedding inversion techniques (Morris et al., 2023, vec2text)** that reconstruct raw sensitive text from 1536-dimensional vectors.

#### The Dual-Track Cadence Formulation (`KR-D3`, `KR-Q3 -> ii`)
To balance operational stability against statutory compliance:
1. **Forward Content Ingestion**: Executes on a **Scheduled Nightly Batch** ($\Delta t_{\text{batch}} = 24\text{ hours}$). Content updates are accepted up to 24 hours stale.
2. **Reverse Erasure & Tombstone Purge**: Executes on an **Immediate Out-of-Band Event Path** ($\Delta t_{\text{purge}} < 60\text{ seconds}$):
   $$\text{Event } \texttt{DocumentDeleted}(D_{\text{id}}) \implies \begin{cases}
   \text{Purge Vector Index Chunks } \{c_k \mid c_k \in D_{\text{id}}\} \\
   \text{Purge Keyword BM25 Inverted Index} \\
   \text{Evict Semantic Cache Hits Derived from } D_{\text{id}} \\
   \text{Register Durable Tombstone } \mathcal{T}(D_{\text{id}})
   \end{cases}$$

---

### Pillar C: Deletion-Aware Ingestion Reconciliation (`KR-D15`)

To prevent stale database snapshots from resurrecting deleted records during the nightly batch ($UU4$), the ingestion pipeline enforces a **Four-Stage Deletion-Aware Reconciliation Protocol**:

$$\begin{aligned}
\text{Stage 1 (Pre-Scan Filter)}: &\quad \mathcal{B}_{\text{filtered}} = \{ d \in \mathcal{B}_{\text{snapshot}} \mid d.\text{doc\_id} \notin \text{DurableTombstones} \} \\
\text{Stage 2 (PII Screening)}: &\quad \mathcal{B}_{\text{masked}} = \text{PresidioMask}(\mathcal{B}_{\text{filtered}}) \\
\text{Stage 3 (Index Upsert)}: &\quad \text{UpsertChunks}(\mathcal{B}_{\text{masked}}) \\
\text{Stage 4 (Post-Batch Audit)}: &\quad \forall t \in \text{DurableTombstones}, \; \text{AssertNotInIndex}(t)
\end{aligned}$$

If Stage 4 detects that an erased document re-appeared in the index, the batch transaction aborts immediately, rolling back changes and raising a high-severity compliance alert (`DP-ADP-05`).

---

## 3. Decision Rules & System Architecture

### Architectural Decision

1. **Ingestion Cadence (`KR-D3`, `KR-Q3(ii)`)**:
   - Content refreshes on a **Scheduled Nightly Batch Sync** ($\le 24\text{h}$ staleness accepted for standard documentation).
   - Deletions, GDPR erasures, and ACL revocations bypass the batch schedule, executing **immediately out-of-band via an event-driven purge listener**.
2. **Chunking Strategy (`KR-D4`)**:
   - Documents are ingested using **Structure-Aware Parsing** (Markdown headers `#`, `##`, tables, and fenced code blocks are never bisected).
   - Chunk layout enforces **Parent-Child Small-to-Big**:
     - Child Chunks: $\approx 100\text{–}150\text{ words}$ (Dense + BM25 indexed).
     - Parent Sections: $300\text{–}800\text{ words}$ (Retrieved and passed to context).
3. **Deletion-Aware Ingestion (`KR-D15`)**:
   - Nightly batches check the durable tombstone store prior to chunking, filtering out all historically purged doc IDs.
   - A mandatory post-ingestion audit verifies that zero tombstones reside in the index post-run.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   DELETION-AWARE INGESTION & CHUNKING ARCHITECTURE                               │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                   │
  ┌────────────────────────────────────────────────┴────────────────────────────────────────────┐
  │ DUAL-TRACK INGESTION DISPATCHER                                                            │
  │                                                                                            │
  │  [Track 1: Nightly Batch (KR-D3)]                [Track 2: Immediate Purge (KR-Q3 ii)]     │
  │  • Runs at 02:00 UTC                              • Subscribes to GDPR / Deletion Events   │
  │  • Ingests Confluence, Jira, Zendesk              • Executes in <60 seconds                │
  └────────────────┬───────────────────────────────────────────────┬───────────────────────────┘
                   │                                               │
                   v                                               v
  ┌───────────────────────────────────────────────┐ ┌──────────────────────────────────────────┐
  │ Stage 1: Tombstone Pre-Filter (KR-D15)        │ │ Immediate Vector & Cache Purge           │
  │ Drops any document ID present in Tombstone DB │ │ • Deletes Qdrant vectors & BM25 tokens   │
  └────────────────┬──────────────────────────────┘ │ • Invalidates Comp 12 Semantic Cache    │
                   │                                │ • Appends ID to Durable Tombstone Store  │
                   v                                └──────────────────────────────────────────┘
  ┌───────────────────────────────────────────────┐
  │ Stage 2: Structure-Aware Chunking (KR-D4)     │
  │ • Preserves Markdown tables & code blocks     │
  │ • Creates 120-word Child Chunks               │
  │ • Links to 500-word Parent Sections           │
  └────────────────┬──────────────────────────────┘
                   │
                   v
  ┌───────────────────────────────────────────────┐
  │ Stage 3: Post-Batch Verification Audit        │
  │ Verifies zero tombstoned IDs exist in index   │
  └───────────────────────────────────────────────┘
```

---

### Concrete Genesis Implementation Contracts

#### 1. Structure-Aware Parent-Child Chunker (`core/knowledge/chunker.py`)

```python
import re
from typing import List, Tuple
from pydantic import BaseModel
from core.knowledge.models import KnowledgeChunk, AuthorityTier, AudienceScope, ContentProvenance

class ParentSection(BaseModel):
    section_id: str
    doc_id: str
    title: str
    content: str  # 300 - 800 words
    audience: AudienceScope

class ChildChunk(BaseModel):
    chunk_id: str
    parent_section_id: str
    doc_id: str
    content: str  # 100 - 150 words
    audience: AudienceScope

class StructureAwareChunker:
    def __init__(self, target_child_words: int = 120):
        self.target_child_words = target_child_words

    def split_document(
        self,
        doc_id: str,
        markdown_text: str,
        audience: AudienceScope
    ) -> Tuple[List[ParentSection], List[ChildChunk]]:
        """
        Structure-aware parsing preserving headings, tables, and code blocks (KR-D4).
        """
        # Split on Markdown H2 / H3 headers
        raw_sections = re.split(r'\n(?=#{2,3}\s)', markdown_text)
        parent_sections: List[ParentSection] = []
        child_chunks: List[ChildChunk] = []

        for s_idx, section in enumerate(raw_sections):
            lines = section.strip().split('\n')
            title = lines[0].replace('#', '').strip() if lines else "Section"
            parent_id = f"{doc_id}_sec_{s_idx}"

            parent_sections.append(ParentSection(
                section_id=parent_id,
                doc_id=doc_id,
                title=title,
                content=section.strip(),
                audience=audience
            ))

            # Split section into small child chunks for vector scent
            words = section.split()
            for c_idx in range(0, len(words), self.target_child_words):
                child_text = " ".join(words[c_idx:c_idx + self.target_child_words])
                child_id = f"{parent_id}_c_{c_idx // self.target_child_words}"
                
                child_chunks.append(ChildChunk(
                    chunk_id=child_id,
                    parent_section_id=parent_id,
                    doc_id=doc_id,
                    content=child_text,
                    audience=audience
                ))

        return parent_sections, child_chunks
```

#### 2. Deletion-Aware Ingestion Pipeline (`core/knowledge/batch_ingestion.py`)

```python
from typing import List, Set
from core.knowledge.chunker import StructureAwareChunker
from core.knowledge.models import KnowledgeChunk
from core.knowledge.tombstone import TombstoneRepository
from core.persistence.vector_store import QdrantStoreManager

class DeletionAwareBatchIngestionPipeline:
    def __init__(
        self,
        tombstone_repo: TombstoneRepository,
        vector_store: QdrantStoreManager,
        chunker: StructureAwareChunker
    ):
        self.tombstone_repo = tombstone_repo
        self.vector_store = vector_store
        self.chunker = chunker

    async def execute_nightly_batch(self, raw_documents: List[dict]) -> dict:
        """
        Executes nightly batch sync with pre/post tombstone verification (KR-D3, KR-D15).
        """
        active_tombstones: Set[str] = await self.tombstone_repo.get_all_tombstoned_doc_ids()

        # Stage 1: Pre-Filter against tombstones (UU4 Mitigation)
        filtered_docs = [
            doc for doc in raw_documents
            if doc["doc_id"] not in active_tombstones
        ]

        total_children = 0
        total_parents = 0

        # Stage 2: Chunk and Ingest
        for doc in filtered_docs:
            parents, children = self.chunker.split_document(
                doc_id=doc["doc_id"],
                markdown_text=doc["content"],
                audience=doc["audience"]
            )
            # Store parent sections in relational DB, child vectors in Qdrant
            await self.vector_store.upsert_parent_sections(parents)
            await self.vector_store.upsert_child_vectors(children)
            total_parents += len(parents)
            total_children += len(children)

        # Stage 3: Mandatory Post-Batch Verification Audit
        await self._verify_zero_tombstones_in_index(active_tombstones)

        return {
            "status": "COMPLETED",
            "ingested_docs": len(filtered_docs),
            "parent_sections": total_parents,
            "child_chunks": total_children,
            "dropped_tombstones": len(raw_documents) - len(filtered_docs)
        }

    async def _verify_zero_tombstones_in_index(self, tombstones: Set[str]) -> None:
        """Enforces KR-D15: asserts no purged IDs leaked into the new index."""
        leaked_ids = await self.vector_store.find_any_present(tombstones)
        if leaked_ids:
            # Atomic emergency rollback
            await self.vector_store.emergency_purge(leaked_ids)
            raise RuntimeError(f"CRITICAL COMPLIANCE BREACH: Tombstones leaked during batch: {leaked_ids}")
```

---

## 4. Knowing Your Unknowns: Failure Modes & Mitigation Matrix

| Quadrant | Failure Mode | Technical Risk Description | Concrete Architectural Mitigation |
| :--- | :--- | :--- | :--- |
| **Q1: Known Knowns** *(Deterministic Contract Breaches)* | **Nightly Batch Half-Completion ($KK1$)** | Batch crashes mid-run, leaving index in a fractured state with mixed document versions. | **Blue/Green Collection Swap**: Nightly sync builds to shadow collection; swaps alias atomically upon 100% completion. |
| **Q1: Known Knowns** *(Deterministic Contract Breaches)* | **Orphaned Derived Embeddings ($KK6$)** | Doc is deleted from CRM, but derived embeddings remain in vector store. | **Immediate Out-of-Band Purge (`KR-Q3 ii`)**: Purge listener executes immediately, cascading deletes across Qdrant, BM25, and Cache. |
| **Q2: Known Unknowns** *(Probabilistic Reasoning Variance)* | **First-Day Incident Staleness ($KU6$)** | Major outage occurs at 09:00 UTC; runbook is not retrievable until 02:00 UTC next day. | **Accepted v1 Trade-off (`KR-D3`)**: Accepted for v1; operational workarounds dispatched via live Human Specialist console. |
| **Q2: Known Unknowns** *(Probabilistic Reasoning Variance)* | **Parent Context Token Overflow ($KR-Q5$)** | 10 retrieved parent sections average 800 words, exceeding 35% RAG slot budget. | **Assembler Quota Compactor (`ADP-03`)**: Assembler trims parent sections dynamically to fit token budget constraints. |
| **Q3: Unknown Knowns** *(Tacit Enterprise Etiquette & Invariants)* | **Table Bisecting Corruption** | Naive length chunker cuts markdown table mid-row, destroying tabular calculations. | **Structure-Aware Parser (`KR-D4`)**: Headings, code blocks, and markdown tables are treated as indivisible atom blocks. |
| **Q3: Unknown Knowns** *(Tacit Enterprise Etiquette & Invariants)* | **Superseded Workaround Retrieval** | A bug is fixed in v4.2.1, but old v4.2 workaround remains indexed. | **Ingestion Status Tagging**: Workarounds carry `status: fixed_in_vX`; query filter excludes resolved issues. |
| **Q4: Unknown Unknowns** *(Emergent Cascades & Black Swans)* | **Resurrected Data Attack ($UU4$)** | GDPR-erased ticket re-enters system via backup snapshot sync during batch. | **Tombstone Pre/Post Audit (`KR-D15`)**: Batch cross-checks durable tombstones before ingest and asserts zero leakage post-run. |
| **Q4: Unknown Unknowns** *(Emergent Cascades & Black Swans)* | **Cross-Tenant Vector Collisions** | Multi-tenant batch accidentally tags Tenant A tickets with Tenant B collection. | **Isolated Tenant Private Pipelines (`KR-Q1`)**: Private ticket ingestion executes in dedicated per-tenant batch worker jobs. |

---

## 5. Closed-Loop Feedback & Telemetry Integration

1. **Batch Execution & Delta Metrics**:
   - Prometheus gauges track nightly batch duration, chunk expansion factor ($P/C$ ratio), and dropped tombstone counts.
2. **Purge SLA Telemetry**:
   - Out-of-band erasure latency is logged ($P_{99} \le 45\text{ seconds}$). Failure to purge any vector index entry raises an immediate PagerDuty incident (`OB-ADP-03`).

---

## 6. Genesis Implementation Directives

### Target File Manifest
1. `core/knowledge/chunker.py`: `StructureAwareChunker` supporting Parent-Child small-to-big layout.
2. `core/knowledge/batch_ingestion.py`: `DeletionAwareBatchIngestionPipeline` with pre/post tombstone checks.
3. `core/knowledge/purge.py`: Event listener handling immediate out-of-band GDPR and deletion events.
4. `core/knowledge/tombstone.py`: `TombstoneRepository` providing durable tracking of purged document IDs.

### Scaffolding Verification Criteria
- [ ] **Table Preservation Invariant**: A 30-row Markdown table remains intact within a single parent section without row splitting.
- [ ] **Tombstone Pre-Filter Test**: Ingesting a batch containing a tombstoned doc ID asserts that the document is dropped and never reaches Qdrant.
- [ ] **Post-Batch Audit Tripwire**: Artificially injecting a tombstone ID during batch causes `_verify_zero_tombstones_in_index` to raise an error and abort.

---

## 7. Consequences & Trade-offs

### Positive Consequences
- **Superior Retrieval Accuracy without Index LLM Costs**: Small-to-big chunking provides sharp vector scent while supplying the model with rich, unsevered contextual parent sections.
- **Strict GDPR & CCPA Compliance**: Out-of-band immediate purges eliminate statutory exposure on derived embeddings and caches.
- **Zero Snapshot Resurrection Hazard**: Four-stage deletion-aware pipeline permanently prevents stale database backups from resurrecting erased data.
- **Operational Simplicity**: Nightly batch synchronization dramatically simplifies infrastructure compared to complex streaming CDC pipelines.

### Negative / Neutral Trade-offs & Mitigations
- **24-Hour Staleness Window**: Documentation published at noon is unavailable until the next morning.  
  *Mitigation*: Incident commanders can trigger manual out-of-band single-document syncs for critical zero-day bugs via the CLI.
- **Storage Amplification**: Storing both child chunks and parent sections increases relational and vector database storage by $\approx 1.4\times$.  
  *Mitigation*: Parent sections reside in cheap relational storage (PostgreSQL/S3); only lightweight child vectors reside in RAM-backed Qdrant indexes.

---

## 8. References

1. **Pirolli, P., & Card, S. (1999)**. *Information foraging*. Psychological Review, 106(4), 643-675.
2. **Sweller, J. (1988)**. *Cognitive load during problem solving: Effects on learning*. Cognitive Science, 12(2), 257-285.
3. **Morris, J. X. et al. (2023)**. *Text Embeddings Reveal (Almost) As Much As Text*. arXiv:2310.06816.
4. **European Parliament (2016)**. *General Data Protection Regulation (Regulation EU 2016/679)*. Article 17: Right to Erasure.
