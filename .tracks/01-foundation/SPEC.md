# Track 01 specification: foundation, configuration, schema, and migrations

- Status: Ready
- Specification version: 1.0
- Planned: 2026-08-05
- Owner: Primary engineering thread
- Depends on: Track 00 (Complete)
- Governing ADRs: ADR-001; foundation-relevant constraints from ADR-002, ADR-003, and ADR-004
- Assessment requirements: ENV-01, ARC-01, DATA-01, DATA-02, DATA-03, DATA-04

## 1. Intent anchor

Build the smallest reproducible application and persistence foundation that later feature tracks can trust: typed configuration, an injectable UTC clock, explicit application lifecycle, synchronous SQLModel sessions, an Alembic-built constrained SQLite schema, and executable local quality commands.

Track 01 must prove database behavior rather than merely declare models. It stops before authentication and bookmark HTTP behavior.

## 2. Must-preserve behavior

- Python 3.12 is the declared project runtime even though the current shell default is Python 3.14.
- FastAPI uses a `create_app()` factory and lifespan; infrastructure must not start at module import time.
- Synchronous SQLModel sessions are short-lived and never shared between threads.
- Alembic revisions are the only schema-creation mechanism in application and test code. No code path calls `SQLModel.metadata.create_all()`, and application startup never silently migrates.
- Every application, migration, test, and later worker connection enables SQLite foreign-key enforcement.
- Database DDL carries required nullability, uniqueness, composite keys, foreign keys, deletion behavior, length checks, and indexes.
- Core table models and later API DTOs remain separate types.
- Ordinary persistence uses SQLModel ORM. Connection pragmas and migration inspection are infrastructure operations, not exceptions that permit business raw SQL.
- UTC timestamps have one explicit, round-trip-safe storage policy, and time acquisition is injectable.
- No environment secret, token, password, user content, or local database artifact is committed or logged.
- The future one-worker statistics lifecycle has an extension point but no Track 06 behavior is implemented here.

## 3. Decision latitude

Track 01 may decide without a new ADR:

- exact internal helper and test-fixture names;
- exact development database filename;
- SQLite busy-timeout value within a documented local-safe range;
- whether small SQLModel metadata import wiring lives in `app/db/models.py` or `app/db/base.py`;
- exact Make target names if one clearly documented bootstrap remains;
- exact compatible dependency versions selected from current primary documentation and locked during implementation;
- test database fixture mechanics, provided migrations and real SQLite constraints are exercised.

The primary must stop and update an ADR before changing the language/framework/ORM/database/migration stack, schema semantics, UTC policy, one-worker constraint, or ORM/raw-SQL boundary.

## 4. Scope

### Included

- `pyproject.toml`, Python pin, lockfile, and runtime/development dependency groups;
- Ruff, mypy, pytest, and coverage configuration;
- typed environment Settings for the accepted application/auth/statistics baseline, with explicit production secret and cross-field validation;
- `.env.example` containing names and safe instructions, never a usable production secret;
- standard-library structured logging foundation with service attribution and redaction-safe configuration;
- UTC-aware clock protocol/system implementation and SQLite timestamp adapter policy;
- SQLModel engine/session factory and connection hooks;
- User, Bookmark, Tag, and `bookmark_tags` table models;
- initial Alembic configuration and reviewed core-schema revision;
- FastAPI application factory and empty/no-op lifespan integration point;
- local migrate, run, bootstrap, format, lint, type-check, and test commands;
- foundation tests for settings, migration lifecycle, pragmas, constraints, indexes, timestamp round trips, and startup non-mutation.

### Excluded

- registration, login, password hashing, JWT issuance, or auth dependencies;
- bookmark DTOs, repositories, services, or routes;
- list filters, pagination, or statistics queries;
- dirty-window/projection tables, queues, caches, threads, or health policy;
- final README claims, Docker, seeding, rate limiting, or cursor pagination.

## 5. Proposed code ownership

```text
.python-version
pyproject.toml
uv.lock
.env.example
Makefile
alembic.ini
alembic/
├── env.py
├── script.py.mako
└── versions/
app/
├── __init__.py
├── main.py
├── core/
│   ├── __init__.py
│   ├── clock.py
│   ├── config.py
│   └── logging.py
├── db/
│   ├── __init__.py
│   ├── engine.py
│   ├── models.py
│   └── types.py
├── auth/
│   ├── __init__.py
│   └── models.py
└── bookmarks/
    ├── __init__.py
    └── models.py
tests/
├── conftest.py
├── integration/
│   ├── test_constraints.py
│   └── test_migrations.py
└── unit/
    ├── test_clock.py
    └── test_config.py
```

