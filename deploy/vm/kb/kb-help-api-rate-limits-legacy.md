---
doc_id: kb-help-api-rate-limits-legacy
title: Legacy API v1 rate limits and throttling headers (2025 archive)
source_system: helpcenter
source_kind: curated
audience: customer_visible
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2025-01-20
intents: [GENERAL_INQUIRY, TECHNICAL_OUTAGE]
test_case: stale
---

# Legacy API v1 rate limits and throttling headers (2025 archive)

## Overview of Nimbus Cloud Platform API v1 rate limiting (2025 specification)

This document describes the request throttling rules and custom HTTP headers used by the Nimbus Cloud Platform REST API (`https://api.nimbuscloud.example.com/v1`) across all US and EU customer tenants as of January 2025. Every API call issued by a tenant's service account or CLI integration counts against a fixed 60-second counter associated with the tenant's subscription plan.

### 2025 API v1 rate limits by subscription tier

Under the 2025 API v1 gateway architecture, Nimbus Cloud Platform enforces the following per-minute request ceilings across Starter, Growth, and Enterprise tenants:

- **Starter Plan Rate Limit (2025 API v1):** **120 requests per minute** (2 requests per second sustained, with no burst allowance).
- **Growth Plan Rate Limit (2025 API v1):** **300 requests per minute** (5 requests per second sustained, burst up to 400 requests per minute).
- **Enterprise Plan Rate Limit (2025 API v1):** **1,500 requests per minute** (25 requests per second sustained, burst up to 2,000 requests per minute).
- **Terraform Provider Mutation Limit (2025 API v1):** All plans are restricted to a flat **30 write mutations per minute** (`POST`, `PUT`, `DELETE`).

## Handling `HTTP 429` responses in the 2025 API v1 gateway

### Custom `X-Nimbus-Wait-Seconds` header

When a tenant exceeds its 60-second request quota on the 2025 API v1 gateway, the server returns `HTTP 429 Too Many Requests`. Unlike gateways that return standard `Retry-After` headers, the 2025 API v1 gateway omits `Retry-After` and instead populates three proprietary headers in every throttled response:

- `X-Nimbus-Quota-Max`: The tenant's maximum allowed requests per minute (`120`, `300`, or `1500`).
- `X-Nimbus-Quota-Used`: The number of requests consumed during the current calendar minute.
- `X-Nimbus-Wait-Seconds`: The number of seconds until the top of the next UTC minute when the counter resets to zero.

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
X-Nimbus-Quota-Max: 300
X-Nimbus-Quota-Used: 301
X-Nimbus-Wait-Seconds: 42

{
  "error": "V1_QUOTA_EXCEEDED",
  "message": "Tenant exceeded 300 requests/min on Growth plan. Wait X-Nimbus-Wait-Seconds."
}
```

### Authentication via `X-Nimbus-Api-Key` header in API v1

In the 2025 API v1 specification, clients authenticate by passing a static 32-character hexadecimal key inside the `X-Nimbus-Api-Key` HTTP header rather than an `Authorization: Bearer` header. Static v1 keys do not distinguish between live and sandbox prefixes and must be rotated manually every 180 days from **Organization Settings > Legacy API Keys**.

## Pagination parameters in API v1

Collection endpoints in the 2025 API v1 specification use page-number offset pagination via `?page=1&per_page=25` (maximum `per_page=50`) rather than cursor-based pagination. Queries requesting `page` values above 100 return `HTTP 400 Bad Request` (`OFFSET_TOO_LARGE`).
