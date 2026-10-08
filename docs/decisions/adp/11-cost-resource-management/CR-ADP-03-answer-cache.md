# CR-ADP-03: Per-Tenant Deterministic Answer Caching (Jev Public-Doc Eligibility, Version-Pinned Cache Keys & Tombstone Invalidation)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-03 *(Confirmed per CR-D3 Public-KB Answer Cache CR-Q2, CR-D14 Version-Aware Composite Cache Key UK1, KR-Q3 & DP-D13 Tombstone Invalidation)*
- **Deciders**: Architecture Team, Principal Data Architect, Lead Security Engineer, FinOps Director
- **Component**: `[11] Cost & Resource Management` (`Component [ 11 ]`)
- **Reasoning Source**: `checkpoint.md` §15 · Diagram: `LLD - [11] Cost & Resource Management`
- **Decisions Covered**:
  - `CR-D3`: Per-Tenant Public-KB Answer Cache — Answers generated purely from public, customer-visible documentation with zero account-specific or tenant-private facts are cached in a dedicated per-tenant key-value store for up to 7 days (`CR-Q2(ii)`); eligibility is governed by a Jev `Noul` predicate (*"Is this question answerable from public docs alone without account-specific state?"*); cross-tenant semantic cache sharing is strictly prohibited to eliminate cross-tenant poisoning vulnerabilities (Failure Matrix Q4); cached responses are instantly invalidated upon nightly knowledge base syncs or deletion tombstones (`KR-Q3`, `DP-D13`) and must pass standard output sanitization checks (`SG-D6`) prior to delivery
  - `CR-D14`: Version-Aware Composite Cache Key — Resolves product version drift ($UK1$) by structuring the cache key as a composite SHA-256 hash: $\text{Key} = \text{Hash}(\text{NormalizedQuestion} \parallel \text{TenantID} \parallel \text{ProductVersion} \parallel \text{KBIndexVersion})$; queries that explicitly mention variable product versions in their text bypass cache insertion entirely to prevent serving stale major-release instructions to newer software versions
