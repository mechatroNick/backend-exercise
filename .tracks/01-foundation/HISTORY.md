# Track 01 history

## 2026-08-05 — Planning started

- Track 00 closed with a passing independent reader re-audit.
- Inspected the current repository and local tool baseline without modifying the environment.
- Found a shell-default Python 3.14.2, installed Python 3.13/3.14 executables, `uv 0.9.15`, GNU Make 3.81, and Git 2.50.1.
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
