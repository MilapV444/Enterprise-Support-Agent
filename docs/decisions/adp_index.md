# Architectural Decision Points (ADPs) — Index

> **Generated** by [`scripts/generate_adp_index.py`](../../scripts/generate_adp_index.py) from [`adp_groups.yaml`](./adp_groups.yaml) (the grouping) and the decision log in [`checkpoint.md`](./checkpoint.md) §3. Do not edit by hand.  
> **Visual:** each component's LLD page in [`architecture.tldr`](../../diagrams/architecture.tldr) ends with the same ADP cards.

**79 ADPs** cover all **230 logged decisions**. An ADP is one architectural concern and is meant to become **one detailed design document**. Each entry below gives the document's brief: the question it answers, the chosen design, the decisions it must cover (with their one-line choices), where the reasoning is, and which ADPs in other components it must stay consistent with.

## Summary

| Component | ADPs | Decisions | Reasoning |
| :--- | :--- | ---: | :--- |
| **Agent Orchestration Core & Runtime** | [ADP-01 · Planning paradigm](./adp/00-orchestration-core/ADP-01-planning-paradigm.md)<br>[ADP-02 · Workflow durability](./adp/00-orchestration-core/ADP-02-workflow-durability.md)<br>[ADP-03 · Context engineering](./adp/00-orchestration-core/ADP-03-context-engineering.md)<br>[ADP-04 · Error recovery & replanning](./adp/00-orchestration-core/ADP-04-error-recovery-replanning.md)<br>[ADP-05 · Decision model (Jev)](./adp/00-orchestration-core/ADP-05-decision-model-jev.md) | 5 | checkpoint.md §2 |
| **[1] User & Application** | [UA-ADP-01 · Channels & API transport](./adp/01-user-application/UA-ADP-01-channels-api-transport.md)<br>[UA-ADP-02 · Identity & downstream tokens](./adp/01-user-application/UA-ADP-02-identity-downstream-tokens.md)<br>[UA-ADP-03 · Sessions & conversation scope](./adp/01-user-application/UA-ADP-03-sessions-conversation-scope.md)<br>[UA-ADP-04 · Response contract & delivery](./adp/01-user-application/UA-ADP-04-response-contract-delivery.md) | 11 | checkpoint.md §5 |
| **[2] Knowledge & Retrieval** | [KR-ADP-01 · Knowledge sources & content labelling](./adp/02-knowledge-retrieval/KR-ADP-01-knowledge-sources-labelling.md)<br>[KR-ADP-02 · Ingestion & freshness](./adp/02-knowledge-retrieval/KR-ADP-02-ingestion-freshness.md)<br>[KR-ADP-03 · Indexing & tenant isolation](./adp/02-knowledge-retrieval/KR-ADP-03-indexing-tenant-isolation.md)<br>[KR-ADP-04 · Retrieval & ranking pipeline](./adp/02-knowledge-retrieval/KR-ADP-04-retrieval-ranking-pipeline.md)<br>[KR-ADP-05 · Retrieval evaluation](./adp/02-knowledge-retrieval/KR-ADP-05-retrieval-evaluation.md) | 16 | checkpoint.md §6 |
| **[3] Memory & State** | [MS-ADP-01 · Conversation & case model](./adp/03-memory-state/MS-ADP-01-conversation-case-model.md)<br>[MS-ADP-02 · Long-term fact model](./adp/03-memory-state/MS-ADP-02-long-term-fact-model.md)<br>[MS-ADP-03 · Fact write path](./adp/03-memory-state/MS-ADP-03-fact-write-path.md)<br>[MS-ADP-04 · Agent state & durability](./adp/03-memory-state/MS-ADP-04-agent-state-durability.md)<br>[MS-ADP-05 · Retention & erasure](./adp/03-memory-state/MS-ADP-05-retention-erasure.md) | 19 | checkpoint.md §7 |
| **[4] Tools & Actions** | [TA-ADP-01 · Tool registry & selection](./adp/04-tools-actions/TA-ADP-01-tool-registry-selection.md)<br>[TA-ADP-02 · Argument safety](./adp/04-tools-actions/TA-ADP-02-argument-safety.md)<br>[TA-ADP-03 · Action validation & approval tiers](./adp/04-tools-actions/TA-ADP-03-action-validation-approval.md)<br>[TA-ADP-04 · Execution, credentials & isolation](./adp/04-tools-actions/TA-ADP-04-execution-credentials-isolation.md)<br>[TA-ADP-05 · Transactional integrity & audit](./adp/04-tools-actions/TA-ADP-05-transactional-integrity-audit.md) | 18 | checkpoint.md §8 |
| **[5] Multi-Agent & Communication** | [MA-ADP-01 · Topology & specialist set](./adp/05-multi-agent-communication/MA-ADP-01-topology-specialist-set.md)<br>[MA-ADP-02 · Delegation & limits](./adp/05-multi-agent-communication/MA-ADP-02-delegation-limits.md)<br>[MA-ADP-03 · Inter-agent contracts & context](./adp/05-multi-agent-communication/MA-ADP-03-inter-agent-contracts-context.md)<br>[MA-ADP-04 · Specialist permissions & writes](./adp/05-multi-agent-communication/MA-ADP-04-specialist-permissions-writes.md)<br>[MA-ADP-05 · Merging & the single voice](./adp/05-multi-agent-communication/MA-ADP-05-merging-single-voice.md) | 18 | checkpoint.md §9 |
| **[6] Safety, Security & Governance** | [SG-ADP-01 · Input screening & injection defence](./adp/06-safety-security-governance/SG-ADP-01-input-screening-injection-defence.md)<br>[SG-ADP-02 · PII protection](./adp/06-safety-security-governance/SG-ADP-02-pii-protection.md)<br>[SG-ADP-03 · Output safety](./adp/06-safety-security-governance/SG-ADP-03-output-safety.md)<br>[SG-ADP-04 · Authorization & tool permissions](./adp/06-safety-security-governance/SG-ADP-04-authorization-tool-permissions.md)<br>[SG-ADP-05 · Governance, retention & providers](./adp/06-safety-security-governance/SG-ADP-05-governance-retention-providers.md) | 18 | checkpoint.md §10 |
| **[7] Data & Persistence** | [DP-ADP-01 · Store topology & residency](./adp/07-data-persistence/DP-ADP-01-store-topology-residency.md)<br>[DP-ADP-02 · Tenant isolation & encryption](./adp/07-data-persistence/DP-ADP-02-tenant-isolation-encryption.md)<br>[DP-ADP-03 · Audit, archive & settings data](./adp/07-data-persistence/DP-ADP-03-audit-archive-settings.md)<br>[DP-ADP-04 · Data movement & stream retention](./adp/07-data-persistence/DP-ADP-04-data-movement-stream-retention.md)<br>[DP-ADP-05 · Erasure, backups & restore](./adp/07-data-persistence/DP-ADP-05-erasure-backups-restore.md) | 15 | checkpoint.md §11 |
| **[8] Evaluation & Experimentation** | [EV-ADP-01 · Datasets & data governance](./adp/08-evaluation-experimentation/EV-ADP-01-datasets-data-governance.md)<br>[EV-ADP-02 · Scoring & calibration](./adp/08-evaluation-experimentation/EV-ADP-02-scoring-calibration.md)<br>[EV-ADP-03 · Suites, environment & cadence](./adp/08-evaluation-experimentation/EV-ADP-03-suites-environment-cadence.md)<br>[EV-ADP-04 · Release gate & approval evidence](./adp/08-evaluation-experimentation/EV-ADP-04-release-gate-approval-evidence.md)<br>[EV-ADP-05 · Live evaluation & experiments](./adp/08-evaluation-experimentation/EV-ADP-05-live-evaluation-experiments.md) | 15 | checkpoint.md §12 |
| **[9] Observability & Monitoring** | [OB-ADP-01 · Instrumentation & trace pipeline](./adp/09-observability-monitoring/OB-ADP-01-instrumentation-trace-pipeline.md)<br>[OB-ADP-02 · Telemetry storage, retention & erasure](./adp/09-observability-monitoring/OB-ADP-02-telemetry-storage-retention-erasure.md)<br>[OB-ADP-03 · Service levels & alerting](./adp/09-observability-monitoring/OB-ADP-03-service-levels-alerting.md)<br>[OB-ADP-04 · Token & cost telemetry](./adp/09-observability-monitoring/OB-ADP-04-token-cost-telemetry.md)<br>[OB-ADP-05 · Failure classification](./adp/09-observability-monitoring/OB-ADP-05-failure-classification.md) | 14 | checkpoint.md §13 |
| **[10] Reliability / Performance / Scale** | [RP-ADP-01 · Admission control](./adp/10-reliability-performance-scale/RP-ADP-01-admission-control.md)<br>[RP-ADP-02 · Dependency failures & fallbacks](./adp/10-reliability-performance-scale/RP-ADP-02-dependency-failures-fallbacks.md)<br>[RP-ADP-03 · Bursts, latency & capacity](./adp/10-reliability-performance-scale/RP-ADP-03-bursts-latency-capacity.md)<br>[RP-ADP-04 · Disaster recovery & regions](./adp/10-reliability-performance-scale/RP-ADP-04-disaster-recovery-regions.md)<br>[RP-ADP-05 · Resilience testing](./adp/10-reliability-performance-scale/RP-ADP-05-resilience-testing.md) | 15 | checkpoint.md §14 |
| **[11] Cost & Resource Management** | [CR-ADP-01 · Model tier routing](./adp/11-cost-resource-management/CR-ADP-01-model-tier-routing.md)<br>[CR-ADP-02 · Token & context economy](./adp/11-cost-resource-management/CR-ADP-02-token-context-economy.md)<br>[CR-ADP-03 · Answer cache](./adp/11-cost-resource-management/CR-ADP-03-answer-cache.md)<br>[CR-ADP-04 · Budgets & cost governance](./adp/11-cost-resource-management/CR-ADP-04-budgets-cost-governance.md)<br>[CR-ADP-05 · Key-management cost](./adp/11-cost-resource-management/CR-ADP-05-key-management-cost.md) | 14 | checkpoint.md §15 |
| **[12] Human-in-the-Loop** | [HL-ADP-01 · Confidence gate](./adp/12-human-in-the-loop/HL-ADP-01-confidence-gate.md)<br>[HL-ADP-02 · Escalation & queues](./adp/12-human-in-the-loop/HL-ADP-02-escalation-queues.md)<br>[HL-ADP-03 · Approval](./adp/12-human-in-the-loop/HL-ADP-03-approval-workflows.md)<br>[HL-ADP-04 · Handoff & waiting](./adp/12-human-in-the-loop/HL-ADP-04-handoff-waiting-experience.md)<br>[HL-ADP-05 · Feedback & console](./adp/12-human-in-the-loop/HL-ADP-05-feedback-console.md) | 14 | checkpoint.md §16 |
| **[13] Testing & Quality** | [TQ-ADP-01 · Testing model-driven logic](./adp/13-testing-quality/TQ-ADP-01-testing-model-driven-logic.md)<br>[TQ-ADP-02 · Contracts & policy checks](./adp/13-testing-quality/TQ-ADP-02-contracts-policy-checks.md)<br>[TQ-ADP-03 · End-to-end tests & test data](./adp/13-testing-quality/TQ-ADP-03-end-to-end-tests-data.md)<br>[TQ-ADP-04 · Merge gate & flaky tests](./adp/13-testing-quality/TQ-ADP-04-merge-gates-flaky-tests.md)<br>[TQ-ADP-05 · Migrations & non-functional tests](./adp/13-testing-quality/TQ-ADP-05-migrations-non-functional-tests.md) | 14 | checkpoint.md §17 |
| **[14] Deployment & LLMOps** | [DL-ADP-01 · Environments & infrastructure](./adp/14-deployment-llmops/DL-ADP-01-environments-infrastructure.md)<br>[DL-ADP-02 · Release tracks & cadence](./adp/14-deployment-llmops/DL-ADP-02-release-tracks-cadence.md)<br>[DL-ADP-03 · Rollout & rollback](./adp/14-deployment-llmops/DL-ADP-03-rollout-rollback.md)<br>[DL-ADP-04 · Versioning of models, indexes & workflows](./adp/14-deployment-llmops/DL-ADP-04-versioning-models-indexes-workflows.md)<br>[DL-ADP-05 · Secrets & key custody](./adp/14-deployment-llmops/DL-ADP-05-secrets-key-custody.md) | 12 | checkpoint.md §18 |
| **[15] Continuous Improvement** | [CI-ADP-01 · Feedback signals](./adp/15-continuous-improvement/CI-ADP-01-feedback-signals.md)<br>[CI-ADP-02 · Failure analysis](./adp/15-continuous-improvement/CI-ADP-02-failure-analysis.md)<br>[CI-ADP-03 · Improvement levers](./adp/15-continuous-improvement/CI-ADP-03-improvement-levers.md)<br>[CI-ADP-04 · Validation & approval of changes](./adp/15-continuous-improvement/CI-ADP-04-validation-approval-changes.md)<br>[CI-ADP-05 · Long-term evolution & retraining](./adp/15-continuous-improvement/CI-ADP-05-long-term-evolution-retraining.md) | 12 | checkpoint.md §19 |
| **Total** | **79** | **230** | |

