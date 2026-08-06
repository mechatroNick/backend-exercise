# Track 04 specification: search, pagination, and canonical current statistics

- Status: Complete
- Specification version: 1.1
- Planned: 2026-08-05
- Owner: Primary engineering thread
- Depends on: Track 03 implementation and closure; Tracks 01--02 closure
- Governing ADRs: ADR-001, ADR-002, ADR-004, ADR-006
- Assessment requirements: QRY-01, QRY-02, SQL-01, SQL-02, SQL-03; ISO-01 statistics dimension

## Intent and must-preserve contracts

Complete discovery and required live statistics while retaining owner isolation.
Track 03 is closed at merge `4df99c9`; its routes, DTOs, owner predicates, publisher
seam, clock, migrations, deterministic tests, and live harness passed the T04-01
compatibility gate without a schema or contract mismatch.

- Protected `GET /api/bookmarks` supports exact normalized `tag`, case-insensitive
  title-substring `q`, `from`/`to` created-date and `updated_from`/`updated_to`
  updated-date filters. Dates are `YYYY-MM-DD`, open ranges work, reversed ranges are
  `422`, and inclusive upper dates use next-UTC-midnight-exclusive comparisons.
- `page >= 1`; `page_size` defaults to 20 and caps at 100. Response is
  `{items,total,page,page_size}` ordered `created_at DESC, id DESC`.
- Search uses SQLModel ORM with eager/select-in loading. Items and total use the same
  predicates and one consistent read transaction; tag filtering cannot duplicate
  bookmarks (EXISTS or deliberate distinct). `q` is a literal substring, so `%`, `_`,
  and escape characters from input cannot become SQL wildcards. Query count remains
  bounded as result/tag volume grows. Do not claim substring-index benefit without
  recorded SQLite `EXPLAIN QUERY PLAN` evidence.
- Protected `GET /api/bookmarks/stats` is registered before `/{bookmark_id}` and is
  user-scoped. Exact body: `total_bookmarks`, `total_tags`, `top_tags[{name,count}]`,
  `bookmarks_per_month[{month,count}]`. Tags are distinct attached tags; top ties use
  count DESC/name ASC; months chronological; Settings top limit defaults to 5.
- Statistics raw SQL is isolated to a stats reader: named parameterized SQLite
  `TextClause`/statements only, every statement user-scoped, concise query comments,
  no interpolation (including the top-tag limit), all component aggregates in one
  consistent read transaction/snapshot. `top_tags.count` counts bookmarks per tag;
  `bookmarks_per_month.count` counts bookmarks in `YYYY-MM` UTC creation months.
  Ordinary search remains ORM.
- No queue/snapshot/history/dirty marker (06/07), schema/index change unless EXPLAIN
  demonstrates a need and reserved review approves, or API-wide OpenAPI conformance (05).

## Scope, decisions, and requirements

Included: query DTO/date policy; ORM list/items/total; raw-SQL stats reader; protected
routes/OpenAPI; deterministic correctness/performance tests. Decision latitude covers
internal query/helper/reader names and chosen eager strategy. ADR/owner review is
required before changing routes/body/filter semantics/order/limits/ORM-vs-raw-SQL
boundary/schema/indexes/snapshot behavior.

| ID | Requirement |
| --- | --- |
| T04-REQ-01 | Strictly validate documented filters, UTC calendar ranges, page bounds, and response metadata. |
| T04-REQ-02 | Build one owner-scoped ORM predicate set and read transaction for items and total, with literal substring semantics, deterministic ordering, duplicate-safe tag filtering, and bounded loading/query count. |
| T04-REQ-03 | Provide protected canonical current stats with exact DTO/body/order semantics. |
| T04-REQ-04 | Isolate named, parameterized, user-scoped SQLite aggregate statements in one consistent read transaction. |
| T04-REQ-05 | Prove filters/pagination, cross-user isolation, aggregates, query count/EXPLAIN, and operation OpenAPI contracts. |

## Dependencies, acceptance, risks, and stop conditions

Track 03 must be Complete; Track 01 provides migrated SQLite/settings/clock and Track
02 provides bearer/errors. Closure requires combined-filter and page-boundary tests;
empty/cross-user/multi-tag/tag-tie/month-year/delete/tag-change stats tests; exact
body/schema proof; no interpolation; same-predicate items/total; bounded query counts;
EXPLAIN receipts for claimed index behavior; deterministic filter/date/pagination/
query-count/raw-SQL tests; and quality/hygiene passes. It also requires the planned
`scripts/verify-track-04.sh` to extend the delivered real bootstrap with a disposable
migrated database, dynamic isolated port, and actual server. The harness must create
authenticated data and make real HTTP list-filter requests covering literal wildcard,
date inclusivity/boundaries, stable pages/total, and exact tag behavior, plus
`/api/bookmarks/stats` body/tie/month/cross-user-isolation assertions and relevant
supported database inspection. Captured JSON Lines, disclosure evidence, and cleanup
must satisfy the detailed rules below. ADR-006 is an Accepted evidence-and-closure
dependency only and does not alter Track 04 query, raw-SQL, DTO, or Track 05 contracts.

Own-user fixture/JWT/list/stat response values are direct assertion inputs only: keep
them ephemeral/in-memory, never print or persist them, and use strictly protected
disposable state only if unavoidable before removing it during cleanup. URL, title,
description, tag, token, and content sentinels must be absent from application logs,
indexed fields, command diagnostics, assertion failures, unsafe debug bundles, and
retained artifacts. Cross-user values are never exposed, including on failure. Captured
JSON Lines validate `source`, service/component, event, level, UTC timestamp, logger,
`process_id`, and execution/thread identifier where applicable; safe request
correlation is never token, user, body, or content based; sensitive data is redacted;
raw exception text is not an indexed field; and an unexpected exception is recorded
exactly once at its owning boundary.

The process smoke does not establish N+1 or index claims: Track 04 retains
deterministic query-count instrumentation and recorded `EXPLAIN QUERY PLAN` evidence
for those assertions. Track 04 imports the shared
[engineering verification guideline](../../docs/ENGINEERING-VERIFICATION-GUIDELINE.md)
and [ADR-006](../ADR/ADR-006-engineering-verification-and-closure-evidence.md)
closure invariant: Complete requires recorded passing deterministic tests and a
real-process harness receipt, never planned work or code presence. The harness does
not alter the ORM-versus-raw-SQL boundary, public DTO, or Track 05 ownership.

Risks: join duplicates, count drift, inconsistent multi-query stats, N+1, cross-user
leakage, and speculative index changes. Mitigate with EXISTS/distinct, shared predicates,
single read transaction, instrumentation, owner parameters everywhere, and EXPLAIN-first
review. Stop on upstream mismatch, contradictory contracts, required schema/index change,
or any request for Track 05--07 behavior.

## Traceability and follow-ups

| Assessment | Requirements | Evidence |
| --- | --- | --- |
| QRY-01/QRY-02 | T04-REQ-01,02,05 | Combined filter/date/page/order/total tests. |
| SQL-01/02 | T04-REQ-03,04,05 | Parameterized raw-SQL empty/populated/tie/month tests. |
| SQL-03 | T04-REQ-02,04,05 | Query-count, eager-loading, EXPLAIN, and raw-SQL isolation review. |
| ISO-01 stats | T04-REQ-02,03,04,05 | Two-user list/stats tests. |

Track 05 owns API-wide conformance; Track 06 owns snapshots/queue/markers/worker;
Track 07 owns history. Track 04 proves only its operations.