The final split may be slightly smaller if it improves clarity, but feature-owned table models must remain identifiable and Alembic must import one deterministic metadata registry.

## 6. Schema contract

### `users`

- integer primary key;
- canonical username, non-null, unique, maximum 80 characters;
- canonical email, non-null and unique; email syntax/normalization is enforced by Track 02 application validation rather than an invented assessment length;
- password hash, non-null and non-empty, sized for Argon2 output but not yet produced in this track;
- non-null UTC `created_at`;
- database checks for assessed maximum lengths rather than relying on `VARCHAR(n)` behavior.

### `bookmarks`

- integer primary key;
- non-null, non-empty URL and title; title maximum 200 characters;
- nullable description, maximum 500 characters when present;
- non-null owner foreign key to `users.id` with `ON DELETE CASCADE`, so a future explicit account deletion cannot leave private bookmarks behind;
- non-null UTC `created_at` and `updated_at`, with a check that `updated_at >= created_at`;
- indexes supporting `(user_id, created_at, id)` and `(user_id, updated_at, id)` access patterns.

URL syntax is an API validation responsibility in Track 03; required storage is enforced here.

### `tags`

- integer primary key;
- canonical lowercase name, non-null, non-empty, globally unique, maximum 50 characters;
- database check for maximum length.

Application normalization arrives with Track 03; this schema assumes the service supplies canonical values and guarantees uniqueness/length under concurrency.

### `bookmark_tags`

- non-null bookmark and tag foreign keys;
- composite primary key `(bookmark_id, tag_id)`;
- cascading association cleanup when a bookmark or tag row is deleted;
- reverse lookup index beginning with `tag_id` because the primary key already begins with `bookmark_id`.

## 7. Timestamp policy

Application-facing datetimes are timezone-aware UTC. The SQLite adapter must normalize aware input to UTC, persist a deterministic representation, and reattach/validate UTC on read so round trips never silently return a local or naive datetime.

Naive datetimes are rejected at the persistence boundary. Table columns remain non-null. Later services, not model defaults, acquire a timestamp from the injected clock so creation can assign exactly one instant to multiple fields.

## 8. Settings baseline

Track 01 establishes only cross-cutting settings needed by the foundation:

- application environment, database URL, and log level/format;
- JWT secret and access-token TTL, even though token behavior begins in Track 02;
- top-tag limit, even though the statistics endpoint begins in Track 04;
- the complete ADR-004 refresher/queue/staleness/reconciliation/dirty-threshold/worker-count baseline, even though no worker behavior starts before Track 06.

Settings tests instantiate the model directly and never depend on the developer's real environment. They cover individual ranges and relationships such as staleness/dirty/full-reconciliation thresholds not being shorter than the refresh cadence. `APP_WORKER_COUNT` must equal `1` when `STATS_REFRESH_ENABLED` is true; disabling the in-process refresher removes that specific process-local-state restriction. Production configuration rejects a missing, known-placeholder, or insufficient-strength signing secret and cannot fall back to a known development secret. Defining these values does not authorize feature behavior in this track.

## 9. Requirements