## Agent Orchestration Core & Runtime

Reasoning: `checkpoint.md` §2 · Diagram: `LLD - Agent Orchestration & Planning Core`

### [ADP-01 · Planning paradigm](./adp/00-orchestration-core/ADP-01-planning-paradigm.md)

- **Question:** How does the agent plan and act — fixed workflows, open-ended reasoning, or both?
- **Chosen design:** Hybrid dual-process statechart — deterministic LangGraph FSM for SOPs + scoped ReAct for diagnostics.
- **Related ADPs:** MA-ADP-01 (Topology & specialist set), TA-ADP-01 (Tool registry & selection)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **ADP-01** | Planning Paradigm | Option C: Hybrid Dual-Process Statechart | Deterministic LangGraph FSM for compliance/SOPs + scoped ReAct in edge nodes. |

### [ADP-02 · Workflow durability](./adp/00-orchestration-core/ADP-02-workflow-durability.md)

- **Question:** How do multi-day workflows survive crashes, waits and human approvals?
- **Chosen design:** Temporal outer saga for durability, timers and approvals + LangGraph inner cognitive loop.
- **Related ADPs:** MS-ADP-04 (Agent state & durability), TA-ADP-05 (Transactional integrity & audit), DL-ADP-04 (Versioning of models, indexes & workflows)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **ADP-02** | Workflow Durability | Option C: Two-Tier Hybrid (Temporal + LangGraph) | Temporal manages multi-day ticket sagas & HITL; LangGraph runs inner cognitive turns. |

### [ADP-03 · Context engineering](./adp/00-orchestration-core/ADP-03-context-engineering.md)

- **Question:** How is the prompt's token budget split between system, profile, knowledge, dialogue and scratchpad?
- **Chosen design:** Tripartite slot allocator — 15 % system · 15 % profile · 35 % knowledge · 25 % dialogue · 10 % scratchpad.
- **Related ADPs:** MS-ADP-01 (Conversation & case model), KR-ADP-04 (Retrieval & ranking pipeline), CR-ADP-02 (Token & context economy)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **ADP-03** | Context Engineering | Option C: Tripartite Structured Slot Allocator | Bounded token quotas: System (15%), Profile (15%), RAG (35%), Chat (25%), Scratchpad (10%). |

### [ADP-04 · Error recovery & replanning](./adp/00-orchestration-core/ADP-04-error-recovery-replanning.md)

- **Question:** How does the agent recover from failed steps without looping or guessing?
- **Chosen design:** Dual-process circuit breaker — max 2 Reflexion trials, a Jev step-success check, then human handoff.
- **Related ADPs:** RP-ADP-02 (Dependency failures & fallbacks), HL-ADP-02 (Escalation & queues)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **ADP-04** | Error Recovery & Replanning | Option C: Dual-Process Circuit Breaker | Max 2 Reflexion critique trials; trips immediately to HITL on repeated failure. |

### [ADP-05 · Decision model (Jev)](./adp/00-orchestration-core/ADP-05-decision-model-jev.md)

- **Question:** Which model makes the structured decisions inside the workflow?
- **Chosen design:** Jev (TypeSafe) at triage, FSM guards and tool selection; code owns control flow; numbers and dates stay in code.
- **Related ADPs:** MA-ADP-02 (Delegation & limits), TA-ADP-01 (Tool registry & selection), HL-ADP-01 (Confidence gate), CR-ADP-01 (Model tier routing), RP-ADP-02 (Dependency failures & fallbacks)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **ADP-05** | Decision model | Jev (TypeSafe) at orchestration decision points; LangGraph kept as runner | Triage, FSM transition guards, System 2 tool selection. Code owns control flow; numbers/dates in code. Q1: LLM critique kept, Jev step check trips HITL · Q2: TypeSafe bands, stricter for data-changing routes · Q3: only PII-masked state sent · Q4 (scope beyond Comp 5) open. |

## [1] User & Application

Reasoning: `checkpoint.md` §5 · Diagram: `LLD - [1] User & Application`

### [UA-ADP-01 · Channels & API transport](./adp/01-user-application/UA-ADP-01-channels-api-transport.md)

- **Question:** Which channels ship first, and how do clients send turns and receive answers?
- **Chosen design:** Web-only v1; POST 202 with an idempotency key + a resumable SSE event stream.
- **Related ADPs:** RP-ADP-01 (Admission control), DP-ADP-04 (Data movement & stream retention)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **UA-D1** | Channels | Web-only v1 | Channel-agnostic envelope keeps later adapters additive. |
| **UA-D2** | API transport | Decoupled POST 202 + resumable SSE | One path for live, reconnect and deferred (HITL) delivery; idempotent submit. |

### [UA-ADP-02 · Identity & downstream tokens](./adp/01-user-application/UA-ADP-02-identity-downstream-tokens.md)

- **Question:** How sure are we who the user is, and what authority does the agent carry into other systems?
- **Chosen design:** Tiered identity (anonymous → OTP → SSO, step-up on demand) + RFC 8693 on-behalf-of tokens valid 24 h.
- **Related ADPs:** TA-ADP-04 (Execution, credentials & isolation), SG-ADP-04 (Authorization & tool permissions)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **UA-D3** | Identity assurance | Tiered T0 anon → T1 OTP → T2 SSO + step-up | Low friction for FAQs; account actions behind real identity. |
| **UA-D4** | Downstream identity | RFC 8693 on-behalf-of tokens (sub + act) | T0 gets a minimal read-only token (UA-Q1 → ii); T1/T2 normal on-behalf-of tokens. |
| **UA-D9** | Token validity | User access token valid 24 h | Outlives the 12 h session cap, which fixes KK3's expiry variant; revocation and theft window remain owned. |

### [UA-ADP-03 · Sessions & conversation scope](./adp/01-user-application/UA-ADP-03-sessions-conversation-scope.md)

- **Question:** What is a session, a conversation and a case, and when do they end?
- **Chosen design:** Session → conversation → case; sessions end at 30 min idle / 12 h; any authenticated request keeps them alive.
- **Related ADPs:** MS-ADP-01 (Conversation & case model), RP-ADP-01 (Admission control)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **UA-D5** | Session scoping | Resolved by MS-D1: session → conversation → case | Conversation outlives the session; several conversations can link to one case. |
| **UA-D6** | Session timeouts | Fixed 30 min idle / 12 h absolute | NIST AAL2; delivery must not depend on a live session. |
| **UA-Q3** | Idle-timer activity | Any authenticated request incl. open SSE | Open tab keeps session to the 12 h cap; accepted (KK3/UK5/UU5). |

### [UA-ADP-04 · Response contract & delivery](./adp/01-user-application/UA-ADP-04-response-contract-delivery.md)

