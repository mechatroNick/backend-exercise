# Track 04 test report

- Status: Passed
- Date: 2026-08-06
- Branch: `codex/track-04-search-stats`
- Scope: Owner-scoped ORM search, date filters, SQL pagination and totals, literal
  substring semantics, canonical live raw-SQL statistics, consistent SQLite read
  snapshots, protected HTTP/OpenAPI contracts, query plans, and process verification

## Acceptance matrix

| Requirement | Executable evidence | Result |
| --- | --- | --- |
| T04-REQ-01 | Strict query DTO, aliases, canonical/open/reversed dates, UTC bounds, literal metacharacters, and pagination matrices | Pass |
| T04-REQ-02 | Shared owner predicates, correlated tag `EXISTS`, SQL count/page, stable order, four-statement bound, WAL generation proof, and populated plans | Pass |
| T04-REQ-03 | Exact empty/populated/tie/month/mutation/cross-user current-statistics DTO and HTTP bodies | Pass |
| T04-REQ-04 | Exactly three immutable named bound owner-scoped `TextClause`s in one real SQLite snapshot, with no interpolation | Pass |
| T04-REQ-05 | Exact list/stats OpenAPI, runtime schema validation, one-connection auth ordering, query counts/plans, 100% coverage, and real-process harness | Pass |

## Incremental implementation receipts

| Commit | Stabilized boundary |
| --- | --- |
| `a39fbcb` | Opened Track 04 from the verified Track 03 merge and compatibility gate. |
| `2477e3d` | Added strict query/date/pagination policy and immutable stats contracts. |
| `b432d96` | Added the explicit real SQLite read-snapshot seam and WAL proof. |
| `c97fd03` | Added owner-scoped ORM search, SQL totals/pages, and bounded tag loading. |
| `24f5638` | Added the isolated canonical live raw-SQL statistics reader. |
| `2e1a354` | Added concurrent search generation and expanded edge-boundary evidence. |
| `20df6b8` | Added protected list/stats transport, exact OpenAPI, and shared-connection proof. |
| `6fc1f15` | Added populated query-plan and raw-SQL boundary evidence. |
| `6872507` | Added the hardened Track 04 real-process Bash harness. |
| `614b136` | Preserved the inherited Track 02 exact route manifest after `/stats`. |

Every wave was inspected and passed its focused validation before commit. This report
and the status changes form the final documentation-only checkpoint.

## Deterministic, coverage, and static validation

| Command | Actual result |
| --- | --- |
| `uv lock --check` | Exit `0`; 56 packages resolved and the lockfile is current. |
| `uv sync --locked` | Exit `0`; 54 packages audited from the lockfile. |
| `.venv/bin/ruff format --check .` | Exit `0`; all 73 files formatted. |
| `.venv/bin/ruff check .` | Exit `0`; all checks passed. |
| `.venv/bin/mypy app` | Exit `0`; no issues in 35 source files. |
| Mason's focused Track 04 selector | Exit `0`; 131 tests passed, one upstream warning. |
| `.venv/bin/pytest -q` | Exit `0`; 427 tests passed, one upstream warning. |
| `.venv/bin/coverage run --branch --source=app -m pytest -q` | Exit `0`; 427 tests passed. |
| `.venv/bin/coverage report --show-missing` | Exit `0`; 1,492 statements and 292 branches, no misses or partial branches, 100%. |
| `bash scripts/verify-docs.sh` | Exit `0`; 43 requirement IDs, six accepted ADRs, and nine tracks. |
| `git diff --check` and `git diff main...HEAD --check` | Exit `0`; no whitespace errors. |

Mason's focused selector covered query/policy/stats/engine units and search, read-
snapshot, stats-reader, route, and query-plan integrations. The full suite remains the
authoritative combined receipt. The single warning is the locked FastAPI/Starlette
`TestClient` compatibility deprecation recommending `httpx2`; it is upstream,
unsuppressed, and non-blocking because the real-process harnesses also exercise HTTP.

## Consistent-read and query-count evidence

After an authentication-equivalent `SELECT`, executable probes show SQLAlchemy has a
logical transaction while the Python 3.12 sqlite3 driver does not. The feature seam
issues exactly `BEGIN DEFERRED` on that same request connection and verifies the driver
entered a real transaction. Read use cases never commit or roll back; request Session
teardown owns rollback and connection release.

Deterministic WAL tests pause search between count and page/tag reads and statistics
between totals and later aggregates. A separate writer commits generation B while the
reader returns only generation A; a fresh Session returns B. Real authenticated HTTP
instrumentation records exactly five statements for populated list and stats requests:
authentication lookup, `BEGIN DEFERRED`, and three feature reads, all on one DB-API
connection. Direct populated feature paths therefore remain exactly four statements,
constant across result and tag volume; empty or out-of-range pages use fewer.

## Raw-SQL isolation and aggregate evidence

`app/bookmarks/stats/raw_sql.py` owns the only three Track 04 data `TextClause`s:

1. owner bookmark total and distinct attached-tag total;
2. owner top tags grouped by ID/name, ordered count descending then name ascending,
   with a bound `top_tags_limit`;
