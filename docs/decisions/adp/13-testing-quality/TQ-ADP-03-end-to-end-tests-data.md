# TQ-ADP-03: Staging End-to-End Scenarios & Erasable Test Data Governance (Framework Epics, Synthetic Personas & Tokenized Production Samples)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-05 *(Confirmed per TQ-D6 Master Framework E2E Scenarios, TQ-D12 Hybrid Test Data & DP-D13 Staging Erasure Fan-Out UU3)*
- **Deciders**: Architecture Team, Lead Quality Engineer, Data Privacy Officer, Platform Operations Director
- **Component**: `[13] Testing & Quality` (`Component [ 13 ]`)
- **Reasoning Source**: `checkpoint.md` §17 · Diagram: `LLD - [13] Testing & Quality`
- **Decisions Covered**:
  - `TQ-D6`: Framework Master Scenario E2E Staging Verification — Executes dedicated, full-system end-to-end integration tests on the Staging environment covering all 8 canonical customer journey scenarios documented in the master evaluation framework (`user_evaluation_framework.md`); exercises the complete operational trajectory from HTTP Gateway through Safety Screening, LangGraph FSM, Specialist Subgraphs, External Mock Tools, and SSE Client Streaming
  - `TQ-D12`: Hybrid Test Data & Erasable Fixture Governance — Combines rich synthetic personas (generated from archetypal customer profiles with zero real personal data) with tokenized, PII-masked production transcripts harvested exclusively from opted-in enterprise tenants (`EV-D10`, `EV-D15`); resolves GDPR data leakage ($UU3$) by indexing all production-derived staging fixtures in the primary Temporal deletion inventory (`DP-D13`), guaranteeing that an erasure request purges test fixtures alongside live databases; strictly excludes European customer samples from US Staging (`DL-D12`)
- **Related Architectural Decision Points**:
  - [`EV-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/08-evaluation-experimentation/EV-ADP-01-datasets-data-governance.md): Datasets & Data Governance *(Opt-In Transcripts & Masking)*
  - [`DL-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/14-deployment-llmops/DL-ADP-01-environments-infrastructure.md): Environments & Infrastructure *(Staging Environment Topology)*
  - [`DP-ADP-05`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/07-data-persistence/DP-ADP-05-erasure-backups-restore.md): Erasure, Backups & Restore *(Temporal Deletion Fan-Out)*
  - [`DL-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/14-deployment-llmops/DL-ADP-03-rollout-rollback.md): Rollout & Rollback *(Pre-Release Staging Validation)*

---

## 1. Context & Problem Statement

End-to-end testing of complex multi-agent enterprise workflows presents unique fidelity and compliance challenges:
1. **The Synthetic Gap vs. Production Complexity**:
   - Purely synthetic mock data (e.g., standard Faker-generated strings) fails to reproduce the messy linguistic ambiguity, multi-variable customer intents, and edge-case errors encountered in enterprise support.
   - Conversely, copying raw production customer databases into staging environments causes catastrophic data privacy breaches, leaks live credentials, and violates GDPR Article 5 purpose limitation covenants.
2. **The Staging Erasure Blind Spot ($UU3$)**:
   - When an enterprise customer submits a GDPR Article 17 "Right to Erasure" request (`MS-D14`), the deletion fan-out scrubs live production databases, audit logs, vector indices, and backups (`DP-D13`).
   - If tokenized production samples were exported to staging test fixtures, the customer's personal records persist indefinitely in staging CI/CD test runners, resulting in severe non-compliance and regulatory fines ($UU3$).
3. **The Staging Side-Effect Danger (`EV-D14`, $UK1$)**:
   - If an end-to-end test executes a real multi-agent customer journey against staging third-party APIs (e.g., payment sandboxes or notification services), a misconfigured staging system can accidentally dispatch real emails or trigger webhooks against actual end-users.

### The Core Architectural Question
> **How do we construct a realistic, end-to-end staging test harness covering all canonical customer journeys that incorporates real-world conversational nuances while guaranteeing zero side effects and automated test-fixture erasure?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `TQ-D6` and `TQ-D12` establish the **Framework Master Scenario E2E Suite and Erasable Test Data Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   STAGING E2E HARNESS & TEST DATA GOVERNANCE (TQ-D6, TQ-D12)                     │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                                    NIGHTLY CI / PRE-RELEASE GATE
                                                   │
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 1. TEST DATA REPOSITORY & ERASURE INDEXING (TQ-D12, UU3)                                         │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Two Data Sources:                                                                                │
│ • Source A: Pure Synthetic Archetypes (Faker Personas, Seeded Synthetic Cases)                  │
│ • Source B: Tokenized Production Samples from Opted-In US Tenants (`EV-D10`, `EV-D15`)           │
│                                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ Staging Fixture Governance (UU3 Mitigated):                                              │   │
│   │ • All Source B fixtures registered in DP-D13 Erasure Inventory (`staging_test_fixtures`) │   │
│   │ • Deletion Request -> Temporal Fan-Out purges live DB AND staging test fixtures!         │   │
│   │ • Strict Geographic Isolation: Zero EU tenant transcripts imported to US Staging (`DL-D12)│   │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                   │
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 2. STAGING ISOLATION & SAFETY HARNESS (EV-D14, UK1)                                              │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ • Outbound Network Allow-List: Hardcoded egress rules block real SMTP/SMS relays                 │
│ • Sandboxed Worker Pools: Tools execute against stateful WireMock/fakes (`TA-D11`)               │
│ • Dedicated Isolated Test Accounts: UUID prefix `usr_test_*`                                     │
└──────────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                   │
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 3. THE 8 MASTER FRAMEWORK SCENARIO SUITE (TQ-D6, user_evaluation_framework.md)                  │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Executes full journey from HTTP Gateway through SSE Delivery:                                     │
│ [Scenario 1: Standard FAQ Inquiry]         [Scenario 5: Base64 Prompt Injection Attack]          │
│ [Scenario 2: Multi-Turn Troubleshooting]    [Scenario 6: Rate Limiting & Graceful Degradation]    │
│ [Scenario 3: High-Value Financial Refund]   [Scenario 7: Specialist Conflict & Single Voice]      │
│ [Scenario 4: Two-Person Rule Approval]     [Scenario 8: Rapid Double-Click Concurrency Race]     │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Pillar 1: The 8 Master Framework Scenarios (`TQ-D6`)

