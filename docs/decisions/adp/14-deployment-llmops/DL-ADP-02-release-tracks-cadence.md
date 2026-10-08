# DL-ADP-02: Dual-Track Release Cadence & Gated Configuration Governance (Continuous Code CD, Scheduled Behavioral Batches & CI Path Rules)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-06 *(Confirmed per DL-D2 Unified GitOps Versioning, DL-D10 Split Release Cadence & DL-Q3 CI Path Rule Invariant UU4)*
- **Deciders**: Architecture Team, Lead DevOps Architect, Head of AI Quality, Platform Release Manager
- **Component**: `[14] Deployment & LLMOps` (`Component [ 14 ]`)
- **Reasoning Source**: `checkpoint.md` §18 · Diagram: `LLD - [14] Deployment & LLMOps`
- **Decisions Covered**:
  - `DL-D2`: Unified GitOps Release Versioning — Platform definitions, system prompts, Jev question wording, confidence gate thresholds, Cedar authorization policies, and OpenAPI tool declarations live in code within a single monorepo (`DP-D12`, `MA-D10`); every deployed artifact is stamped with an immutable semantic release version (`vMajor.Minor.Patch`), ensuring total audit reproducibility of historical agent states
  - `DL-D10`: Asymmetric Dual-Track Release Cadence — Decouples technical software engineering from cognitive model behavior updates:
    - **Track A (Continuous Code Delivery)**: Core application code, backend microservices, performance patches, and infrastructure bug fixes deploy continuously upon passing the merge gate (`TQ-D9`)
    - **Track B (Scheduled Gated Behavioral Releases)**: Changes affecting model prompts, Jev question definitions, confidence routing thresholds, Cedar security rules, or model tier mappings are batched for scheduled releases (e.g., weekly) that must pass the full statistical evaluation gate (`EV-D5`)
  - `DL-Q3(i)`: Automated CI Path-Rule Governance Barrier — Resolves the severe risk of unvetted cognitive behavior changes slipping silently into production ($UU4$); GitHub Actions CI path rules inspect modified files on every pull request: any commit modifying files in `prompts/`, `jev/`, `policies/`, `thresholds/`, or `models.yaml` is automatically held in a release-candidate branch until approved by the scheduled `EV-D5` evaluation gate
- **Related Architectural Decision Points**:
  - [`EV-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/08-evaluation-experimentation/EV-ADP-04-release-gate-approval-evidence.md): Release Gate & Approval Evidence *(The Full EV-D5 Evaluation Gate)*
  - [`TQ-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/13-testing-quality/TQ-ADP-04-merge-gates-flaky-tests.md): Merge Gate & Flaky Tests *(Pre-Merge Code Gates)*
  - [`CI-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/15-continuous-improvement/CI-ADP-04-validation-approval-changes.md): Validation & Approval of Changes *(Behavioral Change Verification)*
  - [`DL-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/14-deployment-llmops/DL-ADP-03-rollout-rollback.md): Rollout & Rollback *(Progressive Delivery Strategy)*

---

## 1. Context & Problem Statement

Releasing autonomous agent software requires fundamentally different release rhythms than standard stateless microservices:
1. **The Behavioral Blast Radius Dilemma**:
   - In traditional web applications, changing an algorithm or database query either works or throws an exception. In LLM systems, modifying three words in a system prompt (e.g., *"be concise"* $\to$ *"be thorough"*) causes widespread behavioral shifts across the entire conversation space. A prompt change can trigger unexpected hallucinations, degrade tool call precision, or increase token burn by $40\%$.
2. **The Ungated Deployment Leak ($UU4$)**:
   - If an organization applies uniform Continuous Deployment (CD) to all commits, a software engineer submitting a routine bugfix who simultaneously edits a prompt to "clean it up" triggers an immediate production rollout.
   - The modified prompt bypasses the extensive statistical evaluation gate (`EV-D5`), resulting in an untested cognitive regression escaping directly to live customer traffic ($UU4$).
3. **The Deployment Velocity Paralyzation**:
   - Conversely, forcing all software engineering pull requests (such as fixing a CSS styling bug, updating an internal Redis timeout, or optimizing a database index) to wait for multi-hour nightly evaluation suites and scheduled weekly release windows destroys engineering agility.

### The Core Architectural Question
> **How do we engineer a dual-track CI/CD pipeline that enables engineering teams to deploy code fixes continuously while strictly quarantining behavioral, prompt, and policy modifications behind a scheduled, statistically evaluated release gate?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `DL-D2` and `DL-D10` establish the **Dual-Track Release Cadence and Path-Governed CI/CD Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   DUAL-TRACK RELEASE CADENCE & CI PATH-RULE GOVERNANCE (DL-D2, DL-D10)           │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                                    DEVELOPER PULL REQUEST MERGE EVENT
                                                   │
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ AUTOMATED CI PATH FILTER (DL-Q3(i), UU4 Invariant Firewall)                                      │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Evaluates Modified File Paths:                                                                   │
│ Match: `prompts/**` | `core/jev/questions/**` | `policies/*.cedar` | `config/thresholds.yaml`    │
│                                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ Path Evaluation Verdict:                                                                 │   │
│   │ • NO (Pure Code / Infra Changes)   ===> TRACK A: CONTINUOUS CODE DEPLOYMENT (DL-D10)     │   │
│   │ • YES (Cognitive Behavior Changes) ===> TRACK B: SCHEDULED GATED RELEASE TRACK (DL-D10)  │   │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘   │
└───────────────────────┬──────────────────────────────────────────────────┬───────────────────────┘
                        │                                                  │
                        ▼                                                  ▼