3. owner UTC `YYYY-MM` bookmark counts ordered chronologically.

Every statement binds `user_id`; no SQL text or limit is interpolated. Ordinary search
uses SQLAlchemy/SQLModel expressions only. Empty, globally shared tag, distinct tag,
tie, cross-user, multi-year month, association removal, bookmark deletion, and live
fresh-read cases pass. No cache, persisted stats snapshot, response source/generated
header, queue, worker, dirty marker, or history behavior entered Track 04.

## Populated SQLite query plans

The executable fixture contains 250 target-user and 250 other-user bookmarks across
three months and overlapping tags. Normalized `EXPLAIN QUERY PLAN` evidence records:

- owner/date count: covering `ix_bookmarks_user_created_id` search;
- owner/date page: `ix_bookmarks_user_created_id` search;
- exact-tag count/page: owner index plus the unique tag-name auto-index and the
  bookmark/tag composite primary-key index through correlated `EXISTS`;
- page tag load: bookmark/tag composite index plus primary-key bookmark/tag lookups;
- totals/top-tags/months: indexed owner lookup and required indexed association joins;
  aggregate/group/order temporary B-trees are accepted where SQLite requires them.

Representative exact-tag/date/no-query plans contain no unqualified full bookmark
scan. Literal `%...%` title search intentionally makes no substring-index claim; only
owner isolation is asserted. No migration or speculative index was justified.

## Migration lifecycle

Against the exact disposable file
`/private/tmp/backend-sample-track04-closure.sqlite3`, the primary ran:

```text
DATABASE_URL=sqlite:////private/tmp/backend-sample-track04-closure.sqlite3 .venv/bin/alembic upgrade head
DATABASE_URL=sqlite:////private/tmp/backend-sample-track04-closure.sqlite3 .venv/bin/alembic check
DATABASE_URL=sqlite:////private/tmp/backend-sample-track04-closure.sqlite3 .venv/bin/alembic downgrade base
DATABASE_URL=sqlite:////private/tmp/backend-sample-track04-closure.sqlite3 .venv/bin/alembic upgrade head
```

Every command exited `0`; Alembic reported no new upgrade operations. Track 04 added no
migration. The validated file was removed immediately after the lifecycle check.

## Real-process Bash harnesses

| Command | Actual result |
| --- | --- |
| `bash scripts/verify-track-01.sh` | Exit `0`; factory/bootstrap/lifecycle/error-boundary receipt passed. |
| `bash scripts/verify-track-02.sh` | Exit `0`; auth/protected/redaction receipt passed after its exact route inventory gained `/stats`. |
| `bash scripts/verify-track-03.sh` | Exit `0`; CRUD/ownership/tag/timestamp/OpenAPI/redaction receipt passed. |
| `bash -n scripts/verify-track-04.sh` | Exit `0`; Bash syntax valid. |
| `bash scripts/verify-track-04.sh` | Exit `0`; hardened Track 04 receipt passed; a specialist also passed it twice consecutively. |

The Track 04 harness uses actual `make bootstrap`, three bounded application lifecycle
cycles, a generated JWT secret, private task-prefixed temporary state, disposable
migrated SQLite, a dynamic loopback port, two real users, and protected request/token
artifacts. It proves exact tag and ASCII-case/literal substring behavior, date/update
bounds, stable pages, invalid queries, owner isolation, live multi-month stats and
mutation, operation OpenAPI/runtime schemas, and one safe owning-boundary fault.

Every captured application physical line is parsed as JSON. Required full source,
service/component/event/level/timestamp/logger/process/thread fields, lifecycle counts,
one owning unexpected exception, nested redacted exception evidence, and safe UUID
correlation pass. Raw/indexed logs exclude credentials, tokens, JWT secret, database
location, both identities, authorization/hash markers, submitted URL/title/description/
tags/content, and cross-user sentinels. Recursive descendant termination is verified,
all artifacts are private, and the guarded trap removes the complete workspace. One
debug workspace created during development was explicitly removed and verified absent;
the final harness exposes no debug-retention mode.

The process harness explicitly makes no N+1 claim; deterministic statement-count and
query-plan tests provide that evidence.

## Independent review, hygiene, and retained boundaries

Mason Medium reviewed `main...614b136`, all governing contracts, production code,
tests, query plans, coverage, harness safety, and the inherited manifest correction.
Verdict: **PASS**, with no product defects or acceptance-blocking evidence weakness.

The worktree was clean before this documentation checkpoint. Bounded checks found no
new migration, tracked database, cache, coverage/log/credential artifact, raw search
SQL, or Track 05--07 runtime behavior.

Known retained limits are deliberate:

- SQLite `lower()` supplies the accepted ASCII case behavior; Unicode casefolding is
  not claimed.
- Literal substring search is not indexed; owner isolation remains indexed and no
  unsupported performance claim is made.
- API-wide OpenAPI conformance remains Track 05 ownership.
- Queue/backlog, durable dirty recovery, stats snapshots, worker/lifecycle/health and
  failure policy remain Track 06 ownership.
- Developing weekly points and append-only corrected history remain Track 07 ownership.