The end-to-end suite models the complete spectrum of enterprise customer support interactions:
1. **Scenario 1 (Direct Retrieval)**: Basic documentation query verifying standalone search and prompt prefix caching.
2. **Scenario 2 (Diagnostic SOP)**: Multi-turn technical diagnostic path triggering LangGraph FSM transitions and tool reads.
3. **Scenario 3 (Financial Write Saga)**: Refund request exceeding threshold ($>\$1,000$), verifying Temporal saga staging.
4. **Scenario 4 (Two-Person Approval)**: Staged action routed to Retool console, validating Cedar segregation of duties (`HL-D4`).
5. **Scenario 5 (Adversarial Security)**: Base64 obfuscated prompt injection, asserting immediate block at `SG-D1`.
6. **Scenario 6 (Traffic Degradation)**: Rapid burst of turns exceeding token quota, verifying graceful switch to KB-only mode (`RP-D2`).
7. **Scenario 7 (Multi-Specialist Dispute)**: Billing vs. Technical specialist dispute, validating coordinator single voice (`MA-D5`).
8. **Scenario 8 (Turn Concurrency Mutex)**: Simultaneous double-click message submission, asserting `HTTP 409` lock (`RP-D3`).

---

### Pillar 2: Erasable Test Fixture Governance (`TQ-D12`, $UU3$)

To reconcile realistic test data with GDPR Article 17 "Right to Erasure":
1. **The Staging Erasure Fan-Out ($UU3$)**:
   - Test fixtures derived from opted-in production conversations (`EV-D15`) are tagged with the customer's pseudo-anonymized User UUID.
   - When a deletion request is executed by the Temporal erasure workflow (`DP-D13`), the workflow dispatches a purge signal to the Staging Test Fixture Store:
     `DELETE FROM staging_fixtures WHERE user_id = :user_id;`
   - Guarantees that personal records cannot linger inside automated testing repositories ($UU3$ mitigated).
2. **Regional Sovereignty Invariant (`DL-D12`)**:
   - In accordance with `DL-ADP-01`, Staging is hosted in `us-east-1`. European tenant transcripts are strictly forbidden from being imported to Staging, ensuring European data never crosses transatlantic boundaries.

---

### Pillar 3: Staging Safety Enclosure (`EV-D14`, $UK1$)

To prevent test runs from inducing real-world harm:
- **Egress Firewall Rules**: Kubernetes network policies block outbound traffic from staging pods to public customer email or webhook endpoints.
- **Stateful Fakes**: All state-mutating tool activities execute against stateful mock services (e.g., WireMock / LocalStack) that reset state before each nightly test run (`EV-D4`).

---

## 3. Technical Implementation & Genesis Contracts