- **Question:** What does a reply look like on the wire, and how do late or held answers reach the user?
- **Chosen design:** Typed event envelope; replies buffered until checks pass with status events meanwhile; deferred answers go to the inbox.
- **Related ADPs:** EV-ADP-05 (Live evaluation & experiments), HL-ADP-04 (Handoff & waiting), SG-ADP-03 (Output safety)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **UA-D7** | Response contract | Typed event envelope | Citations and action cards are first-class; channel-degradable. |
| **UA-D8** | Stream vs. safety gate | Resolved by EV-D11: buffer the checked reply, stream status events meanwhile (UA-F8 c) | Safe; user waits for generation + checks. |
| **UA-Q2** | Deferred delivery | Inbox only (no email notification in v1) | Accepted risk: users who never return miss outcomes. |

## [2] Knowledge & Retrieval

Reasoning: `checkpoint.md` §6 · Diagram: `LLD - [2] Knowledge & Retrieval`

### [KR-ADP-01 · Knowledge sources & content labelling](./adp/02-knowledge-retrieval/KR-ADP-01-knowledge-sources-labelling.md)

- **Question:** What knowledge do we index, and who may see and cite it?
- **Chosen design:** Curated + operational + raw tickets; per-chunk audience label, internal by default; human / agent provenance.
- **Related ADPs:** SG-ADP-04 (Authorization & tool permissions), CI-ADP-03 (Improvement levers)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **KR-D1** | Sources | Curated + operational + raw tickets/chats | Max coverage; ticket placement/PII pending KR-Q1/Q2. |
| **KR-D2** | Internal content | Per-chunk audience label; only customer-visible cited | Internal shown to specialists only; granularity pending KR-Q4. |
| **KR-D13** | Default audience | Internal by default; explicit override for public | Fixes UK4; bulk labeling needed at onboarding. |
| **KR-D16** | Ticket provenance | source = human \| agent; agent text kept but labeled "agent reply, unverified" | KR-Q7 → (ii); mitigates UU5. |

### [KR-ADP-02 · Ingestion & freshness](./adp/02-knowledge-retrieval/KR-ADP-02-ingestion-freshness.md)

- **Question:** How and how often does content enter the index, and how do deletions leave it?
- **Chosen design:** Nightly batch re-index + instant purge for deletions; deletion-aware ingestion with a post-batch check.
- **Related ADPs:** DP-ADP-05 (Erasure, backups & restore), DP-ADP-04 (Data movement & stream retention)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **KR-D3** | Freshness | Nightly batch re-index | ≤24 h stale; deletion/ACL-revocation timing pending KR-Q3. |
| **KR-D15** | Deletion-aware ingestion | Check → filter → ingest → verify + post-batch check | Fixes UU4. |

### [KR-ADP-03 · Indexing & tenant isolation](./adp/02-knowledge-retrieval/KR-ADP-03-indexing-tenant-isolation.md)

- **Question:** How is content chunked, indexed and kept apart between tenants and permissions?
- **Chosen design:** Structure-aware parent-child chunks; shared public index + per-tenant private index; copied ACLs + live check for restricted docs.
- **Related ADPs:** DP-ADP-01 (Store topology & residency), DP-ADP-02 (Tenant isolation & encryption), SG-ADP-04 (Authorization & tool permissions)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **KR-D4** | Chunking | Structure-aware + parent-child small-to-big | No indexing-time LLM cost. |
| **KR-D5** | Tenant isolation | Shared public index + per-tenant private index | T0 anonymous → public only. |
| **KR-D6** | ACL freshness | Copied ACLs + live OBO check for restricted docs | Low latency on the common path. |

### [KR-ADP-04 · Retrieval & ranking pipeline](./adp/02-knowledge-retrieval/KR-ADP-04-retrieval-ranking-pipeline.md)

- **Question:** How does a question become the passages the agent sees?
- **Chosen design:** Standalone rewrite → BM25 + dense (RRF) → screening → validated LLM reranker → always top-10 parent sections.
- **Related ADPs:** ADP-03 (Context engineering), SG-ADP-01 (Input screening & injection defence), CR-ADP-02 (Token & context economy), HL-ADP-01 (Confidence gate)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **KR-D7** | First-stage retrieval | Hybrid BM25 + dense, RRF | Exact IDs + concepts; ADP-03 label mismatch pending KR-Q6. |
| **KR-D8** | Query transform | Standalone rewrite + identifier extraction | No HyDE / multi-query. |
| **KR-D9** | Reranker | LLM-as-reranker | Injectable by retrieved text; uncalibrated scores; cost → Comp 12. |
| **KR-D10** | Admission | Fixed top-k, no abstain | No no_evidence; answer/abstain decision moves to Comp 9; k pending KR-Q5. |
| **KR-D12** | Reranker validation | Schema-check wrapper; fall back to RRF order | Fixes KK3; fallback rate → Comp 10. |
| **KR-D14** | Pre-rerank screening | Screen retrieved text before the LLM reranker | Mitigates UU1; Comp 7 engine invoked inside retrieval. |

### [KR-ADP-05 · Retrieval evaluation](./adp/02-knowledge-retrieval/KR-ADP-05-retrieval-evaluation.md)

- **Question:** How do we know retrieval is good, offline and in production?
- **Chosen design:** Offline golden set + online implicit signals + sampled LLM-judge scoring.
- **Related ADPs:** EV-ADP-02 (Scoring & calibration), EV-ADP-05 (Live evaluation & experiments)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **KR-D11** | Retrieval eval | Offline golden + online signals + sampled LLM judge | Gap signal redefined (no no-evidence rate). |

## [3] Memory & State

Reasoning: `checkpoint.md` §7 · Diagram: `LLD - [3] Memory & State`

### [MS-ADP-01 · Conversation & case model](./adp/03-memory-state/MS-ADP-01-conversation-case-model.md)

- **Question:** How is dialogue grouped and kept within the token budget?
- **Chosen design:** Session → conversation → case (Jev links cases); last N turns verbatim + rolling summary + pinned items.
- **Related ADPs:** UA-ADP-03 (Sessions & conversation scope), ADP-03 (Context engineering)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **MS-D1** | Conversation model | Session → conversation → case | Resolves UA-D5. Case linked by Jev Choice, user confirms below high confidence (MS-Q1). |
| **MS-D2** | Dialogue compaction | Last N verbatim + rolling summary + pinned items | Pinned items never evicted; pinned by rules + Jev Noul, with Jev unpin check (MS-Q2). |

### [MS-ADP-02 · Long-term fact model](./adp/03-memory-state/MS-ADP-02-long-term-fact-model.md)

- **Question:** What do we remember about a user across conversations, and how is it shaped?
- **Chosen design:** Per-user facts only, with validity dates; account facts are never stored — always read from the CRM.
- **Related ADPs:** DP-ADP-02 (Tenant isolation & encryption), TA-ADP-04 (Execution, credentials & isolation)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **MS-D3** | Long-term scope | Per-principal facts only | No tenant-shared facts in v1 (poisoning blast radius). |
| **MS-D4** | Fact representation | Flat facts + vector search, with valid_from / valid_to | Updates close the old fact, not overwrite it. |
| **MS-D6** | Account facts | Never stored; always read from CRM | Memory holds soft facts, preferences, episodes. |

### [MS-ADP-03 · Fact write path](./adp/03-memory-state/MS-ADP-03-fact-write-path.md)

- **Question:** When and how do new facts get extracted and merged safely?
- **Chosen design:** Extract at resolution from user turns + allow-listed tool fields; skip plans and third-party facts; Jev reconciles on masked text.
- **Related ADPs:** SG-ADP-02 (PII protection), TA-ADP-02 (Argument safety), ADP-05 (Decision model (Jev))

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **MS-D5** | Write policy | Extract at conversation/case resolution; user turns + tool-confirmed facts only | Never from retrieved documents. No-case conversations at 24 h idle close; cases > 14 days also per conversation (MS-Q4). |
| **MS-D12** | Reconcile decider | Jev Choice per candidate fact | LLM extracts; Jev decides ADD/UPDATE/DELETE/NOOP; low confidence → NOOP. PII-masked input (ADP-05-Q3). |
| **MS-D15** | Third-party facts | Only facts about the principal (Jev Noul subject check) | UK2 mitigated. |
| **MS-D16** | Tool-confirmed facts | Structured fields from allow-listed tools only | UU1 mitigated; no free-text facts from tools. |
| **MS-D17** | Future-tense statements | Extractor skips plans/intentions; saves only what is true now | From MS-F17 (b). No plan records. UU2 → MITIGATED. |
| **MS-D19** | Masked vs. unmasked facts | Store unmasked (encrypted); mask both sides before Jev | UU5 fixed; keeps ADP-05-Q3. |

### [MS-ADP-04 · Agent state & durability](./adp/03-memory-state/MS-ADP-04-agent-state-durability.md)

- **Question:** Where does agent state live, and how does it survive crashes, deploys and long waits?
- **Chosen design:** LangGraph checkpointer is the truth; checkpoints per node and around side effects; versioned with migrations; re-check after waits > 1 h.
- **Related ADPs:** ADP-02 (Workflow durability), TA-ADP-05 (Transactional integrity & audit), DL-ADP-04 (Versioning of models, indexes & workflows), TQ-ADP-05 (Migrations & non-functional tests)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **MS-D7** | Large tool outputs | By reference + inline summary | Agent can page detail in. |
| **MS-D8** | State truth | LangGraph checkpointer (Postgres); Temporal holds status + checkpoint ID | Avoids Temporal history limits; consistent with ADP-05. |
| **MS-D9** | Checkpoint granularity | Per node + before and after every side-effecting tool call | Side-effecting tools need idempotency keys (Comp 5). |
| **MS-D13** | Checkpoint schema changes | Versioned checkpoints + migrations; unknown version → HITL | KK4 fixed. |
| **MS-D18** | Resume after long wait | Re-fetch + re-check pre-conditions after waits > 1 h | UU3 mitigated. |

### [MS-ADP-05 · Retention & erasure](./adp/03-memory-state/MS-ADP-05-retention-erasure.md)

- **Question:** How long is memory kept, and how is it corrected or erased?
- **Chosen design:** Fixed TTL per memory type; back-office erasure / correction in v1; an erasure inventory covering every store.
- **Related ADPs:** DP-ADP-05 (Erasure, backups & restore), SG-ADP-05 (Governance, retention & providers)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **MS-D10** | Retention | Fixed TTL per memory type | Facts 12 mo since confirmed · episodes 24 mo · blobs + checkpoints case closed + 30 d (MS-Q3). |
| **MS-D11** | User control | Back-office erasure/correction in v1; self-service later | GDPR SLA ≤ 1 month. |
| **MS-D14** | Erasure coverage | Erasure inventory of every store; facts keyed by (principal, tenant) | UK3 fixed; provider logs → Comp 7. |

