---
doc_id: kb-runbook-api-5xx-429-webhook-replay
title: Public REST API 5xx and 429 troubleshooting and failed webhook replay runbook
source_system: runbooks
source_kind: operational
audience: internal
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-09-27
intents: [TECHNICAL_OUTAGE]
test_case: none
---

# Public REST API 5xx and 429 troubleshooting and failed webhook replay runbook

## Diagnosing `HTTP 429 Too Many Requests` vs. `HTTP 5xx` server errors

When a customer reports failing calls to the **Nimbus Cloud Platform v2 REST API** (`https://us.api.nimbuscloud.example.com/v2` or `https://eu.api.nimbuscloud.example.com/v2`), support engineers must first separate client-side rate limiting (`HTTP 429`) from platform server faults (`HTTP 500`, `502`, `503`, `504`).

### Step 1: Inspect gateway request logs by `X-Nimbus-Request-Id`

Every Nimbus REST API response includes a unique correlation header `X-Nimbus-Request-Id` (for example, `req_01J9M7K3W8Z`). Query the regional API gateway log index to inspect the exact status code, latency, and upstream service status:

```bash
# Look up API gateway telemetry for a specific request ID or tenant over the last 30 minutes
nimbus-sre api logs-query \
  --tenant-id <TENANT_ID> \
  --region <REGION> \
  --status-filter "429,500,502,503,504" \
  --window 30m
```

### Step 2: Resolving `HTTP 429 Too Many Requests` (`RATE_LIMIT_EXCEEDED`)

1. Verify the tenant's current subscription tier rate ceiling under the v2 API specification:
   - **Starter:** `600 requests/min` (120 write mutations/min).
   - **Growth:** `3,000 requests/min` (120 write mutations/min).
   - **Enterprise:** `12,000 requests/min` (600 write mutations/min, burst to 18,000 rpm).
2. Identify which service account token (`nmb_live_...`) or IP address is exhausting the bucket:

```bash
nimbus-sre api top-talkers --tenant-id <TENANT_ID> --window 15m
```

3. Instruct the customer to honor the `Retry-After` response header (in integer seconds), implement exponential backoff with jitter, cache read-heavy `GET /v2/db/clusters` polling loops, or upgrade their plan / request an Enterprise burst quota increase.

### Step 3: Triage and recovery for `HTTP 500 / 502 / 503 / 504` errors

1. If `HTTP 502 Bad Gateway`, `503 Service Unavailable`, or `504 Gateway Timeout` spikes across multiple tenants in a region, check `https://status.nimbuscloud.example.com` and verify whether an active control-plane deployment or Envoy ingress pod degradation is underway.
2. If `HTTP 500` or `504` is isolated to a single tenant's mutation calls, instruct the customer to retry safely by passing their original UUID v4 `Idempotency-Key` header (cached for **24 hours**), which prevents duplicate resource creation.
3. If an Envoy API gateway worker shard is wedged for a specific tenant placement group, drain and recycle the gateway shard via:

```bash
nimbus-sre api recycle-gateway-shard --region <REGION> --shard-id <SHARD_ID>
```

## Diagnosing and replaying failed webhook deliveries (`FAILED_EXHAUSTED`)

### Why webhooks enter `FAILED_EXHAUSTED`

Nimbus Cloud Platform expects customer webhook receiver endpoints to return an `HTTP 2xx` status within **10 seconds**. After **6 failed retry attempts** (at 30s, 2m, 10m, 30m, 2h, and 4h), the webhook event is marked `FAILED_EXHAUSTED`.

### How to replay failed webhooks via CLI or REST API

Once the customer fixes their webhook receiver endpoint (or updates an expired TLS certificate on their webhook server), they can bulk-replay all `FAILED_EXHAUSTED` events from the past 7 days:

```bash
# List failed webhook deliveries and replay them in chronological order
nimbus webhooks events list --endpoint-id <WEBHOOK_ENDPOINT_ID> --status FAILED_EXHAUSTED
nimbus webhooks events replay-batch \
  --endpoint-id <WEBHOOK_ENDPOINT_ID> \
  --since "2026-10-30T00:00:00Z" \
  --concurrency 5
```
