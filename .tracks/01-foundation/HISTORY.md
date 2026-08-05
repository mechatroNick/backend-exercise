# Track 01 history

## 2026-08-05 — Planning started

- Track 00 closed with a passing independent reader re-audit.
- Inspected the current repository and local tool baseline without modifying the environment.
- In that earlier `PATH` context, observed a shell-default Python 3.14.2, installed Python 3.13/3.14 executables, `uv 0.9.15`, GNU Make 3.81, and Git 2.50.1.
- The accepted runtime remains Python 3.12; the plan therefore requires an explicit pin and managed 3.12 environment rather than using the shell default.
- A sandboxed `uv python list --only-installed` probe could not provide inventory: the first attempt could not create its user cache, and a writable temporary cache exposed a local `uv` system-configuration panic. No install or environment mutation was attempted. This is an execution-environment observation, not evidence that the repository cannot use `uv` in a normal shell.
- Auth, bookmark API behavior, and statistics runtime work remain out of scope for this track.

## Current state

- Specification: Complete
- Plan: Complete
- Implementation: Complete
- Material product questions: None known

## 2026-08-05 — Planning audit

- A read-only architecture audit identified five places where implementation still had decision latitude that belonged in the plan.
- Closed the test-side schema-creation loophole: Alembic is the only schema path for database-backed tests, and the closure scan covers `app`, `tests`, and `alembic`.
- Fixed physical table names and selected `ON DELETE CASCADE` from users to owned bookmarks, consistent with private-data lifecycle and association cleanup.
- Added fail-closed evidence for SQLite foreign-key enforcement on Alembic's online connection.
- Added direct SQLite failure evidence for empty/whitespace required strings and `updated_at < created_at`, plus `foreign_key_check` and exact index order.
- Made `APP_WORKER_COUNT == 1` conditional on the in-process statistics refresher being enabled.
- The focused re-audit passed all five repaired items and declared the track ready for implementation.

## Next action

Begin Track 02 from this verified foundation. Recheck the Track 01 closure receipt and
preserve the factory, Settings, clock, session, migration, schema, and logging seams
before adding the centralized public error contract and authentication behavior.

## 2026-08-05 — Sequential planning review after Track 00 baseline `d7e8420`

- Reviewed Track 01 against the committed Track 00 baseline `d7e8420` before downstream implementation planning.
- Clarified the factory contract: Uvicorn must invoke `app.main:create_app --factory`;
  `create_app(settings: Settings | None = None)` supports test injection, and import
  creates no application instance, reads no environment, creates no engine, migrates
  no schema, and starts no service.
- Added explicit execution owners and dependency ordering for T01-01 through T01-08, and corrected ADR-002, ADR-003, and ADR-004 affected-track metadata to include Track 01.
- Replaced path-dependent Python-default wording with the observed inventory: `python3` resolves to `/usr/bin/python3` 3.9.6, Homebrew's unversioned Python is 3.14.2, and 3.13.5/3.14.2 are installed; no accepted Python 3.12 runtime is evidenced, so the locked environment must not depend on ambient `PATH`.
- Validated the focused Markdown metadata, task ownership/dependencies, Python inventory, trailing whitespace, diff whitespace, and worktree status without installing dependencies or changing product code.
- Residual boundary: the earlier sandboxed `uv` runtime-inventory probe panicked in local system configuration; that environment limitation remains distinct from repository/toolchain compatibility and must be rechecked when implementation is authorized.

## 2026-08-05 — Shared verification-guideline adoption

- Adopted the committed shared engineering verification guideline in Track 01 planning
  without changing Track 01 status, task IDs, product contracts, or downstream
  dependencies.
- Planned the centralized JSON Lines foundation: attributable source/service/event
  fields, redaction checks, and one structured unexpected-exception record at the
  owning boundary. ADR-004 worker-specific logging remains deferred to Track 06.
- Planned (but did not create or run) `scripts/verify-track-01.sh`: it will exercise
  the delivered Uvicorn factory/bootstrap with a disposable migrated SQLite database,
  a dynamic isolated port, bounded observable-endpoint polling, JSON-Line assertions,
  and verified cleanup.
- No Track 01 test, application process, migration, harness, or runtime validation
  was executed by this planning-only change.

## 2026-08-06 — Incremental verification-governance review correction

- Bumped the planning contract to SPEC/PLAN version 1.1 and added ADR-006 to the
  governing verification and closure evidence.
- Made the centralized JSON Lines ownership map explicit: `source`, service/component,
  event, level, UTC timestamp, logger, `process_id`, and execution/thread identifier
  where applicable; redaction; and exactly one owning-boundary unexpected-exception
  record. Worker-specific fields/events remain Track 06 work under ADR-004.
- Resolved the settings ambiguity: log level is configurable, while the application
  log format/schema is fixed JSON Lines under ADR-006 with no plaintext runtime
  toggle.
- Added `scripts/verify-track-01.sh` only to proposed ownership and pending evidence;
  it has not been created or run. No runtime, test, migration, or harness evidence
  was executed by this planning-only correction.

## 2026-08-06 — Implementation and closure

- Delivered the locked Python 3.12 toolchain, validated Settings, injectable UTC
  clock, fail-closed JSON Lines logging, constrained SQLModel persistence boundary,
  reviewed initial Alembic revision, inert FastAPI factory/lifespan, and documented
  one-worker bootstrap in seven green implementation commits.
- Proved schema constraints, exact index order, foreign-key/cascade behavior,
  per-connection SQLite policy, UTC round trips, transaction rollback, import/startup
  non-mutation, and upgrade/downgrade/re-upgrade behavior against disposable databases
  created only through Alembic.
- A focused closure review found that the first harness used a post-process synthetic
  exception probe. Commit `53b40b8` corrected that gap with one application-owned
  unexpected-request boundary and a private `APP_ENV=test` fault seam. The revised
  harness triggers the real Uvicorn worker, verifies one redacted exception record
  from the lifecycle process, and confirms the worker remains alive.
- Independent re-review returned PASS. Final branch validation recorded 127 passing
  tests, 100% statement and branch coverage across `app`, clean Ruff and mypy gates,
  a clean Alembic lifecycle, a passing real-process harness with verified cleanup,
  and no forbidden `create_all()` call or tracked generated artifact.
- The complete command, selector, tool-version, cleanup, review, and known-gap
  receipts are recorded in `TEST-REPORT.md`.