## [4] Tools & Actions

Reasoning: `checkpoint.md` §8 · Diagram: `LLD - [4] Tools & Actions`

### [TA-ADP-01 · Tool registry & selection](./adp/04-tools-actions/TA-ADP-01-tool-registry-selection.md)

- **Question:** Which tools exist, how are they built and reviewed, and which can a turn use?
- **Chosen design:** Plain Python tools with a reviewed risk class; code filters by tier / role, Jev shortlists and picks.
- **Related ADPs:** ADP-05 (Decision model (Jev)), MA-ADP-04 (Specialist permissions & writes)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **TA-D1** | Tool Registry — Tools per turn | Retrieved per turn: code tier/role filter → Jev shortlist → Jev pick | Low confidence → human (TA-Q3). |
| **TA-D2** | Tool Registry — Tool hosting | Plain Python functions; no MCP in v1 | Contradicts deep-dive Stage 4 / LLD [9] MCP. Run as Temporal activities, one task queue per system (TA-Q2). |
| **TA-D16** | Risk class review | Author + second reviewer; risky tools need approval until reviewed | UK3 mitigated. |

### [TA-ADP-02 · Argument safety](./adp/04-tools-actions/TA-ADP-02-argument-safety.md)

- **Question:** Where may sensitive tool arguments (IDs, amounts, recipients) come from?
- **Chosen design:** They must trace to the user's words or to allow-listed structured tool fields; never free LLM text.
- **Related ADPs:** SG-ADP-02 (PII protection), MS-ADP-03 (Fact write path)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **TA-D3** | Tool Schemas — Argument provenance | Sensitive args must trace to user words or an earlier tool result | Fixes defaulting to production. |
| **TA-D13** | Argument sources | Only allow-listed structured tool fields fill sensitive args | UU2 mitigated. |

### [TA-ADP-03 · Action validation & approval tiers](./adp/04-tools-actions/TA-ADP-03-action-validation-approval.md)

- **Question:** Which actions run automatically, and which need a human?
- **Chosen design:** Reads and low-risk writes automatic; financial ≥ tenant threshold (default $1,000), destructive or irreversible → approval; Jev gate can only tighten.
- **Related ADPs:** HL-ADP-03 (Approval), SG-ADP-04 (Authorization & tool permissions)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **TA-D5** | Action Validation — Approval tiers | Reads auto · low-risk writes auto · financial ≥ threshold / destructive / irreversible → human | Per-tenant threshold, default $1,000 (TA-Q1). |
| **TA-D6** | Action Validation — Jev gating | Jev allow/ask/deny + 'serves the request?'; can only tighten | Stricter-of with static rules. Ask → user (low risk) or specialist (above); deny → failed step (TA-Q4). |
| **TA-D7** | Action Validation — Preview | Dry run where supported; preview on the approval card | Else arguments + fresh state read. |
| **TA-D14** | Threshold counting | Per call | UU4 accepted risk; audit + alerting. |

### [TA-ADP-04 · Execution, credentials & isolation](./adp/04-tools-actions/TA-ADP-04-execution-credentials-isolation.md)

- **Question:** How does a tool call run safely against an external system?
- **Chosen design:** On-behalf-of tokens or a scoped service account + user check; worker pool per system; output screened; safe retries + breakers.
- **Related ADPs:** UA-ADP-02 (Identity & downstream tokens), SG-ADP-01 (Input screening & injection defence), RP-ADP-02 (Dependency failures & fallbacks)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **TA-D4** | Tool Invocation — Credentials | OBO where supported; else scoped service account + agent-side user check | Agent-side check is security-critical. |
| **TA-D9** | Tool Invocation — Tool output text | Screened by Comp 7 before the LLM; size-capped; by reference | Same engine as KR-D14. |
| **TA-D10** | Error Handling — Retries | Retry reads + idempotent writes only; backoff + jitter; breaker per system | Auth/permanent errors normalized to the agent. |
| **TA-D11** | Tool Invocation — Isolation | Worker pool per external system; outbound allow-list | Bulkhead + SSRF closed. No microVMs in v1. |

### [TA-ADP-05 · Transactional integrity & audit](./adp/04-tools-actions/TA-ADP-05-transactional-integrity-audit.md)

- **Question:** How do multi-system writes stay consistent, and what record do they leave?
- **Chosen design:** Temporal sagas with idempotent compensations; no-undo steps last and approved; append-only audit with crypto-shredding.
- **Related ADPs:** ADP-02 (Workflow durability), DP-ADP-03 (Audit, archive & settings data), DP-ADP-02 (Tenant isolation & encryption)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **TA-D8** | Tool Invocation — Multi-system writes | Saga with compensations as a Temporal workflow | Each saga write registers a compensation. |
| **TA-D17** | Compensations | Registered as idempotent tools; failure → human | UU3 fixed. |
| **TA-D18** | No-undo saga steps | Last step + human approval | KU5 mitigated. |
| **TA-D12** | Audit — Audit depth | Append-only record per call + before/after state for financial writes | SOX §404. Erasure conflict → UU5. |
| **TA-D15** | Audit vs. erasure | Crypto-shredding with per-user keys | UU5 fixed. |

## [5] Multi-Agent & Communication

Reasoning: `checkpoint.md` §9 · Diagram: `LLD - [5] Multi-Agent & Communication`

### [MA-ADP-01 · Topology & specialist set](./adp/05-multi-agent-communication/MA-ADP-01-topology-specialist-set.md)

- **Question:** How are agents organised, and which specialists exist?
- **Chosen design:** A coordinator + Generalist, Billing, Technical, Account & Ops specialists as LangGraph subgraphs; static registry.
- **Related ADPs:** ADP-01 (Planning paradigm), ADP-02 (Workflow durability)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **MA-D1** | Topology | Coordinator → specialist sub-agents; no specialist-to-specialist talk | Unified command. |
| **MA-D2** | Specialist set | Generalist, Billing, Technical, Account & Ops; coordinator separate | MA-Q1 (ii), Q2 (i). |
| **MA-D10** | Registry | Static registry in code/config | No remote agents. |
| **MA-D11** | Runtime | LangGraph subgraphs, same graph + checkpoint | Settled upstream (ADP-02, MS-D8). |

### [MA-ADP-02 · Delegation & limits](./adp/05-multi-agent-communication/MA-ADP-02-delegation-limits.md)

- **Question:** Who decides which specialist works, in what order, and within which limits?
- **Chosen design:** Jev picks the lead and extra specialists; parallel if independent; depth 1, ≤ 5 specialists, 2 steps each, 6 per turn.
- **Related ADPs:** ADP-05 (Decision model (Jev)), ADP-04 (Error recovery & replanning), CR-ADP-02 (Token & context economy)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **MA-D3** | Delegation | Jev Choice lead + Noul per specialist; low confidence → HITL | Resolves ADP-05-Q4 supervisor routing. |
| **MA-D6** | Execution order | Parallel if independent, else sequential |  |
| **MA-D8** | Limits | Depth 1 · ≤ 5 specialists · 2 steps per specialist, 6 per turn · shared token budget | Replaces ADP-04's ceiling of 4 for multi-agent turns (MA-Q4). |

### [MA-ADP-03 · Inter-agent contracts & context](./adp/05-multi-agent-communication/MA-ADP-03-inter-agent-contracts-context.md)

- **Question:** What do agents send each other, and how much context does a specialist get?
- **Chosen design:** Typed task / result contracts via the coordinator; a brief plus on-demand reads of the conversation.
- **Related ADPs:** TQ-ADP-02 (Contracts & policy checks)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **MA-D4** | Messages | Typed task/result contracts via the coordinator | Includes a 'blocked' status. |
| **MA-D5** | Context | Brief + on-demand read of the conversation | Reads logged and budgeted. |

### [MA-ADP-04 · Specialist permissions & writes](./adp/05-multi-agent-communication/MA-ADP-04-specialist-permissions-writes.md)

- **Question:** What may a specialist do on its own?
- **Chosen design:** Own identity and allow-list; low-risk writes directly only when running alone; higher-risk writes proposed; actions reported only after verification.
- **Related ADPs:** TA-ADP-01 (Tool registry & selection), TA-ADP-03 (Action validation & approval tiers)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **MA-D9** | Identity | Own identity + allow-list per specialist; reads + low-risk writes directly; everything above proposed via coordinator | Revised from read-only (user reopened). Several writers → UU6 / MA-F18. |
| **MA-D14** | Action claims | Proposed actions reported as proposed; executed low-risk writes reported only after Tools read-back; success announced by the coordinator | Amended for MA-D9 (d). UU1 fixed. |
| **MA-D18** | Several writers | Parallel branches read-only; a specialist writes only when running alone in the case | UU6 fixed. |

### [MA-ADP-05 · Merging & the single voice](./adp/05-multi-agent-communication/MA-ADP-05-merging-single-voice.md)

- **Question:** How are specialists' findings combined into one reply?
- **Chosen design:** Jev scores conflicting claims, numbers go to a human; one merged reply in one voice from the coordinator, checked for redirects.
- **Related ADPs:** HL-ADP-01 (Confidence gate), SG-ADP-03 (Output safety)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **MA-D7** | Conflicts | Jev Score per claim vs. evidence; low/tie → HITL | Numeric conflicts → UU4. |
| **MA-D16** | Numeric conflicts | Numeric disagreement → HITL | UU4 fixed. |
| **MA-D12** | User voice | Only the coordinator talks to the user | Revised from (b). |
| **MA-D13** | Ping-pong | Jev redirect check on the coordinator's reply | UK1 mitigated. |
| **MA-D15** | Merged reply | One reply after join + conflict check | UU2 fixed. |
| **MA-D17** | One voice | Shared persona; coordinator writes every reply | UK2 fixed. |

## [6] Safety, Security & Governance

