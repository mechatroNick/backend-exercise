# Bookmarks API

Local, authenticated bookmark management service built for the supplied backend assessment. It provides registration and login, owner-scoped bookmark CRUD, search, current statistics, health checks, and selected local delivery extensions: deterministic development seeding, a one-worker Docker image, local rate limiting, and cursor pagination.

This is a modular monolith: FastAPI routers map HTTP to application services; repositories own SQLite/SQLModel access; Alembic owns schema changes; a bounded in-process publisher/refresher maintains optional current-statistics snapshots. Canonical raw SQL remains the correctness fallback for current statistics. Weekly projection/history work was deliberately skipped in Track 07 and is not delivered.

## Prerequisites and setup

Use Python **3.12**, [uv](https://docs.astral.sh/uv/), and Git. Docker is needed only for the container workflow below. The project is pinned to Python `>=3.12,<3.13` and has a committed `uv.lock`.

```sh
git clone <repository-url>
cd backend-sample
uv sync --locked
```

`.env.example` is a **comment-only reference**; it is not loaded automatically. Set configuration as process environment variables (or through your deployment’s secret/configuration mechanism) before running a command. Do not commit a `.env` file or usable secret.

The defaults support local development: `APP_ENV=development`, `DATABASE_URL=sqlite:///./bookmarks.db`, and a development-only JWT secret. Production must set `APP_ENV=production`, a unique non-placeholder `JWT_SECRET` of at least 32 characters, and cannot disable rate limiting. `DATABASE_URL` must be a local SQLite URL beginning `sqlite:///`.

All configuration names, ranges, and defaults are listed in [.env.example](.env.example). Cross-field constraints matter: stale, reconciliation, and dirty-marker ages cannot be lower than the refresh interval; the rate-limit idle TTL cannot be lower than either rate-limit window; and `APP_WORKER_COUNT` must be `1` while statistics refresh or rate limiting is enabled. The delivered runtime is intentionally one worker.

## Migrate, run, and seed

`make migrate` upgrades an already chosen database and exits. `make run` starts only the API, assuming its schema is already migrated. `make bootstrap` first upgrades the database, then starts the API; it is the usual local command.

```sh
make migrate
make run
# or, for a fresh local database:
make bootstrap
```

The API listens on `127.0.0.1:8000` by default. Override `HOST` and `PORT` as Make variables when needed. Browse `/docs`, inspect `/openapi.json`, and use `/health/live` and `/health/ready` for local checks.

Seed only a disposable, explicitly named non-production SQLite database after migration:

```sh
DATABASE_URL=sqlite:////absolute/path/bookmarks-dev.sqlite3 \
  APP_ENV=development uv run python -m app.seed
```

The seed command rejects a missing/blank target, production, and a schema not at this checkout’s Alembic head. It never creates a schema, deletes rows, or mutates an existing seed record. A second identical run is idempotent; it reports existing fixed records. If an existing user or bookmark occupies a seed identity but differs from the fixed fixture, it rejects the run and rolls back. The fixture account is fictional: `fictional-reader` / `fictional-reader@example.test`, with password `fictional-seed-password-only`; use it only for local development and never deploy it as a real credential.

## API

All `/api/bookmarks` operations require `Authorization: Bearer <access token>` obtained from login. The 10 documented operations are:

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/auth/register` | Register a user. |
| POST | `/api/auth/login` | Return an access token. |
| POST | `/api/bookmarks` | Create an owned bookmark. |
| GET | `/api/bookmarks` | List/search owned bookmarks. |
| GET | `/api/bookmarks/stats` | Return current, owner-scoped statistics. |
| GET | `/api/bookmarks/{bookmark_id}` | Read one owned bookmark. |
| PATCH | `/api/bookmarks/{bookmark_id}` | Update one owned bookmark. |
| DELETE | `/api/bookmarks/{bookmark_id}` | Delete one owned bookmark (204, no body). |
| GET | `/health/live` | Local process liveness. |
| GET | `/health/ready` | Database/internal-service readiness. |

List filters are `tag` (normalized exact tag), `q` (case-insensitive title substring), `from`/`to` (created date), and `updated_from`/`updated_to` (updated date). Dates are inclusive UTC calendar dates. Page mode is the default and returns `items`, `total`, `page`, and `page_size`; use `page` and `page_size` (default 20, maximum 100).

For keyset traversal, use `pagination=cursor` and omit an explicitly supplied `page`. Supply the opaque response `X-Next-Cursor` value as `cursor` on the next request; a response omits that header when there is no next page. Cursor mode retains the same body fields and uses its signed logical page ordinal. Do not edit, share, reuse across users, or combine a cursor with changed filters. Page mode rejects `cursor`; cursor mode rejects an explicit `page`; invalid, expired, tampered, cross-user, or filter-mismatched cursors all use the fixed 422 `invalid_cursor` error.

Current statistics contain `total_bookmarks`, `total_tags`, deterministic `top_tags`, and chronological `bookmarks_per_month`. When a fresh snapshot is safely available, `X-Stats-Source: snapshot` identifies it; otherwise the service computes canonical current values through raw SQL and returns `X-Stats-Source: live`. There is no weekly history API.

Expected API failures use a stable `error` envelope. Missing/invalid bearer tokens produce 401; an owned-resource miss or another user’s resource produces the same 404; validation failures produce 422; duplicate identities produce 409. Public register/login and all six bookmark operations are locally rate-limited. A rejection is HTTP 429 with `error.code` `rate_limited`, a positive integer `Retry-After`, and `Cache-Control: no-store`. The limiter is process-local, keyed by socket peer IP for auth and authenticated user for bookmarks; it is not a distributed production control.

## Docker

Docker is an optional local delivery path. Build from the repository root, use a Docker-managed named volume for the explicit `/data` database location, and provide runtime variables directly:

```sh
docker build -t bookmarks-api:local .
docker volume create bookmarks-api-data
docker run --rm -p 8000:8000 \
  -v bookmarks-api-data:/data \
  -e APP_ENV=development \
  -e DATABASE_URL=sqlite:////data/bookmarks.sqlite3 \
  -e JWT_SECRET='replace-with-a-local-development-secret' \
  bookmarks-api:local
```

The normal entrypoint runs Alembic migration before Uvicorn. To migrate and exit instead, append `migrate-only`:

```sh
docker run --rm -v bookmarks-api-data:/data \
  -e DATABASE_URL=sqlite:////data/bookmarks.sqlite3 \
  bookmarks-api:local migrate-only
```

Remove the named volume only when its local SQLite data is no longer needed:

```sh
docker volume rm bookmarks-api-data
```

The image runs as a non-root `app` user, exposes 8000, declares `/data` as its volume, health-checks `/health/live`, uses one Uvicorn worker, and uses an exec-form entrypoint with `SIGTERM` configured. Static Docker contract tests are present, but the first durable build/run receipt from the final clean-clone harness is still pending.

## Verify

```sh
uv run ruff format --check .
uv run ruff check .
uv run mypy app
uv run pytest tests/integration/test_seed.py tests/integration/test_rate_limit_routes.py tests/integration/test_cursor_pagination.py tests/contract/test_docker_delivery.py
uv run pytest
uv run coverage run --branch -m pytest -q && uv run coverage report --fail-under=100
uv run pip-audit --local --progress-spinner off --desc off
make check
bash scripts/verify-docs.sh
```

`pip-audit` queries the known PyPA/PyPI advisory data for the installed locked
dependencies. The local `bookmarks-api` distribution is the sole expected
unauditable skip because it is not published to that advisory source. A current
dependency-metadata license inventory finds only that same local distribution with
unknown license metadata; it needs repository-owner review and is not presented as
an assessment failure.

An uncommitted local development receipt at `cee847f` observed a full suite of 719 tests and 2,958 statements / 630 branches at 100% coverage, plus a passing Track 06 harness after the cursor correction. The static OpenAPI development inventory is OpenAPI 3.1.0 with 10 operations and 45 status pairs. These observations are non-durable and are not a substitute for the pending combined clean-clone Track 08 harness and final report; see [Track 08 evidence](.tracks/08-final-handoff/EVIDENCE-MATRIX.md).

## Security, limits, and evolution

Passwords use Argon2; access tokens are HS256 JWTs; secrets are not logged; protected resources are query-scoped by owner; SQLite foreign keys are enabled; expected failures have redacted stable envelopes; application logs are JSON Lines with redaction and bounded exception evidence. Local SQLite, a process-local queue/cache/limiter, and one worker are intentional assessment constraints, not a production topology.

For production evolution, move SQLite to a managed relational database, use a shared atomic rate-limit store with an explicit trusted-proxy policy, replace in-process events with a transactional outbox and durable worker/broker, provide multi-process coordination, externalize secret management and observability, and load-test/back up/operate the system. These are future directions only; this repository does not implement them.

## Reader and handoff material

- [Walkthrough](docs/WALKTHROUGH.md) — safe local demonstration steps.
- [Solution design](docs/SOLUTION-DESIGN.md) — architecture and contract rationale.
- [AI-assisted work disclosure](docs/AI-ASSISTED-WORK.md) — evidence-bounded provenance statement.
- [Release handoff](docs/RELEASE-HANDOFF.md) — implemented state, pending final evidence, and owner-only actions.
- [Documentation index](docs/README.md) and [Track index](.tracks/README.md) — decisions and execution records.

Track 07 weekly projections were owner-skipped. Track 08 is in progress: it does not yet have a final clean-clone receipt or final `TEST-REPORT.md`. Only the repository owner may choose a final ref, push, archive, share, deploy, or submit the work.
