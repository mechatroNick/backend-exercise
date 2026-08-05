# Track 03 specification: protected bookmark CRUD, normalized tags, and ownership isolation

- Status: Planned
- Specification version: 1.0
- Planned: 2026-08-05
- Owner: Primary engineering thread
- Depends on: Track 02 implementation and closure; Track 01 implementation and closure; Track 00 (Complete)
- Governing ADRs: ADR-001, ADR-002, ADR-004
- Assessment requirements: BKM-01, BKM-02, BKM-03, ISO-01, TAG-01, TIME-01; AUTH-04 dependency

## 1. Intent anchor

Deliver the smallest protected bookmark capability that later discovery/statistics
tracks can trust: owner-scoped CRUD, canonical many-to-many tags, exact timestamps,
and a post-commit invalidation seam without a worker.

Planning follows committed Track 02 (`6dd4deb`). Implementation is dependency-gated
until Track 02 closes with bearer-auth, error-boundary, route, Settings, clock,
persistence, and test evidence.

## 2. Must-preserve contracts

- All bookmark routes use Track 02 bearer auth: `POST /api/bookmarks` is `201`; GET
  collection/detail and PATCH detail are `200`; DELETE detail is bodyless `204`.
- Missing and other-user identifiers are indistinguishable `404` envelopes. Every
  repository lookup/mutation/deletion includes authenticated `user_id` in its query;
  services do not fetch arbitrary rows and compare ownership afterward.
- Use strict separate create, PATCH, public, tag, and paginated-list DTOs. Create:
  absolute HTTP(S) URL, title 1--200, optional description <=500, at least one
  normalized tag. Duplicate URLs are allowed.
- PATCH distinguishes omitted from null; URL/title cannot be null; description may be
  cleared; supplied tags must normalize to non-empty membership; timestamps/IDs/owner
  are not mutable.
- Tags trim/lowercase; empty or over-50-character values fail; input duplicates collapse deterministically;
  globally unique rows are reused race-safely; responses use deterministic tag order;
  orphan tag rows remain.
- Services own commit/rollback; repositories never commit. Bookmark, association, and
  timestamp writes are transactional. One injected UTC instant sets both creation
  timestamps; `created_at` is immutable; `updated_at` changes only after committed
  material scalar or normalized tag-membership change. Empty/equivalent/reordered/
  failed/rolled-back work does not advance either timestamp.
- Track 03 leaves an explicit post-commit injection point for a narrow
  `DomainEventPublisher` and supplies only a no-op adapter. It does not define or
  assert concrete invalidation publication, payload, queue, worker, durable marker,
  lifecycle, or statistics behavior; those remain Track 06 obligations under
  ADR-004.
- Public bookmark DTOs contain `id`, `url`, `title`, `description`, normalized tags,
  `created_at`, and `updated_at`, but not `user_id` or persistence-only fields. GET
  collection establishes a forward-compatible `{items,total,page,page_size}` DTO and
  accepted default ordering. Track 04 owns public filter/page parameters, page slicing,
  total-query correctness, and N+1/query-count proof. Track 05 owns broad OpenAPI
  conformance.
- Public DTOs/errors/events/logs never leak credential data, authorization values,
  cross-user data, database internals, or unintended bookmark content.

## 3. Scope

### Included

- DTOs; normalized-tag/material-change policies; owner-scoped repositories;
  service-owned create/list baseline/detail/PATCH/delete transactions; protected CRUD
  routes; deterministic association handling; no-op publisher port; focused unit,
  migrated-SQLite integration, endpoint, and operation-level OpenAPI tests.

### Non-goals

- auth/error redesign; filters/pagination totals/query plan/raw-SQL stats (Track 04);
  exhaustive OpenAPI conformance (Track 05); queues/dirty markers/workers/snapshots
  (Track 06); account features, rate limiting, schema redesign, dependencies, or
  product implementation while Planned.

## 4. Decision latitude and reserved decisions

Track 03 may select internal module/port/helper/DTO/repository names, deterministic
tag display order consistent with ADR-002, fixtures, no-op wiring, and a list DTO
that preserves Track 04 compatibility. Stop for ADR/owner direction before changing
paths/statuses, `404` concealment, error envelope, URL/title/description/tag contract,
normalization/global uniqueness/orphans, timestamps, transaction boundary,
post-commit-only publication, or Track 04--06 ownership.

## 5. Requirements