Reasoning: `checkpoint.md` §10 · Diagram: `LLD - [6] Safety, Security & Governance`

### [SG-ADP-01 · Input screening & injection defence](./adp/06-safety-security-governance/SG-ADP-01-input-screening-injection-defence.md)

- **Question:** How is untrusted text (messages, passages, tool output) kept from steering the agent?
- **Chosen design:** Self-hosted Llama Guard 3 + injection classifier with pass / review / block bands, plus spotlighting; hostility via persona only.
- **Related ADPs:** KR-ADP-04 (Retrieval & ranking pipeline), TA-ADP-04 (Execution, credentials & isolation)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **SG-D1** | Injection defence | Screening + spotlighting | No quarantined LLM; TA-D9 kept. |
| **SG-D2** | Screening engine | Llama Guard 3 + injection classifier, self-hosted; not Jev | Resolves ADP-05-Q4 for Comp 7. |
| **SG-D3** | Screening outcome | Pass / review / block bands per source type | Review = read-only turn or human. |
| **SG-D7** | Hostility | Persona guidance only | Human always available (SG-D14). |

### [SG-ADP-02 · PII protection](./adp/06-safety-security-governance/SG-ADP-02-pii-protection.md)

- **Question:** How is personal data kept out of models while tools still work?
- **Chosen design:** Reversible tokenization with a vault and global deterministic tokens; real values restored only into needs_pii fields; degrade if the vault is down.
- **Related ADPs:** DP-ADP-02 (Tenant isolation & encryption), DL-ADP-05 (Secrets & key custody), MS-ADP-03 (Fact write path)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **SG-D4** | PII in prompts | Reversible tokenization with a vault | Models see tokens; restored in reply + tool args. |
| **SG-D5** | What is masked | Custom recognizers + technical-ID allow-list + global deterministic tokens | SG-Q3 (ii); UU1 accepted. |
| **SG-D16** | PII restore | Restore only into needs_pii tool fields | UU2 mitigated. |
| **SG-D18** | Vault down | Reply keeps tokens; PII-needing tools blocked | KK4 mitigated. |

### [SG-ADP-03 · Output safety](./adp/06-safety-security-governance/SG-ADP-03-output-safety.md)

- **Question:** What is checked on every reply before it reaches the user?
- **Chosen design:** Leakage and URL / markdown checks + a rule-based promise check; no tone check.
- **Related ADPs:** HL-ADP-01 (Confidence gate), MA-ADP-05 (Merging & the single voice)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **SG-D6** | Reply checks | Leakage + URL / markdown sanitization only | No commitment or tone check (UK1, UK2). |
| **SG-D15** | Promises | Rule-based promise check; hold for one rewrite unless backed | UK2 mitigated. |

### [SG-ADP-04 · Authorization & tool permissions](./adp/06-safety-security-governance/SG-ADP-04-authorization-tool-permissions.md)

- **Question:** Who may see or do what, and what happens when the policy engine is down?
- **Chosen design:** Central Cedar policies (tickets by role, blackout windows); writes fail closed, reads use a short cache when it's down.
- **Related ADPs:** TA-ADP-03 (Action validation & approval tiers), HL-ADP-03 (Approval), KR-ADP-03 (Indexing & tenant isolation)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **SG-D8** | Authorization | Central policy engine: AWS Cedar; versioned, tested policies | SG-Q1 (ii). |
| **SG-D9** | Ticket visibility | Author + tenant support / admin roles only | Closes KR UK3; hand-off to Comp 3. |
| **SG-D10** | Change freezes | Tenant blackout windows; destructive / prod actions need approval | Closes TA UK4. |
| **SG-D17** | Policy engine down | Writes fail closed; reads use a short cache | UU5 mitigated. |

### [SG-ADP-05 · Governance, retention & providers](./adp/06-safety-security-governance/SG-ADP-05-governance-retention-providers.md)

- **Question:** What is recorded, disclosed and retained for compliance, and on what terms do providers see data?
- **Chosen design:** Every automated decision recorded with a "why" view; AI disclosure + human always available; 2-year transcript archive; standard provider terms.
- **Related ADPs:** DP-ADP-03 (Audit, archive & settings data), HL-ADP-04 (Handoff & waiting)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **SG-D11** | Providers | Standard API terms | Providers see tokens, not PII. |
| **SG-D12** | Transcripts | Legal archive for 2 years; out of agent stores on erasure | SG-Q2 (i). |
| **SG-D13** | Decision audit | Every automated decision recorded + 'why' view (users: reasons + checks only) | SG-Q4 (i). |
| **SG-D14** | AI disclosure | Disclosure + human always available + review for a fixed list of significant decisions | SG-Q5 (i). |

## [7] Data & Persistence

Reasoning: `checkpoint.md` §11 · Diagram: `LLD - [7] Data & Persistence`

### [DP-ADP-01 · Store topology & residency](./adp/07-data-persistence/DP-ADP-01-store-topology-residency.md)

- **Question:** Which stores exist, and where does each tenant's data live?
- **Chosen design:** Postgres + Qdrant, deployed per region (US, EU); each tenant pinned to one region.
- **Related ADPs:** KR-ADP-03 (Indexing & tenant isolation), RP-ADP-04 (Disaster recovery & regions)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **DP-D1** | Topology | Postgres + Qdrant for Knowledge | DP-Q1 (i). |
| **DP-D10** | Residency | Regional deployments (US + EU); shared token key, vault per region | DP-Q2 (i), Q3 (i). |

### [DP-ADP-02 · Tenant isolation & encryption](./adp/07-data-persistence/DP-ADP-02-tenant-isolation-encryption.md)

- **Question:** How are tenants kept apart, and how is personal data encrypted and shredded?
- **Chosen design:** Shared tables with forced row-level security; envelope encryption with per-user data keys; an isolated token vault.
- **Related ADPs:** SG-ADP-02 (PII protection), CR-ADP-05 (Key-management cost), TQ-ADP-02 (Contracts & policy checks)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **DP-D2** | Tenant isolation | Pool: shared tables + forced row-level security | Tenant from verified token. |
| **DP-D4** | Per-user keys | Envelope encryption: per-user data key under a per-tenant KMS key | Revised by CR-D10 (was one KMS key per user). |
| **DP-D5** | Token vault | Separate, isolated database |  |

### [DP-ADP-03 · Audit, archive & settings data](./adp/07-data-persistence/DP-ADP-03-audit-archive-settings.md)

- **Question:** Where do audit records, transcripts and settings live?
- **Chosen design:** Append-only audit tables; transcript archive behind a restricted role; platform definitions in code, tenant settings in the database.
- **Related ADPs:** TA-ADP-05 (Transactional integrity & audit), SG-ADP-05 (Governance, retention & providers), DL-ADP-02 (Release tracks & cadence)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **DP-D3** | Audit store | Append-only Postgres tables | Not tamper-evident (UK1, accepted). |
| **DP-D8** | Transcript archive | Postgres table behind a restricted role (2 years) |  |
| **DP-D12** | Settings | Platform definitions in code; tenant settings in DB | Keeps MA-D10. |

### [DP-ADP-04 · Data movement & stream retention](./adp/07-data-persistence/DP-ADP-04-data-movement-stream-retention.md)

- **Question:** How do changes move between components, and how long are event streams and raw sources kept?
- **Chosen design:** No event bus — direct writes; 7-day event-log replay; versioned raw snapshots per nightly batch.
- **Related ADPs:** UA-ADP-01 (Channels & API transport), KR-ADP-02 (Ingestion & freshness)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **DP-D6** | Events | No event bus; direct writes to consumers | Lost tombstones risk (UU1). |
| **DP-D7** | Event log retention | 7-day replay window; older rebuilt from transcript | Bounds UA KU3. |
| **DP-D11** | Raw sources | Versioned raw snapshots per batch, unbounded | Erased content in snapshots (UU3). |

### [DP-ADP-05 · Erasure, backups & restore](./adp/07-data-persistence/DP-ADP-05-erasure-backups-restore.md)

- **Question:** How is erasure guaranteed across stores, snapshots and backups?
- **Chosen design:** Erasure fan-out as a Temporal workflow with a completion check; snapshots cleaned; backups expire after 35 days; restore risk accepted.
- **Related ADPs:** MS-ADP-05 (Retention & erasure), OB-ADP-02 (Telemetry storage, retention & erasure), RP-ADP-04 (Disaster recovery & regions)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **DP-D9** | Backups vs. erasure | Backups expire after 35 days; documented | DP-Q4 (i); restore risk accepted (DP-D14). |
| **DP-D13** | Deletion fan-out | Temporal workflow with durable retries + completion check | UU1 fixed. |
| **DP-D14** | Restore vs. erasure | Accepted; documented | UU2 accepted. |
| **DP-D15** | Snapshots vs. erasure | Remove erased items from every snapshot | UU3 fixed. |

## [8] Evaluation & Experimentation

Reasoning: `checkpoint.md` §12 · Diagram: `LLD - [8] Evaluation & Experimentation`

### [EV-ADP-01 · Datasets & data governance](./adp/08-evaluation-experimentation/EV-ADP-01-datasets-data-governance.md)

- **Question:** What data do we evaluate on, and under which privacy rules?
- **Chosen design:** Framework episodes + seeds + opted-in production conversations, tokenized, regional and erasable.
- **Related ADPs:** TQ-ADP-03 (End-to-end tests & test data), CI-ADP-03 (Improvement levers)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **EV-D1** | Datasets | Framework episodes + seeds + curated production conversations | Adopts user_evaluation_framework.md. |
| **EV-D10** | Production data | Tokenized, tenant-tagged, regional, in the erasure workflow | Closes KR KK6 for eval copies. |
| **EV-D15** | Consent | Per-tenant opt-in for production conversations | UK2 fixed. |

### [EV-ADP-02 · Scoring & calibration](./adp/08-evaluation-experimentation/EV-ADP-02-scoring-calibration.md)

- **Question:** How are outputs scored, and how are decision thresholds calibrated?
- **Chosen design:** Assertions + a cross-family LLM judge calibrated on human labels; thresholds calibrated per route each release.
- **Related ADPs:** ADP-05 (Decision model (Jev)), HL-ADP-01 (Confidence gate)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **EV-D2** | Scoring | Assertions + LLM judge (different model family), human-calibrated | EV-Q3 (ii). |
| **EV-D9** | Calibration | Per route on labelled sets (ECE), each release |  |

