# DL-ADP-01: Multi-Region Infrastructure & Sovereign Environments (Regional Kubernetes, Dev/Staging/Prod Topology & Transatlantic Sample Isolation)

- **Status**: Accepted & Confirmed
- **Date**: 2026-10-06 *(Confirmed per DL-D1 Asymmetric Environment Topology, DL-D9 Kubernetes Regional IaC & DL-D12 EU Transatlantic Data Isolation DL-F12)*
- **Deciders**: Architecture Team, Lead Cloud Infrastructure Architect, Chief Information Security Officer (CISO), SRE Director
- **Component**: `[14] Deployment & LLMOps` (`Component [ 14 ]`)
- **Reasoning Source**: `checkpoint.md` §18 · Diagram: `LLD - [14] Deployment & LLMOps`
- **Decisions Covered**:
  - `DL-D1`: Multi-Region Environment Topology — Provisions an asymmetric environment fleet: Local Developer environments, a single consolidated Staging environment hosted in US-East (`us-east-1`), and fully isolated, sovereign Production clusters deployed per geographic region (US and EU); balances pre-production staging infrastructure costs against full multi-region production sovereignty
  - `DL-D9`: Regional Kubernetes & Infrastructure-as-Code — Deploys platform workloads on regional managed Kubernetes clusters (AWS EKS / Azure AKS) managed via Terraform and Helm; unifies CPU-based microservice pods (FastAPI, Temporal workers, Redis proxies) and high-density GPU worker pools (vLLM serving local Llama 3.1 70B `RP-D4`, `CR-D9`) under a single infrastructure control plane
  - `DL-D12`: Transatlantic Data Sovereignty & Staging Quarantine — Directly resolves the transatlantic cross-border data leakage vulnerability ($UU2$); because Staging is centralized in the US (`DL-D1`), production test transcripts harvested from opted-in European enterprise tenants (`EV-D10`, `EV-D15`) are strictly forbidden from being imported or mounted in US Staging; US Staging utilizes exclusively US-derived samples and pure synthetic fixtures, guaranteeing that European personal data never leaves the EU
