# Track 04 history

## 2026-08-05 — Sequential planning started

- Planned Track 04 after committed Track 03 (`f0dd994`), preserving ORM search,
  isolated raw-SQL current stats, owner scoping, and later-track boundaries.
- Status is **Planned**, not Ready: Track 03 remains unimplemented and must close
  before its CRUD/query seams can be consumed.
- No code, dependency, migration, installation, or source-PDF change was made.

## Current state

- Specification: Ready
- Plan: Ready
- Implementation: Authorized; T04-01 compatibility gate complete

## Next action

Freeze the explicit SQLite read-snapshot design, then execute T04-02 query DTO and
date-policy work without changing public semantics or downstream ownership.

## 2026-08-05 — Shared verification-guideline adoption

- Adopted the committed engineering verification guideline in Track 04 planning
  without changing status, task IDs/dependencies, the ORM-versus-raw-SQL boundary,
  public DTO, or Track 05 ownership.
- Planned (but did not create or run) `scripts/verify-track-04.sh` for real filtered
  list/current-statistics HTTP evidence, supported database inspection, JSON-Line
  attribution/redaction checks, and cleanup via the delivered bootstrap.
- Retained deterministic query-count instrumentation and recorded `EXPLAIN QUERY PLAN`
  evidence as the only basis for N+1/index claims; a process smoke alone is not proof.
- No Track 04 test, application process, migration, harness, or runtime validation
  was executed by this planning-only change.

## 2026-08-06 — Incremental verification-governance review correction

- Bumped the SPEC/PLAN planning contract to version 1.1 and added ADR-006 as an
  Accepted evidence-and-closure dependency only; status, task IDs/dependencies,
  raw-SQL/query/DTO contracts, and Track 05 ownership remain unchanged.
- Expanded pending harness evidence to validate inherited JSON Lines fields, safe
  correlation not based on token/user/body/content, redaction, no raw exception text
  indexed field, and exactly one unexpected exception at its owning boundary.
- Clarified that own-user fixture/JWT/list/stat responses are ephemeral assertion
  inputs only and that sensitive/content sentinels and cross-user values never reach
  logs, diagnostics, assertion failures, unsafe debug bundles, or retained artifacts.
- Retained deterministic query-count instrumentation and recorded `EXPLAIN QUERY PLAN`
  as the only N+1/index proof; no Track 04 test, process, migration, harness, or
  runtime validation was executed by this planning-only correction.

## 2026-08-06 — Track 03 compatibility gate passed

- Opened `codex/track-04-search-stats` from verified Track 03 merge `4df99c9`; the
  worktree was clean and Track 03's 348-test, 100%-coverage, migration, review, and
  real-process closure receipts were present.
- Confirmed direct reuse of bearer `CurrentSubject`, request-scoped Session, strict
  bookmark/public/list DTOs, owner-scoped repositories, deterministic list ordering,
  UTC fixed-width timestamp storage, static-route reservation, `TOP_TAGS_LIMIT`, and
  the disposable live-harness pattern.
- Populated and empty-schema discovery plans used the delivered owner/date and
  association indexes. Exact-tag `EXISTS`, owner/date ordering, and stats joins have
  usable plans; literal substring and aggregate grouping correctly require scans or
  temporary B-trees. No schema/index migration or ADR change is justified.
- A disposable driver probe found an important implementation constraint: after an
  authenticated Session `SELECT`, SQLAlchemy reports a logical transaction while the
  Python 3.12 SQLite connection remains outside a real database transaction in legacy
  mode. Track 04 must explicitly prove one actual read snapshot across items, total,
  tag loads, and stats aggregates rather than equating shared Session state with
  SQLite snapshot consistency.
- Preserved boundaries: ordinary search remains ORM; raw SQL is isolated to canonical
  current stats; no snapshot/header/queue/worker/history behavior is introduced; and
  broad API conformance remains Track 05.
