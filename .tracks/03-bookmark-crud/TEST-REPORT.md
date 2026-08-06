# Track 03 test report

- Status: Passed
- Date: 2026-08-06
- Branch: `codex/track-03-bookmark-crud`
- Scope: Protected bookmark CRUD, canonical tags, ownership isolation, transaction
  atomicity, material timestamps, inert post-commit seam, bounded OpenAPI, and process
  verification

## Acceptance matrix

| Requirement | Executable evidence | Result |
| --- | --- | --- |
| T03-REQ-01 | Strict create/PATCH/public/tag/list DTO and normalization/materiality matrices | Pass |
| T03-REQ-02 | Protected create/list/detail/PATCH/delete endpoint statuses, envelopes, positive IDs, and bodyless `204` | Pass |
| T03-REQ-03 | Owner-predicate repository instrumentation and response-identical missing/cross-user tests | Pass |
| T03-REQ-04 | Canonicalization/reuse/orphan tests, deterministic native SQLite unique-conflict recovery, and concurrent final-state proof | Pass |
| T03-REQ-05 | Repository-no-commit checks plus service commit/rollback/fault-order matrices | Pass |
| T03-REQ-06 | Fixed-clock creation equality, immutable creation time, material advancement, and no-op/failure invariance | Pass |
| T03-REQ-07 | Zero-argument no-op publisher, post-commit ordering, inert composition, and downstream-negative scans | Pass |
| T03-REQ-08 | Fixed baseline list body/order/first-20 behavior without public filters, page inputs, or performance claims | Pass |
| T03-REQ-09 | Focused/full tests, 100% branch coverage, operation-schema validation, live harness, redaction, and hygiene | Pass |

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
| FastAPI | 0.139.2 |
| pwdlib | 0.3.0 |
| PyJWT | 2.13.0 |
| jsonschema | 4.26.0 |

The checked `uv.lock` and Python 3.12 constraint remain authoritative. Tests use only
disposable migrated SQLite databases, injected clocks where exact time is asserted,
and local loopback processes; no external service, developer database, live
credential, or unbounded wall-clock wait participates.

## Incremental implementation receipts

| Commit | Stabilized boundary |
| --- | --- |
| `25ea39e` | Opened Track 03 after the verified Track 02 merge and compatibility gate. |
| `aec76d1` | Added strict bookmark DTOs and canonical materiality policies. |
| `c4c9e98` | Added explicit owner-scoped bookmark/tag repositories. |
| `d43327f` | Added transactional CRUD services and the inert publisher seam. |
| `1150ffb` | Added protected HTTP composition, endpoint tests, and bounded OpenAPI proof. |
| `6642fb1` | Added the real-process Track 03 harness. |
| `f19fb60` | Preserved the inherited Track 02 harness's exact route inventory after bookmark routes. |
| `b30f2ba` | Replaced an overclaimed race receipt with deterministic native SQLite recovery evidence. |

Every wave passed focused tests and primary inspection before its commit. This report
and the status updates form the final documentation-only commit on the track branch.

## Deterministic and static validation

| Command | Actual result |
| --- | --- |
| `uv lock --check` | Exit `0`; 56 packages resolved and lockfile current. |
| `uv sync --locked` | Exit `0`; 54 packages audited from the lockfile. |
| `.venv/bin/ruff format --check .` | Exit `0`; all 63 files formatted. |
| `.venv/bin/ruff check .` | Exit `0`; all checks passed. |
| `.venv/bin/mypy app` | Exit `0`; no issues in 32 source files. |
| Focused Track 03 selector below | Exit `0`; 112 tests passed, one upstream warning. |
| `.venv/bin/coverage run --branch -m pytest -q` | Exit `0`; 348 tests passed, one upstream warning. |
| `.venv/bin/coverage report --show-missing --fail-under=100` | Exit `0`; 1,282 statements and 234 branches, no misses or partial branches, 100%. |
| `bash scripts/verify-docs.sh` | Exit `0`; 43 requirement IDs, six accepted ADRs, and nine tracks. |
| `git diff --check` and `git diff main...HEAD --check` | Exit `0`; no whitespace errors. |

The exact focused selector was:

```text
.venv/bin/pytest -q -p no:cacheprovider \
  tests/unit/test_bookmark_events.py \
  tests/unit/test_bookmark_policy.py \
  tests/unit/test_bookmark_schemas.py \
  tests/unit/test_bookmark_service.py \
  tests/integration/test_bookmark_repository.py \
  tests/integration/test_bookmark_routes.py \
  tests/integration/test_bookmark_service.py
```

The ledger covers strict and malformed inputs; userinfo/URL/tag boundaries; omitted,
null, scalar, tag-only, mixed, equivalent, and reordered patches; duplicate URLs;
detached DTOs; deterministic ordering; missing/cross-user outcomes; every service
mutation and commit failure point; publisher-after-commit failure; tag savepoints;
concurrent final state; unrelated integrity errors; route schemas; and disclosure.

## Native SQLite conflict evidence

Mason's initial review returned **CHANGES REQUIRED** because the original two-thread
test proved only one final tag and two links; thread scheduling could let the second
request observe the first committed tag without entering recovery. That test was
renamed to state its actual final-state guarantee.

The replacement migrated-SQLite test uses a bounded test repository/connection seam
after a real absent lookup. It inserts the canonical winner on the real outer
connection, then observes the service's candidate `INSERT` inside its real savepoint
fail with DB-API `sqlite3.IntegrityError`, error code
`SQLITE_CONSTRAINT_UNIQUE`, and exact message
`UNIQUE constraint failed: tags.name`. SQL instrumentation proves winner insert,
`SAVEPOINT`, candidate insert, and `ROLLBACK TO SAVEPOINT` ordering. The service then
reloads the winner, commits once without outer rollback, publishes once, and leaves
exactly one bookmark, tag, and association. The focused proof passed 20 consecutive
runs. A second real SQLite CHECK-constraint test proves unrelated integrity errors
propagate and leave no partial state.

