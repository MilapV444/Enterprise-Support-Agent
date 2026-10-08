# CI-ADP-03: Multi-Tiered Improvement Levers & Contamination-Proof Few-Shot Curation (Knowledge Drafting, Curated Few-Shot Quarantine & Regional Fine-Tuning)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-06 *(Confirmed per CI-D4 Holistic Improvement Levers & Regional Fine-Tuning CI-Q1/Q2, CI-D5 Contamination-Free Few-Shot Quarantine KK1, CI-D6 Agent-Drafted / Human-Published Articles UK1)*
- **Deciders**: Architecture Team, Principal Machine Learning Scientist, Head of Knowledge Management, Lead AI Safety Engineer
- **Component**: `[15] Continuous Improvement` (`Component [ 15 ]`)
- **Reasoning Source**: `checkpoint.md` §19 · Diagram: `LLD - [15] Continuous Improvement`
- **Decisions Covered**:
  - `CI-D4`: Holistic Multi-Tiered Improvement Levers — Authorizes a comprehensive spectrum of engineering levers to remediate diagnosed failures: prompt engineering, Jev question wording refinement, confidence gate threshold calibration, OpenAPI tool descriptions, Knowledge Base article publication, curated few-shot examples, and per-region fine-tuning of the self-hosted open-weights foundation model (`RP-D4`, `CR-D9`); fine-tuning operates under updated tenant opt-in terms (`CI-Q1(ii)`) and executes strictly within sovereign regional boundaries (`CI-Q2(i)`), producing sovereign US and EU model checkpoints
  - `CI-D5`: Contamination-Proof Few-Shot Example Quarantine — Resolves benchmark data contamination ($KK1$, `EV-KK4`); high-quality production conversations curated as in-context few-shot exemplars are tokenized under `SG-D4` and registered in an immutable exclusion registry; automated CI linters guarantee that no few-shot prompt exemplar is ever included in offline evaluation suites or regression benchmarks
  - `CI-D6`: Agent-Drafted, Human-Published Knowledge Curation — Closes the knowledge gap lifecycle (KR Flow C); when retrieval analyzers detect repetitive documentation gaps, the agent automatically synthesizes draft knowledge articles from successfully resolved support cases; drafts are tagged `audience: "internal"` by default (`KR-D13`) and must undergo human knowledge manager review and sign-off before being promoted to customer-visible publication, preventing hallucinated errors from polluting the public knowledge base ($UK1$)
- **Related Architectural Decision Points**:
  - [`KR-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/02-knowledge-retrieval/KR-ADP-01-knowledge-sources-labelling.md): Knowledge Sources & Content Labelling *(Internal by Default & Provenance)*
  - [`EV-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/08-evaluation-experimentation/EV-ADP-01-datasets-data-governance.md): Datasets & Data Governance *(Test Set Contamination Guard)*
  - [`CR-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/11-cost-resource-management/CR-ADP-01-model-tier-routing.md): Model Tier Routing *(Self-Hosted Model Utilization)*
  - [`DP-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/07-data-persistence/DP-ADP-01-store-topology-residency.md): Store Topology & Residency *(Regional GPU Training)*

---

## 1. Context & Problem Statement

Remediating diagnosed failure modes in enterprise conversational AI requires a disciplined hierarchy of engineering interventions:
1. **The Few-Shot Evaluation Contamination Hazard ($KK1$, `EV-KK4`)**:
   - In-context few-shot learning is one of the most effective levers for improving prompt compliance. Engineers routinely copy real customer transcripts into system prompts as few-shot demonstrations.
   - However, if a conversation used as a prompt exemplar is also present in offline evaluation benchmarks, the evaluation harness tests the model on examples it has already memorized. Reported benchmark accuracy spikes while real-world production performance degrades ($KK1$).
2. **The "Model Collapse" Knowledge Feedback Loop ($UK1$)**:
   - When an autonomous agent encounters missing documentation, allowing it to automatically generate and publish public knowledge base articles creates a dangerous self-referential feedback loop.
   - If the agent hallucinates a subtle technical requirement and publishes it to Zendesk, future vector searches retrieve the agent's own hallucination as ground-truth evidence, cementing the error into corporate institutional memory ($UK1$).
