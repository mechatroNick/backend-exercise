# Local reviewer walkthrough

This walkthrough demonstrates the delivered local service without retaining credentials, tokens, or protected response bodies. The final Track 08 clean-source harness passed separately; this walkthrough remains a reader guide rather than a substitute for that receipt.

## 1. Prepare a disposable database

```sh
uv sync --locked
DATABASE_URL=sqlite:////absolute/path/bookmarks-walkthrough.sqlite3 make migrate
DATABASE_URL=sqlite:////absolute/path/bookmarks-walkthrough.sqlite3 \
  APP_ENV=development make bootstrap
```

Expected safe outcome: Alembic upgrades the explicitly selected SQLite database, then a one-worker server listens on `127.0.0.1:8000`. In another terminal, `curl -i http://127.0.0.1:8000/health/live` returns 200; `/health/ready` returns 200 only after required startup work is ready. Stop the server with `SIGTERM`/Ctrl-C and remove the disposable database afterward.

## 2. Inspect public contracts

Open `http://127.0.0.1:8000/docs` or request `/openapi.json`. The OpenAPI inventory is 3.1.0 with 10 operations and 45 documented status pairs; the final clean-source runtime verification passed these selectors.

## 3. Register, log in, and exercise protected routes

Use a unique disposable email, username, and a password meeting the API’s validation rules. Register, log in, then keep the returned JWT only in the invoking shell/process. Use it as `Authorization: Bearer <token>` to create a bookmark, list it, fetch `/api/bookmarks/stats`, update it, and delete it. Do not paste JWTs or protected bodies into shell history, documentation, commits, or evidence files.

Expected safe outcomes: protected bookmark operations return their documented success body/status; another account receives the same 404 for this bookmark as for a missing ID; deletion is a bodyless 204; stats returns current user-scoped totals and `X-Stats-Source: live` or `snapshot`.

## 4. Demonstrate filters and pagination

Create enough disposable bookmarks to obtain more than one page. Check `tag`, `q`, `from`, `to`, `updated_from`, and `updated_to` separately and in combination. In default page mode, request `page=1&page_size=20` then a later page. For cursor mode, request `pagination=cursor&page_size=<n>`, read `X-Next-Cursor`, and provide it unchanged as `cursor` on the next request. Do not send `page` with cursor mode or `cursor` with page mode.

Expected safe outcomes: page mode keeps the legacy body; cursor mode keeps that body and advertises only a next page via `X-Next-Cursor`; no header means traversal is complete. Altered/expired/foreign/filter-mismatched cursors all return the same 422 `invalid_cursor` response.

## 5. Demonstrate rate limiting deterministically

Do not use a busy loop or rely on elapsed waiting. Start an isolated app instance with a small explicit local window, for example `RATE_LIMIT_AUTH_REQUESTS=1`, `RATE_LIMIT_AUTH_WINDOW_SECONDS=60`, and a fresh process. Make two login attempts from the same local peer. Inspect only status, `Retry-After`, `Cache-Control`, and the error code; keep credentials and response bodies ephemeral.

Expected safe outcome: the second request is 429 with `rate_limited`, a positive integer `Retry-After`, and `Cache-Control: no-store`. The deterministic unit/integration tests use injected monotonic time for refill boundaries; this manual demo is only a visible contract check.

## 6. Demonstrate safe seed behavior

After migration, run the documented `app.seed` command against a fresh, explicit non-production SQLite path twice. The first run creates only the fixed fictional fixture; the second is idempotent. A mismatching existing seed identity is rejected rather than overwritten. The command rejects production, missing target, and non-head schema states.

## 7. Optional container check

Follow the Docker commands in the root README. Verify `/health/live`; test `migrate-only` separately. The final clean-source Docker validation passed the one-worker/non-root/volume/entrypoint, health, JSON Lines lifecycle, SIGTERM, removal, and cleanup checks.

## 8. Run evidence available today

Run focused local tests for seed, Docker, rate limiting, and cursor pagination, then `uv run pytest`, coverage, and `bash scripts/verify-docs.sh`. The passing final clean-source evidence is recorded in the Track 08 matrix and final report.