This deterministic seam uses one connection because the service has already flushed
the bookmark and holds SQLite's single-writer lock before tag lookup; it does not
claim two independent SQLite writers can reach that exact ordering. The retained
two-session test separately proves concurrent callers complete with one canonical
tag and two links. Mason's focused re-review returned **PASS**.

## Migration lifecycle

Against one validated task-prefixed file under `/private/tmp`, the primary ran:

```text
DATABASE_URL=sqlite:///<disposable> .venv/bin/alembic upgrade head
DATABASE_URL=sqlite:///<disposable> .venv/bin/alembic check
DATABASE_URL=sqlite:///<disposable> .venv/bin/alembic downgrade base
DATABASE_URL=sqlite:///<disposable> .venv/bin/alembic upgrade head
```

Every final command exited `0`; Alembic reported no new upgrade operations. SQLite
inspection found the single `0001_core_schema` head and required `users`, `bookmarks`,
`tags`, and `bookmark_tags` tables. The exact file was removed. Track 03 added no
migration and all test schemas continue to be Alembic-owned.

## Bookmark-operation OpenAPI proof

Endpoint tests and the live harness validate actual Track 03 bodies through the
generated schemas using `referencing.Registry` and `Draft202012Validator`. The exact
bookmark operations advertise:

- create: `201`, `401`, `422`, `500`;
- collection list: `200`, `401`, `500`;
- detail GET/PATCH: `200`, `401`, `404`, `422`, `500`;
- detail DELETE: `204`, `401`, `404`, `422`, `500`.

All operations require `BearerAuth`; success DTOs exclude `user_id`; representative
authentication, concealment, validation, and unexpected envelopes validate; and the
`204` response has no content schema or runtime body. This is bounded Track 03
operation evidence only. Track 05 retains exhaustive API-wide conformance ownership.

## Real-process Bash harnesses

| Command | Actual result |
| --- | --- |
| `bash -n scripts/verify-track-03.sh` | Exit `0`; Bash syntax valid. |
| `bash scripts/verify-track-03.sh` | Exit `0`; real CRUD/isolation/tag/timestamp/bodyless-delete/OpenAPI/redaction receipt passed. |
| `bash scripts/verify-track-01.sh` | Exit `0`; inherited factory/lifecycle/error-boundary receipt passed. |
| `bash scripts/verify-track-02.sh` | Exit `0`; inherited auth/protected/redaction receipt passed after its exact manifest gained the two bookmark paths. |

Track 03's harness uses `make bootstrap`, a generated JWT secret, a protected
task-prefixed temporary directory, disposable Alembic SQLite, dynamic loopback port,
bounded readiness, two real registered/logged-in users, and protected curl configs.
It proves create/list/detail/material and no-op PATCH/delete, duplicate URL, canonical
tags, two-user isolation, identical concealed `404`, positive-ID `422`, bodyless
`204`, operation schemas, and process survival after the inherited injected fault.

Captured JSON Lines contain the required absolute source location and line, service,
component, event, level, UTC timestamp, logger, process/thread IDs, one lifecycle
sequence, one owning unexpected exception, safe UUID correlation, complete redacted
frames, and no indexed raw exception text. Raw output and parsed JSONL are scanned for
both users' registration/login tokens, JWT secret, identities, password, submitted
URL/title/description/tags, authorization terms, hash internals, and database URL.
The guarded trap terminates and waits for the child, then removes every request,
response, credential, curl-config, database, output, and log artifact even on failure.

ShellCheck was not installed and therefore was not claimed. Bash syntax, two
independent successful runs, source-scan error handling, process cleanup, and diff
checks supply the recorded shell evidence.

## Independent review and repository hygiene

- Mason Medium reviewed the full `main...HEAD` delta, Track 03 contracts, upstream
  seams, deterministic tests, full coverage, migrations, OpenAPI, and all harnesses.
  DTO, ownership, transaction, timestamp, publisher, HTTP, cleanup, redaction, and
  downstream-scope review found no product defect.
- Its initial blocker concerned only inadequate proof that native tag-conflict
  recovery executed. Closure stopped, a Smith High test-only correction supplied
  real driver/savepoint evidence, and Mason's second review passed it.
- Bounded scans found no application/test `metadata.create_all`, queue, refresher,
  dirty marker, statistics snapshot, weekly projection, or Track 03 `/stats` route.
- Hygiene scans found no tracked SQLite database, coverage data, virtual environment,
  cache, JSON-Line/log, credential, private-key, or token artifact. Status contained
  only the intended closure documents before their commit.

## Known gaps and retained boundaries

- The suite emits one Starlette deprecation warning from locked FastAPI's TestClient
  compatibility import recommending `httpx2`. It is upstream, unsuppressed, and
  non-blocking; three real-process harnesses independently exercise HTTP behavior.
- SQLite and one application worker remain the accepted scope. The deterministic
  collision proof is explicit about the single-writer boundary and makes no claim
  about a separately committing writer after the bookmark write lock is held.
- Public filtering/date/page parameters, SQL totals, query counts/N+1, query plans,
  and canonical current statistics remain Track 04 work.
- API-wide OpenAPI conformance remains Track 05 work. Concrete events, queue/backlog,
  dirty recovery, stats worker/lifecycle/health/snapshots, and failure policy remain
  Track 06 work; weekly projections/history remain Track 07 work.