- **Related Architectural Decision Points**:
  - [`KR-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/02-knowledge-retrieval/KR-ADP-02-ingestion-freshness.md): Ingestion & Freshness *(Nightly Batch Syncs & Deletion Purges)*
  - [`SG-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/06-safety-security-governance/SG-ADP-02-pii-protection.md): PII Protection *(Zero Account Entity Persistence)*
  - [`SG-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/06-safety-security-governance/SG-ADP-03-output-safety.md): Output Safety *(Pre-Delivery Sanitization on Cache Hits)*
  - [`MS-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/03-memory-state/MS-ADP-02-long-term-fact-model.md): Long-Term Fact Model *(Account Facts Never Stored)*
  - [`DP-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/07-data-persistence/DP-ADP-05-erasure-backups-restore.md): Erasure Fan-Out *(Semantic Cache Invalidation)*

---

## 1. Context & Problem Statement

Recomputing foundational LLM inferences for repeated, generic customer queries is economically wasteful:
1. **The Repeated Query Inefficiency**:
   - In enterprise SaaS environments, standard procedural questions ("How do I configure SAML SSO with Okta?", "What are your firewall IP ranges?", "Where do I invite team members?") account for $30–45\%$ of total inbound volume.
   - Re-running vector search, LLM reranking, and frontier neural generation on identical documentation queries incurs hundreds of dollars in daily redundant API fees and adds $3.5\text{s}$ of latency.
2. **The Cross-Tenant Cache Poisoning Threat (Failure Matrix Q4)**:
   - Naive semantic caching architectures attempt to share cached questions and answers across all enterprise tenants. However, an attacker in Tenant A can craft an inquiry containing subtle prompt injection payloads or misleading instructions. If the cache stores and serves Tenant A's corrupted output to Tenant B, Tenant B's users are compromised.
   - Furthermore, even identical questions may have divergent policy answers across enterprise subscription tiers (e.g., Enterprise SLA vs. Starter SLA).
3. **The Product Versioning Trap ($UK1$)**:
   - Software documentation evolves across releases. If an agent caches an answer for "How do I configure SSL?" under Product v3.2 (which required manual OpenSSL cert generation), and subsequently serves that cached response to a user running Product v4.5 (which uses automated Let's Encrypt certificates), the customer receives incorrect, outdated guidance.

### The Core Architectural Question
> **How do we construct an intelligent, deterministic answer cache that maximizes hit rates for public procedural queries, guarantees zero cross-tenant contamination, avoids version-drift hallucinations, and invalidates instantly upon knowledge base updates?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `CR-D3` and `CR-D14` establish the **Per-Tenant Version-Aware Public Documentation Cache Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   DETERMINISTIC PER-TENANT ANSWER CACHING PIPELINE (CR-D3, CR-D14)               │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                           Incoming Query $Q$ (Normalized String, Sanitized)
                                                  │
                                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 1. VERSION DETECTION & EXCLUSION FILTER (CR-D14, UK1)                                            │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Regex & NER Check: Does query text explicitly mention a product version? (e.g., "in v4.2")       │
│ • YES ===> BYPASS CACHE WRITE (Volatile Versioned Question: Execute Full Agent Workflow)         │
│ • NO  ===> Proceed to Cache Key Computation                                                      │
└─────────────────────────────────────────────────┬────────────────────────────────────────────────┘
                                                  │
                                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 2. COMPOSITE CACHE KEY COMPUTATION (CR-D14)                                                      │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ $K = \text{SHA256}(\text{Norm}(Q) \parallel \text{TenantID} \parallel \text{ProductVer} \parallel \text{KBIndexVer})$             │
│ • Strict Tenant Namespace Isolation (Zero Cross-Tenant Sharing, Failure Matrix Q4)              │
│ • Pinned to Active Knowledge Base Snapshot Hash (`KR-D3`)                                        │
└─────────────────────────────────────────────────┬────────────────────────────────────────────────┘
                                                  │
                                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 3. CACHE LOOKUP GATEWAY                                                                          │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Check Redis Cluster: `GET cache:answer:{TenantID}:{K}`                                           │
│                                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ Cache Status:                                                                            │   │
│   │ • HIT  ===> Pass through Output Safety Check (`SG-D6`) -> Stream to Client (Latency <50ms)│   │
│   │ • MISS ===> Execute Full Knowledge & Reasoning Agent Pipeline                            │   │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┬────────────────────────────────────────────────┘
                                                  │ (On Cache Miss & Generation Complete)
                                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 4. JEV PUBLIC-DOC ELIGIBILITY GATEWAY (CR-D3, ADP-05 Use 4)                                      │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Jev Noul Evaluation: "Is this answer derived exclusively from public documentation?"             │
│ • Contains account data / CRM facts / dynamic balances? ===> DO NOT CACHE (MS-D6 Invariant)     │
│ • Pure Public Documentation?                            ===> STORE IN CACHE (TTL = 7 Days CR-Q2) │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Pillar 1: Public-Doc Eligibility Gating (`CR-D3`, `ADP-05` Use 4)

Not all generated answers are safe to persist. Caching customer-specific data creates catastrophic data leak vectors.
Before any generated response is written to the cache, it must pass a strict dual-validation gate:
1. **Deterministic State Invariant (`MS-D6`)**:
   - The execution trace must verify that zero external state-mutating or CRM-reading tools (`TA-D1`) were invoked during the turn.
2. **Jev `Noul` Categorization (`ADP-05` Use 4)**:
   - A dedicated Jev classifier evaluates the generated turn:
     $$\text{Eligible} = \text{Jev}_{\text{Noul}}(\text{"Answerable from public documentation alone without account data?"})$$
   - If Jev outputs `False`, the response is flagged as account-specific and is discarded from cache insertion.
   - If Jev outputs `True`, the response represents invariant product documentation and is written to the tenant's cache namespace.

---

### Pillar 2: Version-Aware Composite Key Formulation (`CR-D14`, $UK1$)

To eliminate cross-version contamination, cache keys incorporate explicit software state metadata:
$$K = \mathcal{H}\left( \text{Normalize}(Q) \parallel T_{\text{id}} \parallel V_{\text{product}} \parallel V_{\text{kb\_index}} \right)$$

Where:
- $\text{Normalize}(Q)$: Lemmatized, lowercased, punctuation-stripped query representation.
- $T_{\text{id}}$: The authenticated tenant identifier (prevents cross-tenant poisoning).
- $V_{\text{product}}$: Customer's deployed product version extracted from identity context (`UA-D3`).
- $V_{\text{kb\_index}}$: Cryptographic hash of the tenant's active Qdrant vector index snapshot (`KR-D3`).

#### The Dynamic Version Exclusion Rule ($UK1$)
If user query $Q$ contains explicit semantic version tokens (e.g., matching regex `r"v?[0-9]+\.[0-9]+(\.[0-9]+)?"`), the query is flagged as **Version-Volatile**. Version-volatile queries bypass cache insertion entirely, ensuring that queries discussing transient migration or release upgrades are always dynamically deliberated.

---

### Pillar 3: Invalidation Dynamics & Tombstone Fan-Out (`CR-D3`, `KR-Q3`, `DP-D13`)

Cached entries have a default time-to-live of 7 days (`CR-Q2(ii)`), but undergo immediate reactive eviction under two enterprise triggers:
1. **Nightly Knowledge Base Batch Sync (`KR-D3`)**:
   - When the nightly batch ingestion pipeline completes and increments $V_{\text{kb\_index}}$, all previously cached keys for that tenant become instant cache misses, guaranteeing zero propagation of stale documentation.
2. **Immediate Deletion Tombstone Fan-Out (`DP-D13`)**:
   - If a documentation article is purged or marked with a GDPR deletion tombstone, the Temporal erasure workflow dispatches an eviction event to the semantic cache, purging all keys referencing the affected documentation ID.
3. **Pre-Delivery Safety Verification (`SG-D6`)**:
   - Even on a cache hit, the cached text passes through regex leakage and markdown link sanitizers (`SG-D6`) before wire delivery, ensuring downstream security guarantees remain invariant.

---

## 3. Technical Implementation & Genesis Contracts

```python
"""
core/cost/answer_cache.py
Pydantic v2 schemas and Redis-backed Answer Cache Manager.
"""

import hashlib
import re
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class CacheLookupResult(BaseModel):
    is_hit: bool
    cache_key: str
    cached_content: Optional[str] = None
    ttl_remaining_seconds: Optional[int] = None
    bypass_reason: Optional[str] = None


class AnswerCacheManager:
    """
    Governs per-tenant deterministic answer caching, version-aware key hashing,
    and Jev public-doc eligibility gating (CR-D3, CR-D14).
    """

    VERSION_PATTERN = re.compile(r"\bv?[0-9]+\.[0-9]+(\.[0-9]+)?\b", re.IGNORECASE)
    DEFAULT_TTL_SECONDS = 7 * 24 * 3600  # 7 Days (CR-Q2(ii))

    def __init__(self, redis_client: Any):
        self.redis = redis_client

    def normalize_query(self, query: str) -> str:
        """
        Strips whitespace, punctuation, and standardizes casing.
        """
        normalized = re.sub(r"[^\w\s]", "", query).strip().lower()
        return " ".join(normalized.split())

    def compute_cache_key(
        self,
        query: str,
        tenant_id: str,
        product_version: str,
        kb_index_version: str
    ) -> Optional[str]:
        """
        Computes composite SHA-256 cache key. Returns None if version-volatile (CR-D14, UK1).
        """
        # If user explicitly mentions a version, do not cache (CR-D14)
        if self.VERSION_PATTERN.search(query):
            return None

        normalized_q = self.normalize_query(query)
        payload = f"{normalized_q}|{tenant_id}|{product_version}|{kb_index_version}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def get_cached_answer(
        self,
        query: str,
        tenant_id: str,
        product_version: str,
        kb_index_version: str
    ) -> CacheLookupResult:
        """
        Executes safe per-tenant cache lookup.
        """
        cache_key = self.compute_cache_key(query, tenant_id, product_version, kb_index_version)
        if not cache_key:
            return CacheLookupResult(
                is_hit=False,
                cache_key="",
                bypass_reason="explicit_product_version_in_query"
            )

        redis_key = f"cache:answer:{tenant_id}:{cache_key}"
        cached_val = self.redis.get(redis_key)
        
        if cached_val:
            ttl = self.redis.ttl(redis_key)
            return CacheLookupResult(
                is_hit=True,
                cache_key=cache_key,
                cached_content=cached_val,
                ttl_remaining_seconds=ttl
            )

        return CacheLookupResult(
            is_hit=False,
            cache_key=cache_key
        )

    def store_cached_answer(
        self,
        query: str,
        answer: str,
        tenant_id: str,
        product_version: str,
        kb_index_version: str,
        is_public_doc_eligible: bool  # Output from Jev Noul (CR-D3)
    ) -> bool:
        """
        Persists generated answer if verified as public-doc eligible by Jev (CR-D3).
        """
        if not is_public_doc_eligible:
            return False  # Never cache account-specific facts (MS-D6)

        cache_key = self.compute_cache_key(query, tenant_id, product_version, kb_index_version)
        if not cache_key:
            return False

        redis_key = f"cache:answer:{tenant_id}:{cache_key}"
        self.redis.setex(redis_key, self.DEFAULT_TTL_SECONDS, answer)
        return True

    def invalidate_tenant_cache(self, tenant_id: str) -> int:
        """
        Purges all cached answers for a tenant upon KB re-index or tombstone (KR-Q3, DP-D13).
        """
        pattern = f"cache:answer:{tenant_id}:*"
        keys = self.redis.keys(pattern)
        if keys:
            return self.redis.delete(*keys)
        return 0