┌───────────────────────────────────────────────┐ ┌────────────────────────────────────────────────┐
│ TRACK A: CONTINUOUS CODE DEPLOYMENT           │ │ TRACK B: SCHEDULED GATED BEHAVIOR RELEASE      │
├───────────────────────────────────────────────┤ ├────────────────────────────────────────────────┤
│ • Merge Gate Passed (`TQ-D9`)                 │ │ • Pull Requests held in `release-candidate`    │
│ • Unit, Integration, & Contract Tests         │ │ • Weekly Release Window Cadence                │
│ • Zero Live LLM Evals Required                │ │ • MANDATORY FULL EV-D5 EVALUATION GATE:        │
│ • Container Built & Deployed Immediately      │ │   - Component Quality Thresholds               │
│ • Zero Downtime Rolling Deployment            │ │   - Zero Risk-Tier Invariant Violations        │
│                                               │ │   - Pass^k Benchmark on Golden Episodes        │
│                                               │ │   - Cost Per Resolved Turn $\le +10\%$ (CR-D12)│
│                                               │ │   - Progressive Shadow -> Canary Rollout       │
└───────────────────────────────────────────────┘ └────────────────────────────────────────────────┘
```

---

### Pillar 1: Single GitOps Monorepo Versioning (`DL-D2`)

To ensure complete forensic auditability and disaster recovery:
1. **Infrastructure, Code & Behavior as Code**:
   - The entire platform state resides in a unified monorepo.
   - Prompts (`src/core/prompts/`), Jev questions (`src/core/jev/`), Cedar policies (`src/policies/`), and tool declarations (`src/core/tools/`) are checked into git alongside Python microservice code.
2. **Immutable Semantic Tagging**:
   - Every build generates an immutable semantic version tag: `vMAJOR.MINOR.PATCH`.
   - The version string is stamped into all OpenTelemetry traces (`OB-D1`), LangGraph state checkpoints (`MS-D8`), and decision audit records (`SG-D13`), enabling operators to reconstruct the exact prompt and model configuration that governed any historical turn.

---

### Pillar 2: Asymmetric Dual-Track Cadence (`DL-D10`)

We decouple release frequency based on risk profile:
- **Track A (Technical Core CD)**: Deploys continuously multiple times daily. Encompasses database migrations, API gateway routing, frontend Retool console components, and operational bugfixes. Bypasses statistical evaluation suites to preserve developer velocity.
- **Track B (Cognitive Behavioral Gated Releases)**: Ships on a scheduled weekly cadence. Encompasses changes to prompt text, few-shot examples (`CI-D5`), Jev triage/grounding questions (`ADP-05`), route confidence thresholds (`HL-D2`), and model tier mappings (`CR-D1`).

---

### Pillar 3: CI Path-Rule Governance Barrier (`DL-Q3(i)`, $UU4$)

To guarantee that no behavioral change slips into Track A deployments ($UU4$):
1. **GitHub Actions Path Rule Filter**:
   - The continuous deployment workflow inspects git diff file paths:
     ```yaml
     # .github/workflows/deploy-track-a.yml
     on:
       push:
         branches: [ main ]
         paths-ignore:
           - 'src/core/prompts/**'
           - 'src/core/jev/questions/**'
           - 'src/policies/**'
           - 'config/thresholds.yaml'
           - 'config/models.yaml'
     ```
2. **Holding Barrier**:
   - If a pull request modifies any file in the restricted cognitive directories, GitHub Actions blocks automatic container deployment and diverts the commit into the `candidate/weekly-behavior` release branch.
   - The commit cannot deploy to production until it passes the full `EV-D5` evaluation suite, receives release approval evidence (`EV-D13`), and executes the progressive shadow/canary rollout (`DL-D4`).

---

## 3. Technical Implementation & Genesis Contracts

```yaml
# .github/workflows/ci-path-rule-governor.yml
# GitHub Actions workflow enforcing Dual-Track Release Cadence (DL-D10, DL-Q3(i)).

name: CI Release Track Router

on:
  pull_request:
    branches: [ main ]

