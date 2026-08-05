# Track 01 history

## 2026-08-05 — Planning started

- Track 00 closed with a passing independent reader re-audit.
- Inspected the current repository and local tool baseline without modifying the environment.
- In that earlier `PATH` context, observed a shell-default Python 3.14.2, installed Python 3.13/3.14 executables, `uv 0.9.15`, GNU Make 3.81, and Git 2.50.1.
- The accepted runtime remains Python 3.12; the plan therefore requires an explicit pin and managed 3.12 environment rather than using the shell default.
- A sandboxed `uv python list --only-installed` probe could not provide inventory: the first attempt could not create its user cache, and a writable temporary cache exposed a local `uv` system-configuration panic. No install or environment mutation was attempted. This is an execution-environment observation, not evidence that the repository cannot use `uv` in a normal shell.
- Auth, bookmark API behavior, and statistics runtime work remain out of scope for this track.

## Current state

- Specification: Ready
- Plan: Ready
- Implementation: Not started
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

Start T01-01 only when implementation is authorized: resolve current compatible package versions from primary sources, create the Python 3.12 locked environment, and stop for review if the selected stack cannot meet ADR-001.

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