```

---

## 4. Failure Modes & Mitigation Matrix

| Failure ID | Sub-Component | Failure Mode Description | Root Cause | Effect on System | Architectural Mitigation (`CR-D3`, `CR-D14`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Failure Matrix Q4** | Cost Optimization | Cross-tenant cache poisoning | Shared semantic cache pool across tenants | Tenant B served malicious or incorrect prompt output from Tenant A | `CR-D3` strictly mandates per-tenant isolated cache namespaces; cross-tenant sharing is prohibited |
| **$UK1$** | Cost Optimization | Cached answer serves outdated version instructions | Key only hashed query text without product release | v4.2 customer receives legacy v3.1 deprecated configuration instructions | `CR-D14` incorporates `ProductVersion` into composite hash and excludes version-explicit queries |
| **$KU2$** | Cost Optimization | Low cache hit rate in production | Enterprise questions exhibit high lexical diversity | Marginal FinOps cost savings | Normalized lemmatization preprocessing; evaluated post-launch via `OB-D13` |
| **$KK1$** | Cost Optimization | Stale policy served after documentation update | Cache persists after Confluence/Zendesk edit | Customer provided deprecated SLA or refund rules | `KR-D3` nightly re-index updates $V_{\text{kb\_index}}$, instantly rendering all stale keys obsolete |
| **$UU1$** | Cost Optimization | PII or account balances leaked via cached answer | Agent stores output from billing query | Other users in same tenant view sensitive account balance | `CR-D3` mandates Jev `Noul` public-doc gating; queries touching CRM tools strictly excluded |

---

## 5. Closed-Loop Telemetry & Verification Directives

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   ANSWER CACHE TELEMETRY & OBSERVABILITY PIPELINE                                │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Incoming Query ──► [ Cache Lookup Gate ] ──► Prometheus: `cost.answer_cache.hit_count`
                              │
                              ├──► [ Cache Miss Reason ] ──► Spans: `cache.bypass_reason`
                              │
                              └──► [ Jev Eligibility Gate ] ──► Metric: `cost.answer_cache.ineligible`
```

