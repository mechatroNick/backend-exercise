# Track 03 history

## 2026-08-05 — Sequential planning started

- Created Track 03 SPEC/PLAN after reviewing committed Track 02 (`6dd4deb`) and the
  Track 00/01 baseline.
- Preserved ADR-001 ORM/DTO and transaction boundaries, ADR-002 CRUD/tag/timestamp
  semantics, and ADR-004's narrow post-commit publisher dependency without adding
  a queue, durable marker, event worker, or statistics behavior.
- Track 03 is **Planned**, not Ready: Track 02 remains unimplemented, so bearer-auth
  and error-boundary integration seams lack runtime evidence.
- Reserved filters/pagination/totals/query-count, broad OpenAPI proof, and runtime
  invalidation infrastructure for Tracks 04, 05, and 06.
- No product code, dependencies, installs, migration, or source-PDF changes occurred.

## Current state

- Specification: Complete
- Plan: Complete
- Implementation: Complete and independently reviewed
- Material product questions: None known

## Next action

Merge the verified Track 03 branch into `main`, then open Track 04 and rerun its
compatibility checkpoint before search, pagination, or current-statistics work.

## 2026-08-05 — Shared verification-guideline adoption

- Adopted the committed engineering verification guideline in Track 03 planning
  without changing status, task IDs/dependencies, CRUD/tag/timestamp semantics, the
  inert publisher seam, or Track 04/05/06 ownership.
- Planned (but did not create or run) `scripts/verify-track-03.sh` to extend the
  delivered bootstrap with real authenticated CRUD, two-user concealment, tag and
  timestamp assertions, JSON-Line redaction/attribution evidence, and cleanup.
- The planned proof confirms that Track 03's injected no-op publisher does not alter
  CRUD outcomes and does not claim concrete Track 06 event publication.
- No Track 03 test, application process, migration, harness, or runtime validation
  was executed by this planning-only change.

## 2026-08-06 — Incremental verification-governance review correction

- Bumped the SPEC/PLAN planning contract to version 1.1 and added ADR-006 as an
  Accepted evidence-and-closure dependency only; status, task IDs/dependencies,
  CRUD/tag/time semantics, the inert no-op publisher seam, and downstream ownership
  remain unchanged.
- Expanded pending harness evidence to validate inherited JSON Lines fields, safe
  request correlation not based on token/user/content, redaction, and exactly one
  unexpected-exception record at the owning HTTP boundary.
- Clarified legitimate own-user assertion inputs: bookmark URL/title/description/tags/
  timestamps and returned JWT remain ephemeral/in-memory (or strictly protected
  disposable state only if unavoidable), are parsed/used without echoing, removed
  during cleanup, and never disclose cross-user data or enter unsafe receipt surfaces.
- This correction is planning only: no Track 03 test, process, migration, harness,
  runtime validation, product artifact, or credential was created or executed.

## 2026-08-06 — Track 01/02 compatibility gate passed

- Verified clean Track 03 branch creation from Track 02 completion merge `adb0e8c`
  and inspected both upstream `TEST-REPORT.md` receipts.
- Confirmed the existing Alembic revision already owns the required `bookmarks`,
  globally unique `tags`, and composite-key `bookmark_tags` schema, owner foreign
  key, timestamp check, cascades, and ordering indexes. Track 03 needs no migration.
- Confirmed direct reuse of Track 02's request-scoped rollback/close session,
  `CurrentSubject.user_id` bearer dependency, typed concealment `NotFoundError`,
  centralized response boundary, injected UTC clock, router composition, and
  service-owned transaction convention.
- Ran 48 focused model, clock, auth-dependency, constraint, and auth-route tests;
  all passed with the one already-recorded upstream TestClient warning. Diff and
  worktree checks remained clean.
- Identified only expected implementation gaps: Track 03 DTO/policy, owner-scoped
  repository, transaction service, inert no-op publisher port, protected router,
  edge tests, and live process harness. No contradiction or stop condition was found.
- Preserved downstream boundaries: no public filtering/page slicing/raw SQL or
  performance claim from Track 04, no full API-wide OpenAPI claim from Track 05,
  and no concrete event, payload, queue, dirty marker, worker, lifecycle, or
  statistics behavior from Track 06.

## 2026-08-06 — Track 03 implementation and closure passed

- Delivered strict bookmark DTOs and materiality policy, owner-scoped repositories,
  transactional CRUD services, canonical global tags, fixed timestamp semantics,
  an inert post-commit publisher seam, bearer-protected routes, and bounded operation
  OpenAPI contracts without a schema migration or downstream runtime behavior.
- Added deterministic unit, migrated-SQLite repository/service, endpoint, isolation,
  rollback, disclosure, and OpenAPI evidence. The full suite passed with 348 tests and
  100% coverage of 1,282 application statements and 234 branches.
- Mason's first review correctly rejected the original final-state concurrency test
  as proof that native tag-conflict recovery ran. The replacement deterministic
  real-engine test observes the actual SQLite unique error, savepoint rollback,
  winner reload, single outer commit, and durable bookmark/tag/link; a second real
  constraint test proves unrelated integrity errors remain unmasked. Mason's focused
  re-review passed the correction.
- Delivered and ran `scripts/verify-track-03.sh` against the actual bootstrap. It
  proved two-user authenticated CRUD, canonical tags, material/no-op timestamps,
  concealed `404`, bodyless `204`, bounded schemas, JSON-Line attribution/redaction,
  exactly one owning fault, and deletion of all disposable credentials and state.
- Re-ran the Track 01 and corrected Track 02 inherited harnesses, a disposable
  Alembic upgrade/check/downgrade/upgrade lifecycle, lock/sync checks, Ruff, mypy,
  documentation verification, source scans, and repository-hygiene checks.
- [TEST-REPORT.md](TEST-REPORT.md) records exact commands, versions, incremental
  receipts, review findings/correction, cleanup, the one upstream TestClient warning,
  and retained Track 04/05/06 boundaries.
