---
doc_id: kb-ticket-pos-red-screen-gateway-timeout
title: Resolved ticket: Acme Retail registers showing red screen with GATEWAY_TIMEOUT
source_system: tickets
source_kind: ticket
audience: internal
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-10-05
intents: [TECHNICAL_OUTAGE]
test_case: none
---

# Resolved ticket: Acme Retail registers showing red screen with GATEWAY_TIMEOUT

## Case metadata and problem summary

- **Ticket ID:** `TCK-2026-85219`
- **Tenant Organization:** `Acme Retail` (US Region `us-east-1`, Enterprise Plan)
- **Requester Contact:** `<NAME_1>` (`<EMAIL_1>`, Phone: `<PHONE_1>`, Role: `POS Store Manager`, Verified at **Tier 2** via Azure AD OIDC + MFA)
- **Affected Resource:** Nimbus POS Gateway terminals across 14 US East retail stores (`store-us-101` through `store-us-114`)

### Reported problem description

Store operations manager `<NAME_1>` opened an urgent chat in panic: *"The screen is completely red on all 6 cash registers in our flagship store and our cashiers can't charge anyone! There is a line of 30 shoppers waiting!"*

## Root cause investigation

### Differentiating `POS-OFFLINE` vs. `GATEWAY_TIMEOUT`

The AI support assistant immediately prompted `<NAME_1>` to check the error badge in the top-right corner of the red register screen and checked `https://status.nimbuscloud.example.com`, while simultaneously triggering a **Priority P1 Human Handoff** to `queue-tech-sre` due to a multi-register retail store stoppage:

1. `<NAME_1>` confirmed the top-right corner displayed **`ERR: GATEWAY_TIMEOUT (0x504)`** (not `POS-OFFLINE`).
2. Because the code was `GATEWAY_TIMEOUT`, local store Wi-Fi and port `8443` egress were healthy, and the register had established mTLS with `pos-us.nimbuscloud.example.com:8443`.
3. On-call SRE `<NAME_2>` ran `nimbus-sre pos relay-health --region us-east-1 --window 15m` and discovered that primary upstream ISO-8583 acquirer pool `relay-pool-us-a` was experiencing 9,200 ms latency spikes (exceeding the 8,000 ms timeout ceiling) following an upstream processor TLS session-ticket key rotation.

## Resolution steps executed

### Failing over the POS Gateway relay pool and verifying zero double-charges

1. While the SRE executed the backend pool switchover, `<NAME_1>` tapped the top-left Nimbus logo 5 times on two registers to open the **POS Diagnostic Overlay** and tapped **Switch to Backup Relay Pool**, immediately restoring those two lanes.
2. SRE `<NAME_2>` executed the tenant-wide relay failover command from runbook `kb-runbook-pos-gateway-internal`:

```bash
nimbus-sre pos failover-tenant-relay \
  --tenant-id tnt_01H9ACMERETAIL \
  --region us-east-1 \
  --from-pool relay-pool-us-a \
  --to-pool relay-pool-us-b \
  --flush-stale-mtls-sessions
```

3. Within 35 seconds of moving `Acme Retail` to `relay-pool-us-b`, all 14 stores cleared their red screens automatically and authorization latency dropped to 310 ms.
4. Support verified in the POS transaction log that all timed-out swipes had automatically emitted `ISO-8583 0420` auto-reversals via their `Idempotency-Key`, resulting in zero duplicate shopper charges.
