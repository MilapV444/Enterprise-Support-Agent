---
doc_id: kb-help-plans-and-limits
title: Plans and resource limits: Starter, Growth, Enterprise, and HTTP 429 rate limits
source_system: helpcenter
source_kind: curated
audience: customer_visible
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-09-18
intents: [SUBSCRIPTION_UPDATE, GENERAL_INQUIRY, TECHNICAL_OUTAGE]
test_case: none
---

# Plans and resource limits: Starter, Growth, Enterprise, and HTTP 429 rate limits

## Comparison of Nimbus Cloud Platform subscription tiers

Nimbus Cloud Platform offers three subscription tiers designed for business tenants across the US and EU regions: **Starter**, **Growth**, and **Enterprise**. Every tenant belongs to exactly one subscription tier, which governs included user seats, infrastructure quotas, Service Level Agreement (SLA) uptime targets, support response times, and public REST API rate limits.

### Starter, Growth, and Enterprise feature matrix

| Feature or Quota | Starter Plan | Growth Plan | Enterprise Plan |
| :--- | :--- | :--- | :--- |
| **Base Price (USD)** | $250 / month ($2,700 / year) | $1,200 / month ($12,960 / year) | Custom annual contract (min $24,000 / year) |
| **Included User Seats** | Up to 10 seats ($20/mo per extra seat) | Up to 50 seats ($35/mo per extra seat) | Custom seat block ($45/mo per extra seat) |
| **Monthly Uptime SLA** | Best-effort (no SLA credits) | **99.90%** monthly uptime SLA | **99.95%** monthly uptime SLA |
| **Authentication & SSO** | Local password + mandatory MFA | SAML 2.0 / OIDC SSO + MFA | SAML 2.0 / OIDC SSO + FIDO2 enforcement + SCIM |
| **Nimbus DB Clusters** | Up to 3 single-AZ clusters | Up to 15 multi-AZ clusters | Unlimited multi-AZ clusters + read replicas |
| **Nimbus Run Clusters** | Up to 2 clusters (max 20 nodes) | Up to 10 clusters (max 100 nodes) | Custom quota (500+ nodes per region) |
| **Nimbus Net VPCs** | 2 VPCs per region | 10 VPCs per region + VPN Gateway | 50 VPCs per region + Dedicated Interconnect |
| **Nimbus POS Gateway** | Not included | Up to 50 retail store terminals | Unlimited retail terminals + dedicated relay |
| **Support Coverage** | 24h target web chat | Priority web chat (P1: 30m, P2: 2h) | 24/7 web chat (P1: 15m, P2: 1h) + Named Support Manager |

## Public REST API rate limits and HTTP 429 handling

### Current v2 REST API rate limits per subscription tier

To ensure multi-tenant stability across the Nimbus Cloud Platform control plane (`https://api.nimbuscloud.example.com/v2`), API requests are metered per tenant across a 60-second sliding window using a token-bucket algorithm:

- **Starter Plan Rate Limit:** **600 requests per minute** (10 requests per second sustained, burst up to 900 rpm).
- **Growth Plan Rate Limit:** **3,000 requests per minute** (50 requests per second sustained, burst up to 4,500 rpm).
- **Enterprise Plan Rate Limit:** **12,000 requests per minute** (200 requests per second sustained, burst up to 18,000 rpm). Enterprise tenants can request custom higher rate limits through their Named Support Manager.
- **Terraform Provider Mutation Limit:** Write/mutation endpoints (`POST`, `PUT`, `PATCH`, `DELETE`) are additionally capped at **120 mutations per minute** on Starter/Growth and **600 mutations per minute** on Enterprise.

### Interpreting `HTTP 429 Too Many Requests` and `Retry-After` headers

Every response from the Nimbus Cloud Platform v2 REST API includes three standard rate-limit headers so client applications can monitor consumption in real time:

- `X-RateLimit-Limit`: The maximum requests per minute permitted for your tenant tier (for example, `3000`).
- `X-RateLimit-Remaining`: The number of requests remaining in the current 60-second window.
- `X-RateLimit-Reset`: The UTC Unix epoch timestamp (in seconds) when the token bucket replenishes.

When a tenant exceeds its per-minute allowance, the Nimbus Cloud Platform API gateway returns `HTTP 429 Too Many Requests` with error code `RATE_LIMIT_EXCEEDED` and an RFC 7231-compliant `Retry-After` header indicating the exact number of integer seconds (for example, `Retry-After: 18`) the client must wait before sending another request. Clients must honor the `Retry-After` header and implement exponential backoff with full jitter rather than tight polling loops.
