# Track 06 plan: event-driven current statistics, durable recovery, and operations

- Specification: [SPEC.md](SPEC.md), version 1.2
- Governing ADRs: ADR-001, ADR-004, ADR-005, ADR-006
- Status: Ready (implementation authorized)
- Active item: T06-07 — deterministic closure suite and real-process harness

## Dependency gate and intent check

Before any implementation, the primary engineering thread verifies Track 05 is
**Complete**, its `TEST-REPORT.md` records passing mandatory core evidence, and no
critical/high defect remains. Re-read delivered Track 03 publisher/transaction seams,
Track 04 canonical reader/body, Track 05 contract evidence, ADR-001/004/005/006, and this
SPEC's terminal current-only marker-completion boundary. Stop for an upstream mismatch; do
not adapt a public or durable-state contract silently.

| ID | Work item | Owner | Depends on | Status | Exit evidence |
| --- | --- | --- | --- | --- | --- |
| T06-01 | Verify Track 05 closure receipts and delivered core seams; confirm the current-only marker-completion boundary is represented in the implementation design. | Smith / implementation | Track 05 Complete | Complete | Compatibility/gate receipt at `001056c`; mandatory core proof remains intact and the cleanup boundary is traceable. |
| T06-02 | Create/review Alembic dirty-marker migration and transaction-safe atomic upsert/reconciliation repository operations. | Smith / implementation | T06-01 | Complete | Commit `bf7546f`; exact migrated DDL/metadata/indexes, atomic upsert, rollback, generation race, restart recovery, downgrade/re-upgrade, 484-test full suite, and 100% coverage passed. |
| T06-03 | Define `BookmarkStatsInvalidated`, replace the Track03 no-op publisher adapter, and integrate same-transaction dirty marking plus exactly-one post-commit nonblocking publish. | Smith / implementation | T06-01, T06-02 | Complete | Commit `4768ceb`; typed safe DTO, same-session marker ordering, original delete window, rollback/no-op absence, commit-visible-before-publish, 509-test full suite, and 100% coverage passed. |
| T06-04 | Implement bounded queue, overflow flag/logging, coalescing, immutable snapshot store, and live `/stats` source selection/headers. | Smith / implementation | T06-01, T06-03 | Complete | Commits `38539c8` and `58eaa08`; total queue adapter, epoch-safe immutable snapshots, exact live fallback, documented headers, concurrency/failure tests, and 100% coverage passed. |
| T06-05 | Implement lifecycle-owned `bookmark-stats-refresher`, startup/periodic/full reconciliation, per-cycle sessions, generation-safe cleanup, and bounded cooperative shutdown. | Smith / implementation | T06-02, T06-04 | Complete | Commit `3de2c76`; exact non-daemon thread, bounded cursor/backlog and epoch-safe reconciliation, one session/non-overlap, generation/CAS/commit races, retry, deferred timeout cleanup, 556-test full suite, 100% coverage, and independent PASS. |
| T06-06 | Implement exact health routes, readiness state, worker-count enforcement, safe structured lifecycle logs, and redaction tests. | Smith / implementation | T06-04, T06-05 | Complete | Commit `5b4e489`; exact public health surface, static liveness, fail-closed database/worker/publisher/backlog readiness, transition-only redacted logs, 10-operation/37-pair OpenAPI inventory, 601-test full suite, 100% statement/branch coverage, and independent PASS. |
| T06-07 | Run deterministic integration/concurrency/failure suite, migration/quality validation, and the real-process closure harness; assemble evidence. | Smith / implementation | T06-02, T06-03, T06-04, T06-05, T06-06 | Pending | No real sleep; barrier/fault-injection proof for generation and concurrency; full ledger, SQL/live fallback parity, migration lifecycle, contracts, ephemeral response/token assertion handling, hygiene, and actual `bash scripts/verify-track-06.sh` receipt. |
| T06-08 | Primary closure, risk review, Track 08 handoff, and `TEST-REPORT.md`. | Primary engineering thread | T06-01, T06-02, T06-03, T06-04, T06-05, T06-06, T06-07 | Pending | All SPEC traceability complete; no critical/high defect; truthful deterministic/process-harness results, verified cleanup, safe debug-artifact disposition, and terminal current-only marker contract recorded. |

## Shared completion gate