### [EV-ADP-03 · Suites, environment & cadence](./adp/08-evaluation-experimentation/EV-ADP-03-suites-environment-cadence.md)

- **Question:** What runs, against what, and how often?
- **Chosen design:** Component suites + a risk-tier end-to-end suite; staging, else fakes or recordings; smoke per commit, full nightly.
- **Related ADPs:** TQ-ADP-04 (Merge gate & flaky tests), DL-ADP-01 (Environments & infrastructure)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **EV-D3** | Unit | Per-component suites + end-to-end suite for the risk tier only | EV-Q1 (ii). |
| **EV-D4** | Environment | Staging; else fakes for write / multi-step integrations, recordings for read-only, skip low-priority | EV-Q2. |
| **EV-D6** | Cadence | Smoke per commit; full nightly + before release |  |
| **EV-D14** | Staging safety | Test accounts + outbound allow-list + notifications off | UK1 mitigated. |

### [EV-ADP-04 · Release gate & approval evidence](./adp/08-evaluation-experimentation/EV-ADP-04-release-gate-approval-evidence.md)

- **Question:** What must be true before a version ships?
- **Chosen design:** Component thresholds, zero risk-tier violations, pass^k, cost / latency budgets, live CSAT / FCR / CES; evidence only for routes covered.
- **Related ADPs:** CR-ADP-04 (Budgets & cost governance), DL-ADP-03 (Rollout & rollback)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **EV-D5** | Release gate | Component thresholds + zero risk-tier violations + pass^k + cost / latency + live CSAT / FCR / CES | Weighted task success dropped (EV-Q1). |
| **EV-D13** | Approval evidence | Live evidence only for routes it covered; high-risk changes need offline + shadow | UU2 fixed. |

### [EV-ADP-05 · Live evaluation & experiments](./adp/08-evaluation-experimentation/EV-ADP-05-live-evaluation-experiments.md)

- **Question:** How is quality watched and tested on real traffic?
- **Chosen design:** Implicit signals + sampled judge scoring; shadow (writes never executed) and canary on read-only routes; replies buffered until checked.
- **Related ADPs:** UA-ADP-04 (Response contract & delivery), DL-ADP-03 (Rollout & rollback), CI-ADP-01 (Feedback signals)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **EV-D7** | Live experiments | Shadow + canary / A/B on read-only routes | EV-Q4 (i). |
| **EV-D8** | Live quality | Implicit signals + sampled judge scoring |  |
| **EV-D12** | Shadow tools | Reads live; writes recorded as proposals, never executed | UU5 fixed. |
| **EV-D11** | Streaming | Buffer checked reply; stream status events (resolves UA-D8) |  |

## [9] Observability & Monitoring

Reasoning: `checkpoint.md` §13 · Diagram: `LLD - [9] Observability & Monitoring`

### [OB-ADP-01 · Instrumentation & trace pipeline](./adp/09-observability-monitoring/OB-ADP-01-instrumentation-trace-pipeline.md)

- **Question:** How are traces produced, scrubbed and sampled?
- **Chosen design:** OpenTelemetry + SDK spans; collector scrubs PII; tail sampling keeps errors, escalations, risk-tier and slow traces with full content.
- **Related ADPs:** SG-ADP-02 (PII protection), TQ-ADP-02 (Contracts & policy checks)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **OB-D1** | Instrumentation | OpenTelemetry + LLM SDK as instrumentation only, exporting OTel spans | OB-Q1 (i). |
| **OB-D3** | Trace content | Full tokenized content only for kept traces; metadata otherwise |  |
| **OB-D4** | Sampling | Tail-based: keep errors, escalations, risk-tier, slow |  |
| **OB-D14** | PII in telemetry | Collector runs PII recognizers on logs and spans | KK1 mitigated. |

### [OB-ADP-02 · Telemetry storage, retention & erasure](./adp/09-observability-monitoring/OB-ADP-02-telemetry-storage-retention-erasure.md)

- **Question:** Where is telemetry stored, for how long, and how is it erased?
- **Chosen design:** Jaeger + OpenSearch per region; JSON logs with trace IDs; 7-day retention; delete by user / conversation ID.
- **Related ADPs:** DP-ADP-05 (Erasure, backups & restore), DP-ADP-01 (Store topology & residency)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **OB-D2** | Trace backend | Jaeger + OpenSearch, per region | OB-Q3 (i). |
| **OB-D5** | Retention | 7 days for traces and logs | Eval copies within window. |
| **OB-D6** | Erasure | Delete by user / conversation ID (OpenSearch query) in the DP-D13 workflow |  |
| **OB-D12** | Logs | Structured JSON, separate store, trace ID in every line |  |

### [OB-ADP-03 · Service levels & alerting](./adp/09-observability-monitoring/OB-ADP-03-service-levels-alerting.md)

- **Question:** What do we alert on, and against which targets?
- **Chosen design:** Internal SLOs (no tenant-facing targets) with burn-rate alerts + specific hand-off alerts; Temporal UI for runs.
- **Related ADPs:** RP-ADP-03 (Bursts, latency & capacity), HL-ADP-02 (Escalation & queues)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **OB-D7** | Service levels | No tenant-facing targets; internal SLOs for alerting only | OB-Q2 (ii). |
| **OB-D8** | Alerting | Burn-rate on internal SLOs + hand-off alerts |  |
| **OB-D10** | Execution | Temporal UI + traces only | Forgotten workflows (UU3). |

### [OB-ADP-04 · Token & cost telemetry](./adp/09-observability-monitoring/OB-ADP-04-token-cost-telemetry.md)