3. **The Transatlantic Training Data Cross-Contamination ($UU2$, `CI-Q2`)**:
   - Fine-tuning open-weights models (such as Llama 3.1 70B) on customer transcripts requires training clusters. Training a single global model using European customer transcripts on US-based GPU clusters breaches GDPR Chapter V and violates regional tenant residency covenants (`DP-D10`).

### The Core Architectural Question
> **How do we establish a principled spectrum of continuous improvement levers that cures failure modes, prevents few-shot test contamination, enforces human editorial control on documentation, and guarantees regional training data sovereignty?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `CI-D4`, `CI-D5`, and `CI-D6` establish the **Multi-Tiered Improvement and Contamination-Proof Curation Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   CONTINUOUS IMPROVEMENT LEVERS & CURATION PIPELINE (CI-D4, CI-D5, CI-D6)        │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                       Ranked Weekly Failure Cluster $C_k$ (Volume x Severity, CI-D3)
                                                   │
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ THE HIERARCHY OF IMPROVEMENT INTERVENTIONS (CI-D4)                                               │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 1. Documentation Lever: Content Gap? ===> AGENT DRAFTS ARTICLE -> HUMAN PUBLISHES (CI-D6)        │
│ 2. Tool Description Lever: Schema Bug? ===> Refine OpenAPI Parameter Descriptions (`TA-D1`)      │
│ 3. Confidence Boundary Lever: Gate Bug? ===> Recalibrate Cutoffs via EV-D9                       │
│ 4. Few-Shot Exemplar Lever: Syntax Drift? ===> CURATE FEW-SHOT WITH TEST EXCLUSION (CI-D5)      │
│ 5. Foundation Model Fine-Tuning: Cognitive Gap? ===> SOVEREIGN REGIONAL FINE-TUNING (CI-D4)     │
└───────────────────────┬──────────────────────────────────────────────────┬───────────────────────┘
                        │                                                  │
                        ▼                                                  ▼
