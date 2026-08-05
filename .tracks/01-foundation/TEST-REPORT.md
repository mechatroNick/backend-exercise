# Track 01 test report

- Status: Passed
- Date: 2026-08-06
- Branch: `codex/track-01-foundation`
- Scope: Locked foundation toolchain, configuration, UTC/logging infrastructure,
  core schema and migrations, application lifecycle, and real-process bootstrap

## Acceptance matrix

| Requirement | Executable evidence | Result |
| --- | --- | --- |
| T01-REQ-01 | Managed Python 3.12.12, `.python-version`, `pyproject.toml`, `uv.lock`, locked sync/check | Pass |
| T01-REQ-02 | Settings range, relationship, environment, production-secret, and injection tests | Pass |
| T01-REQ-03 | Factory/import/lifespan tests against unmigrated disposable databases | Pass |
| T01-REQ-04 | Independent engine connections and Alembic online connection prove FK and finite busy-timeout policy | Pass |
| T01-REQ-05 | Metadata and migrated-schema inventory for users, bookmarks, tags, and `bookmark_tags` | Pass |
| T01-REQ-06 | Real SQLite required, whitespace, unique, length, timestamp-order, FK, and composite-key failure tests | Pass |
| T01-REQ-07 | Migrated ordered-index and foreign-key-action inspection | Pass |
| T01-REQ-08 | Empty upgrade, current/heads/check, downgrade to base, and re-upgrade on a disposable file database | Pass |
| T01-REQ-09 | Aware UTC normalization/round-trip and naive-bind rejection tests with injected clock | Pass |
| T01-REQ-10 | JSON schema/redaction/failure tests plus live Uvicorn lifecycle and exactly-one owning-boundary exception evidence | Pass |
| T01-REQ-11 | Locked sync, format, lint, type, test, migration, bootstrap, and check commands | Pass |
| T01-REQ-12 | Disposable Alembic-migrated SQLite integration suite and live process harness | Pass |

## Runtime and tool versions

| Tool | Resolved version |
| --- | --- |
| Python | 3.12.12 |
| uv | 0.9.15 |
| pytest | 9.1.1 |
| Coverage.py | 7.15.3 with C extension |
| Ruff | 0.15.22 |
| mypy | 2.3.0 compiled |
| Alembic | 1.19.0 |
| Bash | 3.2.57(1)-release |
| ripgrep | 15.1.0 |

The accepted runtime was acquired into disposable tool-managed storage because the
ambient macOS `python3` is 3.9.6. The repository lockfile, not ambient `PATH`, is the
dependency authority.

## Deterministic and static validation

| Command | Actual result |
| --- | --- |
| `uv sync --locked` | Exit `0`; Python 3.12 environment synchronized from `uv.lock`. |
| `uv lock --check` | Exit `0`; lockfile current. |
| `.venv/bin/ruff format --check .` | Exit `0`; 29 files already formatted. |
| `.venv/bin/ruff check .` | Exit `0`; all checks passed. |
| `.venv/bin/mypy app` | Exit `0`; no issues in 14 source files. |
| `.venv/bin/coverage run --branch --source=app -m pytest -q` | Exit `0`; 127 tests passed. |
| `.venv/bin/coverage report --fail-under=100` | Exit `0`; 445 statements and 100 branches, 100% statement and branch coverage. |
| `bash scripts/verify-docs.sh` | Exit `0`; 43 requirement IDs, six accepted ADRs, and nine tracks. |
| `rg -n 'metadata\.create_all|create_all\(' app tests alembic` | Exit `1` as expected; no forbidden schema-creation call. |
| `git diff --check` | Exit `0`; no whitespace errors. |

The 127-test suite includes unit, integration, and migration tests. It exercises
success, boundary, malformed configuration, redaction/serialization failure,
exception cause/context/group structure, constraint violations, cascades, rollback,
migration policy failure, lifecycle initialization failure, partial-engine cleanup,
and both re-raising and default-500 request-boundary behavior. No unconditional skip,
expected failure, external service, real sleep, or developer database is used.

