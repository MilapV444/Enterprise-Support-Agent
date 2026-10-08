# CI-ADP-02: Hierarchical Failure Taxonomy & Incident Prioritization (Component Failure Trees, Severity-Volume Matrix & Blameless Postmortems)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-06 *(Confirmed per CI-D2 Code-Versioned Failure Taxonomy OB-D11 & CI-D3 Weekly Severity-Volume Reviews / Blameless Postmortems)*
- **Deciders**: Architecture Team, VP of Engineering, Head of Customer Support, Lead SRE
- **Component**: `[15] Continuous Improvement` (`Component [ 15 ]`)
- **Reasoning Source**: `checkpoint.md` §19 · Diagram: `LLD - [15] Continuous Improvement`
- **Decisions Covered**:
  - `CI-D2`: Hierarchical Component-Mapped Failure Taxonomy — Establishes a unified, code-versioned taxonomy of conversational and agentic failure modes (`core/ci/taxonomy.yaml`); formally claims ownership of the classification taxonomy utilized by automated runtime analyzers (`OB-D11`); structures errors across two hierarchical dimensions:
    - **Architectural Subsystem**: Ingestion & Triage, Knowledge Retrieval, Multi-Agent Delegation, Tool Invocation, Safety & Guardrails, and Confidence Gating
    - **Epistemic Failure Quadrant**: Mapped directly to Known Knowns ($KK$), Known Unknowns ($KU$), Unknown Knowns ($UK$), and Unknown Unknowns ($UU$)
    - Enforces a monthly engineering review of unclassified outlier failures to propose and merge new taxonomy branches
  - `CI-D3`: Severity-Volume Prioritization & Mandatory Blameless Postmortems — Establishes weekly operational review rhythms: failure clusters are ranked using an objective risk product: $\text{Priority} = \text{Volume} \times \text{Severity}$; the top-3 clusters are assigned dedicated engineering owners; mandates a rigorous blameless postmortem (Google SRE methodology) for any security jailbreak, unauthorized PII disclosure, or unapproved financial transaction
