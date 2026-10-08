# SG-ADP-05: Governance, Retention & Providers (EU AI Act Transparency, 2-Year Legal Transcript Archive & GDPR Art. 22 Significant Decision Safeguards)

- **Status**: Accepted & Confirmed
- **Date**: 2026-09-30 *(Amended: 2026-09-30 per SG-D11 Provider Terms, SG-D12 2-Year Archive, SG-D13 Dual "Why" Views, SG-D14 Significant Decisions & SG-Q2/Q4/Q5)*
- **Deciders**: Architecture Team, General Counsel, Chief Compliance Officer
- **Component**: `[6] Safety, Security & Governance` (`Component [ 6 ]`)
- **Reasoning Source**: `checkpoint.md` §10 · Diagram: `LLD - [6] Safety, Security & Governance`
- **Decisions Covered**:
  - `SG-D11`: Provider Terms & Zero-PII Ingestion — Standard API terms with commercial LLM and Jev providers; risk neutralized by upstream reversible tokenization (`SG-D4`): vendors process surrogate tokens only; business text retention accepted ($UU4$)
  - `SG-D12`: Legal Transcript Archive & Two-Year Retention — Conversational transcripts preserved for $2$ years (`SG-Q2`) in an access-restricted legal archive store; GDPR Article 17 erasures purge transcripts from all agent-usable memory and vector indexes while preserving legal dispute records under GDPR Art. 17(3)(e) (*Moffatt v. Air Canada*)
  - `SG-D13`: Decision Recording & Dual-Persona "Why" Views — Comprehensive logging of all automated decisions (Jev answers, confidence, Cedar policies, model versions); user-facing "Why" view shows plain-language reasons and checks passed without exposing internal thresholds or prompt text (`SG-Q4`); specialists receive full forensic traces
  - `SG-D14`: AI Disclosure & Mandatory Human Review for Significant Effects — Full compliance with EU AI Act Art. 50 (omnipresent AI disclosure) and GDPR Art. 22; "Talk to a Human" option always available; mandatory human review for a fixed list of significant decisions: account suspension, dispute/refund rejection, and contract changes (`SG-Q5`)
