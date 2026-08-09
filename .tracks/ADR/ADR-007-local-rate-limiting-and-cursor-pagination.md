# ADR-007: local rate limiting and cursor pagination

- Status: Accepted
- Date: 2026-08-09
- Owners: Primary engineering thread
- Scope: Track 08 selected bonus contracts

## Context

Track 08 must add rate limiting and cursor pagination after the mandatory API is
green. The delivered runtime is deliberately local: one Uvicorn worker, synchronous
SQLite access, an in-process statistics worker, and no external cache or broker. The
bonus work must preserve every accepted page-pagination response, ownership boundary,
error shape, JSON Lines logging rule, and one-worker deployment invariant.

## Decision

### Rate limiting

Use a process-local, thread-safe token bucket with an injectable monotonic clock.
Registration and login share one bucket keyed by the socket peer IP; forwarded-client
headers are ignored because no trusted-proxy contract exists. All six bookmark
operations share one bucket keyed by the already-authenticated user identifier. The
limiter therefore runs before authentication for public auth endpoints and after
successful authentication for bookmark endpoints.

Health, documentation, OpenAPI, unknown routes, and explicit internal/test seams are
not limited. Defaults are enabled, 10 auth requests per 60 seconds, and 120 bookmark
requests per 60 seconds. Limits and windows are positive and bounded. Production
cannot disable the limiter, and rate limiting requires `APP_WORKER_COUNT=1` so a
process-local bucket cannot imply a false distributed guarantee.

Bucket storage is bounded by a configurable maximum and idle TTL. Expired keys are
evicted and active keys use least-recently-used eviction; when all capacity is active,
an unseen key fails closed rather than bypassing the policy. A rejected request
returns the existing error envelope with code `rate_limited`, HTTP 429, a positive
integer `Retry-After`, and `Cache-Control: no-store`; it does not emit an authentication
challenge or log identity, token, body, or raw client-controlled content.

### Cursor pagination

`GET /api/bookmarks` retains page pagination as the default and preserves its exact
body. A new `pagination=cursor` mode accepts an optional opaque `cursor`; cursor mode
forbids an explicitly supplied `page`, and page mode forbids `cursor`. The common body
remains `items`, `total`, `page`, and `page_size`; in cursor mode `page` is the signed
logical page ordinal. A further page is advertised only through `X-Next-Cursor`.

The cursor is URL-safe canonical JSON authenticated with HMAC-SHA256 using a key
derived from `JWT_SECRET`. It contains versioned boundary values for descending
`created_at, id` order, logical page, issued/expiry timestamps, owner binding, and a
canonical fingerprint of search/tag/date filters. It contains no credential or
bookmark content. Tokens expire after a configurable 900 seconds by default, bounded
from 60 to 3600 seconds.

Malformed, oversized, unsupported-version, non-canonical, tampered, expired,
cross-user, or filter-mismatched cursors all return the same fixed HTTP 422
`invalid_cursor` response without revealing which check failed. Keyset selection uses
`created_at < boundary OR (created_at = boundary AND id < boundary_id)`, descending
order, and `page_size + 1`; it retains the existing count/items/tags snapshot and query
budget. Existing indexes remain sufficient for the assessment database.

## Configuration contract

- `RATE_LIMIT_ENABLED=true`
- `RATE_LIMIT_AUTH_REQUESTS=10` (1..10000)
- `RATE_LIMIT_AUTH_WINDOW_SECONDS=60` (1..3600)
- `RATE_LIMIT_BOOKMARK_REQUESTS=120` (1..10000)
- `RATE_LIMIT_BOOKMARK_WINDOW_SECONDS=60` (1..3600)
- `RATE_LIMIT_MAX_KEYS=10000` (1..100000)
- `RATE_LIMIT_IDLE_TTL_SECONDS=300` (1..86400 and not below either window)
- `CURSOR_TTL_SECONDS=900` (60..3600)

## Consequences

The bonus is deterministic and dependency-free and fits the documented one-worker
local topology. It is not a production-distributed rate limiter: horizontal scale
requires a shared atomic store and trusted-proxy policy. Cursor tokens become invalid
when the signing secret changes, intentionally bind all filters and owners, and avoid
offset drift for subsequent pages; the reported total is still a per-request snapshot.

OpenAPI must document HTTP 429 for the two public auth operations and six bookmark
operations, the cursor query parameters, `X-Next-Cursor`, and fixed error schemas.
The original mandatory-operation manifest stays unchanged; Track 08 records the added
bonus responses separately.

## Verification

Unit evidence covers refill boundaries, monotonic time, shared buckets, bounded/LRU/
idle behavior, capacity fail-closed behavior, configuration rejection, cursor
round-trip, canonical encoding, expiry, tamper, ownership/filter binding, and boundary
tuples. Integration/contract evidence covers exact headers and envelopes, endpoint
inclusion/exclusion, authentication ordering, page compatibility, invalid parameter
combinations, stable no-duplicate traversal under inserts, query count, SQL plan/index
use, OpenAPI, JSON Lines/redaction, and the complete inherited regression suite.

## Rejected alternatives

- External Redis or proxy middleware: outside the local assessment and FUT-01 scope.
- Trusting `X-Forwarded-For`: unsafe without an explicit trusted-proxy boundary.
- Per-route independent bookmark buckets: weakens the selected shared-user policy.
- Plain or merely encoded cursors: permits tampering and cross-owner/filter reuse.
- Replacing page pagination: breaks an accepted mandatory public contract.
- Offset encoded inside a cursor: retains the drift cursor pagination is intended to
  avoid.