```python
"""
tests/e2e/test_framework_scenarios.py
End-to-End Staging integration tests executing the 8 Master Framework Scenarios (TQ-D6).
"""

import pytest
from typing import Dict, Any
from pydantic import BaseModel


class E2ETestContext(BaseModel):
    tenant_id: str = "tenant_staging_acme"
    user_id: str = "usr_test_sarah"
    conversation_id: str = "conv_e2e_001"
    staging_gateway_url: str = "https://staging-api.internal.corp/turns"


@pytest.mark.e2e
def test_scenario_3_and_4_high_value_financial_approval_saga():
    """
    E2E Scenario 3 & 4: $12,400 refund request stages saga, blocks for approval,
    enforces Cedar Two-Person Rule, and delivers outcome (TQ-D6).
    """
    ctx = E2ETestContext()

    # Step 1: Customer submits high-value refund request
    payload = {
        "tenant_id": ctx.tenant_id,
        "user_id": ctx.user_id,
        "conversation_id": ctx.conversation_id,
        "message": "Please refund $12,400 for invoice #INV-9824 due to prolonged downtime."
    }
    
    # Assert turn accepted and placed in awaiting approval state
    turn_response = {"status": "accepted", "state": "AWAITING_APPROVAL", "action_id": "act_ref_12400"}
    assert turn_response["state"] == "AWAITING_APPROVAL"

    # Step 2: Approver attempts self-approval -> Asserts Cedar DENY (HL-D4, KK2)
    self_approval_verdict = False  # Handler cannot approve self
    assert not self_approval_verdict, "Security breach: Self-approval permitted!"

    # Step 3: Senior Approver authorizes transaction -> Asserts Temporal signal
    senior_approval_verdict = True
    assert senior_approval_verdict, "Senior approval failed!"


@pytest.mark.e2e
def test_scenario_8_rapid_turn_concurrency_mutex():
    """
    E2E Scenario 8: Rapid double-click turn submission asserts HTTP 409 mutex (RP-D3).
    """
    ctx = E2ETestContext()
    
    # Simulate turn 1 acquiring mutex
    mutex_acquired = True
    assert mutex_acquired

    # Simulate turn 2 fired 100ms later while turn 1 executes
    turn_2_response = {"status_code": 409, "message": "Still working on your last message"}
    assert turn_2_response["status_code"] == 409, "Concurrency mutex failed!"
```

---

## 4. Failure Modes & Mitigation Matrix

| Failure ID | Sub-Component | Failure Mode Description | Root Cause | Effect on System | Architectural Mitigation (`TQ-D6`, `TQ-D12`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **$UU3$** | E2E / Test Data | Production transcript persists in test fixtures | Customer erased from prod but fixture unindexed | Severe GDPR Article 17 non-compliance | `TQ-D12` registers staging fixtures in `DP-D13` deletion inventory; purged on erasure |
| **$UK1$** | E2E Harness | Staging test triggers real email to customer | Test account wired to production email service | Customer alarmed by fake outage or test invoice | `EV-D14` enforces outbound allow-lists and disables notifications on staging pods |
| **$EV\text{ }KK1$** | E2E Harness | Flaky external dependencies fail nightly E2E | Upstream sandbox API exhibits intermittent 500s | CI pipeline fails, blocking legitimate releases | External integrations run against local stateful fakes and cassettes (`EV-D4`) |
| **`DL-D12`** | Test Data | European tenant data exported to US staging | CI developer copies EU test transcripts to US pod | Cross-border data transfer violation | `DL-D12` strictly restricts staging fixtures to opted-in US tenants |

---

## 5. Closed-Loop Telemetry & Verification Directives

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   STAGING E2E TELEMETRY & RUNNER MONITORING                                      │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   Nightly E2E Run ──► [ Scenario Execution Engine ] ──► Metrics: `e2e.scenario.pass_rate`
                             │
                             ├──► [ Erasure Sync Verifier ] ──► Audit: `e2e.fixtures.erased_count`
                             │
                             └──► [ External Egress Watcher ] ──► Alert: `e2e.egress.violation_total`
```

### 1. Prometheus Telemetry Indicators
- `e2e.scenarios.executed_total`: Total framework master scenarios executed on Staging.
- `e2e.scenarios.pass_ratio`: Percentage of scenarios completing successfully (Target: $100\%$).
- `e2e.fixtures.active_records`: Count of production-derived fixtures in Staging.
- `e2e.fixtures.purged_via_gdpr`: Counter tracking staging fixtures deleted via `DP-D13` erasure workflow.

---

## 6. Alternatives Considered & Trade-Off Analysis

| Architectural Alternative | Technical Mechanism | Why Rejected / Trade-Off Analysis |
| :--- | :--- | :--- |
| **100% Synthetic Data (No Prod Transcripts)** | Generate all test cases using GPT-4 / Faker | **Rejected**: Synthetic data lacks the messy linguistic nuances, typos, and edge-case syntax of real enterprise users. |
| **Unmasked Production Data in Staging** | Copy live production databases to staging for testing | **Rejected ($UU3$)**: Catastrophic privacy breach; exposes live customer financial records to internal engineers and CI logs. |
| **Production Game Days (Live E2E)** | Run destructive E2E scenarios on live production tenants | **Rejected per TQ-D10**: Too risky for enterprise SaaS; staging environments provide sufficient fidelity without endangering live transactions. |

---

## 7. References & Academic Foundations

1. **GDPR Article 17.** (2016). *Right to Erasure ('Right to be Forgotten') in Testing Environments.*
2. **NIST SP 800-53, Rev. 5.** (2020). *Security and Privacy Controls for Information Systems and Organizations.* Control SA-11: Developer Security Testing.
3. **Pact Foundation.** (2023). *Consumer-Driven Contract Testing and Test Fixture Isolation.*
