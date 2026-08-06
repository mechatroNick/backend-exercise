# Track 02 history

## 2026-08-05 — Sequential planning started

- Created the detailed Track 02 specification and execution plan after reviewing the
  committed Track 00 baseline and Track 01 plan.
- Preserved the accepted ADR-002 API/error contract and ADR-003 identity/password/
  access-token semantics without introducing new product decisions.
- Marked the track **Planned**, not Ready: Track 01 is Ready but has not implemented
  or closed the Settings, clock, session, migration, factory, and quality seams that
  Track 02 must consume.
- Bounded Track 02's OpenAPI evidence to registration/login operations. Track 05
  remains responsible for full cross-operation OpenAPI conformance.
- No product code, dependencies, installs, migration, or source-PDF changes were
  made during planning.

## Current state

- Specification: Complete
- Plan: Complete
- Implementation: Complete and independently reviewed
- Material product questions: None known

## Next action

Merge the verified Track 02 branch into `main`, then open Track 03 and rerun its
compatibility checkpoint before bookmark implementation.

## 2026-08-05 — Shared verification-guideline adoption

- Adopted the committed engineering verification guideline in Track 02 planning
  without changing status, task IDs/dependencies, authentication/error semantics, or
  Track 05's full cross-operation OpenAPI gate.
- Planned (but did not create or run) `scripts/verify-track-02.sh` as an extension of
  the delivered Track 01 bootstrap. Its future proof covers real auth HTTP flows,
  a protected success, representative generic auth/error failure, JSON-Line
  attribution/correlation where applicable, seeded-sentinel redaction, and cleanup.
- No Track 02 test, application process, migration, harness, runtime validation, or
  real credential was created, executed, printed, or stored by this planning-only
  change.

## 2026-08-06 — Incremental verification-governance review correction

- Bumped the SPEC/PLAN planning contract to version 1.1 and added ADR-006 as an
  Accepted evidence-and-closure dependency only; status, task IDs/dependencies,
  authentication/error semantics, and the Track 05 OpenAPI boundary remain unchanged.
- Expanded pending harness evidence to validate inherited base JSON Lines fields,
  safe request correlation, redaction, no raw exception text indexed field, and
  exactly one unexpected-exception record at the owning HTTP boundary.
- Required safe password/token/content sentinels to be absent from logs,
  diagnostic/command output, assertion failures, and retained artifacts. The planned
  protected flow parses and uses its returned JWT without echoing it and removes its
  protected disposable state during cleanup; correlation never uses credential or
  identity values and no public correlation-header contract is added.
- This correction is planning only: no Track 02 test, process, migration, harness,
  runtime validation, credential, or artifact was created or executed.

## 2026-08-06 — Track 01 compatibility gate passed

- Verified Track 01's closure receipt and merge commit `8fa39b0`: 127 deterministic
  tests, 100% application statement/branch coverage, a complete disposable Alembic
  lifecycle, and the real Uvicorn process harness all passed before this branch was
  created.
- Inspected the delivered integration seams. `Settings` supplies a secret-bearing
  JWT key and bounded token TTL; `Clock` supplies aware UTC time; the synchronous
  session factory creates caller-owned sessions; the `users` table has canonical
  unique identity columns and 255-character non-empty hash storage; the app factory
  is injectable and lifecycle-owned; and tests build databases only through Alembic.
- Confirmed the Track 01 unexpected-exception/logging boundary can be evolved by the
  centralized Track 02 HTTP translation registration without introducing route-local
  mappings or duplicate exception records.
- No schema migration, compatibility workaround, ADR change, or Track 03 behavior is
  required. T02-01 is Complete and Track 02 is Ready for implementation.

## 2026-08-06 — Track 02 implementation and closure passed

- Delivered typed application errors, one HTTP translation boundary, canonical
  identities, NFC-aware Argon2 password handling, strict injected-clock HS256 access
  tokens, transactional auth persistence, JSON register/login routes, reusable bearer
  subject resolution, and bounded auth-operation OpenAPI contracts.
- Preserved database-authoritative uniqueness and fail-closed translation: only the
  exact native SQLite username/email uniqueness failures become `409`; unrelated
  integrity faults roll back, reach the owning unexpected boundary, log once with
  redaction, and return the generic `500` envelope.
- Added deterministic unit, migrated-SQLite integration, endpoint, generated-schema,
  concurrency, malformed-input, non-enumeration, token/subject, rollback, and
  no-disclosure evidence. The full suite passed with 236 tests and 100% coverage of
  866 statements and 166 branches.
- Delivered and ran `scripts/verify-track-02.sh` against the actual `make bootstrap`
  process. It proved registration/login/protected/error flows, response schemas,
  JSON-Line attribution/correlation/redaction, exactly one owning fault record, and
  removal of the verified disposable database, logs, responses, token config, and
  process state.
- Re-ran Track 01's inherited process harness and a disposable Alembic
  upgrade/downgrade/upgrade lifecycle. Both passed and cleaned up, preserving inert
  imports, Alembic-only schema ownership, and one-worker lifecycle behavior.
- Mason's cross-layer review passed requirements, security/redaction, 100% branch
  coverage, harness process safety, and Track 01 preservation. Its initial
  changes-required verdict concerned only the then-unwritten closure report and stale
  statuses; this closure update resolves that documentary finding.
- [TEST-REPORT.md](TEST-REPORT.md) records exact commands, versions, receipts,
  independent review, hygiene scans, the one upstream TestClient warning, and the
  retained Track 05 full-OpenAPI boundary.
