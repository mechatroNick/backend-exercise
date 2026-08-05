# Track 01 plan: foundation, configuration, schema, and migrations

- Specification: [SPEC.md](SPEC.md), version 1.1
- Governing ADRs: ADR-001; foundation-relevant constraints from ADR-002, ADR-003, and ADR-004; ADR-006 verification and closure evidence
- Status: Complete
- Active item: None; Track 01 closed with passing deterministic, migration, coverage,
  and real-process evidence recorded in `TEST-REPORT.md`

## Execution plan

| ID | Work item | Owner | Depends on | Status | Exit evidence |
| --- | --- | --- | --- | --- | --- |
| T01-01 | Establish the Python 3.12 project and locked toolchain. | Smith / implementation | None | Complete | `.python-version`, `pyproject.toml`, lockfile, dependency groups, Ruff/mypy/pytest configuration, and clean environment sync. |
| T01-02 | Implement typed configuration, UTC clock, and structured JSON Lines logging foundations. | Smith / implementation | T01-01 | Complete | Settings safety/cross-environment tests; aware UTC clock tests; JSON-Line schema tests for `source`, service/component, event, level, UTC timestamp, logger, `process_id`, and execution/thread identifier where applicable; redaction; and exactly-one owning-boundary exception-record tests. |
| T01-03 | Implement feature-owned core SQLModel tables and UTC persistence type. | Smith / implementation | T01-01, T01-02 | Complete | Metadata review shows the four required tables, relationships, named constraints, and indexes; unit tests cover the UTC adapter. |
| T01-04 | Implement the synchronous engine/session boundary and SQLite connection policy. | Smith / implementation | T01-01, T01-02 | Complete | Separate connections report FK enforcement and finite busy timeout; sessions are short-lived and injectable. |
| T01-05 | Configure Alembic and author the reviewed core-schema revision. | Smith / implementation | T01-03, T01-04 | Complete | Empty upgrade, schema inspection, downgrade-to-base, and re-upgrade pass on disposable file databases. |
| T01-06 | Implement the FastAPI factory/lifespan foundation, local operator commands, and Track 01 process harness. | Smith / implementation | T01-02, T01-04, T01-05 | Complete | Import/startup has no schema side effect; migrate/run/bootstrap/check commands are documented; one-worker startup is explicit; and `scripts/verify-track-01.sh` uses the actual factory/bootstrap with a disposable migrated SQLite DB, dynamic isolated port, bounded observable-endpoint polling, startup/shutdown JSON-Line field/redaction/exactly-one-owning-boundary-exception assertions, and verified cleanup. |
| T01-07 | Add real-database constraint/index/cascade integration tests. | Smith / implementation | T01-03, T01-05 | Complete | Required, unique, length, FK, association, deletion, index, and UTC round-trip evidence passes. |
| T01-08 | Run the complete foundation closure gate and review the diff. | Primary engineering thread | T01-01, T01-02, T01-03, T01-04, T01-05, T01-06, T01-07 | Complete | Deterministic unit/integration tests, format, lint, mypy, migration rehearsal, and `bash scripts/verify-track-01.sh` actually pass; TEST-REPORT records exact commands/results/versions/selectors/cleanup, guideline conformance, gaps, and primary diff/repository-hygiene review. |

## Work-wave detail

### T01-01 — Toolchain

- Select compatible current versions from primary project documentation at implementation time.
- Use the installed `uv` workflow for environment/lock management, pin Python 3.12, and do not rely on the ambient `PATH`: current evidence resolves `python3` to `/usr/bin/python3` 3.9.6 while Homebrew's unversioned Python is 3.14.2; 3.13.5 and 3.14.2 are installed, and no accepted 3.12 runtime is presently evidenced.
- Add only foundation runtime dependencies initially: FastAPI, Uvicorn, SQLModel, Alembic, and Pydantic Settings. Add auth/statistics/contract packages in their owning tracks.
- Add pytest/httpx/coverage, Ruff, and mypy as development dependencies.
- Preserve the existing `.gitignore`; make only narrow additions proven necessary by generated artifacts.

### T01-02 — Cross-cutting core

- Make Settings construction explicit and injectable; avoid an import-time global that reads the real environment during tests.
- Validate the SQLite database scheme; missing/placeholder/insufficient production secrets; individual accepted setting ranges; and ADR-004 timing relationships. Require `APP_WORKER_COUNT == 1` only while `STATS_REFRESH_ENABLED` is true. Permit configurable log level only: ADR-006 fixes the application format/schema as JSON Lines and forbids a plaintext runtime toggle.
- Implement `Clock` and `SystemClock`; tests use a fixed/fake clock later without sleep.
- Configure one standard-library JSON Lines schema/formatter with stable `source`, service/component, event, level, UTC timestamp, logger, `process_id`, and execution/thread identifier where applicable; prove redaction of seeded secrets/content and exactly one structured unexpected-exception record at the owning boundary. Detailed refresher fields and events remain Track 06 under ADR-004.