| ID | Requirement |
| --- | --- |
| T03-REQ-01 | Provide distinct strict create, PATCH, public, tag, and compatible paginated-list DTOs. |
| T03-REQ-02 | Implement protected create, baseline list, detail, PATCH, and bodyless delete routes with accepted statuses/envelope. |
| T03-REQ-03 | Apply owner identity in all repository predicates so missing/other-user resources have the same typed not-found outcome. |
| T03-REQ-04 | Normalize/deduplicate/reuse tags, handle global-unique races safely, retain orphans, and return deterministic order. |
| T03-REQ-05 | Keep bookmark/tag/association work in service-owned transactions; repositories do not commit and failed work rolls back. |
| T03-REQ-06 | Enforce one-clock creation, immutable `created_at`, and material-only timestamp advancement including tag-only changes. |
| T03-REQ-07 | Provide an inert, no-op-capable `DomainEventPublisher` injection seam at the explicit post-commit boundary without defining or claiming Track 06 event publication behavior. |
| T03-REQ-08 | Establish a compatible `{items,total,page,page_size}` list response and default ordering only; defer public filter/page parameters, slicing, total-query correctness, and performance evidence to Track 04. |
| T03-REQ-09 | Prove CRUD, isolation, normalization, timestamp, transaction, publisher, disclosure, and bounded OpenAPI contracts. |

## 6. Dependencies and readiness gate

| Dependency | Required state | Reason |
| --- | --- | --- |
| Track 00 | Complete | Accepted routes/schema/tag/timestamp/extension boundaries. |
| Track 01 | Implemented and closed | Migration, constraints, sessions, clock, factory, quality workflow. |
| Track 02 | Implemented and closed | Bearer current-user dependency, typed error envelope, and auth integration. |
| ADR-001/002/004 | Accepted | ORM/DTO, CRUD/tag/timestamp, and publisher-seam contracts. |

Track 03 is **Planned**, not Ready, until Track 02 closure supplies actual evidence.
Revise before code if delivered interfaces materially differ.

## 7. Acceptance evidence threshold

- Bearer-protected CRUD returns accepted bodies/statuses; duplicate URLs work.
- Validation covers URL/title/description/tags and PATCH omitted/null semantics.
- Canonical tags trim/lowercase/deduplicate/reuse; invalid/empty/overlong values fail;
  global uniqueness races are safe; orphan rows remain.
- Two-user tests prove list/detail/PATCH/delete isolation and response-identical `404`.
- Fixed-clock tests prove creation equality, immutable `created_at`, material scalar/
  tag advancement, and no movement for empty/equivalent/reordered/failed/rolled-back work.
- Delete is transactional, association-only cleanup leaves orphan tags, and emits
  bodyless `204`. Composition tests prove the no-op publisher seam is inert and cannot
  change CRUD outcomes; Track 03 claims no concrete invalidation publication.
- List DTO/default ordering compatibility is proved without claiming Track 04 filters,
  page parameters, total correctness, or N+1/query-count evidence.
- Focused/full quality tests and Track 03 operation-schema validation pass; no secret
  or generated artifact appears in status. Full cross-operation OpenAPI proof is Track 05.

## 8. Risks, stop conditions, and follow-ups

| Risk | Mitigation |
| --- | --- |
| Track 02 seams differ | Gate on closure and inspect delivered interfaces. |
| Existence leak | Put `user_id` in every repository predicate. |
| Tag insert race | Database uniqueness is authoritative; handle known conflict after rollback/reload. |
| No-op touches time | Normalize/compare before mutation; fixed-clock tests. |
| Partial association write | One service-owned transaction and failure tests. |
| Track 06 scope leakage | Port/no-op only; no queue/worker/marker. |

Stop if Track 01/02 is not closed, required records conflict, delivered schema cannot
honor constraints without a reserved schema decision, later-track behavior is required,
or a change exposes protected/public contract data.

- **Track 04:** filters, dates, pagination parameters/totals, query design, raw SQL,
  eager-loading/N+1 proof.
- **Track 05:** API-wide OpenAPI response/status/content-type/schema conformance.
- **Track 06:** invalidation payload, marker, queue adapter/worker/lifecycle/health.

## 9. Traceability

| Assessment requirement | Track requirements | Planned evidence |
| --- | --- | --- |
| BKM-01 | T03-REQ-01,02,05,06,09 | CRUD/status/transaction/timestamp tests. |
| BKM-02 | T03-REQ-01,02,06,09 | URL/title/description DTO and fixed-clock tests. |
| BKM-03 | T03-REQ-01,04,05,09 | Tag normalization/reuse/association tests. |
| ISO-01 | T03-REQ-02,03,05,09 | Two-user concealment tests. |
| TAG-01 | T03-REQ-04,05,06,09 | Empty/overlong/dedup/reuse/orphan/reordered tests. |
| TIME-01 | T03-REQ-05,06,09 | Material/no-op/failure/rollback fixed-clock tests. |
| AUTH-04 dependency | T03-REQ-02,03,09 | Bearer and owner-scoped endpoint tests; Track 02 owns auth primitive. |