The [engineering verification guideline](../../docs/ENGINEERING-VERIFICATION-GUIDELINE.md)
and [ADR-006](../ADR/ADR-006-engineering-verification-and-closure-evidence.md) apply
without changing Track 06's status, task IDs/dependencies, marker-generation
rules, transaction/publication ordering, current-stats fallback contract, one-worker
topology, ADR-004 log fields, or the terminal current-only completion rule. Planned, Ready, or
Blocked is not done. T06-08 may mark Track 06 Complete only after recorded passing
deterministic tests, migrated-database evidence, JSON-Line/redaction evidence, and
actual `bash scripts/verify-track-06.sh` results with cleanup; planned, skipped, or
blocked commands never count as pass.

## T06-01 compatibility and design receipt

The dependency gate closed from actual Track 05 evidence: merge `001056c`, 473 tests,
100% statement/branch coverage, exact 79-node mandatory selection, clean migration
lifecycle, and the passing real-process harness. Primary post-merge execution of
`scripts/verify-track-05.sh`, documentation verification, and the abnormal-cleanup
self-test also passed. Independent compatibility and architecture review found no
critical/high defect.

Implementation preserves these reviewed boundaries:

- The service-owned request transaction performs one atomic dirty upsert before
  commit, then one total/non-throwing typed publication attempt after commit.
- The Track 04 `BookmarkStatsReader` remains the only aggregate SQL implementation
  for worker recomputation and live fallback.
- Publication invalidates a per-user local epoch before nonblocking enqueue. A worker
  candidate may be exposed only when both that epoch and every observed durable
  generation still match during generation-safe finalization; this prevents a
  computed-before-concurrent-write snapshot from becoming observable.
- Marker removal uses current-only generation-safe completion. Track 07 is skipped,
  so no retention activation, historical backfill, or dual-consumer completion is
  authorized.
- The queue, snapshot store, worker, request-facing stats service, and health router
  remain narrow feature-owned components. No SQLAlchemy global commit listener,
  weekly projection table, history route, or second aggregation path is authorized.

Stop and return to primary/ADR review if the implementation cannot preserve the same
request session for dirty marking, uses read-then-write generation updates, lets
publication raise after commit, lacks epoch-and-generation protection, makes marker
deletion durable before recoverable snapshot publication, shares request sessions,
overlaps cycles, starts a daemon/import-time worker, changes the stats body/raw SQL,
or introduces weekly projection state.

The future `scripts/verify-track-06.sh` extends the delivered Track 05 mandatory
bootstrap/gate. It uses only a disposable database created through the real Alembic
migration path and a dynamic isolated port, starts the actual API process, and proves
that its exact named non-daemon `bookmark-stats-refresher` thread is running. It makes
real HTTP mutation, current-stats, `X-Stats-Source`/`X-Stats-Generated-At`,
`/health/live`, and `/health/ready` requests; bounds observation of actual worker
completion, degradation, and recovery through delivered configuration and observable
seams; checks snapshot/live body parity and observable or database-supported
queue/dirty recovery; and verifies clean shutdown and trap cleanup. It must not add a
test-only public endpoint, a second process, or a second worker thread.

This process proof supplements, rather than proves, generation, transaction-ordering,
no-overlap, and snapshot-publication concurrency invariants. Deterministic fake-clock,
manual-cycle, barrier, and fault-injection tests remain mandatory for those claims and
never wait for a real ten-second cadence.

## Work-wave detail

### T06-01 — mandatory core and compatibility gate

- Confirm the Track05 report actually covers current canonical stats rather than only
  schema reachability. Preserve its raw SQL parameterization/owner scope/body results.
- Inspect the implemented Track03 no-op seam and every material mutation transaction;
  integrate without moving commit/rollback ownership into repositories. Confirm the
  Track04 raw stats reader can be reused identically by worker and live fallback.
- Confirm Settings injection, SQLite FK/busy-timeout connection behavior, JSON logging,
  `create_app` lifespan, and no import-time side effects from Track01.
- Preserve terminal current-only generation completion. Track 07 is skipped; do not
  add historical retention, backfill, or a second consumer.

### T06-02/T06-03 — marker and post-commit event boundary

- Add only `bookmark_stats_window_dirty`; do not create weekly working/developed
  tables. Use `(user_id, window_start)` unique grain, generation, bounded reason,
  first/last marked UTC timestamps, user FK cascade, and query-shape indexes.