jobs:
  classify-release-track:
    runs-on: ubuntu-latest
    outputs:
      is_behavioral_change: ${{ steps.filter.outputs.behavioral }}
    steps:
      - uses: actions/checkout@v4
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            behavioral:
              - 'src/core/prompts/**'
              - 'src/core/jev/questions/**'
              - 'src/policies/*.cedar'
              - 'config/thresholds.yaml'
              - 'config/models.yaml'

  enforce-governance:
    needs: classify-release-track
    runs-on: ubuntu-latest
    steps:
      - name: Check Release Track Invariants
        run: |
          if [ "${{ needs.classify-release-track.outputs.is_behavioral_change }}" == "true" ]; then
            echo "COGNITIVE BEHAVIOR CHANGE DETECTED (Track B, DL-D10)."
            echo "This PR modifies prompts, Jev questions, policies, or thresholds."
            echo "Enforcing Full EV-D5 Evaluation Gate requirement..."
            echo "Automatic continuous deployment is DISABLED for this commit."
          else
            echo "PURE CODE / INFRA CHANGE DETECTED (Track A, DL-D10)."
            echo "Eligible for Continuous Deployment upon passing TQ-D9 merge gate."
          fi
```

```python
"""
core/deployment/release_manifest.py
Pydantic v2 schemas for Unified GitOps Release Manifest (DL-D2).
"""

from typing import Dict, Any, List
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class ReleaseManifest(BaseModel):
    """
    Immutable release manifest stamped into runtime containers (DL-D2).
    """
    release_version: str = Field(..., pattern=r"^v[0-9]+\.[0-9]+\.[0-9]+$")
    commit_sha: str = Field(..., min_length=40, max_length=40)
    release_track: str = Field(..., description="'track_a_code' or 'track_b_behavior'")
    built_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    active_prompt_hashes: Dict[str, str]
    jev_question_version: str
    cedar_policy_bundle_hash: str
    ev_evaluation_pass_token: str
    target_regions: List[str] = ["us-east-1", "eu-central-1"]
```

---

## 4. Failure Modes & Mitigation Matrix

| Failure ID | Sub-Component | Failure Mode Description | Root Cause | Effect on System | Architectural Mitigation (`DL-D2`, `DL-D10`, `DL-Q3`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **$UU4$** | CI/CD | Untested prompt change deployed directly to prod | Developer bundles prompt edit with urgent code bugfix | Severe regression in answer grounding or token spend | `DL-Q3(i)` CI path rule blocks continuous CD if prompt or threshold files are modified |
| **$KK1$** | Versioning | Historical turn cannot be reproduced | Prompts edited via external web UI without git commit | Lost audit trail for regulatory compliance inquiries | `DL-D2` mandates all prompts and policies live in code; stamped with semantic release tag |
| **$KU1$** | CI/CD | Weekly behavioral release delayed by pipeline flakiness | Nightly evaluation suite experiences transient timeout | Delayed deployment of critical prompt improvements | Merge gates use selective retry on non-safety integration tests (`TQ-D8`); evals monitored via FinOps |
| **`EV-D5`** | Quality Gate | Behavioral change deployed without evaluation sign-off | Manual CI bypass used to merge release candidate | Incompatible confidence thresholds breach error SLOs | Release manifests strictly require cryptographic `ev_evaluation_pass_token` signed by CI |

---

## 5. Closed-Loop Telemetry & Verification Directives

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   RELEASE TRACK TELEMETRY & AUDIT PIPELINE                                       │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Deployment Trigger ──► [ Release Manifest Validator ] ──► Metric: `deploy.track.type`
                                 │
                                 ├──► [ Path Filter Inspector ] ──► Metric: `deploy.path_holds_total`
                                 │
                                 └──► [ Runtime Version Exposer ] ──► OTel: `service.version`
```

### 1. Prometheus Telemetry Indicators
- `deploy.release.total`: Counter tracking deployments tagged by track (`track_a` vs. `track_b`).
- `deploy.path_rules.held_prs_total`: Count of pull requests held for scheduled behavioral release windows.
- `deploy.manifest.version_info`: Gauge exposing active semantic version (`vMajor.Minor.Patch`) across regional Kubernetes pods.

---

## 6. Alternatives Considered & Trade-Off Analysis

| Architectural Alternative | Technical Mechanism | Why Rejected / Trade-Off Analysis |
| :--- | :--- | :--- |
| **Continuous Deployment for All Commits (DL-F10(a))** | Deploy all prompt and code changes immediately on merge | **Rejected ($UU4$)**: Unacceptable operational risk; prompt edits escape without comprehensive statistical evaluation, destabilizing production. |
| **Dynamic Runtime Prompt Registry (DL-F2(c))** | Store prompts in database with admin UI for live editing | **Rejected (`DP-D12`)**: Destroys GitOps reproducibility; bypasses code review and CI testing; impossible to deterministically replay historical agent states. |
| **Unified Weekly Release for All Changes** | Hold all code, bugfixes, and prompt changes for weekly batch | **Rejected**: Unnecessarily cripples engineering velocity; blocks critical zero-day security patches and trivial bugfixes for days. |

---

## 7. References & Academic Foundations

1. **Humble, J., & Farley, D.** (2010). *Continuous Delivery: Reliable Software Releases through Build, Test, and Deployment Automation.* Addison-Wesley Professional.
2. **Google Cloud Architecture Center.** (2023). *GitOps-Style Continuous Delivery for Machine Learning Systems.*
3. **NIST SP 800-53, Rev. 5.** (2020). *Security and Privacy Controls for Information Systems and Organizations.* Control CM-3: Configuration Change Control.