- **Question:** How are tokens and cost observed per tenant, conversation and component?
- **Chosen design:** Per tenant / conversation / component, estimated from kept traces (exact numbers come from Cost's counter).
- **Related ADPs:** CR-ADP-04 (Budgets & cost governance), RP-ADP-01 (Admission control)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **OB-D9** | Tokens / cost | Per tenant, conversation, component | Sampling gap (UU1). |
| **OB-D13** | Cost numbers | Scaled from kept traces (estimates) | UU1 accepted. |

### [OB-ADP-05 · Failure classification](./adp/09-observability-monitoring/OB-ADP-05-failure-classification.md)

- **Question:** How are failed conversations categorised at scale?
- **Chosen design:** Rules on error codes and decision records, then a Jev Choice over the failure taxonomy.
- **Related ADPs:** CI-ADP-02 (Failure analysis)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **OB-D11** | Failure classes | Rules, then Jev Choice over a failure taxonomy | Jev use 7. |

## [10] Reliability / Performance / Scale

Reasoning: `checkpoint.md` §14 · Diagram: `LLD - [10] Reliability / Performance / Scale`

### [RP-ADP-01 · Admission control](./adp/10-reliability-performance-scale/RP-ADP-01-admission-control.md)

- **Question:** How much traffic do we accept, and what happens when there's too much?
- **Chosen design:** Limits per tenant, user, conversation and tokens/min (exact counter); over the limit → knowledge-base-only answer, then 429; one active turn per conversation.
- **Related ADPs:** UA-ADP-01 (Channels & API transport), CR-ADP-04 (Budgets & cost governance)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **RP-D1** | Rate limits | Per tenant / user / conversation + tokens per minute per tenant | Needs real-time token counts (UU1). |
| **RP-D2** | Over limit | Knowledge-base-only answer (generated, or snippets if no LLM); 429 at a hard ceiling | RP-Q1 (iii). |
| **RP-D3** | Duplicate messages | One active turn per conversation (HITL waits count); reject new messages | RP-Q2 (ii). |
| **RP-D14** | Token counts | Provider-reported usage into a per-tenant counter | UU1 fixed; counter store → Comp 8. |

### [RP-ADP-02 · Dependency failures & fallbacks](./adp/10-reliability-performance-scale/RP-ADP-02-dependency-failures-fallbacks.md)

- **Question:** What happens when an LLM provider, Jev or a tool system fails?
- **Chosen design:** Self-hosted fallback LLM; fallback classifier for Jev; tool requests held up to 24 h; one retry layer with retry budgets.
- **Related ADPs:** ADP-04 (Error recovery & replanning), ADP-05 (Decision model (Jev)), TA-ADP-04 (Execution, credentials & isolation), CR-ADP-01 (Model tier routing)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **RP-D4** | LLM provider failure | Fail over to a self-hosted open-weights model per region; then knowledge-base-only | RP-Q3 (iii); also serves easy low-risk turns in normal operation (CR-D9). |
| **RP-D5** | Jev outage | Fallback LLM classifier for triage / delegation; guards stay fail-safe | Adds to ADP-05. |
| **RP-D7** | Breaker open | Hold up to 24 h, deliver to the inbox on recovery; then human | RP-Q4 (ii). |
| **RP-D13** | Retry layers | One layer per dependency + per-turn and global retry budgets | KK3 fixed. |

### [RP-ADP-03 · Bursts, latency & capacity](./adp/10-reliability-performance-scale/RP-ADP-03-bursts-latency-capacity.md)

- **Question:** How do we stay fast and absorb spikes?
- **Chosen design:** Request coalescing + incident mode; first status ≤ 1 s, p95 targets per route; autoscaling with a pre-warmed minimum.
- **Related ADPs:** OB-ADP-03 (Service levels & alerting), UA-ADP-04 (Response contract & delivery)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **RP-D6** | Bursts | Request coalescing + incident mode (Jev Noul → status answer) | Jev uses 4, 8. |
| **RP-D8** | Latency | First status ≤ 1 s; final p95 FAQ 5 s · diagnostics 20 s · multi-specialist 45 s | RP-Q5 (i). |
| **RP-D9** | Capacity | Autoscaling + pre-warmed minimum |  |

### [RP-ADP-04 · Disaster recovery & regions](./adp/10-reliability-performance-scale/RP-ADP-04-disaster-recovery-regions.md)

- **Question:** How do we survive zone, data and region failures?
- **Chosen design:** Multi-AZ inside each region, no cross-region failover; point-in-time recovery; monthly drills into a warm standby.
- **Related ADPs:** DP-ADP-01 (Store topology & residency), DP-ADP-05 (Erasure, backups & restore)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **RP-D10** | Region loss | Multi-AZ inside each region; no cross-region failover | Keeps DP-D10. |
| **RP-D11** | Backups / DR | Point-in-time recovery + monthly drills incl. Qdrant, vault, OpenSearch |  |
| **RP-D15** | Drill data | Drills restore into a same-region warm standby (treated as production) | In the erasure fan-out. |

### [RP-ADP-05 · Resilience testing](./adp/10-reliability-performance-scale/RP-ADP-05-resilience-testing.md)

- **Question:** How do we prove the fallbacks and capacity work before users depend on them?
- **Chosen design:** Load tests before every release + chaos tests on staging.
- **Related ADPs:** TQ-ADP-05 (Migrations & non-functional tests)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **RP-D12** | Testing | Load tests per release + chaos tests |  |

## [11] Cost & Resource Management

Reasoning: `checkpoint.md` §15 · Diagram: `LLD - [11] Cost & Resource Management`

### [CR-ADP-01 · Model tier routing](./adp/11-cost-resource-management/CR-ADP-01-model-tier-routing.md)

- **Question:** Which model answers each turn?
- **Chosen design:** A Jev difficulty score picks self-hosted / mid-tier / frontier; failed steps cascade one tier up; the self-hosted tier also serves easy turns.
- **Related ADPs:** ADP-05 (Decision model (Jev)), RP-ADP-02 (Dependency failures & fallbacks), DL-ADP-04 (Versioning of models, indexes & workflows)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **CR-D1** | Model tier | Jev difficulty Score picks self-hosted / mid-tier / frontier per turn | CR-Q1 (ii). |
| **CR-D2** | Escalation | Cascade to the next tier on failed checks / low confidence |  |
| **CR-D9** | Fallback model use | Self-hosted model also serves easy low-risk turns | Extends RP-D4. |

### [CR-ADP-02 · Token & context economy](./adp/11-cost-resource-management/CR-ADP-02-token-context-economy.md)

- **Question:** How are tokens per turn kept down?
- **Chosen design:** Turn and daily conversation budgets; provider prompt caching + passage compression; cheaper tiers for helpers where proven.
- **Related ADPs:** ADP-03 (Context engineering), KR-ADP-04 (Retrieval & ranking pipeline), MA-ADP-02 (Delegation & limits)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **CR-D5** | Turn budget | Token budget per turn by route + daily per conversation; wrap up or hand off | Room for one cascade step. |
| **CR-D6** | Context cost | Slots + provider prompt caching + passage compression | Dialogue, pins, delimiters never compressed. |
| **CR-D8** | Helpers | Cheaper tiers for reranker / screening / judge where EV shows no loss |  |

### [CR-ADP-03 · Answer cache](./adp/11-cost-resource-management/CR-ADP-03-answer-cache.md)

- **Question:** When can an answer be reused instead of generated?
- **Chosen design:** Per-tenant cache of public-KB-only answers for 7 days, keyed by question + version + KB index; Jev decides eligibility.
- **Related ADPs:** KR-ADP-02 (Ingestion & freshness), SG-ADP-02 (PII protection)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **CR-D3** | Answer cache | Per tenant, public-KB-only answers, 7 days; Jev eligibility Noul; invalidated by KB updates + tombstones | CR-Q2 (ii). |
| **CR-D14** | Cache key | Question + tenant + version + KB index; version questions not cached | UK1 mitigated. |

### [CR-ADP-04 · Budgets & cost governance](./adp/11-cost-resource-management/CR-ADP-04-budgets-cost-governance.md)

- **Question:** How is spend measured, reported and capped?
- **Chosen design:** Exact cost from the usage counter, reconciled monthly; tenant budgets with a soft cap; reports for tenant admins; ≤ 10 % cost rise per release.
- **Related ADPs:** EV-ADP-04 (Release gate & approval evidence), RP-ADP-01 (Admission control), OB-ADP-04 (Token & cost telemetry)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **CR-D4** | Tenant budget | Monthly budget; alert at 80 %; soft cap → KB-only answers |  |
| **CR-D7** | Cost reports | Per-tenant usage reports for tenant admins |  |
| **CR-D11** | Cost truth | Exact counter × price table, reconciled monthly with invoices |  |
| **CR-D12** | Release gate | ≤ 10 % rise per release; ceiling 1.5 × first month's cost per route | CR-Q3 (i), Q4 (i). |

### [CR-ADP-05 · Key-management cost](./adp/11-cost-resource-management/CR-ADP-05-key-management-cost.md)

- **Question:** How do per-user encryption keys stay affordable and erasable?
- **Chosen design:** Envelope encryption under per-tenant KMS keys; wrapped keys in a separate store with 1-day backups.
- **Related ADPs:** DP-ADP-02 (Tenant isolation & encryption), DP-ADP-05 (Erasure, backups & restore)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **CR-D10** | KMS keys | Envelope encryption (revises DP-D4) | Backup key copies → UU1. |
| **CR-D13** | Key storage | Separate key store per region, 1-day backup retention | UU1 mitigated. |

## [12] Human-in-the-Loop

Reasoning: `checkpoint.md` §16 · Diagram: `LLD - [12] Human-in-the-Loop`

### [HL-ADP-01 · Confidence gate](./adp/12-human-in-the-loop/HL-ADP-01-confidence-gate.md)

- **Question:** When is a draft reply sent, edited by a human, or handed off?
- **Chosen design:** Jev checks support and relevance; send ≥ 0.90, co-pilot 0.50–0.90, hand off below; money / SLA figures always reviewed.
- **Related ADPs:** ADP-05 (Decision model (Jev)), EV-ADP-02 (Scoring & calibration), MA-ADP-05 (Merging & the single voice)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **HL-D1** | Confidence gate | Jev: claims supported (Noul) + relevance (Score) per draft | Numbers → UU1. |
| **HL-D2** | Gate bands | Send ≥ 0.90 · co-pilot 0.50–0.90 (staffed routes) · hand off < 0.50 | HL-Q1 (ii). |
| **HL-D13** | Numbers in drafts | Money / SLA figures → co-pilot band | UU1 fixed; more human load. |

### [HL-ADP-02 · Escalation & queues](./adp/12-human-in-the-loop/HL-ADP-02-escalation-queues.md)

- **Question:** How does work reach the right human in time?
- **Chosen design:** One typed escalation packet; skills-based queues with SLA timers; aging alerts; undecided approvals cancelled after 3 days.
- **Related ADPs:** ADP-04 (Error recovery & replanning), OB-ADP-03 (Service levels & alerting)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **HL-D3** | Queues | Skills-based; SLA: handoff 15 min, approval 1 h, review 1 business day → senior queue | HL-Q2 (i). |
| **HL-D9** | Stuck items | Aging alerts; undecided approvals cancelled after 3 days | HL-Q4 (i). |
| **HL-D12** | Escalation format | One typed escalation packet for all sources |  |

### [HL-ADP-03 · Approval](./adp/12-human-in-the-loop/HL-ADP-03-approval-workflows.md)

- **Question:** Who may approve an action, and what must they check?
- **Chosen design:** Rights by role and amount (senior ≥ tenant amount, default $5,000), approver ≠ handler; card with evidence, dry-run and field-by-field confirmation.
- **Related ADPs:** TA-ADP-03 (Action validation & approval tiers), SG-ADP-04 (Authorization & tool permissions)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **HL-D4** | Approval rights | By role and amount (senior ≥ tenant setting, default $5,000); approver ≠ handler | HL-Q3 (iii). |
| **HL-D5** | Approval card | Evidence + dry-run; confirm key fields one by one |  |

### [HL-ADP-04 · Handoff & waiting](./adp/12-human-in-the-loop/HL-ADP-04-handoff-waiting-experience.md)

- **Question:** How does a conversation move to a human, and what does the user see meanwhile?
- **Chosen design:** Immediate handoff on request; cold handoff once a human picks up; wait estimate and cancel option; human replies checked as warnings.
- **Related ADPs:** UA-ADP-04 (Response contract & delivery), SG-ADP-05 (Governance, retention & providers)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **HL-D6** | Handoff | Cold: human takes over, agent stops |  |
| **HL-D7** | Human request | Immediate handoff; agent answers low-risk while waiting; Jev Noul detects |  |
| **HL-D8** | Waiting UX | Status + inbox + wait estimate + cancel pending action |  |
| **HL-D14** | Human replies | Same output checks as warnings, override with reason | UK3 mitigated. |

### [HL-ADP-05 · Feedback & console](./adp/12-human-in-the-loop/HL-ADP-05-feedback-console.md)

- **Question:** What do specialists record, and where do they work?
- **Chosen design:** Approve / reject with reason codes; self-hosted Retool in each region.
- **Related ADPs:** CI-ADP-01 (Feedback signals), DP-ADP-01 (Store topology & residency)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **HL-D10** | Feedback | Approve / reject + reason codes |  |
| **HL-D11** | Console | Self-hosted Retool per region | HL-Q5 (i). |

## [13] Testing & Quality

Reasoning: `checkpoint.md` §17 · Diagram: `LLD - [13] Testing & Quality`

### [TQ-ADP-01 · Testing model-driven logic](./adp/13-testing-quality/TQ-ADP-01-testing-model-driven-logic.md)

- **Question:** How do we test code whose inputs come from models?
- **Chosen design:** Models mocked; scripted and property-based tests of the safety invariants; a fixed injection set.
- **Related ADPs:** EV-ADP-03 (Suites, environment & cadence), SG-ADP-01 (Input screening & injection defence)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **TQ-D1** | Model calls in tests | Always mocked; model behaviour only in Evaluation |  |
| **TQ-D2** | Control logic | Deterministic tests + property-based invariant tests |  |
| **TQ-D3** | Adversarial | Fixed injection / jailbreak set in CI | Goes stale (accepted). |

### [TQ-ADP-02 · Contracts & policy checks](./adp/13-testing-quality/TQ-ADP-02-contracts-policy-checks.md)

- **Question:** How do we stop components, policies and data rules from silently breaking?
- **Chosen design:** Contract tests for shared formats; Cedar, RLS and tool-declaration checks in CI; end-to-end trace tests.
- **Related ADPs:** SG-ADP-04 (Authorization & tool permissions), DP-ADP-02 (Tenant isolation & encryption), OB-ADP-01 (Instrumentation & trace pipeline)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **TQ-D4** | Policy + security | Cedar unit tests + CI checks (RLS, tool declarations, policy tests) |  |
| **TQ-D5** | Contracts | Contract tests for shared formats incl. Jev question sets |  |
| **TQ-D11** | Trace context | Integration tests for one trace end to end | Closes OB KK2 in tests. |

### [TQ-ADP-03 · End-to-end tests & test data](./adp/13-testing-quality/TQ-ADP-03-end-to-end-tests-data.md)

- **Question:** Which journeys are tested end to end, and on what data?
- **Chosen design:** One test per framework scenario on staging; synthetic personas + opted-in tokenized samples.
- **Related ADPs:** EV-ADP-01 (Datasets & data governance), DL-ADP-01 (Environments & infrastructure)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **TQ-D6** | E2E | One E2E test per framework scenario (8) on staging |  |
| **TQ-D12** | Test data | Synthetic personas + tokenized opted-in production samples | Fixtures in erasure inventory; EU samples excluded (DL-D12). |

### [TQ-ADP-04 · Merge gate & flaky tests](./adp/13-testing-quality/TQ-ADP-04-merge-gates-flaky-tests.md)

- **Question:** What must pass before a merge, and how are flaky tests handled?
- **Chosen design:** Unit + integration + contracts + policy + EV smoke; retries allowed except for safety tests.
- **Related ADPs:** EV-ADP-03 (Suites, environment & cadence), DL-ADP-02 (Release tracks & cadence)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **TQ-D8** | Flaky tests | Automatic retries | Can hide races (UU1). |
| **TQ-D9** | Merge gate | Unit + integration + contracts + policy + EV smoke |  |
| **TQ-D13** | Safety-test retries | No retries for invariant / property / policy / security tests | UU1 fixed. |

### [TQ-ADP-05 · Migrations & non-functional tests](./adp/13-testing-quality/TQ-ADP-05-migrations-non-functional-tests.md)

- **Question:** How are schema changes, checkpoints and performance validated?
- **Chosen design:** SQL migrations by review; old checkpoints must load through migrations; load + chaos before each release.
- **Related ADPs:** MS-ADP-04 (Agent state & durability), RP-ADP-05 (Resilience testing)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **TQ-D7** | Migrations | Code review only | KK4 owned. |
| **TQ-D14** | Checkpoint migrations | Automated test: old stored checkpoints load via migrations | KK4 mitigated. |
| **TQ-D10** | Load / chaos | Staging before each release | As RP-D12. |

## [14] Deployment & LLMOps

Reasoning: `checkpoint.md` §18 · Diagram: `LLD - [14] Deployment & LLMOps`

### [DL-ADP-01 · Environments & infrastructure](./adp/14-deployment-llmops/DL-ADP-01-environments-infrastructure.md)

- **Question:** Which environments exist, and what do they run on?
- **Chosen design:** Dev + one US staging + production per region on Kubernetes with IaC; only US samples in staging.
- **Related ADPs:** DP-ADP-01 (Store topology & residency), TQ-ADP-03 (End-to-end tests & test data)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **DL-D1** | Environments | Dev + one US staging + production per region | EU samples → UU2. |
| **DL-D9** | Infrastructure | Kubernetes per region + IaC |  |
| **DL-D12** | Staging samples | Only US tenants' samples in US staging | UU2 fixed; amends TQ-D12 for EU. |

### [DL-ADP-02 · Release tracks & cadence](./adp/14-deployment-llmops/DL-ADP-02-release-tracks-cadence.md)

- **Question:** How do code and behaviour changes ship?
- **Chosen design:** Code deploys continuously; prompts, Jev questions, thresholds and model config are held for a scheduled gated release.
- **Related ADPs:** EV-ADP-04 (Release gate & approval evidence), TQ-ADP-04 (Merge gate & flaky tests), CI-ADP-04 (Validation & approval of changes)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **DL-D2** | Behaviour versioning | Ship with code; CI path rule holds behaviour merges for the scheduled gated release | DL-Q3 (i). |
| **DL-D10** | Cadence | Code continuous; behaviour + model changes scheduled through the gate | DL-Q3 (i). |

### [DL-ADP-03 · Rollout & rollback](./adp/14-deployment-llmops/DL-ADP-03-rollout-rollback.md)

- **Question:** How does a release reach production, and how is it undone?
- **Chosen design:** Code all at once per region; behaviour and model releases shadow → canary → all; manual rollback.
- **Related ADPs:** EV-ADP-05 (Live evaluation & experiments), OB-ADP-03 (Service levels & alerting)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **DL-D4** | Rollout | Code all at once; behaviour / model releases shadow → canary → all | DL-Q2 (i). |
| **DL-D5** | Rollback | Manual |  |

### [DL-ADP-04 · Versioning of models, indexes & workflows](./adp/14-deployment-llmops/DL-ADP-04-versioning-models-indexes-workflows.md)

- **Question:** How do model, index and workflow versions change safely?
- **Chosen design:** Latest aliases for LLM tiers, embedding model and Jev pinned; in-place re-index; Continue-As-New for in-flight workflows.
- **Related ADPs:** ADP-02 (Workflow durability), MS-ADP-04 (Agent state & durability), KR-ADP-03 (Indexing & tenant isolation)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **DL-D3** | Model versions | Latest aliases for LLM tiers; embedding model + Jev pinned | DL-Q1 (ii). |
| **DL-D6** | In-flight workflows | Continue-As-New at release boundaries | Drain signals first (UU3). |
| **DL-D11** | Re-index | In place, in a maintenance window |  |

### [DL-ADP-05 · Secrets & key custody](./adp/14-deployment-llmops/DL-ADP-05-secrets-key-custody.md)

- **Question:** How are secrets and the shared token key stored and rotated?
- **Chosen design:** Secrets manager per region with scheduled rotation; the shared token key stored per region and not rotated.
- **Related ADPs:** SG-ADP-02 (PII protection), DP-ADP-02 (Tenant isolation & encryption)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **DL-D7** | Secrets | Secrets manager per region, scheduled rotation |  |
| **DL-D8** | Token key | In each region's secrets manager; no rotation | UU5 accepted. |

## [15] Continuous Improvement

Reasoning: `checkpoint.md` §19 · Diagram: `LLD - [15] Continuous Improvement`

### [CI-ADP-01 · Feedback signals](./adp/15-continuous-improvement/CI-ADP-01-feedback-signals.md)

- **Question:** What signals tell us something went wrong or right?
- **Chosen design:** Thumbs, reason codes, implicit signals and a post-resolution survey; free text classified and ranked by Jev.
- **Related ADPs:** HL-ADP-05 (Feedback & console), EV-ADP-05 (Live evaluation & experiments)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **CI-D1** | Feedback | Thumbs + reason codes + implicit signals + post-resolution survey |  |
| **CI-D11** | Free-text feedback | Jev Choice category + Score severity | Jev use 7. |

### [CI-ADP-02 · Failure analysis](./adp/15-continuous-improvement/CI-ADP-02-failure-analysis.md)

- **Question:** How are failures categorised, prioritised and reviewed?
- **Chosen design:** Hierarchical taxonomy in code; weekly reviews by volume × severity; postmortems for safety or financial incidents.
- **Related ADPs:** OB-ADP-05 (Failure classification)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **CI-D2** | Taxonomy | Hierarchical, mapped to components, versioned; monthly new-category review | Owner of OB-D11 taxonomy. |
| **CI-D3** | Reviews | Weekly by volume × severity + postmortems for safety / financial incidents |  |

### [CI-ADP-03 · Improvement levers](./adp/15-continuous-improvement/CI-ADP-03-improvement-levers.md)

- **Question:** What may we change to fix a failure?
- **Chosen design:** Prompts, Jev questions, thresholds, tools, KB articles (agent drafts, human publishes), curated few-shot, per-region fine-tuning.
- **Related ADPs:** KR-ADP-01 (Knowledge sources & content labelling), EV-ADP-01 (Datasets & data governance), CR-ADP-01 (Model tier routing)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **CI-D4** | Levers | Prompts, Jev questions, thresholds, tools, KB, few-shot + per-region fine-tuning of the self-hosted model | CI-Q1 (ii) same opt-in, new terms; CI-Q2 (i) per region. |
| **CI-D5** | Few-shot | Curated per route, tokenized, excluded from tests | Closes EV KK4. |
| **CI-D6** | Articles | Agent drafts, human reviews and publishes |  |

### [CI-ADP-04 · Validation & approval of changes](./adp/15-continuous-improvement/CI-ADP-04-validation-approval-changes.md)

- **Question:** How do we prove a fix works and approve it?
- **Chosen design:** Every failure becomes a test first; gate + before / after + read-only A/B; normal code review.
- **Related ADPs:** EV-ADP-04 (Release gate & approval evidence), DL-ADP-02 (Release tracks & cadence), TQ-ADP-04 (Merge gate & flaky tests)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **CI-D7** | Failures → tests | Every reviewed failure → test before fix; clustered |  |
| **CI-D8** | Validation | Gate + before / after on cluster + read-only A/B |  |
| **CI-D10** | Approval | Normal code review | UK2 accepted. |

### [CI-ADP-05 · Long-term evolution & retraining](./adp/15-continuous-improvement/CI-ADP-05-long-term-evolution-retraining.md)

- **Question:** How does the system stay current over months?
- **Chosen design:** Monthly user-distribution check; quarterly owned-risk review; quarterly retraining without erased users' data.
- **Related ADPs:** EV-ADP-01 (Datasets & data governance), MS-ADP-05 (Retention & erasure)

| Decision | Title | Choice | Notes |
| :--- | :--- | :--- | :--- |
| **CI-D9** | Evolution | Monthly distribution check + quarterly owned-risk review |  |
| **CI-D12** | Erasure vs. weights | Quarterly retraining without erased users' data | UU1 mitigated. |