| ID | Requirement |
| --- | --- |
| T01-REQ-01 | Declare Python 3.12, use a reproducible lockfile workflow, and separate runtime from development dependencies. |
| T01-REQ-02 | Provide injectable Settings for every accepted baseline value, including token, top-tag, and ADR-004 worker settings, with range/cross-field validation and no usable production secret default. |
| T01-REQ-03 | Provide an application factory and lifespan foundation with no import-time services, schema creation, or migration side effect. |
| T01-REQ-04 | Provide synchronous engine/session factories and enable `foreign_keys=ON` on every SQLite connection; configure and test a finite busy timeout. |
| T01-REQ-05 | Model User, Bookmark, Tag, and the many-to-many link table with deterministic naming, required relationships, and deletion behavior. |
| T01-REQ-06 | Enforce non-empty required strings, uniqueness, composite keys, foreign keys, `updated_at >= created_at`, and the assessed 80/200/500/50 length limits in emitted SQLite DDL. |
| T01-REQ-07 | Create and verify indexes for owner/time list queries, updated-time queries, unique identities/tags, and reverse tag lookup. |
| T01-REQ-08 | Build the complete core schema only through a reviewed Alembic revision that upgrades an empty database and supports downgrade/re-upgrade rehearsal; `create_all()` is forbidden in app and test code. |
| T01-REQ-09 | Persist application-facing timestamps with deterministic UTC-aware round trips and reject naive values; expose an injectable clock. |
| T01-REQ-10 | Provide service-attributed logging and one documented bootstrap that migrates then starts one Uvicorn worker; application startup itself does not migrate. |
| T01-REQ-11 | Provide reproducible format, lint, type-check, test, migration, and run commands that do not require a paid or cloud service. |
| T01-REQ-12 | Prove schema and infrastructure invariants with real SQLite behavior, not only model/metadata inspection. |

## 10. Acceptance evidence threshold

Track 01 closes only when all of the following pass from the locked environment:

- a Python 3.12 environment syncs from the lockfile;
- `alembic upgrade head` builds a new file-backed SQLite database;
- downgrade to base and re-upgrade succeed on a disposable database;
- `PRAGMA foreign_keys` is `1` on separately opened application/test sessions and on Alembic's online migration connection; the Alembic path fails closed if that pragma is not enabled;
- invalid foreign keys and duplicate username/email/tag/association inserts fail;
- empty and whitespace-only required strings fail at the database boundary;
- over-limit username/title/description/tag inserts fail at the database boundary;
- a bookmark with `updated_at < created_at` fails at the database boundary;
- expected indexes and foreign-key actions appear in the migrated schema;
- `PRAGMA foreign_key_check` returns no rows, and index inspection proves exact ordered columns;
- UTC timestamps round-trip as aware UTC and naive inputs fail;
- importing/starting the app against an unmigrated disposable database does not create tables, and a repository scan finds no `create_all()` call in `app`, `tests`, or `alembic`;
- the documented bootstrap migrates then starts exactly one application worker;
- formatting, linting, type checks, and all Track 01 tests pass;
- no secret or generated database/coverage/cache artifact appears in repository status.

## 11. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Shell default is Python 3.14, not accepted Python 3.12 | Pin `.python-version`; let the documented environment tool acquire/select 3.12 before locking or testing. |
| SQLModel metadata looks correct but Alembic DDL loses checks/indexes | Manually review the generated revision and inspect a migrated database. |
| SQLite accepts values longer than `VARCHAR(n)` | Emit named `CHECK(length(...))` constraints and test real failures. |
| Foreign keys are declared but disabled per connection | Central connection hook plus independent connection tests and invalid inserts. |
| SQLite returns naive datetimes | Use one tested UTC adapter policy rather than scattered `replace(tzinfo=...)`. |
| Alembic import wiring misses a feature model | One explicit metadata-import module used by `env.py`, plus table-inventory test. |
| App startup hides migration drift | Never auto-create or auto-migrate; bootstrap runs Alembic as a distinct visible step. |
| Tool versions drift during the exercise | Resolve from primary project sources during implementation and commit the lockfile. |

## 12. Stop conditions

Stop and reframe before implementation if:

- Python 3.12 cannot run the selected compatible dependency set;
- SQLModel cannot express a required constraint without a clear SQLAlchemy construct and reviewed migration;
- timestamp round-trip behavior cannot meet the aware-UTC contract;
- a migration change would include Track 06 statistics tables or feature behavior outside this scope;
- a proposed bootstrap requires application startup to mutate schema;
- local tooling would require paid/cloud infrastructure;
- existing user changes overlap a proposed file and cannot be preserved.

## 13. Traceability

| Assessment requirement | Track 01 evidence |
| --- | --- |
| ENV-01 | T01-REQ-01, T01-REQ-11 |
| ARC-01 | T01-REQ-03, T01-REQ-10, module and bootstrap review |
| DATA-01 | T01-REQ-05, T01-REQ-08 |
| DATA-02 | T01-REQ-06, T01-REQ-07, T01-REQ-12 |
| DATA-03 | T01-REQ-05 and association constraint tests |
| DATA-04 | T01-REQ-04 and real per-connection enforcement tests |