- **Related Architectural Decision Points**:
  - [`DP-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#dp-adp-03--audit-archive--settings): Audit, Archive & Settings Data *(Encrypted Compliance Archive)*
  - [`HL-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp_index.md#hl-adp-04--action-approval--presentation): Action Approval & Presentation *(Human Review Interface)*
  - [`MS-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/03-memory-state/MS-ADP-05-retention-erasure.md): Memory Retention & Erasure *(Erasure Cascades vs. Legal Archives)*
  - [`UA-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/01-user-application/UA-ADP-01-channels-api-transport.md): Channels & API Transport *(Client-Side Disclosure Banners)*

---

## 1. Context & Problem Statement

Deploying fully autonomous AI agents in enterprise customer-facing environments triggers strict statutory compliance obligations across global jurisdictions:
1. **EU AI Act (Regulation EU 2024/1689, Article 50)**: Mandates that deployers of generative AI systems ensure that natural persons are informed that they are interacting with an AI system, with clear options to access human representatives.
2. **GDPR Article 22 (Automated Decision-Making Rights)**: Grants data subjects the right not to be subject to a decision based solely on automated processing which produces legal or similarly significant effects (e.g., terminating services, refusing refund claims, or canceling subscription contracts) without the right to human intervention.
3. **The Legal Evidence Preservation Mandate (*Moffatt v. Air Canada*, 2024)**: Automated chat transcripts constitute primary documentary evidence in contractual and commercial disputes. If an enterprise completely deletes chat logs upon a standard GDPR erasure request, it loses all documentary evidence to defend itself against false breach-of-contract or fraud claims.
4. **The "Why" View Reconnaissance Vulnerability ($UU3$)**: GDPR Article 22 requires providing "meaningful information about the logic involved". However, exposing raw model confidence scores, prompt weights, or internal policy rules directly to end users enables adversarial actors to probe and reverse-engineer security guardrails.

### The Core Architectural Question
> **How do we establish a compliant governance framework that enforces EU AI Act disclosures, guarantees human review for legally significant decisions, preserves dispute transcripts for 2 years without violating GDPR erasure rights, and provides explainability without leaking internal guardrails?**

---

## 2. Decision Framework & Theoretical Formulation

To solve these challenges, we establish the **Dual-View Governance Architecture with Compliant Legal Archiving**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                            GOVERNANCE & COMPLIANCE ARCHITECTURE (SG-D12, SG-D14)                 │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                                    CUSTOMER INTERACTION
                                                │
                                                ▼
                             ┌──────────────────────────────────────┐
                             │ EU AI Act Article 50 Disclosure      │
                             │ • Omnipresent Header: "AI Assistant" │
                             │ • "Talk to a Human" Button ALWAYS on │
                             └──────────────────────────────────────┘
                                                │
                                                ▼
                             ┌──────────────────────────────────────┐
                             │ Decision Classification Gate (SG-D14)│
                             │ Is action in "Significant List"?     │
                             │ [Account Close, Dispute Reject, Plan]│
                             └──────────────────────────────────────┘
                                                │
                       ┌────────────────────────┴────────────────────────┐
                       │ YES (Significant Impact)                        │ NO (Standard Query)
                       ▼                                                 ▼
        ┌─────────────────────────────┐                   ┌─────────────────────────────┐
        │ MANDATORY HUMAN SPECIALIST  │                   │ Autonomous AI Resolution    │
        │ GDPR Article 22 Sign-Off    │                   │ Emits Dual-View "Why" Record│
        │ Agent cannot execute alone  │                   │ (SG-D13)                    │
        └─────────────────────────────┘                   └─────────────────────────────┘
                                                                         │
                                                                         ▼
                                                          ┌─────────────────────────────┐
                                                          │ 2-Year Legal Archive (SG-D12)│
                                                          │ Encrypted Compliance WORM   │
                                                          │ Excluded from Agent Memory  │
                                                          └─────────────────────────────┘
```

---

### Pillar A: Dual-Tier "Why" Explainability Architecture (`SG-D13` / $UU3$)

To satisfy GDPR Article 22 explainability while neutralizing attacker reconnaissance ($UU3$), the system projects decision records through two strictly segregated views:

$$\text{DecisionRecord} = \langle \text{id}, t, \text{action}, \mathcal{R}_{\text{plain}}, \mathcal{C}_{\text{checks}}, \mathcal{S}_{\text{scores}}, \mathcal{P}_{\text{policy\_text}} \rangle$$

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             DUAL-VIEW EXPLAINABILITY LATTICE (SG-D13)                            │
├─────────────────────────────────────────────────┬────────────────────────────────────────────────┤
│   USER-FACING "WHY" PROJECTION (π_user)         │   SPECIALIST-FACING AUDIT PROJECTION (π_spec)  │
├─────────────────────────────────────────────────┼────────────────────────────────────────────────┤
│   • Plain-language business rationale:          │   • Full unredacted decision trace             │
│     "Account upgrade requires verified payment" │   • Raw Jev scores and confidence probabilities│
│   • List of high-level checks evaluated:        │   • Exact Cedar policy rule ASTs               │
│     ["Identity verification", "Balance check"]  │   • Classifier hazard risk scores (Llama Guard)│
│   • SUPPRESSED: Scores, thresholds, raw prompts │   • Model IDs, git commit hashes, prompt vers  │
│   • Prevents attacker probe tuning (UU3 Fixed)  │   • Comprehensive forensic analysis capability │
└─────────────────────────────────────────────────┴────────────────────────────────────────────────┘
```

---

### Pillar B: Two-Year Legal Archive vs. GDPR Erasure (`SG-D12`, `SG-Q2`)

We resolve the tension between *Moffatt v. Air Canada* and GDPR Article 17 through **Statutory Segregation**:

$$\text{Chat Transcript Lifespan} = \begin{cases}
\text{Agent-Usable Memory (Postgres/Qdrant)} & \implies \text{Purged Immediately on Erasure Webhook} \\
\text{Legal Compliance Archive (S3 WORM)} & \implies \text{Retained Strictly for 2 Years (730 Days)}
\end{cases}$$

1. **Article 17(3)(e) Legal Exception**: Transcripts are retained under GDPR Art. 17(3)(e), which explicitly exempts personal data necessary for *"the establishment, exercise or defence of legal claims"*.
2. **Agent-Facing Amnesia**: Upon an erasure event (`MS-ADP-05`), all embeddings, conversation threads, rolling summaries, and user facts are expunged. The agent completely forgets the user.
3. **Restricted Archive Access**: Legal transcripts are isolated in an encrypted S3 Object Lock vault (`DP-ADP-03`). Access requires dual-authorization sign-off from General Counsel; zero agent models or operational workflows possess read access.

---

### Pillar C: Significant Decision Human Review Gate (`SG-D14`, `SG-Q5`)

Under GDPR Article 22, automated systems may not unilaterally impose significant negative legal effects.
We compile an immutable **Significant Decision Allow-List** (`SG-Q5`):

$$\mathcal{D}_{\text{significant}} = \left\{ 
\text{"account\_suspension"}, \text{"account\_termination"}, 
\text{"dispute\_rejection"}, \text{"refund\_denial"}, 
\text{"contract\_downgrade"}, \text{"sla\_breach\_denial"}
\right\}$$

#### Architectural Invariant
$$\forall a \in \text{ProposedActions}, \quad a.\text{type} \in \mathcal{D}_{\text{significant}} \implies \text{ExecutionMode}(a) = \text{MANDATORY\_HUMAN\_REVIEW}$$
- The agent may investigate, assemble diagnostic packets, and propose an action.
- The agent is **structurally incapable** of executing a rejection or termination autonomously; the decision must route to a human specialist queue with an interactive sign-off card (`HL-ADP-04`).

---

### Pillar D: Provider Terms & Token-Only Exposure (`SG-D11`)

We adopt standard commercial enterprise terms for external foundation model APIs (OpenAI, Anthropic, TypeSafe Jev):
1. **Surrogate Tokenization**: Because all personal data is tokenized into format-preserving surrogate tokens at ingress (`SG-ADP-02`), external model providers process tokens (`<EMAIL_8a9f2b1c>`), never cleartext PII.
2. **Accepted Residual ($UU4$)**: Technical business context (syslogs, SQL schemas) is processed under standard enterprise terms (zero model training, 30-day vendor security retention). This residual risk was formally approved by General Counsel given upstream tokenization safeguards.

---

## 3. Decision Rules, Structural Invariants & Code Contracts

### Decision Invariants
1. **Invariant 1 (Disclosure Omnipresence)**: Every customer conversational interface must present a persistent banner stating that the service utilizes artificial intelligence.
2. **Invariant 2 (Human Handoff Inviolability)**: The "Talk to a Human" escape route must be permanently selectable on every turn, bypassing all automated conversational loops.
3. **Invariant 3 (Significant Action Autonomy Ban)**: The runtime statechart must reject any attempt by an autonomous agent to finalize an account closure or dispute rejection without a signed human specialist token.
4. **Invariant 4 (WORM Archive Isolation)**: The legal transcript archive must reside in a separate AWS IAM boundary with zero API keys shared with the active agent execution runtime.

---

### Python & Pydantic Data Contracts

```python
"""
Data contracts for Governance, Explainability, and Regulatory Compliance.
Module: core/safety/governance.py
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class SignificantDecisionCategory(str, Enum):
    ACCOUNT_SUSPENSION = "account_suspension"
    DISPUTE_REJECTION = "dispute_rejection"
    REFUND_DENIAL = "refund_denial"
    CONTRACT_CHANGE = "contract_change"


class UserWhyView(BaseModel):
    """Sanitized explainability payload presented to end customers (SG-Q4)."""
    case_id: str
    decision_summary: str = Field(..., description="Plain-language justification")
    checks_evaluated: List[str] = Field(..., description="High-level policy gates verified")
    requires_human_review: bool
    human_support_available: bool = Field(default=True)


class SpecialistAuditView(BaseModel):
    """Full forensic diagnostic payload presented to internal specialists and auditors."""
    case_id: str
    decision_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Internal evaluation metadata
    jev_answers: Dict[str, Any]
    jev_confidences: Dict[str, float]
    cedar_policy_evaluations: List[Dict[str, Any]]
    classifier_hazard_scores: Dict[str, float]
    
    # System provenance
    model_version_ids: Dict[str, str]
    system_prompt_commit_sha: str
    code_release_version: str


class LegalTranscriptArchiveEnvelope(BaseModel):
    """Archival container preserved for 2 years in encrypted WORM storage (SG-D12)."""
    archive_id: str
    case_id: str
    tenant_id: str
    principal_id: str
    
    conversation_start_at: datetime
    conversation_end_at: datetime
    retention_expires_at: datetime = Field(..., description="Exactly 2 years from close")
    
    raw_transcript_json: str = Field(..., description="AES-256-GCM encrypted transcript payload")
    legal_hold_active: bool = Field(default=False)
```

---

## 4. Failure Modes Matrix & Resilience Invariants

| Quadrant | Failure Scenario | Detection Mechanism | Systemic Mitigation & Recovery |
| :--- | :--- | :--- | :--- |
| **Q1: Known Knowns** | **Autonomous Dispute Rejection ($SG-D14$)**: Agent rejects a customer's billing refund dispute without human review, violating GDPR Art. 22. | Action validation engine intercepts `dispute_rejection` tool call. | Hard invariant: Significant decisions require human sign-off (`SG-D14`); action is converted to an approval card for specialist review. |
| **Q2: Known Unknowns** | **The "Why" View Reconnaissance Probe ($UU3$)**: Attacker analyzes decision responses to map internal threshold cutoffs. | Explainability serializer inspects outbound `UserWhyView`. | User projection ($\pi_{\text{user}}$) strips all scores, probabilities, and policy syntax (`SG-Q4`); customer sees only high-level business reasons. |
| **Q3: Unknown Knowns** | **Premature Legal Archive Destruction**: Standard user deletion job expunges legal dispute records needed for ongoing arbitration. | Erasure coordinator checks storage target against `ErasureTargetStore`. | Legal archive is isolated from standard memory erasure routines (`SG-D12`); retained for 2 years under GDPR Art. 17(3)(e). |
| **Q4: Unknown Unknowns** | **Vendor Policy Change on Data Retention ($UU4$)**: External model provider changes Terms of Service to retain prompt logs longer. | Compliance legal monitoring and tokenization safeguards. | Upstream tokenization (`SG-ADP-02`) ensures vendor sees surrogate tokens only; prompt logs contain zero customer personal data. |

---

## 5. Closed-Loop Feedback & Verification Signals

1. **Compliance Health Metrics**:
   - `Significant_Decision_Human_Handoff_Rate`: Asserts that $100\%$ of significant actions route through human review.
   - `Human_Escalation_Button_Click_Volume`: Monitored per route; tracks customer demand for human assistance.
   - `Legal_Archive_Retention_Sweeper_Volume`: Verifies that 2-year-old transcripts are expunged precisely upon expiration.
2. **Quarterly GDPR Article 22 & EU AI Act Audit**:
   - Independent compliance audit reviews $200$ automated case trajectories, verifying explicit AI disclosure banners, human option availability, and explainability records.

---

## 6. Genesis Implementation Directives

1. **Code Locations**:
   - Implement the dual-view explainability engine in `core/safety/explainability.py`.
   - Implement the significant decision gate in `core/safety/significant_decisions.py`.
   - Implement the legal archive repository in `core/safety/legal_archive.py`.
   - Implement UI disclosure metadata in `api/serializers/governance_serializers.py`.
2. **Database Directives**:
   - Create legal archive metadata table in `db/migrations/006_legal_archive.sql`:
     ```sql
     CREATE TABLE legal_transcript_archive (
         archive_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
         case_id VARCHAR(64) NOT NULL,
         tenant_id VARCHAR(64) NOT NULL,
         principal_id VARCHAR(128) NOT NULL,
         s3_worm_uri TEXT NOT NULL,
         retained_until TIMESTAMPTZ NOT NULL,
         legal_hold BOOLEAN DEFAULT FALSE,
         created_at TIMESTAMPTZ DEFAULT NOW()
     );
     CREATE INDEX idx_legal_retention ON legal_transcript_archive(retained_until);
     ```

---

## 7. Consequences & Trade-offs

### Positive Consequences
- **Absolute Regulatory Immunity**: Strict adherence to EU AI Act Article 50 and GDPR Article 22 protects the enterprise from severe statutory penalties.
- **Protected Commercial Defense**: Preserving dispute transcripts for 2 years guarantees documentary evidence for contract defense (*Moffatt v. Air Canada*).
- **Hardened Explainability**: Projecting sanitized plain-language explanations provides user transparency while neutralizing attacker reconnaissance.

### Negative Consequences & Trade-offs
- **Human Review Operational Load**: Mandating specialist review for all dispute rejections and account terminations shifts high-touch cases to human queues.
- **S3 WORM Archive Storage Costs**: Preserving two years of full conversational transcripts increases long-term compliance storage costs.
- **Customer Conversational Friction**: Prompt disclosures that the agent is an AI can slightly reduce initial customer adoption among legacy users.

---

## 8. References & Cross-Disciplinary Grounding

1. **EU Artificial Intelligence Act (Regulation EU 2024/1689)**: Article 50 — Transparency Obligations for Providers and Deployers of AI Systems.
2. **General Data Protection Regulation (Regulation EU 2016/679)**: Article 22 (Automated Individual Decision-Making) & Article 17(3)(e) (Legal Claims Exception).
3. **Moffatt v. Air Canada**: 2024 BCCRT 149. (Legal precedent on corporate liability for representations made by automated chat interfaces).
4. **NIST AI Risk Management Framework (AI RMF 1.0)**: National Institute of Standards and Technology. (Governance and Explainability Core).