- Test `INSERT ... ON CONFLICT ... DO UPDATE` (or equivalent reviewed SQLite atomic
  operation): insert `generation=1`; conflict increments in the database, preserves
  first mark, updates last mark/reason. Every mark participates in canonical mutation
  transaction rollback.
- The event DTO remains separate from bookmark/public/persistence DTOs. Publish it
  only once after successful material commit. Validate all disallowed content is
  structurally absent, including from queue/log representations. Compute delete's
  window from the pre-delete entity before removal.

### T06-04/T06-05 — queue, current-serving, and worker

- Queue capacity is Settings-controlled and uses nonblocking enqueue. Full/adapter
  error sets thread-safe `full_reconciliation_required`, increments safe telemetry,
  logs a single bounded warning policy, and returns without raising into a committed
  request. Queue is never source of truth.
- Drain bounded batches and dirty rows every manual/periodic cycle. Coalesce events
  by user and durable marker work by `(user, window)`. Canonically recompute current
  state; do not apply arithmetic deltas. Startup reconciliation is immediate and full
  reconciliation is configurable, bounded defense in depth.
- Build immutable snapshot values off lock, then atomically swap. Do not evict a valid
  prior snapshot on compute failure. `/stats` preserves exact JSON and uses fresh
  snapshot else the same raw SQL for missing/stale/disabled/unhealthy state; document
  `X-Stats-Source` and `X-Stats-Generated-At` in operation OpenAPI.
- Lifespan constructs one named, non-daemon worker, gives it a stop event and per-cycle
  session factory, forbids concurrent cycles, and joins it for configured timeout.
  Generation compare-and-delete must include observed generation in the delete
  predicate so a concurrent increment persists.

### T06-06 — health, lifecycle logging, and safe observability

- Register only `/health/live` and `/health/ready`; liveness must not invoke business
  SQL or make refresher failure fatal. Readiness uses database and enabled-service
  state: started/alive, not stuck/overdue, cycle/success freshness, failure state,
  snapshot freshness, queue/dirty thresholds, and safe error code. It is bounded,
  cache-disabled, and redacted.
- Validate Settings reject multiple application workers when the service is enabled;
  disabled refresh has no process-local-service readiness requirement and `stats`
  stays correct via live SQL.
- Parse captured JSON Lines and enforce `source`, service/component, event, level, UTC
  timestamp, logger, `process_id`, execution/thread identity including `thread_name`,
  and ADR-004 `service_instance_id`, plus applicable safe duration, queue/count,
  generation/count, affected-user, interval, and failure-count fields. Correlation is
  supplied/generated only, never token/user ID/request body/content derived. Capture
  startup, cycle, retry, overflow, readiness, shutdown, and join outcomes. Deliberately
  seed safe credential/content/ID sentinels and assert their absence. At the final
  owning request/task/thread/process boundary, unexpected exceptions log once with
  redacted structured type, safe message, ordered frames, cause/context, no locals,
  and no raw exception text indexed; intermediates add safe context and re-raise
  without duplicate logs. Do not duplicate or weaken ADR-004.

### T06-07 — deterministic and real-process evidence

- Keep concurrency, marker-generation, transaction-order, no-overlap, and
  publication-atomicity proof deterministic with fake clocks, manual-cycle hooks,
  controlled barriers, and fault injection. The real-process harness supplements
  these tests and cannot prove those invariants by elapsed time or scheduler luck.
- Deliver `scripts/verify-track-06.sh` only after the Track 05 bootstrap exists. It
  extends that delivered mandatory gate with a verified disposable migrated database,
  dynamic isolated port, actual API process, and its named non-daemon refresher
  thread. Use bounded polling and delivered configuration/observable seams for worker
  completion, degradation, and recovery; never add a test-only endpoint, second
  process, or second worker thread.
- Exercise real mutation, current-stats, source-header, `/health/live`, and
  `/health/ready` flows. Parse the actual process JSON Lines; prove snapshot/live
  parity, queue/dirty recovery through observable state or the disposable database,
  clean shutdown, and trap cleanup. Own-user stats bodies, `X-Stats-*` headers, and
  safe health bodies are ephemeral in-memory assertions; JWTs are parsed/used in memory
  only without echo/persistence. Own-user values/tokens/IDs/content sentinels and all
  cross-user data are absent from logs, indexed fields, command/diagnostic output,
  assertion failures, unsafe debug bundles, and retained artifacts. Health remains
  bounded/redacted with no SQL/content/credentials/paths/raw exceptions. Remove
  disposable response/token/debug state unless explicit safe debug mode applies. No
  real ten-second sleep is a valid assertion.

