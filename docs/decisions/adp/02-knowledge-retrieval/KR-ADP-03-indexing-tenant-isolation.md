# KR-ADP-03: Indexing & Tenant Isolation (Dual-Index Topology & Hybrid On-Behalf-Of ACL Verification)

- **Status**: Accepted & Confirmed
- **Date**: 2026-09-24
- **Deciders**: Architecture Team, Lead Security Architect, Data Privacy Core
- **Component**: `[2] Knowledge & Retrieval` (`Component [ 2 ]`)
- **Reasoning Source**: `checkpoint.md` §6 · Diagram: `LLD - [2] Knowledge & Retrieval`
- **Decisions Covered**:
  - `KR-D5`: Tenant Isolation — Shared Global/Public Index + Per-Tenant Private Index (Queried Together; `T0` Anonymous Hits Public Index Only)
  - `KR-D6`: ACL Enforcement — Copied ACL Metadata at Ingestion + Live OBO Permission Check for Restricted Documents
- **Related Architectural Decision Points**:
  - [`DP-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#dp-adp-01--store-topology--residency): Store Topology & Residency *(Multi-Region Vector Placement)*
  - [`DP-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#dp-adp-02--tenant-isolation--encryption): Tenant Isolation & Encryption *(KMS Encryption per Tenant)*
  - [`SG-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#sg-adp-04--authorization--tool-permissions): Authorization & Tool Permissions *(Token Scoping & ACL Policies)*
  - [`UA-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/01-user-application/UA-ADP-02-identity-downstream-tokens.md): Identity & Downstream Tokens *(RFC 8693 On-Behalf-Of Tokens)*

---

## 1. Context & Problem Statement

Multi-tenant enterprise Retrieval-Augmented Generation (RAG) systems handle a mixture of globally public knowledge (official documentation, API references, product release notes) and deeply sensitive, tenant-isolated proprietary data (internal support tickets, custom SLA contracts, private postmortems).

In multi-tenant vector databases, naive indexing architectures encounter severe architectural vulnerabilities:
1. **The Shared-Index Vector Poisoning & Bleed Hazard (OWASP LLM08)**: Storing all enterprise tenants within a single shared vector collection filtered solely by metadata tags (`tenant_id == 'acme'`) creates a catastrophic security surface. A subtle software bug, malformed query filter, or HNSW vector graph traversal bypass allows Tenant A to retrieve private support tickets belonging to Tenant B ($KK2$).
2. **Access Control List (ACL) Staleness vs. Query Latency**: Document permissions in upstream source systems (Confluence, Google Drive, Jira) mutate dynamically. If ACLs are copied only during ingestion, revoked permissions remain stale for up to 24 hours. Conversely, validating live permissions across 50 candidate documents at query time via external HTTP APIs introduces 300–800ms of latency, severely degrading user experience.
3. **Anonymous Ingress Privilege Escalation ($KK4$)**: An unauthenticated user (`T0_ANON`) browsing public documentation could manipulate API query parameters to execute searches against private tenant collections if isolation is enforced purely at the application layer.

### The Core Architectural Question
> **How are enterprise tenants structurally isolated in vector and keyword indexes to prevent cross-tenant information bleed, and how does the retrieval engine enforce fine-grained document access control without incurring crippling latency overhead?**

---

## 2. Decision Framework & Theoretical Formulation

We formulate our indexing and isolation architecture upon three theoretical pillars: **OWASP LLM08 Physical Separation Formalism**, **Hybrid Fast-Path / Live-Path Access Control Calculus**, and **Token-Bound Tenant Scoping Invariants**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             ISOLATION THEORETICAL PILLARS                                        │
├────────────────────────────────┬────────────────────────────────┬────────────────────────────────┤
│   Pillar A: OWASP LLM08        │   Pillar B: Hybrid ACL         │   Pillar C: Token-Bound        │
│   Dual-Index Partitioning      │   Calculus & Live OBO Checks   │   Tenant Verification          │
│                                │                                │                                │
│   • Shared Public Index I_pub  │   • Fast path: Ingested ACLs   │   • Tenant extracted from OBO  │
│   • Isolated Private Index I_t │   • Live path: Restricted docs │     token (never request body) │
│   • Physical namespace boundary│   • P(Restricted) ≤ 0.05       │   • Anonymous T0 restricted    │
│   • Zero cross-tenant bleed    │   • Bound latency while safe   │     strictly to I_pub (KK4)    │
└────────────────────────────────┴────────────────────────────────┴────────────────────────────────┘
```

---

### Pillar A: OWASP LLM08 Dual-Index Topology (Public vs. Private)

Following **OWASP Top 10 for LLM Applications (2025) LLM08 "Vector and Embedding Weaknesses"**, multi-tenant isolation requires strict physical or structural segregation:
- **Shared Global/Public Index ($\mathcal{I}_{\text{public}}$)**:
  - Contains: Canonical documentation, release notes, verified bug workarounds, public FAQs.
  - Access Model: Read-only to all authenticated users and `T0_ANON` anonymous visitors.
  - Sizing & Infrastructure: Optimized for high-throughput global caching and multi-region replication.
- **Per-Tenant Isolated Private Index ($\mathcal{I}_{\text{private}}^{(T)}$)**:
  - Contains: Historical support tickets, private incident postmortems, proprietary architecture runbooks, and customer-specific account notes (`KR-Q1`).
  - Access Model: Strictly restricted to principals authenticating with verified credentials belonging to Tenant $T$.
  - Separation Guarantee: Enforced via **dedicated Qdrant collection namespaces or isolated physical collections** (`DP-ADP-02`). Cross-tenant graph traversals are physically impossible at the database engine level.

#### The Dual-Query Fusion Equation
When an authenticated enterprise user belonging to Tenant $T$ with assurance level $\mathcal{A} \ge \text{T1}$ submits query $Q$, the retrieval engine queries both collections concurrently:

$$\mathcal{C}_{\text{candidates}} = \text{Query}(\mathcal{I}_{\text{public}}, Q) \;\cup\; \text{Query}(\mathcal{I}_{\text{private}}^{(T)}, Q)$$

If the user is an anonymous visitor ($\mathcal{A} = \text{T0}$), the private query is suppressed unconditionally:

$$\text{If } \mathcal{A} == \text{T0} \implies \mathcal{C}_{\text{candidates}} \equiv \text{Query}(\mathcal{I}_{\text{public}}, Q) \quad (\textbf{Fixes KK4})$$

---

### Pillar B: Hybrid Fast-Path / Live-Path Access Control Calculus

Enterprise documents fall into two distinct security classes:
1. **Public / Tenant-Wide Documents ($D_{\text{standard}}$)**: Visible to all authorized employees of tenant $T$ (e.g., standard internal engineering runbooks).
2. **Restricted Confidential Documents ($D_{\text{restricted}}$)**: Restricted to specific user groups or security classifications (e.g., executive compensation policies, customer audit reports, legal holds).

#### Mathematical Latency vs. Freshness Optimization
Let $N_{\text{candidates}} = 50$ represent the top first-stage retrieval candidates. Performing live HTTP permission introspection across all 50 candidates requires:

$$T_{\text{live\_all}} = 50 \cdot t_{\text{api}} \approx 50 \cdot 25\text{ms} = \mathbf{1,250\text{ms}} \quad (\text{Unacceptable Latency})$$

We formulate a **Hybrid Permission Evaluation Function** (`KR-D6`):
- During ingestion, documents are stamped with an explicit boolean flag: $\texttt{is\_restricted} \in \{0, 1\}$ and initial group ACLs.
- At query time:
  - **Fast-Path**: If $\texttt{is\_restricted} == 0$, evaluate the copied ACL metadata against user claims locally in memory ($t < 1\text{ms}$).
  - **Live-Path**: If $\texttt{is\_restricted} == 1$, dispatch an asynchronous parallel live permission check against the upstream source system (Confluence/Jira/Google Drive) using the user's RFC 8693 On-Behalf-Of (OBO) token (`UA-D4`).

Because restricted documents represent a small fraction of the corpus ($P(D \in D_{\text{restricted}}) \le 0.05$):

$$\mathbb{E}[N_{\text{live}}] = N_{\text{candidates}} \cdot P(\text{Restricted}) \approx 50 \cdot 0.05 = \mathbf{2.5 \text{ live checks}}$$

Parallel asynchronous execution bounds live permission latency to a single HTTP round-trip ($T_{\text{live}} \le 35\text{ms}$), achieving 100% authorization freshness on sensitive assets without penalizing common-path performance.

---

### Pillar C: Token-Bound Tenant Verification Invariants

A critical failure mode in distributed multi-tenant systems is the **Request-Parameter Spoofing Vulnerability ($KK2$)**: an authenticated user belonging to Tenant A supplies a query payload containing `{"tenant_id": "tenant_B"}`. If the retrieval service uses the payload parameter to select the vector collection, cross-tenant data leaks immediately.

#### Strict Token-Bound Assertion Invariant
The retrieval service **strictly rejects any tenant identifier passed in the HTTP JSON body or query string**.

$$\text{Active Tenant } T \equiv \text{ExtractClaim}(\text{VerifiedJWT}, \texttt{"tenant\_id"})$$

$$\text{If } \text{Payload}.\texttt{tenant\_id} \neq T \implies \text{Raise } \texttt{SecurityBreachException} \land \text{Emit Security Alert}$$

The vector database collection name is synthesized programmatically from the cryptographically verified JWT claims, guaranteeing zero spoofing.

---

## 3. Decision Rules & System Architecture

### Architectural Decision

1. **Dual-Index Layout (`KR-D5`)**:
   - Maintain a shared **Global Public Index** (`public_knowledge_v1`) containing public documentation and release notes.
   - Maintain an isolated **Private Tenant Index** (`tenant_{tenant_id}_private_v1`) per enterprise customer.
   - Anonymous `T0` users are physically restricted to `public_knowledge_v1` (`KK4` fixed). Authenticated users query both public and their own private index concurrently.
2. **Hybrid ACL Enforcement (`KR-D6`)**:
   - Ingested documents copy source ACL metadata for high-speed local filtering.
   - Documents flagged with `is_restricted = True` undergo a mandatory **Live OBO Permission Check** using the end-user's delegated RFC 8693 token before being admitted to the reranker.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   DUAL-INDEX TOPOLOGY & HYBRID ACL ENFORCEMENT                                   │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                   │
                                     [Incoming Retrieval Request]
                                                   │
                                                   v
                                   ┌───────────────────────────────┐
                                   │  Token-Bound Identity Parser  │
                                   │  Extracts tenant_id & tier    │
                                   └───────────────┬───────────────┘
                                                   │
                     ┌─────────────────────────────┴─────────────────────────────┐
                     │ [T0 Anonymous User]                                       │ [T1 / T2 Authenticated User]
                     v                                                           v
          ┌──────────────────────┐                                    ┌──────────────────────┐
          │ Shared Public Index  │                                    │ Shared Public Index  │
          │ (Documentation/Docs) │                                    │ (Documentation/Docs) │
          └──────────┬───────────┘                                    └──────────┬───────────┘
                     │                                                           │
                     │                                                           ├──────────────────────────┐
                     │                                                           │                          │
                     │                                                           v                          v
                     │                                                ┌──────────────────────┐   ┌──────────────────────┐
                     │                                                │ Private Tenant Index │   │ Copied Ingested ACLs │
                     │                                                │ tenant_{id}_private  │   │ Fast-path local filter│
                     │                                                └──────────┬───────────┘   └──────────┬───────────┘
                     │                                                           │                          │
                     │                                                           └───────────┬──────────────┘
                     │                                                                       │
                     │                                                                       v
                     │                                                        ┌─────────────────────────────┐
                     │                                                        │ is_restricted == True?      │
                     │                                                        └──────────────┬──────────────┘
                     │                                                                       │
                     │                                                   ┌───────────────────┴───────────────────┐
                     │                                                   │ [Yes]                                 │ [No]
                     │                                                   v                                       v
                     │                                        ┌─────────────────────┐                 ┌─────────────────────┐
                     │                                        │ Live OBO Check via  │                 │ Pass Directly to    │
                     │                                        │ Source API (UA-D4)  │                 │ RRF Fusion Stage    │
                     │                                        └──────────┬──────────┘                 └──────────┬──────────┘
                     │                                                   │                                       │
                     └───────────────────────────────────────────────────┼───────────────────────────────────────┘
                                                                         │
                                                                         v
                                                            [Admitted Candidate Passages]
```

---

### Concrete Genesis Implementation Contracts

#### 1. Tenant-Isolated Index Coordinator (`core/knowledge/indexing.py`)

```python
from typing import List, Dict, Any, Optional
from core.identity.models import IdentityContext, AssuranceTier
from core.persistence.vector_store import QdrantStoreManager

class TenantIsolatedIndexCoordinator:
    def __init__(self, vector_store: QdrantStoreManager):
        self.vector_store = vector_store
        self.public_collection_name = "public_knowledge_v1"

    async def execute_isolated_query(
        self,
        query_vector: List[float],
        query_sparse: Dict[str, float],
        identity: IdentityContext,
        top_k: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Enforces KR-D5: Physical dual-index routing bound to verified JWT identity.
        """
        # 1. Query Shared Public Index (Always allowed)
        public_candidates = await self.vector_store.query_collection(
            collection_name=self.public_collection_name,
            dense_vector=query_vector,
            sparse_vector=query_sparse,
            limit=top_k
        )

        # 2. Enforce KK4: Anonymous T0 users are barred from private indexes
        if identity.assurance_tier == AssuranceTier.T0_ANON:
            return public_candidates

        # 3. Derive Tenant Collection strictly from Token (KK2 Mitigation)
        tenant_private_collection = f"tenant_{identity.tenant_id}_private_v1"

        # 4. Query Tenant Private Index concurrently
        private_candidates = await self.vector_store.query_collection(
            collection_name=tenant_private_collection,
            dense_vector=query_vector,
            sparse_vector=query_sparse,
            limit=top_k
        )

        return public_candidates + private_candidates
```

#### 2. Hybrid ACL Enforcement Validator (`core/knowledge/acl_checker.py`)

```python
import httpx
from typing import List, Dict, Any
from core.identity.models import IdentityContext

class HybridACLValidator:
    def __init__(self, auth_service_url: str):
        self.auth_service_url = auth_service_url

    async def filter_authorized_passages(
        self,
        candidates: List[Dict[str, Any]],
        identity: IdentityContext,
        obo_token: str
    ) -> List[Dict[str, Any]]:
        """
        Enforces KR-D6: Copied metadata check for standard docs + live OBO check for restricted docs.
        """
        authorized_passages = []
        restricted_to_check = []

        for cand in candidates:
            # Fast-Path: Standard tenant-wide documents
            if not cand.get("is_restricted", False):
                # Verify local copied ACL groups
                allowed_groups = cand.get("acl_groups", [])
                if not allowed_groups or any(g in identity.roles for g in allowed_groups):
                    authorized_passages.append(cand)
            else:
                # Live-Path: Confidential document requiring upstream check
                restricted_to_check.append(cand)

        # Execute parallel live permission checks for restricted subset
        if restricted_to_check:
            verified_restricted = await self._verify_live_permissions(
                restricted_to_check,
                obo_token
            )
            authorized_passages.extend(verified_restricted)

        return authorized_passages

    async def _verify_live_permissions(
        self,
        restricted_docs: List[Dict[str, Any]],
        obo_token: str
    ) -> List[Dict[str, Any]]:
        """Invokes upstream source API using RFC 8693 on-behalf-of token."""
        doc_ids = [d["doc_id"] for d in restricted_docs]
        headers = {"Authorization": f"Bearer {obo_token}"}
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.auth_service_url}/check-permissions",
                json={"document_ids": doc_ids},
                headers=headers,
                timeout=2.0
            )
            if response.status_code == 200:
                allowed_ids = set(response.json().get("allowed_document_ids", []))
                return [d for d in restricted_docs if d["doc_id"] in allowed_ids]
            return []  # Fail-safe: drop restricted docs on permission check error
```

---

## 4. Knowing Your Unknowns: Failure Modes & Mitigation Matrix

| Quadrant | Failure Mode | Technical Risk Description | Concrete Architectural Mitigation |
| :--- | :--- | :--- | :--- |
| **Q1: Known Knowns** *(Deterministic Contract Breaches)* | **Wrong Tenant Query ($KK2$)** | Bug takes `tenant_id` from request JSON body instead of token, leaking data. | **Token-Bound Identity Invariant**: Collection name is synthesized strictly from verified JWT `tenant_id`. |
| **Q1: Known Knowns** *(Deterministic Contract Breaches)* | **Anonymous Private Access ($KK4$)** | Anonymous user queries tenant private index. | **Assurance Tier Guard**: `T0_ANON` tier suppresses private collection queries unconditionally. |
| **Q1: Known Knowns** *(Deterministic Contract Breaches)* | **Embedding Model Drift ($KK5$)** | New embedder deployed without re-indexing; similarity search becomes meaningless. | **Index Version Stamp**: Collection metadata embeds model version (`embedder_v2`); rejects queries from mismatched versions. |
| **Q2: Known Unknowns** *(Probabilistic Reasoning Variance)* | **Upstream ACL API Latency** | Source system permissions API experiences latency spike during live check. | **Bounded Timeout & Fallback**: Live check timeout is 2.0s; on timeout, restricted docs are safely dropped (fail-closed). |
| **Q3: Unknown Knowns** *(Tacit Enterprise Etiquette & Invariants)* | **Within-Tenant Privacy Leaks ($UK3$)** | Acme-corp user queries private tickets and sees a colleague's confidential HR ticket. | **User-Level Copied ACLs**: Tickets copy creator user ID and department tags; local filter screens non-HR users. |
| **Q4: Unknown Unknowns** *(Emergent Cascades & Black Swans)* | **Vector Inversion Leaks via Cross-Namespace Attack** | Vulnerability in vector DB kernel allows memory reading across collection boundaries. | **Physical Storage Isolation (`DP-ADP-02`)**: High-compliance enterprise tenants receive physically separate Qdrant clusters. |

---

## 5. Closed-Loop Feedback & Telemetry Integration

1. **Dual-Index Latency & Ratio Metrics**:
   - Prometheus histograms track latency across public vs. private index searches ($P_{99} \le 18\text{ms}$).
2. **Live Permission Audit Logging**:
   - Every live ACL check logs the requesting user, target document, and decision to the audit log (`DP-ADP-03`).
   - If live permission rejection rate exceeds 15% on a specific document, an automated alert flags possible stale ACL metadata.

---

## 6. Genesis Implementation Directives

### Target File Manifest
1. `core/knowledge/indexing.py`: `TenantIsolatedIndexCoordinator` managing dual-collection query routing.
2. `core/knowledge/acl_checker.py`: `HybridACLValidator` executing fast-path local checks and live OBO checks.
3. `tests/test_tenant_isolation.py`: Unit tests verifying that anonymous tokens cannot reach private collections.

### Scaffolding Verification Criteria
- [ ] **Token-Bound Enforcement Test**: Supplying `tenant_id = "tenant_B"` in the JSON payload of a `tenant_A` user queries `tenant_A_private` exclusively.
- [ ] **T0 Anonymous Suppression Test**: Calling the coordinator with a `T0_ANON` context asserts that zero private collections are contacted.
- [ ] **Live ACL Fail-Closed Test**: Simulating an HTTP 500 error on the live ACL checker causes all restricted documents to be dropped.

---

## 7. Consequences & Trade-offs

### Positive Consequences
- **Absolute Elimination of Cross-Tenant Data Leaks**: Dedicated private indexes guarantee that multi-tenant vector collisions cannot occur.
- **Zero Ingress Escalation Hazards**: Anonymous visitors are structurally barred from private knowledge assets.
- **Sub-20ms Search Velocity on Common Paths**: Fast-path local metadata checks keep standard retrieval latency under 20ms.
- **Real-Time Security on Sensitive Assets**: Live OBO verification guarantees zero permission staleness on confidential documents.

### Negative / Neutral Trade-offs & Mitigations
- **Operational Collection Management**: Operating thousands of Qdrant collections increases vector DB metadata memory.  
  *Mitigation*: Shared public index absorbs 80% of total document volume; private collections hold compact ticket indices.
- **Upstream Source API Dependencies**: Live checks depend on the uptime of Confluence/Jira APIs.  
  *Mitigation*: Fail-closed architecture ensures that source API outages drop restricted documents rather than failing open.

---

## 8. References

1. **OWASP Foundation (2025)**. *Top 10 for Large Language Model Applications: LLM08 Vector and Embedding Weaknesses*.
2. **IETF (2020)**. *OAuth 2.0 Token Exchange (RFC 8693)*. Internet Engineering Task Force.
3. **Malkov, Y. A., & Yashunin, D. A. (2018)**. *Efficient and robust approximate nearest neighbor search using Hierarchical Navigable Small World graphs*. IEEE TPAMI.