┌───────────────────────────────────────────────┐ ┌────────────────────────────────────────────────┐
│ FEW-SHOT TEST EXCLUSION ENVELOPE (CI-D5, KK1) │ │ REGIONAL MODEL FINE-TUNING (CI-D4, CI-Q2)      │
├───────────────────────────────────────────────┤ ├────────────────────────────────────────────────┤
│ • Curated from High-CSAT / Specialist-Approved│ │ • Opted-In Tenants with Updated Terms (CI-Q1)  │
│   Conversations (Avoids Self-Reinforcement UU3│ │ • Sovereign Training Pipelines:                │
│ • Masked via Global PII Tokens (`SG-D4`)      │ │   - US GPU Cluster trains `llama-70b-us-vNext` │
│ • CI Linters assert: `Exemplar_ID` NOT IN     │ │   - EU GPU Cluster trains `llama-70b-eu-vNext` │
│   `eval_test_fixtures/*.json` ($KK1$ Fixed)   │ │ • Fine-tuned weights must beat baseline in     │
│ • Stamped into Git Release Manifest (`DL-D2`) │ │   full EV-D5 release gate before promotion!    │
└───────────────────────────────────────────────┘ └────────────────────────────────────────────────┘
```

---

### Pillar 1: The Hierarchy of Improvement Levers (`CI-D4`)

When remediating a diagnosed failure mode, engineering teams apply the least intrusive lever that resolves the root cause:
1. **Level 1: Knowledge Curation (`CI-D6`)**: If the agent lacked information, draft a new knowledge article. Zero code changes required.
2. **Level 2: Tool Schema Tuning**: If the model called tools with invalid parameters, enhance OpenAPI parameter docstrings with explicit boundary examples.
3. **Level 3: Jev Question Refinement**: Refine structured triage or grounding prompt wording in `core/jev/`.
4. **Level 4: In-Context Few-Shot Exemplars (`CI-D5`)**: Inject 1–2 tokenized demonstrations into the route prompt.
5. **Level 5: Parameter Fine-Tuning**: If open-weights Llama 3.1 70B repeatedly fails complex SOP reasoning, fine-tune model weights on curated enterprise transcripts.

---

### Pillar 2: Contamination-Proof Few-Shot Quarantine (`CI-D5`, $KK1$)

To prevent few-shot exemplars from corrupting evaluation benchmarks:
1. **The Mutual Exclusion Invariant ($KK1$ Fixed)**:
   $$\mathcal{D}_{\text{few\_shot}} \cap \mathcal{D}_{\text{eval\_benchmarks}} = \emptyset$$
2. **Automated CI Cross-Contamination Linter**:
   - An automated CI test inspects all few-shot transcripts referenced in prompt templates.
   - It computes cryptographic SHA-256 hashes of all normalized utterances and checks them against the evaluation dataset repository (`tests/fixtures/eval/`).
   - If an exemplar matches an evaluation episode, the build immediately breaks.
3. **Selection Criteria ($UU3$ Mitigation)**:
   - Few-shot examples must originate from conversations that received a positive human signal: verified specialist edit (`HL-D10`), human approval, or explicit 5-star CSAT. Training on raw unverified agent outputs is strictly prohibited to prevent self-reinforcing errors ($UU3$).

---

### Pillar 3: Agent-Drafted, Human-Published Knowledge Loop (`CI-D6`, $UK1$)

To close the loop on repetitive documentation omissions (KR Flow C):
1. **Automated Article Drafting**:
   - When vector search retrieval precision drops or specialists repeatedly cite missing SOPs, the agent synthesizes a candidate documentation article summarizing the resolved case.
2. **The "Internal by Default" Safeguard (`KR-D13`)**:
   - The generated article is saved in Zendesk/Confluence tagged `audience: "internal"` and `author: "agent"`.
   - It is invisible to customer vector searches.
3. **Human Knowledge Gate ($UK1$ Mitigated)**:
   - A human technical writer reviews the article, verifies technical veracity, edits instructions, and clicks **Publish to Customer**. Only then does the article enter the public vector search index.

---

### Pillar 4: Sovereign Regional Fine-Tuning (`CI-D4`, `CI-Q1`, `CI-Q2`)

When fine-tuning the self-hosted open-weights fallback model (`RP-D4`, `CR-D9`):
1. **Consent Protocol (`CI-Q1(ii)`)**:
   - Transcripts are ingested exclusively from enterprise tenants that have accepted updated terms explicitly naming model training.
2. **Regional Isolation (`CI-Q2(i)`)**:
   - US customer data is fine-tuned on US Kubernetes GPU pods, producing `llama-3.1-70b-ft-us`.
   - EU customer data is fine-tuned on EU Kubernetes GPU pods, producing `llama-3.1-70b-ft-eu`. Zero customer data crosses transatlantic boundaries ($UU2$ fixed).
3. **Release Gate Gatekeeper**:
   - Fine-tuned weights must achieve a higher $\text{Pass}^k$ score on the route's golden benchmark than the base model before replacing baseline weights in production.

---

## 3. Technical Implementation & Genesis Contracts

```python
"""
core/ci/few_shot_validator.py
CI Validation script asserting zero data contamination between few-shot exemplars and test sets (CI-D5).
"""

import hashlib
import glob
import json
import re
from typing import Set


def normalize_utterance(text: str) -> str:
    """Strips whitespace and punctuation for strict hash comparison."""
    return re.sub(r"[^\w\s]", "", text).strip().lower()


def compute_hash(text: str) -> str:
    return hashlib.sha256(normalize_utterance(text).encode("utf-8")).hexdigest()


def test_few_shot_quarantine_against_evaluation_fixtures():
    """
    CI Invariant Test: Asserts that NO few-shot prompt exemplar exists
    inside any evaluation test fixture (CI-D5, KK1).
    """
    # 1. Collect all hashes from active few-shot prompt templates
    few_shot_files = glob.glob("src/core/prompts/few_shot/**/*.json")
    few_shot_hashes: Set[str] = set()

    for file_path in few_shot_files:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            for turn in data.get("turns", []):
                few_shot_hashes.add(compute_hash(turn["content"]))

    # 2. Collect all hashes from evaluation benchmarks
    eval_files = glob.glob("tests/fixtures/eval/**/*.json")
    contamination_detected = []

    for file_path in eval_files:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            for episode in data.get("episodes", []):
                for turn in episode.get("turns", []):
                    h = compute_hash(turn["content"])
                    if h in few_shot_hashes:
                        contamination_detected.append((file_path, turn["content"][:60]))

    assert not contamination_detected, (
        f"BENCHMARK CONTAMINATION DETECTED (CI-D5): Found {len(contamination_detected)} shared examples! "
        f"Violations: {contamination_detected}"
    )
```

---

## 4. Failure Modes & Mitigation Matrix

| Failure ID | Sub-Component | Failure Mode Description | Root Cause | Effect on System | Architectural Mitigation (`CI-D4`, `CI-D5`, `CI-D6`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **$KK1$** | Improvement | Few-shot exemplar is present in test benchmark | Developer copies same customer case to prompt and eval set | Artificially inflated evaluation score; live quality regression | `CI-D5` CI linter asserts cryptographic mutual exclusion between prompts and test sets |
| **$UK1$** | Improvement | Agent-drafted KB article cements hallucination | Agent publishes article directly without human verification | Model retrieves its own past hallucination as ground-truth | `CI-D6` tags agent drafts internal by default (`KR-D13`); human editor must review and publish |
| **$UU2$** | Improvement | Cross-border training data export | EU transcripts used to fine-tune US base model | Violation of GDPR Chapter V cross-border transfer laws | `CI-Q2(i)` enforces regional fine-tuning: US models train on US data, EU models on EU data |
| **$UU3$** | Improvement | Model collapse via self-reinforcing training | Fine-tuning on raw unverified agent outputs | Reinforces agent linguistic quirks and subtle blind spots | `CI-D4` restricts fine-tuning data strictly to cases with verified positive human outcomes |

---

## 5. Closed-Loop Telemetry & Verification Directives

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   IMPROVEMENT LEVERS TELEMETRY & OBSERVABILITY PIPELINE                          │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Article Drafted ──► [ Knowledge Editor Queue ] ──► Metric: `kb.agent_drafts.published_total`
                             │
                             ├──► [ Few-Shot Linter ] ──► Status: `few_shot_quarantine_passed`
                             │
                             └──► [ Fine-Tuned Model Gate ] ──► Eval Score: `model.ft_baseline_delta`
```

### 1. Prometheus Telemetry Indicators
- `ci.kb.drafts_generated_total`: Total documentation articles synthesized by agent.
- `ci.kb.drafts_published_total`: Count of agent-drafted articles reviewed and published by humans.
- `ci.few_shot.active_exemplars_count`: Total active in-context few-shot demonstrations across all routes.
- `ci.model.fine_tune_pass_rate`: Benchmark score delta of fine-tuned model vs. base foundation model.

---

## 6. Alternatives Considered & Trade-Off Analysis

| Architectural Alternative | Technical Mechanism | Why Rejected / Trade-Off Analysis |
| :--- | :--- | :--- |
| **Automated KB Publishing (Option C)** | Agent automatically publishes generated articles to public FAQ | **Rejected ($UK1$)**: Catastrophic hallucination risk; models can publish incorrect pricing or SLA rules that bind the enterprise. |
| **Global Fine-Tuning in Single Region** | Train one global model in US using pooled worldwide data | **Rejected ($UU2$)**: Direct violation of EU GDPR data residency mandates; transatlantic training is unlawful without adequacy treaties. |
| **Dynamic Similarity-Based Few-Shot Retrieval** | Dynamically retrieve few-shot examples via vector search per turn | **Rejected (`CR-ADP-02`)**: Adds 300ms vector lookup latency and consumes dynamic prompt token budget; static curated exemplars are more stable. |

---

## 7. References & Academic Foundations

1. **Knowledge-Centered Service (KCS) Academy.** (2020). *KCS v6 Practices Guide: Solve, Capture, Structure, Reuse.* Consortium for Service Innovation.
2. **Brown, T. et al.** (2020). *Language Models are Few-Shot Learners.* Advances in Neural Information Processing Systems (NeurIPS). Data Contamination Analysis.
3. **GDPR Chapter V (Articles 44–50).** (2016). *Transfers of Personal Data to Third Countries.*
4. **NIST SP 800-53, Rev. 5.** (2020). *Security and Privacy Controls for Information Systems and Organizations.* Control SI-4: Information System Monitoring.
