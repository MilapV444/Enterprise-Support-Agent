---
doc_id: kb-ticket-run-oomkilled-crashloop
title: Resolved ticket: Nimbus Run checkout-worker pods in CrashLoopBackOff due to OOMKilled
source_system: tickets
source_kind: ticket
audience: internal
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-10-12
intents: [TECHNICAL_OUTAGE]
test_case: none
---

# Resolved ticket: Nimbus Run checkout-worker pods in CrashLoopBackOff due to OOMKilled

## Case metadata and problem summary

- **Ticket ID:** `TCK-2026-87410`
- **Tenant Organization:** `Acme Retail` (US Region `us-east-1`, Growth Plan)
- **Requester Contact:** `<NAME_1>` (`<EMAIL_1>`, Phone: `<PHONE_1>`, Role: `Infrastructure Operator`, Verified at **Tier 2** via Corporate SSO + MFA)
- **Affected Resource:** Nimbus Run cluster `run-us-prod-02`, deployment `checkout-worker` in namespace `retail-prod`

### Reported problem description

On-call engineer `<NAME_1>` reached out via web chat: *"Container pod crashlooping! All 8 replicas of `checkout-worker` in our Nimbus Run cluster `run-us-prod-02` are stuck in `CrashLoopBackOff` after we deployed release `v4.12.0` ten minutes ago."*

## Root cause investigation

### Inspecting `lastState.terminated` and `--previous` container logs

Support engineer `<NAME_2>` walked `<NAME_1>` through the triage steps in runbook `kb-runbook-run-pod-crashloopbackoff`:

1. Running `kubectl describe pod checkout-worker-7c8f9d-x2k9p -n retail-prod` revealed:
   - `Last State: Terminated`
   - `Reason: OOMKilled`
   - `Exit Code: 137`
2. Running `kubectl logs checkout-worker-7c8f9d-x2k9p -n retail-prod --previous --tail=150` showed that release `v4.12.0` pre-loaded a 420 MB product catalog lookup table into memory at startup while the container's Kubernetes memory limit (`resources.limits.memory`) was still set to `512Mi`, and the Node.js runtime had `--max-old-space-size=1024`. As soon as the catalog hydrated, container RSS spiked to 540 MiB and the Linux kernel cgroup OOM killer terminated the process with `Exit Code 137`.

## Resolution steps executed

### Increasing container memory limits and aligning Node.js heap ceiling

`<NAME_1>` applied the resource patch from `kb-runbook-run-pod-crashloopbackoff` to raise the pod memory request to `1Gi` and memory limit to `2Gi`, while setting `NODE_OPTIONS="--max-old-space-size=1536"` (75% of the 2 GiB limit):

```bash
# Update container memory requests/limits and set Node.js heap limit below cgroup ceiling
kubectl set resources deployment/checkout-worker -n retail-prod \
  -c checkout-worker --requests=memory=1Gi --limits=memory=2Gi

kubectl set env deployment/checkout-worker -n retail-prod \
  NODE_OPTIONS="--max-old-space-size=1536"

# Verify clean rolling deployment and zero restarts
kubectl rollout status deployment/checkout-worker -n retail-prod
kubectl get pods -n retail-prod -l app=checkout-worker
```

All 8 `checkout-worker` pods transitioned to `1/1 Running` with `RESTARTS: 0`, stabilizing at 680 MiB steady-state memory usage.