### 1. Prometheus Telemetry Indicators
- `cost.answer_cache.requests_total`: Total cache lookup attempts.
- `cost.answer_cache.hits_total`: Total served cache hits.
- `cost.answer_cache.hit_ratio`: $\frac{\text{hits\_total}}{\text{requests\_total}}$ (Target: $20–35\%$ of total traffic).
- `cost.answer_cache.evictions_total`: Total keys invalidated via KB re-indexing and tombstones.

### 2. OpenTelemetry Attributes
- `cache.operation`: `"lookup"` | `"store"` | `"invalidate"`
- `cache.hit`: `boolean`
- `cache.key_hash`: Truncated 8-char SHA-256 key prefix
- `cache.jev_public_eligible`: `boolean`

---

## 6. Alternatives Considered & Trade-Off Analysis

| Architectural Alternative | Technical Mechanism | Why Rejected / Trade-Off Analysis |
| :--- | :--- | :--- |
| **Global Shared Semantic Cache (Option A)** | Cross-tenant cosine-similarity cache on vector embeddings | **Rejected (Failure Matrix Q4)**: Massive security vulnerability; creates cross-tenant prompt injection vectors and leaks private policy nuances across competing organizations. |
| **Query-Only Hashing (Option B)** | Key calculated purely on question text hash | **Rejected ($UK1$)**: Causes catastrophic version-drift bugs, serving outdated procedures to users on newer software versions. |
| **Zero Caching / 100% Neural Generation (Option C)** | Disable caching entirely; recompute all responses | **Rejected**: Wastes $30\%$ of token budgets on trivial procedural queries and adds $3.5\text{s}$ unnecessary latency to common FAQ lookups. |
| **24-Hour Cache TTL (CR-Q2(iii))** | Restrict cache lifetime to 24 hours | **Rejected per CR-Q2(ii)**: Enterprise documentation is stable over weekly cycles; 7-day TTL with proactive tombstone invalidation yields $3\times$ higher hit rates. |

---

## 7. References & Academic Foundations

1. **Chen, L., Zaharia, M., & Zou, J.** (2023). *FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance.* arXiv preprint arXiv:2305.05176.
2. **Redis Enterprise Documentation.** (2024). *Semantic Caching and Cache-Aside Design Patterns in Generative AI.*
3. **NIST Special Publication 800-88, Rev. 1.** (2014). *Guidelines for Media Sanitization.* Cache Purging Controls.
4. **GDPR Article 17.** (2016). *Right to Erasure ('Right to be Forgotten').* Cache Invalidation and Tombstone Propagation.