### T01-03/T01-04 — Persistence model and connections

- Use feature-owned `User`, `Bookmark`, `Tag`, and link models with an explicit metadata import registry for Alembic.
- Use named checks and indexes so migration diffs and failing tests are intelligible.
- Enforce non-empty required strings and `updated_at >= created_at`; defer any title-search index until Track 04 has a query plan that justifies it.
- Put commit/rollback ownership outside repositories; Track 01 exposes session context/dependency infrastructure only.
- Apply SQLite pragmas through one connection hook shared by application and Alembic configuration. Make Alembic's online path verify `foreign_keys=1` and fail before migration if the invariant is absent.
- Enable WAL conditionally for supported file-backed SQLite databases, never for in-memory databases. If focused tests expose migration/locking instability, explicitly defer WAL while retaining mandatory FK and busy-timeout behavior; do not claim unsupported concurrency properties.

### T01-05 — Migration

- Generate once, then manually edit/review the revision; autogeneration is a starting point, not evidence.
- Keep only the four core tables in the initial revision.
- Ensure downgrade order respects foreign keys.
- Inspect table, column, constraint, foreign-key, and index inventory after upgrade.

### T01-06 — Lifecycle and commands

- `create_app(settings: Settings | None = None)` owns app construction and a no-op/extensible lifespan; tests inject Settings and the Uvicorn factory call resolves them only when invoked.
- Invoke Uvicorn as `app.main:create_app --factory`; do not expose a module-level instantiated app. Importing the module must not read the environment, create an engine, migrate, or start a service.
- Provide a bootstrap target that visibly runs Alembic then starts Uvicorn with one worker; provide separate migrate and run targets for development/debugging.
- No Track 06 thread is started yet.
- Deliver `scripts/verify-track-01.sh` using that actual documented factory/bootstrap, never a fake server. It must create only a verified disposable migrated SQLite DB and dynamic isolated port; bounded-poll a delivered observable endpoint (OpenAPI/docs or another delivered readiness seam); make real HTTP assertions; capture startup/shutdown JSON Lines; verify `source`, service/component, event, level, UTC timestamp, logger, `process_id`, and execution/thread identifier where applicable, seeded-redaction absence, and exactly one owning-boundary unexpected-exception record; and trap child/resource cleanup. Preserve diagnostics only behind an explicit debug flag.

### T01-07/T01-08 — Evidence and closure

- Use disposable file-backed SQLite databases where connection and migration behavior matters.
- Prohibit `SQLModel.metadata.create_all()` throughout application and test code. Every database-backed test fixture uses the real Alembic revision; pure unit tests do not create a database schema.
- Require empty/whitespace required-string failures, inverted timestamp failure, `PRAGMA foreign_key_check`, exact ordered indexes, and migration-connection FK enforcement in addition to ordinary uniqueness/FK/length cases.
- Record exact command output summaries and known gaps in Track 01 TEST-REPORT/HISTORY.

## Shared completion gate

The [engineering verification guideline](../../docs/ENGINEERING-VERIFICATION-GUIDELINE.md)
and [ADR-006](../ADR/ADR-006-engineering-verification-and-closure-evidence.md) apply
to Track 01 without changing its product contract. A Pending or Ready item is not
done. T01-08 can mark the track Complete only after recorded passing deterministic
tests, real migrated-database evidence, and the real-process harness receipt; planned
or blocked commands do not count as pass.

## Planned validation commands

Exact command spelling will be finalized with the toolchain, but the closure interface should be equivalent to:

```text
uv sync --locked
uv run python --version
uv lock --check
uv run ruff format --check .
uv run ruff check .
uv run mypy app
uv run pytest
uv run alembic upgrade head
uv run alembic current
uv run alembic heads
uv run alembic check
uv run alembic downgrade base
uv run alembic upgrade head
make check
bash scripts/verify-track-01.sh
rg -n 'metadata\.create_all|create_all\(' app tests alembic
```

Migration rehearsal must target an explicit disposable database rather than the developer's normal database. The test/report records the resolved path and confirms it was not a broad or user-data location. The final `rg` is expected to return no matches.

## Review checkpoints

1. After T01-01: dependency/tool configuration review before writing application code.
2. After T01-03: schema/constraint/index review before generating the migration.
3. After T01-05: emitted DDL and migration lifecycle review before app bootstrap.
4. After T01-07: test adequacy and failure-mode review.
5. At T01-08: primary full diff and clean-environment closure review.

## Commit boundary

Preferred single-track commit after the closure gate:

`build: establish application foundation and constrained schema`

If reviewability benefits from two commits, split only at a green boundary:

1. `build: establish Python application foundation`
2. `feat: add constrained core schema and migrations`

Do not commit generated databases, secrets, caches, or a failing intermediate state.
