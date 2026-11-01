---
doc_id: kb-help-api-basics-webhooks
title: Public REST API basics: authentication, pagination, idempotency, and webhooks
source_system: helpcenter
source_kind: curated
audience: customer_visible
provenance: human
acl_groups: []
is_restricted: false
updated_at: 2026-09-21
intents: [GENERAL_INQUIRY, TECHNICAL_OUTAGE]
test_case: none
---

# Public REST API basics: authentication, pagination, idempotency, and webhooks

## Authenticating to the Nimbus Cloud Platform REST API

The Nimbus Cloud Platform v2 REST API provides programmatic access to manage Nimbus DB clusters, Nimbus Run workloads, Nimbus Net VPCs, and Nimbus POS Gateway terminals. All API requests must be made over HTTPS using TLS 1.2 or TLS 1.3 against the regional API base URL (`https://us.api.nimbuscloud.example.com/v2` for US tenants or `https://eu.api.nimbuscloud.example.com/v2` for EU tenants). Plain HTTP requests are rejected with `400 Bad Request`.

### Bearer API tokens and service accounts

To authenticate API calls, create a scoped Service Account token under **Organization Settings > API & Service Accounts** and pass the token in the HTTP `Authorization` header using the `Bearer` scheme. Service Account tokens begin with the prefix `nmb_live_` for production resources or `nmb_test_` for sandbox environments:

```bash
curl -X GET "https://us.api.nimbuscloud.example.com/v2/db/clusters" \
  -H "Authorization: Bearer nmb_live_9f8e7d6c5b4a3210EXAMPLE" \
  -H "Accept: application/json"
```

If a token is missing, expired, or revoked, the API returns `HTTP 401 Unauthorized` with error code `AUTH_INVALID_TOKEN`. If the token lacks permission for the requested resource, the API returns `HTTP 403 Forbidden` with error code `AUTH_INSUFFICIENT_SCOPE`.

## Cursor-based pagination on collection endpoints

All `GET` list endpoints on the Nimbus Cloud Platform v2 REST API use cursor-based pagination rather than offset pagination to ensure consistent results across large datasets. List responses include a `page_info` object containing `next_cursor` and `has_more`:

- **`limit` query parameter:** Controls the number of records returned per page. The default is `50` and the maximum allowed value is `200`.
- **`cursor` query parameter:** Pass the opaque string returned in `page_info.next_cursor` from the previous response to fetch the next page of results.

```json
{
  "data": [
    { "id": "dbc_01J4K9L2M", "name": "db-prod-west", "status": "AVAILABLE" }
  ],
  "page_info": {
    "limit": 50,
    "has_more": true,
    "next_cursor": "eyJpZCI6ImRiY18wMUo0SzlMMk0ifQ=="
  }
}
```

## Idempotency keys for safe mutation retries

To prevent duplicate resource creation or double-charging when network timeouts occur during `POST` or `PATCH` requests, pass a unique UUID v4 string (up to 64 characters) in the `Idempotency-Key` HTTP header:

- Nimbus Cloud Platform caches the HTTP status code and response body associated with each `Idempotency-Key` per tenant for **24 hours**.
- If you retry a request with the exact same `Idempotency-Key` and request payload within 24 hours, the API returns the cached outcome without re-executing the operation.
- If you reuse an `Idempotency-Key` with a different request payload within 24 hours, the API rejects the request with `HTTP 422 Unprocessable Entity` (`IDEMPOTENCY_PAYLOAD_MISMATCH`).

## Webhook delivery, signature verification, and retries

### Verifying `X-Nimbus-Signature-256` headers

Nimbus Cloud Platform can send real-time webhook events (such as `db.failover.completed`, `pos.terminal.offline`, or `invoice.payment_failed`) to HTTPS endpoints registered under **Organization Settings > Webhooks**. Every webhook request includes a timestamp header (`X-Nimbus-Timestamp`) and an HMAC-SHA256 signature header (`X-Nimbus-Signature-256`) computed over `<timestamp>.<raw_json_body>` using your endpoint's webhook signing secret (`whsec_...`).

### Automatic webhook retry schedule

Your webhook receiver must return an `HTTP 2xx` status code within **10 seconds**. If your endpoint times out or returns an `HTTP 4xx/5xx` error, Nimbus Cloud Platform retries delivery up to **6 times** over approximately 6 hours using an exponential backoff schedule: **30 seconds**, **2 minutes**, **10 minutes**, **30 minutes**, **2 hours**, and **4 hours**. After 6 consecutive failures, the event is marked `FAILED_EXHAUSTED` and can be manually replayed from the console or via `POST /v2/webhooks/events/{event_id}/replay`.