- **Related Architectural Decision Points**:
  - [`OB-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/09-observability-monitoring/OB-ADP-05-failure-classification.md): Failure Classification *(Automated Runtime Triage)*
  - [`DL-ADP-02`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/14-deployment-llmops/DL-ADP-02-release-tracks-cadence.md): Release Tracks & Cadence *(Taxonomy Versioning in Code)*
  - [`CI-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/15-continuous-improvement/CI-ADP-04-validation-approval-changes.md): Validation & Approval of Changes *(Failures Clustered to Tests)*
  - [`SG-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/06-safety-security-governance/SG-ADP-05-governance-retention-providers.md): Governance & Compliance *(Incident Audit Trails)*

---

## 1. Context & Problem Statement

Engineering teams maintaining complex agent architectures face thousands of raw error logs, angry customer messages, and failed tool invocations weekly:
1. **The "Whack-a-Mole" Complaint Trap**:
   - Without an objective classification taxonomy, engineering teams reactively chase the loudest customer escalation or executive complaint rather than fixing systemic structural bottlenecks.
   - Developers spend hours investigating an isolated cosmetic typo while a critical grounding hallucination silently affects $8\%$ of billing disputes.
2. **The Fragmented Taxonomy Deficit (`OB-D11`)**:
   - Observability systems (`OB`) detect runtime exceptions (e.g., HTTP 504s, tool timeouts). Support consoles (`HL`) record specialist rejection codes (e.g., `WRONG_CALCULATION`). Evaluation teams (`EV`) track benchmark assertion failures.
   - Without a centralized taxonomy owner, cross-functional teams speak different dialects, preventing unified data clustering and root-cause analysis.
3. **The Culture of Blame**:
   - When an autonomous agent erroneously issues an unapproved credit or exposes sensitive data, organizations frequently assign blame to individual operators or isolated prompt authors rather than diagnosing systemic gaps in Cedar policies, verification cards, or confidence boundaries.

### The Core Architectural Question
> **How do we engineer an authoritative, code-versioned failure taxonomy that unifies runtime telemetry, automates incident prioritization via Volume $\times$ Severity ranking, and institutionalizes blameless postmortems?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `CI-D2` and `CI-D3` establish the **Authoritative Failure Taxonomy and Incident Prioritization Engine**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   AUTHORITATIVE FAILURE TAXONOMY & PRIORITIZATION (CI-D2, CI-D3)                 │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                       Aggregated Failure Events (Traces, Reason Codes, Re-Asks)
                                                   │
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 1. HIERARCHICAL TAXONOMY ENGINE (CI-D2, core/ci/taxonomy.yaml)                                   │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Level 1: Subsystem (Triage, Retrieval, Multi-Agent, Tools, Safety, Confidence Gate)              │
│ Level 2: Specific Failure Mode (e.g., `tools.argument_hallucination`, `retrieval.stale_chunk`)    │
│ Level 3: Failure Matrix Quadrant Tag ($KK1..KK4$, $KU1..KU5$, $UK1..UK3$, $UU1..UU6$)             │
└──────────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                   │
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 2. SEVERITY-VOLUME RISK RANKING (CI-D3)                                                          │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ For each failure cluster $C_k$, compute aggregate risk score:                                    │
│ $$R(C_k) = \text{Volume}(C_k) \times \text{SeverityWeight}(C_k)$$                                │
│ • Critical Severity ($10\times$): Security jailbreaks, PII leakage, financial inaccuracies      │
│ • Moderate Severity ($3\times$):  Sub-optimal tool routing, prolonged turn latencies             │
│ • Minor Severity ($1\times$):     Cosmetic markdown formatting, slight tone mismatch             │
└──────────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                   │
           ┌───────────────────────────────────────┴───────────────────────────────────────┐
           ▼ (Top-3 Ranked Clusters)                                                       ▼ (Safety or Financial Incident)
┌───────────────────────────────────────────────┐ ┌────────────────────────────────────────────────┐
│ WEEKLY OPERATIONAL REVIEW (CI-D3)             │ │ BLAMELESS POSTMORTEM (CI-D3, Google SRE)       │
├───────────────────────────────────────────────┤ ├────────────────────────────────────────────────┤
│ • Every Monday at 10:00 UTC                   │ │ Triggered automatically upon:                  │
│ • Top-3 Clusters assigned named owners        │ │ - Any prompt injection security escape         │
│ • Mandate: Every failure cluster becomes a    │ │ - Any unapproved financial write $\ge \$1,000$ │
│   reproducible test episode (`CI-D7`) before  │ │ Output: Published postmortem doc with timeline,│
│   code fix ships!                             │ │ root cause, and 5 preventive action items      │
└───────────────────────────────────────────────┘ └────────────────────────────────────────────────┘
```

---

### Pillar 1: Code-Versioned Hierarchical Taxonomy (`CI-D2`)

`CI-D2` formally claims ownership of the platform's standardized error vocabulary (`core/ci/taxonomy.yaml`):
1. **Subsystem Mapping**:
   - `triage.*`: Misclassified acuity domain, missed human escalation request.
   - `retrieval.*`: Passage missing from vector search, stale documentation, reranker failure.
   - `multi_agent.*`: Specialist coordination deadlock, contradictory specialist claims (`MA-D7`).
   - `tools.*`: Argument hallucination, schema parsing failure, unhandled upstream 500 error.
   - `safety.*`: Input screening bypass, PII token vault failure, unauthorized tool call.
   - `gate.*`: Numeric grounding blind spot (`HL-D13`), miscalibrated confidence threshold.
2. **Continuous Taxonomy Governance**:
   - Automated analyzers (`OB-D11`) and free-text classifiers (`CI-D11`) tag outliers with `unclassified_anomaly`.
   - On the first Tuesday of every month, engineering leads review all unclassified anomalies, merging new standardized branches into `taxonomy.yaml`.

---

### Pillar 2: Quantitative Severity-Volume Prioritization (`CI-D3`)

To eliminate subjective prioritization debates, engineering effort is allocated via mathematical risk ranking:
$$R(C_k) = \sum_{i \in C_k} \text{SeverityWeight}(e_i)$$

Where:
- $\text{SeverityWeight} = 100$ for Tier 4 Critical Incidents (Financial mutations, PII leaks, authorization escapes).
- $\text{SeverityWeight} = 10$ for Tier 2 Behavioral Defects (Broken workflows, incorrect policy claims).
- $\text{SeverityWeight} = 1$ for Tier 1 Superficial Flaws (Stylistic inconsistencies, minor delays).

The top-3 ranked clusters become mandatory sprint deliverables, ensuring that engineering cycles are focused where customer impact is highest.

---

### Pillar 3: Blameless Postmortem Discipline (`CI-D3`)

In accordance with Google Site Reliability Engineering (SRE) principles:
1. **Mandatory Postmortem Triggers**:
   - Any prompt injection payload that circumvents `SG-D1`.
   - Any financial adjustment executed without required two-person authorization (`HL-D4`).
   - Any customer PII exposed unmasked in external provider logs.
2. **Postmortem Invariants**:
   - Focuses strictly on systemic vulnerabilities (e.g., *"Why did the Cedar linter allow an incomplete role mapping?"*), never human fault.
   - Produces measurable action items: an automated test reproducing the failure (`CI-D7`), an updated CI linter (`TQ-D4`), and an updated architecture checkpoint note.

---

## 3. Technical Implementation & Genesis Contracts

```python
"""
core/ci/failure_taxonomy.py
Pydantic v2 schemas and Prioritization Engine for Failure Analysis (CI-D2, CI-D3).
"""

from enum import Enum
from typing import List, Dict, Any
from pydantic import BaseModel, Field


class FailureSeverity(int, Enum):
    COSMETIC = 1       # Formatting, tone, slight delay
    OPERATIONAL = 10   # Unhelpful answer, unnecessary handoff
    CRITICAL = 100     # Financial error, PII leak, safety bypass


class FailureCluster(BaseModel):
    cluster_id: str
    taxonomy_path: str = Field(..., description="e.g. tools.argument_hallucination")
    failure_count: int
    severity: FailureSeverity
    sample_case_ids: List[str]
    assigned_owner: str = ""

    @property
    def total_risk_score(self) -> int:
        """
        Computes mathematical risk score: Volume x Severity (CI-D3).
        """
        return self.failure_count * self.severity.value


class FailurePrioritizer:
    """
    Ranks failure clusters and enforces weekly operational review thresholds (CI-D3).
    """

    def rank_clusters(self, clusters: List[FailureCluster]) -> List[FailureCluster]:
        """
        Sorts clusters by total risk score in descending order.
        """
        return sorted(clusters, key=lambda c: c.total_risk_score, reverse=True)

    def extract_top_review_targets(self, clusters: List[FailureCluster], top_n: int = 3) -> List[FailureCluster]:
        """
        Extracts top-N clusters that mandate weekly engineering ownership (CI-D3).
        """
        ranked = self.rank_clusters(clusters)
        return ranked[:top_n]
```

---

## 4. Failure Modes & Mitigation Matrix

| Failure ID | Sub-Component | Failure Mode Description | Root Cause | Effect on System | Architectural Mitigation (`CI-D2`, `CI-D3`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`OB-D11`** | Taxonomy | Drift between telemetry and analysis taxonomy | Different teams modify taxonomy independently | Failure telemetry cannot join with bug trackers | `CI-D2` establishes single authoritative `taxonomy.yaml` in code; shared across all components |
| **$CI-D3$** | Prioritization | Engineering spends sprint on low-impact bug | Prioritizing by loud executive complaints | Major systematic grounding bugs remain unfixed | `CI-D3` enforces objective mathematical ranking: $\text{Volume} \times \text{Severity}$ |
| **$UK1$** | Review | Repeated incidents due to lack of postmortems | Incident treated as isolated human error | Root causes persist, causing recurring customer outages | `CI-D3` mandates blameless postmortems with verifiable prevention action items |

---

## 5. Closed-Loop Telemetry & Verification Directives

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   FAILURE ANALYSIS OBSERVABILITY PIPELINE                                        │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Failure Events ──► [ Taxonomy Classifier ] ──► Metric: `ci.failure.events_by_path`
                            │
                            ├──► [ Risk Score Calculator ] ──► Prometheus: `ci.failure.cluster_risk`
                            │
                            └──► [ Postmortem Tracker ]  ──► Audit Log: `ci.postmortem.completed`
```

### 1. Prometheus Telemetry Indicators
- `ci.failure.clusters_active_total`: Gauge tracking total identified failure clusters.
- `ci.failure.top_risk_score`: Maximum risk score among active unassigned failure clusters.
- `ci.postmortems.completed_total`: Counter tracking published blameless postmortems.

---

## 6. Alternatives Considered & Trade-Off Analysis

| Architectural Alternative | Technical Mechanism | Why Rejected / Trade-Off Analysis |
| :--- | :--- | :--- |
| **Flat Error List (Option A)** | Maintain unnested list of 100 error codes | **Rejected**: Fails to provide architectural attribution; impossible to see which subsystem is generating the bulk of errors. |
| **Volume-Only Prioritization** | Rank bugs strictly by raw frequency | **Rejected**: Catastrophic for security; a single PII leak affecting 1 user would be ignored in favor of 50 cosmetic markdown formatting bugs. |
| **Ad-Hoc Failure Reviews** | Meet to discuss failures only when an outage occurs | **Rejected**: Reactive and chaotic; weekly disciplined reviews eliminate bugs before they cause public outages. |

---

## 7. References & Academic Foundations

1. **Beyer, B. et al.** (2016). *Site Reliability Engineering: How Google Runs Production Systems.* O'Reilly Media. Chapter 15: Postmortem Culture: Learning from Failure.
2. **FinOps Foundation.** (2023). *FinOps Framework: Inform, Optimize, Operate.*
3. **NIST SP 800-61, Rev. 2.** (2012). *Computer Security Incident Handling Guide.* National Institute of Standards and Technology.