## Migration lifecycle

The following commands used a unique file created under `/private/tmp` and removed
by a shell trap:

```text
APP_ENV=test DATABASE_URL=sqlite:///<disposable> .venv/bin/alembic upgrade head
APP_ENV=test DATABASE_URL=sqlite:///<disposable> .venv/bin/alembic current
APP_ENV=test DATABASE_URL=sqlite:///<disposable> .venv/bin/alembic heads
APP_ENV=test DATABASE_URL=sqlite:///<disposable> .venv/bin/alembic check
APP_ENV=test DATABASE_URL=sqlite:///<disposable> .venv/bin/alembic downgrade base
APP_ENV=test DATABASE_URL=sqlite:///<disposable> .venv/bin/alembic upgrade head
```

Actual result: every command exited `0`; current and heads reported
`0001_core_schema (head)`, autogenerate check reported
`No new upgrade operations detected.`, and re-upgrade completed. Integration tests
separately inspect exact tables, named checks, unique constraints, foreign keys,
ordered indexes, cascades, `PRAGMA foreign_keys`, busy timeout, and
`PRAGMA foreign_key_check`.

## Real-process Bash harness

| Command | Actual result |
| --- | --- |
| `bash -n scripts/verify-track-01.sh` | Exit `0`; Bash syntax valid. |
| `bash scripts/verify-track-01.sh` | Exit `0`; `Track 01 process evidence: factory bootstrap, one worker, OpenAPI, JSON lifecycle, request exception boundary`. |

The harness uses `mktemp -d`, a dynamically allocated loopback port, the documented
`make bootstrap`, a disposable Alembic-migrated database, bounded readiness polling,
and real HTTP requests. While the actual Uvicorn worker is live, a private fault seam
enabled only by `APP_ENV=test` returns a generic HTTP 500. The harness proves the
worker remains alive and emits exactly one `http.request.unexpected_exception` JSON
record with complete RuntimeError frames, the same `process_id` as lifecycle events,
and no seeded secret or submitted-content sentinel. It then proves one shutdown
lifecycle and reports `Track 01 harness cleanup: removed verified disposable
resources`.

No port, child process, database, log, response, or temporary directory remained.
The debug-preservation flag was not enabled, so no artifact location was retained.

## Review and repository hygiene

- Primary review inspected every Track 01 commit and the final branch diff against
  `main`, including migration DDL/model agreement, request middleware scope,
  lifespan failure handling, harness PID/cleanup behavior, and test assertions.
- The first focused Mason review returned changes required because a synthetic
  post-process diagnostic probe did not prove application ownership. Commit
  `53b40b8` removed it and added the live boundary proof.
- Focused re-review returned PASS: one app-level owning boundary, live Uvicorn fault
  evidence, same-process attribution, redaction, cleanup, and no Track 02 auth,
  route, or public error-envelope behavior.
- Repository scans found no `create_all()` call and no tracked database, coverage,
  virtual-environment, cache, log, or secret artifact.

## Known gaps and boundaries

- The suite emits one Starlette deprecation warning from the locked FastAPI
  `TestClient` compatibility import recommending `httpx2`. It is upstream code, not
  a failing assertion or local deprecated API, and the independent review classified
  it as a non-blocking dependency-refresh follow-up. It is not suppressed.
- The request-boundary fault seam is private, test-only behavior and must remain
  confined to process verification. Track 02 owns the public error envelope,
  validation/authentication handlers, registration, login, JWTs, and auth OpenAPI.
- WAL remains intentionally deferred. Track 01 proves mandatory foreign-key and
  finite busy-timeout behavior but makes no WAL or multi-process concurrency claim.
- This report closes only Track 01. It does not count as implementation evidence for
  Tracks 02-08.
