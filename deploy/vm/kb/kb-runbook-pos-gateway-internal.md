---
doc_id: kb-runbook-pos-gateway-internal
title: Nimbus POS Gateway internal engineering runbook: POS-OFFLINE and GATEWAY_TIMEOUT
source_system: runbooks
source_kind: operational
audience: internal
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-09-25
intents: [TECHNICAL_OUTAGE]
test_case: none
---

# Nimbus POS Gateway internal engineering runbook: POS-OFFLINE and GATEWAY_TIMEOUT

## Overview of Nimbus POS Gateway retail terminal outages

When a retail customer (such as `Acme Retail`) reports that store cash registers display a **completely red screen** and cannot charge credit or debit cards, the **Nimbus POS Gateway** terminal SDK has entered a hard payment-halt state. Support specialists and on-call SREs must immediately distinguish between three distinct terminal error codes displayed in the top-right corner of the red register screen: **`POS-OFFLINE`**, **`GATEWAY_TIMEOUT`**, and **`CARD-DECLINED-GATEWAY`**.

## Error code reference and diagnostic matrix

| Terminal Error Code | Screen State | Primary Fault Domain | Meaning & Root Cause |
| :--- | :--- | :--- | :--- |
| **`POS-OFFLINE`** | Solid Red Banner + `ERR: POS-OFFLINE (0x104)` | **Store Local Network / ISP / Firewall** | The physical cash register cannot reach the regional Nimbus POS Gateway ingress (`pos-us.nimbuscloud.example.com:8443` or `pos-eu.nimbuscloud.example.com:8443`). Usually caused by store Wi-Fi/VLAN drop, local DNS failure, or outbound port `8443` blocked. |
| **`GATEWAY_TIMEOUT`** | Solid Red Screen + `ERR: GATEWAY_TIMEOUT (0x504)` | **Nimbus POS Gateway Relay / Upstream Acquirer** | The register successfully established a TLS 1.3 mTLS session with Nimbus POS Gateway, but the upstream ISO-8583 payment processor relay timed out after **8,000 ms** without returning an authorization response. |
| **`CARD-DECLINED-GATEWAY`** | Amber Warning Popup + `ERR: CARD-DECLINED-GATEWAY (0x402)` | **Merchant Account Config / Card Issuer** | The gateway is healthy and reachable, but the transaction was rejected due to an expired merchant MID certificate, invalid terminal pairing token, or issuer decline (`05 Do Not Honor`). |

## Step-by-step triage: What the retail store checks vs. what Nimbus Engineering does

### Step 1: Check the Nimbus Status Page first (`status.nimbuscloud.example.com`)

1. Immediately check **`https://status.nimbuscloud.example.com`** for any active incident on **Nimbus POS Gateway (US or EU Retail Relay)**.
2. Query the internal regional relay telemetry to see if multiple tenants are experiencing `GATEWAY_TIMEOUT`:

```bash
# Check regional POS Gateway relay latency, HTTP 504 rate, and upstream acquirer health
nimbus-sre pos relay-health \
  --region us-east-1 \
  --window 15m
```

### Step 2: What the retail store manager can check immediately (for `POS-OFFLINE` or single-store issues)

Instruct the store manager or retail IT operator to perform these four quick local checks on the affected cash register:

1. **Read the Exact Error Code on the Red Screen:** Confirm whether the top-right badge shows `POS-OFFLINE` or `GATEWAY_TIMEOUT`.
2. **Run the Built-In Register Network Test:** Press **`Ctrl + Shift + D`** (or tap the top-left Nimbus logo 5 times on touch terminals) to open the **POS Diagnostic Overlay** and tap **Test Connection**.
3. **For `POS-OFFLINE`:** Verify that the store router can resolve `pos-us.nimbuscloud.example.com` (or `pos-eu.nimbuscloud.example.com`) and that TCP port **`8443`** and NTP port **`123`** are open outbound. Power-cycle the payment PIN pad and restart the local `nimbus-pos-agent` service.
4. **Prevent Double Charging on `GATEWAY_TIMEOUT`:** Reassure the store that every `GATEWAY_TIMEOUT` transaction carries an automatic `Idempotency-Key` and triggers an automatic **ISO-8583 Auto-Reversal (`0420`)** within 60 seconds so shoppers are not double-charged if the cashier re-swipes after recovery.

### Step 3: What Nimbus Engineering / SRE executes on the backend (for `GATEWAY_TIMEOUT` or `CARD-DECLINED-GATEWAY`)

If the store terminal shows `GATEWAY_TIMEOUT` across multiple registers or `nimbus-sre pos relay-health` reveals degraded upstream acquirer pools:

1. Drain the degraded ISO-8583 acquirer tunnel and fail over the tenant's store group to the secondary regional payment relay pool:

```bash
# Fail over a tenant's POS Gateway traffic from primary relay pool to standby pool
nimbus-sre pos failover-tenant-relay \
  --tenant-id <TENANT_ID> \
  --region us-east-1 \
  --from-pool relay-pool-us-a \
  --to-pool relay-pool-us-b \
  --flush-stale-mtls-sessions
```

2. If the error is `CARD-DECLINED-GATEWAY (0x402)` caused by a desynchronized terminal mTLS certificate after a store hardware swap, rotate and push a fresh terminal pairing bundle (requires **Tier 2** verification):

```bash
nimbus pos terminal-cert rotate \
  --tenant-id <TENANT_ID> \
  --store-id <STORE_ID> \
  --push-over-control-channel
```

3. Because a multi-register red screen stoppage blocks live retail store revenue, **always escalate active multi-register `GATEWAY_TIMEOUT` incidents to a human engineer in `queue-tech-sre` as Severity P1/P2**.
