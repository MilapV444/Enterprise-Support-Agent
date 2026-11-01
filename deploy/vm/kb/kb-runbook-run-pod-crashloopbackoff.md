---
doc_id: kb-runbook-run-pod-crashloopbackoff
title: Nimbus Run runbook: triaging and resolving container pod CrashLoopBackOff
source_system: runbooks
source_kind: operational
audience: internal
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-09-24
intents: [TECHNICAL_OUTAGE]
test_case: none
---

# Nimbus Run runbook: triaging and resolving container pod CrashLoopBackOff

## Overview of `CrashLoopBackOff` on Nimbus Run container clusters

When a container pod deployed on a **Nimbus Run** managed Kubernetes cluster repeatedly starts, exits with a non-zero status code, and restarts, the kubelet places the pod into `CrashLoopBackOff` with an exponential backoff delay (10s, 20s, 40s, up to 5 minutes). On-call engineers triaging a `CrashLoopBackOff` alert must systematically inspect five common failure modes: **application crash logs**, **exit code 137 (`OOMKilled`)**, **missing ConfigMaps/Secrets (`CreateContainerConfigError`)**, **failed liveness/startup probes**, and **architecture or entrypoint mismatches**.

## Step-by-step triage and resolution workflow

### Step 1: Inspect pod events, exit codes, and termination reason

1. Authenticate your kubeconfig to the target Nimbus Run cluster and inspect the failing pod's `Last State` and `Exit Code`:

```bash
# Bind kubeconfig to the target Nimbus Run cluster and inspect pod state
nimbus run kubeconfig update --cluster <CLUSTER_NAME> --region <REGION>
kubectl describe pod <POD_NAME> -n <NAMESPACE>
kubectl get pod <POD_NAME> -n <NAMESPACE> -o jsonpath='{.status.containerStatuses[*].lastState.terminated}'
```

2. Check the `exitCode` and `reason` fields in the output:
   - `exitCode: 1` or `2` (`Error`): Uncaught application exception, missing environment variable, or failed database connection at startup.
   - `exitCode: 137` (`OOMKilled`): Container exceeded its configured `resources.limits.memory` cgroup ceiling and was terminated by the Linux kernel OOM killer.
   - `exitCode: 126` or `127`: Entrypoint binary not found or not executable (`exec format error` if an `arm64` image was deployed onto an `amd64` Nimbus Run node pool).
   - `exitCode: 143` (`SIGTERM`): Liveness probe failed repeatedly, causing kubelet to kill the container before initialization completed.

### Step 2: Retrieve logs from the previous crashed container instance

1. Always pass the `--previous` (`-p`) flag to `kubectl logs` so you capture the stack trace from the terminated container instance rather than the currently waiting container:

```bash
# Fetch the last 150 lines of logs from the crashed container instance
kubectl logs <POD_NAME> -n <NAMESPACE> -c <CONTAINER_NAME> --previous --tail=150
```

### Step 3: Remediate the specific root cause

#### Case A: Remediation for `OOMKilled` (Exit Code 137)

If `lastState.terminated.reason` is `OOMKilled`, compare historical memory usage via `nimbus run metrics pod <POD_NAME>` against the deployment's `resources.limits.memory`. Increase the memory request and limit in the deployment manifest (ensuring JVM `MaxRAMPercentage` or Node.js `--max-old-space-size` stays at or below 80% of the container limit):

```bash
# Patch container memory request and limit to 1Gi / 2Gi and trigger a rolling restart
kubectl set resources deployment/<DEPLOYMENT_NAME> -n <NAMESPACE> \
  -c <CONTAINER_NAME> --requests=memory=1Gi --limits=memory=2Gi
```

#### Case B: Remediation for missing Secret, ConfigMap, or DB credentials

If `kubectl logs --previous` shows `FATAL: password authentication failed` or `kubectl describe pod` reports `CreateContainerConfigError`, verify that the referenced Kubernetes `Secret` or `ConfigMap` exists in `<NAMESPACE>` and contains the expected keys:

```bash
kubectl get secret <SECRET_NAME> -n <NAMESPACE> -o jsonpath='{.data}' | jq 'keys'
```

#### Case C: Remediation for aggressive Liveness Probes during slow startup

If the container is killed with `Exit Code 143` while running database migrations or warming caches, add a dedicated `startupProbe` (for example, `failureThreshold: 30`, `periodSeconds: 5`) so the liveness probe does not kill the pod during startup.

## Step 4: Verify pod stability after applying the fix

Monitor the rollout and verify that `RESTARTS` remains `0` for at least 5 consecutive minutes:

```bash
kubectl rollout status deployment/<DEPLOYMENT_NAME> -n <NAMESPACE>
kubectl get pods -n <NAMESPACE> -l app=<APP_LABEL> -w
```