- **Related Architectural Decision Points**:
  - [`DP-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/07-data-persistence/DP-ADP-01-store-topology-residency.md): Store Topology & Residency *(Regional Isolation US/EU)*
  - [`TQ-ADP-03`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/13-testing-quality/TQ-ADP-03-end-to-end-tests-data.md): End-to-End Tests & Test Data *(Staging Fixture Generation)*
  - [`RP-ADP-04`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/10-reliability-performance-scale/RP-ADP-04-disaster-recovery-regions.md): Disaster Recovery & Regions *(Multi-AZ Infrastructure)*
  - [`CR-ADP-01`](file:///c:/Users/omkar/Documents/ANTERN/Projects/Enterprise%20Support%20Agent/docs/decisions/adp/11-cost-resource-management/CR-ADP-01-model-tier-routing.md): Model Tier Routing *(Regional GPU Serving)*

---

## 1. Context & Problem Statement

Operating autonomous enterprise AI agents across international regulatory boundaries creates acute infrastructure tensions:
1. **The Multi-Region Staging Cost Explosion**:
   - Replicating complete production-grade staging environments across every operating geography (US, EU, APAC) doubles non-production cloud spend. Maintaining dedicated H100 GPU clusters, Qdrant vector nodes, and standby database clusters in multiple staging regions consumes tens of thousands in monthly idle infrastructure fees.
2. **The Transatlantic Data Transfer Trap ($UU2$)**:
   - Consolidating staging into a single geographic region (US-East) introduces severe compliance risks. Under GDPR Chapter V (Articles 44–50) and CJEU Schrems II rulings, exporting European customer transcripts—even if tokenized and pseudo-anonymized—to US-based staging servers constitutes an unlawful international data transfer without adequacy mechanisms.
3. **The Heterogeneous Compute Orchestration Challenge**:
   - Enterprise agent runtimes require low-latency microservices (FastAPI handling webhooks in $<10\text{ms}$), stateful workflow engines (Temporal managing long sagas), and massive GPU clusters (vLLM serving 70B parameter models requiring 160GB of high-bandwidth VRAM). Disjointed infrastructure stacks create operational friction and monitoring blind spots.

### The Core Architectural Question
> **How do we engineer an infrastructure topology that minimizes non-production cloud spend, deploys unified containerized CPU/GPU clusters via Infrastructure-as-Code, and enforces mathematical boundaries preventing European data from transiting transatlantic staging networks?**

---

## 2. Decision Framework & Theoretical Formulation

To resolve these tensions, `DL-D1`, `DL-D9`, and `DL-D12` establish the **Regional Sovereign Kubernetes and Asymmetric Environment Architecture**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   SOVEREIGN REGIONAL INFRASTRUCTURE TOPOLOGY (DL-D1, DL-D9, DL-D12)              │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                                      GLOBAL ROUTING (Cloudflare / Route53 Geo-DNS)
                                                            │
                     ┌──────────────────────────────────────┴──────────────────────────────────────┐
                     ▼                                                                             ▼
┌───────────────────────────────────────────────┐             ┌───────────────────────────────────────────────┐
│ SOVEREIGN US REGION (AWS us-east-1)           │             │ SOVEREIGN EU REGION (AWS eu-central-1)        │
├───────────────────────────────────────────────┤             ├───────────────────────────────────────────────┤
│ [PRODUCTION CLUSTER]                          │             │ [PRODUCTION CLUSTER]                          │
│ • K8s EKS Cluster with Terraform / Helm (DL-D9)│             │ • K8s EKS Cluster with Terraform / Helm (DL-D9)│
│ • Microservice Pods (FastAPI, LangGraph, Temp)│             │ • Microservice Pods (FastAPI, LangGraph, Temp)│
│ • Local vLLM GPU Nodes (Llama 3.1 70B RP-D4)   │             │ • Local vLLM GPU Nodes (Llama 3.1 70B RP-D4)   │
│ • Sovereign DB (Postgres US, Qdrant US)       │             │ • Sovereign DB (Postgres EU, Qdrant EU)       │
│                                               │             │                                               │
│ [SINGLE CENTRALIZED STAGING CLUSTER] (DL-D1)  │             │ [NO EU STAGING CLUSTER PROVISIONED] (DL-D1)   │
│ • Staging Pods, WireMock, Mock LLMs           │             │ • Zero EU Data Leaves Europe! (DL-D12, UU2)   │
│ • Data: Synthetic Personas + US-Only Samples  │             │ • EU Transcripts QUARANTINED from US Staging  │
└───────────────────────────────────────────────┘             └───────────────────────────────────────────────┘
```

---

### Pillar 1: Asymmetric Environment Fleet (`DL-D1`)

To maximize capital efficiency without compromising production reliability:
1. **Developer Environments (`dev`)**:
   - Ephemeral local Docker Compose stacks and mocked cloud emulators (LocalStack). Zero cloud GPU allocation.
2. **Single Consolidated Staging (`staging`)**:
   - Centralized in `us-east-1`. Hosts pre-release validation batteries, Locust load tests (`TQ-D10`), and integration suites.
   - Sized for fractional production load, utilizing spot instances for non-critical workers.
3. **Sovereign Production Fleet (`prod-us`, `prod-eu`)**:
   - Fully redundant, multi-AZ production Kubernetes clusters deployed in US-East and EU-Central.
   - Complete store isolation: zero cross-region database links or shared storage volumes (`DP-D10`).

---

### Pillar 2: Unified Kubernetes & IaC Orchestration (`DL-D9`)

All cloud infrastructure is declared in modular Terraform repositories and orchestrated via Helm:
1. **Node Group Segregation**:
   - `nodegroup-core`: Spot/on-demand CPU instances (e.g., `m6i.2xlarge`) running stateless API gateways and Temporal workflow pollers.
   - `nodegroup-gpu`: Dedicated on-demand GPU instances (e.g., `g5.12xlarge` / `p4d.24xlarge` with NVIDIA A100/H100s) running containerized vLLM inference engines (`RP-D4`, `CR-D9`).
2. **Continuous Autoscaling**:
   - Kubernetes Horizontal Pod Autoscaler (HPA) scales microservice pods on CPU/latency metrics.
   - Cluster Autoscaler provisions additional GPU nodes dynamically when admission queues surge (`RP-D9`).

---

### Pillar 3: Transatlantic Data Sovereignty Quarantine (`DL-D12`, $UU2$)

To comply with EU General Data Protection Regulation (GDPR) Article 44:
1. **Transatlantic Export Prohibition ($UU2$ Fixed)**:
   - The test data ingestion pipeline enforces strict geographical source tagging.
   - Production transcripts originating from European tenants (tagged `region: "eu"`) are **hardcoded blocked** from export to US Staging S3 buckets.
2. **US Staging Composition**:
   - Staging test fixtures (`TQ-D12`) are constructed exclusively from:
     - Purely synthetic persona generators (Faker/GPT-4).
     - Tokenized transcripts harvested from opted-in US-based enterprise tenants.
3. **Accepted Engineering Trade-Off ($KU2$)**:
   - We explicitly accept the risk that EU-specific cultural phrasing or multilingual nuances are not exercised in pre-production US Staging ($KU2$); these are monitored post-release via regional live telemetry (`EV-D8`).

---

## 3. Technical Implementation & Genesis Contracts

```terraform
# infrastructure/terraform/modules/kubernetes/main.tf
# Terraform configuration for Regional Sovereign Kubernetes Cluster (DL-D9).

variable "region" {
  type        = string
  description = "Target deployment region (us-east-1 or eu-central-1)"
}

variable "environment" {
  type        = string
  description = "Environment identifier (staging or prod)"
}

# Regional EKS Cluster
resource "aws_eks_cluster" "regional_cluster" {
  name     = "agent-${var.environment}-${var.region}"
  role_arn = aws_iam_role.cluster_role.arn

  vpc_config {
    subnet_ids              = module.vpc.private_subnet_ids
    endpoint_private_access = true
    endpoint_public_access  = false # VPC-Internal only!
  }
}

# Dedicated GPU Worker Pool for Local vLLM Inference (RP-D4, CR-D9)
resource "aws_eks_node_group" "gpu_inference_pool" {
  cluster_name    = aws_eks_cluster.regional_cluster.name
  node_group_name = "vllm-gpu-workers"
  node_role_arn   = aws_iam_role.gpu_node_role.arn
  subnet_ids      = module.vpc.private_subnet_ids

  instance_types = ["g5.12xlarge"] # 4x NVIDIA A10G GPUs (96GB VRAM)

  scaling_config {
    desired_size = var.environment == "prod" ? 4 : 1
    max_size     = var.environment == "prod" ? 8 : 2
    min_size     = 1
  }

  labels = {
    "workload.type" = "gpu-inference"
  }

  taint {
    key    = "nvidia.com/gpu"
    value  = "true"
    effect = "NO_SCHEDULE"
  }
}
```

```python
"""
scripts/ci/validate_staging_data_sovereignty.py
CI Validation script verifying that no EU customer data is imported to US Staging (DL-D12).
"""

import json
import glob
import sys


def assert_zero_eu_data_in_staging():
    """
    Enforces transatlantic quarantine: No EU-tagged fixtures may exist in staging repository (DL-D12, UU2).
    """
    fixture_files = glob.glob("tests/fixtures/staging/**/*.json", recursive=True)
    violations = []

    for file_path in fixture_files:
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                region = data.get("origin_region", "").lower()
                if region in ["eu", "eu-central-1", "europe"]:
                    violations.append((file_path, region))
            except Exception:
                continue

    if violations:
        print("CRITICAL DATA SOVEREIGNTY BREACH: EU data found in US Staging fixtures!")
        for file_path, reg in violations:
            print(f" - {file_path}: origin={reg}")
        sys.exit(1)

    print("SUCCESS: Zero EU customer samples detected in US Staging.")


if __name__ == "__main__":
    assert_zero_eu_data_in_staging()
```

---

## 4. Failure Modes & Mitigation Matrix

| Failure ID | Sub-Component | Failure Mode Description | Root Cause | Effect on System | Architectural Mitigation (`DL-D1`, `DL-D9`, `DL-D12`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **$UU2$** | Environments | European customer transcripts imported to US Staging | CI developer syncs production samples across all regions | GDPR Chapter V cross-border illegal data export | `DL-D12` strictly quarantines EU data; CI linter fails if any EU fixture enters US staging |
| **$KU2$** | Environments | EU-specific bugs appear only in production | No pre-production staging environment in EU | Regional edge-case failures during rollout | Regional live canary on read-only routes (`DL-D4`); monitored via `OB-D8` regional SLOs |
| **$KK1$** | Infrastructure | GPU node failure halts local inference | Hardware failure in AWS AZ | Dropped customer turns on Tier 1 model | Kubernetes Cluster Autoscaler spreads GPU pods across multiple availability zones (`RP-D10`) |
| **`DL-D9`** | Infrastructure | Inconsistent infrastructure drift between regions | Manual console edits by regional SREs | "Works in US, breaks in EU" release failure | Infrastructure declared $100\%$ in version-controlled Terraform with zero manual changes |

---

## 5. Closed-Loop Telemetry & Verification Directives

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   INFRASTRUCTURE & ENVIRONMENT TELEMETRY PIPELINE                                │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   K8s Cluster State ──► [ Prometheus Node Exporter ] ──► Metric: `k8s.node.gpu_utilization`
                               │
                               ├──► [ Egress Network Monitor ] ──► Alert: `cross_region.egress_bytes`
                               │
                               └──► [ CI Sovereignty Verifier ] ──► Status: `staging_sovereignty_verified`
```

### 1. Prometheus Telemetry Indicators
- `infra.k8s.nodes_ready_total`: Count of healthy Kubernetes worker nodes per region.
- `infra.gpu.vram_allocated_pct`: Percentage of GPU memory utilized by vLLM containers.
- `infra.cross_region.data_transfer_bytes`: Gauge tracking network traffic crossing US/EU boundaries (Must be zero for tenant data).

---

## 6. Alternatives Considered & Trade-Off Analysis

| Architectural Alternative | Technical Mechanism | Why Rejected / Trade-Off Analysis |
| :--- | :--- | :--- |
| **Dual Staging Environments (US + EU, DL-F1(a))** | Deploy identical full staging clusters in both US and EU regions | **Rejected**: Doubles non-production cloud spend ($\approx +\$15,000/\text{month}$) for marginal pre-production validation benefit. |
| **Copy EU Data to US Staging (DL-F12(c))** | Allow tokenized EU transcripts in US Staging | **Rejected ($UU2$)**: Severe violation of GDPR Chapter V cross-border transfer laws; exposes enterprise to legal sanctions. |
| **Managed Serverless Containers (Cloud Run / Fargate)** | Run all agent services on serverless container infrastructure | **Rejected per DL-D9**: Cloud Run cannot efficiently manage high-performance GPU tensor parallelism required for local 70B parameter models. |

---

## 7. References & Academic Foundations

1. **GDPR Chapter V (Articles 44–50).** (2016). *Transfers of Personal Data to Third Countries or International Organisations.*
2. **Court of Justice of the European Union (CJEU).** (2020). *Data Protection Commissioner v Facebook Ireland and Maximillian Schrems (Schrems II).* Case C-311/18.
3. **Terraform Best Practices.** (2024). *Multi-Region Infrastructure as Code Deployment Patterns.* HashiCorp Documentation.
4. **NIST SP 800-53, Rev. 5.** (2020). *Security and Privacy Controls for Information Systems and Organizations.* Control SC-7: Boundary Protection.