### T06-08 — closure and Track 08 handoff

- Primary records a truthful `TEST-REPORT.md` only from actual deterministic,
  migrated-database, quality, and `bash scripts/verify-track-06.sh` results, including
  versions, selectors, artifacts, selected non-sensitive port, cleanup, gaps, and
  retained debug artifacts where applicable.
- Hand Track 08 the confirmed terminal current-only completion contract and the Track
  07 skip/absence boundary. Do not claim historical points or weekly corrections.

## Deterministic edge-case/evidence ledger

| Area | Cases and required proof |
| --- | --- |
| Transaction/event | Create, material scalar PATCH, tag change, delete each increment marker in canonical transaction and post-commit publish once; reads/no-op/rollback do neither; delete retains original window. |
| Queue/recovery | Capacity overflow, publisher failure, post-commit crash before publish, dropped, duplicate, reordered events; marker poll/startup/full reconciliation recovers without request failure. |
| Generation | Concurrent mutation barrier after worker observes generation; compare-and-delete cannot remove new work; retry preserves marker after worker/SQL failure. |
| Snapshot/live SQL | Fresh source and every fallback (missing/stale/disabled/unhealthy) return semantically identical schema-conforming JSON from the same raw-SQL semantics for empty, ties, month boundaries, delete/tag change, and two users. |
| Reader concurrency | Multiple readers during off-lock build/swap see either prior or complete new immutable snapshot, never partial/mixed data. |
| Lifecycle | Fake clock/manual cycle, no real sleep: exact name/non-daemon, one instance, own sessions, no overlap, interruptible wait, startup timeout, shutdown during work, bounded join timeout, restart isolation, disabled service. |
| Health | Live remains independent; ready reports safe 200/503 transitions for DB failure, dead/stuck/never-success/repeated failure/stale worker, dirty backlog/age, overflow, startup and disabled states. |
| Logging | Parse structured logs; service/event names present for startup/cycle/retry/overflow/readiness/shutdown/join timeout, while seeded IDs/content/URLs/tags/secrets/tokens are absent. |
| Migration | Migrated SQLite empty/existing upgrade, DDL/FK/cascade/key/index inspection, atomic generation conflict, rollback, clean downgrade/re-upgrade, and restart recovery. |
| Track 07 boundary | Track 07 is skipped; current-only generation completion remains final and weekly tables, consumers, backfill, and correction revisions remain absent. |

## Planned validation commands

Run these after delivered tooling is confirmed; record exact output, database paths,
test selectors, headers, and any unavailable command in `TEST-REPORT.md`.

```text
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run mypy app
uv run pytest tests/unit tests/integration tests/contract -k 'stats or invalidation or dirty or snapshot or health or lifecycle'
uv run pytest
uv run alembic upgrade head
uv run alembic downgrade base
uv run alembic upgrade head
uv run alembic check
make check
bash scripts/verify-track-06.sh
git diff --check
git status --short
```

Focused tests use fake clocks, manual worker-cycle triggers, fake/session factories,
barriers, and deterministic failure injection. They must not wait ten seconds or rely
on scheduler timing. The planned harness extends delivered Track 05 bootstrap/process
evidence but cannot substitute for deterministic invariant proof. Add exact migration
DDL/constraint/index inspection, endpoint header/body parity, structured-log parsing,
and closure-report commands only when implemented; never claim these planned commands
passed before they run.

## Review checkpoints and commit boundary

1. Gate and terminal current-only completion review; 2. migration/upsert/rollback review;
3. post-commit event safety review; 4. queue/snapshot/live-SQL equivalence review;
5. worker generation/lifecycle review; 6. health/log redaction review; 7. primary
closure and Track 08 handoff review.

Preferred green-boundary commit: `feat: add observable event-driven statistics refresh`.
Do not commit generated databases/caches/coverage, secrets, user content, tokens,
or a failing intermediate state. Do not add weekly historical tables/revisions,
bonuses, or final narrative to this change.
