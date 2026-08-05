# Track 06 specification: event-driven current statistics, durable recovery, and operations

- Status: Planned (implementation-gated)
- Specification version: 1.0
- Planned: 2026-08-05
- Owner: Primary engineering thread
- Depends on: Track 05 **Complete**, including its core quality-gate receipts and no known critical/high defect
- Governing ADRs: ADR-001, ADR-004, ADR-005
- Assessment requirements: EVT-01, EVT-02, EVT-03, WIN-03, OPS-01; preserves SQL-01 and SQL-02

## 1. Intent anchor

Add the optional, observable runtime only after the mandatory core API is proved. It
accelerates current-statistics reads with snapshots, but the canonical raw-SQL reader
remains the correctness authority: process-local queue, thread, and snapshot state
must never be required for a correct `GET /api/bookmarks/stats` response.

Track 06 is **Blocked** until Track 05 is Complete with its stated core gate evidence.
Its detailed plan is planning only; it does not authorize implementation or make the
extension Ready.

## 2. Must-preserve contracts

- Preserve the exact Track 04 `GET /api/bookmarks/stats` response body and its
  SQL-01/SQL-02 semantics: authenticated user scope, `total_bookmarks`,
  `total_tags`, ordered `top_tags[{name,count}]`, and chronological
  `bookmarks_per_month[{month,count}]`. The snapshot and live reader must use the
  same canonical raw SQL and be cross-user equivalent.
- Replace Track 03's inert post-commit `DomainEventPublisher` seam with a concrete
  `BookmarkStatsInvalidated` DTO and publisher adapter. Its safe fields are only
  `user_id`, UTC `window_start`, mutation kind, resource/bookmark ID, occurrence
  time, and correlation ID. It contains no URL, title, description, tag text, email,
  username, password/hash, authorization value, or token.
- A material bookmark create, scalar update, tag-membership update, or delete marks
  the affected `(user_id, window_start)` dirty row by insert-or-increment in the
  **same canonical mutation transaction**, commits, then publishes exactly one
  nonblocking event after commit. Reads, semantically no-op updates, and rollback
  publish and mark nothing. Delete obtains the bookmark's original UTC window before
  deleting it.
- The queue is a bounded, process-local wake-up hint; the durable dirty marker is
  recovery authority. A full queue sets a thread-safe reconciliation-required flag
  and writes a sanitized low-cardinality warning, but cannot fail or roll back an
  already committed request. Duplicate, reordered, dropped, and post-commit-crash
  events are harmless because processing recomputes canonical state.
- FastAPI lifespan owns exactly one non-daemon thread named
  `bookmark-stats-refresher`. It has no request-scoped/session sharing, constructs a
  session per cycle, uses interruptible waits, does not overlap cycles, and has a
  bounded cooperative shutdown join. No worker starts at import time.
- A successful cycle creates each immutable per-user snapshot entirely off lock, then
  publishes it atomically. Failure retains the last complete snapshot and pending
  work for retry. A request uses a fresh snapshot only; absent, stale, disabled, or
  unhealthy snapshot service falls back synchronously to the same raw SQL.
- Keep exactly the accepted health routes: `/health/live` and `/health/ready`.
  Liveness is independent of refresher success. Readiness has a bounded, redacted
  body and evaluates database plus enabled-service progress rather than thread
  existence alone. When enabled, `APP_WORKER_COUNT != 1` is invalid.
- Do not add weekly working/developed tables, correction revisions, a history API,
  bonuses, or a final submission narrative. Those remain Tracks 07 and 08.

## 3. Scope and decision latitude

### Included

- a strict internal event DTO, publisher port adapter, bounded queue, and post-commit
  integration into delivered Track 03 material-mutation services;
- one Alembic migration and repository operations for durable dirty work;
- lifecycle-owned worker, startup/periodic/full reconciliation, atomic current
  snapshots, current stats source headers, health, and service-attributed logging;
- deterministic unit, migrated-SQLite integration, endpoint, lifecycle, concurrency,
  and failure tests; and a closure `TEST-REPORT.md` from actual evidence.

### Local decision latitude

This track may choose internal module/port/repository names, batch limits, snapshot
representation, low-cardinality reason/error enums, and exact redacted health field
names, provided all ADR-004 Settings and bounds are preserved. It may add the
non-secret operational settings already established by Track 01 only through the
injected Settings boundary.

Stop for primary/ADR review before changing the stats body, raw-SQL ownership or
semantics, mutation/timestamp rules, event safe-field boundary, marker grain,
one-worker deployment constraint, accepted health paths, or historical semantics.

## 4. Durable invalidation contract

### 4.1 `bookmark_stats_window_dirty` migration

Create `bookmark_stats_window_dirty` at exact durable grain `(user_id, window_start)`
with:

| Column / rule | Contract |
| --- | --- |
| `user_id` | non-null foreign key to `users.id`, indexed for user work lookup, `ON DELETE CASCADE` |
| `window_start` | non-null UTC Monday window start; paired with `user_id` as the unique key |
| `generation` | non-null positive/incrementing integer for compare-and-delete safety |
| `reason` | non-null bounded low-cardinality mutation/reconciliation reason, never content |
| `first_marked_at` | non-null UTC timestamp set only at first insert |
| `last_marked_at` | non-null UTC timestamp updated for each mark |

The revision must create the unique constraint/index for `(user_id, window_start)`,
the user/window reconciliation access indexes justified by these query shapes, and
the cascade FK. It must be manually reviewed, upgrade a new and existing core schema,
downgrade/re-upgrade safely, retain SQLite foreign-key enforcement, and have a
forward recovery/reconciliation receipt. No application startup auto-migrates.

`mark_dirty` is a single transactional upsert: insert generation `1` with both mark
times on absence; on conflict atomically increment generation, replace the bounded
reason with the newest safe reason, and update only `last_marked_at`. It is called
inside the same service-owned transaction as canonical bookmark/tag state. No
read-then-write increment is acceptable.

### 4.2 Event and queue adapter

The post-commit adapter attempts one `put_nowait` for the DTO. Its outcome does not
alter committed domain state. Full queue or publisher failure is observable through a
safe outcome and reconciliation flag, not a second publication attempt that could
break exactly-once-per-committed-mutation semantics at the application seam. The
system makes no exactly-once-delivery claim: the event can be lost after commit, and
durable state makes the outcome at-least-eventual canonical recomputation.

Queue draining is bounded. Current snapshot candidates coalesce by `user_id`; dirty
work coalesces by `(user_id, window_start)`. A cycle reads durable markers even if it
received no event; startup reconciles current stats before normal scheduling; a
configurable full reconciliation is defense in depth for overflow/suspected drift.

### 4.3 Staged consumer completion

ADR-004 and ADR-005 use one staged installed-consumer rule. Before Track 07 exists, a
successful canonical current-stat recomputation may clear a generation-matching marker
after atomically publishing the relevant snapshot. This is current completion only;
Track 06 does not claim to have produced historical points.

Track 07 must perform a canonical initial historical backfill and must not treat rows
previously cleared by Track 06 as historical evidence. After the historical consumer
is installed, marker removal requires both current-snapshot and historical-projection
completion for the observed generation. A concurrent increment remains pending. The
initial backfill is the bridge between pre-projection cleanup and multi-consumer
completion.

## 5. Worker, snapshots, and serving

At enabled-app lifespan startup, construct one service instance and start its exact
non-daemon thread once. It immediately performs bounded current reconciliation, then
waits up to `STATS_REFRESH_INTERVAL_SECONDS` (default `10`) using a stop event rather
than sleeping uninterruptibly. Each cycle owns and closes its own SQLModel Session,
has a bounded batch, runs non-overlapping work, records completion/failure, and leaves
failed users/windows pending. A bounded `STATS_SHUTDOWN_TIMEOUT_SECONDS` join is
always attempted; timeout is a distinct failure/log state, not silently ignored.

Snapshot construction is off-lock from the Track 04 canonical reader, represented as
an immutable complete per-user value carrying generation and generation timestamp.
One atomic reference swap publishes it; readers never observe partial maps or mixed
aggregate fields. Failing raw SQL, persistence, or publication retains the prior
generation and dirty/pending work. A request chooses only a fresh snapshot and adds:

- `X-Stats-Source`: documented cache/snapshot versus live canonical source;
- `X-Stats-Generated-At`: snapshot generation time when applicable, with a documented
  non-content value/absence policy for live fallback.

These headers must not alter the JSON body or disclose user/content/internal errors.

## 6. Health and observability

`/health/live` is local process liveness only and remains independent of database
refresh success. `/health/ready` applies `Cache-Control: no-store`, bounded timeout
and redacted response fields, checks database readiness, and when refresh is enabled
requires startup completed, exactly one started/alive worker, recent completed cycle,
at least one successful reconciliation, non-stuck/non-overdue progress, acceptable
consecutive failures, acceptable snapshot freshness, and dirty backlog count/age
thresholds. It records queue depth/overflow and sanitized error code without IDs,
content, SQL, paths, secrets, or exception text. Disabled refresh remains ready based
on database/lifecycle policy and `/stats` live fallback remains correct.

All lifecycle and worker logs use the established structured schema with service
attribution (`bootstrap`, `api`, `database`, `bookmark_stats_refresher`) and only
low-cardinality fields such as duration, queue depth, generation count, affected-user
count, interval, and failure count. They never log user IDs, resource IDs, tag/content
data, credentials, tokens, URLs, SQL, or secrets. Emit distinct events for startup,
cycle success/failure, retry, overflow, readiness transition, shutdown, and join
timeout.

The Track 06 test and process-harness log audit parses every captured application log
as JSON Lines and enforces the ADR-004 fields exactly: `service`, `event`,
`thread_name`, `process_id`, `service_instance_id`, timestamp, level, and logger.
It also checks correlation identifiers when a request or asynchronous flow has one,
and checks duration, queue/count, generation/count, affected-user count, interval,
and failure-count fields when the selected event makes them applicable. It captures
the expected startup, cycle, retry, overflow, readiness, shutdown, and join outcomes.
It deliberately seeds safe credential, submitted-content, and identifier sentinels
and proves that none appear in logs, HTTP output, or retained artifacts. The shared
[engineering verification guideline](../../docs/ENGINEERING-VERIFICATION-GUIDELINE.md)
governs unexpected-exception evidence: the owning request, task, thread, or process
boundary logs it exactly once with safe structured exception evidence; intermediate
layers add safe context and re-raise. This supplements, and neither duplicates nor
weakens, ADR-004's logging contract.

## 7. Requirements and acceptance evidence

| ID | Requirement |
| --- | --- |
| T06-REQ-01 | Replace the Track 03 no-op with the safe post-commit invalidation DTO/publisher adapter for each and only material committed mutation. |
| T06-REQ-02 | Add a migration-backed, same-transaction, atomic dirty-generation upsert and generation-safe recovery/cleanup protocol. |
| T06-REQ-03 | Provide a bounded queue and loss/overflow-tolerant reconciliation that never makes a committed request fail. |
| T06-REQ-04 | Provide one lifecycle-owned named worker with per-cycle session ownership, immediate/startup and periodic reconciliation, cooperative bounded shutdown, and no cycle overlap. |
| T06-REQ-05 | Atomically publish immutable current snapshots and preserve exact live raw-SQL body correctness for snapshot fallback paths. |
| T06-REQ-06 | Provide exact accepted health routes, one-worker enforcement, bounded redacted readiness, and safe service-attributed lifecycle logs. |
| T06-REQ-07 | Prove deterministic concurrency, failure, recovery, isolation, and observability behavior without real sleeps; run the real-process closure harness and close with `TEST-REPORT.md`. |

Closure requires every Track 05 core gate receipt, migrated migration lifecycle proof,
same-transaction ordering proof, event safe-field/content proof, queue-loss/overflow
recovery, generation race proof, snapshot/live exact-body parity for two users,
lifecycle and health degradation/recovery evidence, JSON/redaction log evidence, and
all relevant quality commands. The planned `scripts/verify-track-06.sh` extends the
delivered Track 05 mandatory bootstrap/gate using a disposable database built by the
real migration path and a dynamic isolated port. It must launch the actual API process
and observe its exact named non-daemon `bookmark-stats-refresher` thread, then make
real HTTP mutation, current-stats, source-header, liveness, and readiness flows. It
must use delivered configuration and observable seams to bound observation of actual
worker completion, degradation, and recovery; it must not add a test-only public
endpoint, second process, or second worker thread. The harness proves snapshot/live
body parity, observable or database-supported queue/dirty recovery, clean shutdown,
and verified cleanup.

The process harness supplements rather than proves transaction ordering, generation
compare-and-delete, no-overlap, or reader-publication concurrency invariants. Those
claims require deterministic fake-clock/manual-cycle tests, controlled barriers, and
fault injection, with no real ten-second sleeps. No known critical/high defect may
remain.

## 8. Edge-case and failure ledger

| Dimension | Required deterministic evidence |
| --- | --- |
| Publication ordering | Material create/scalar/tag/delete marks then commits then emits once; read/no-op/rollback emit and mark none; delete derives original window before row removal. |
| Event loss | Simulate crash after commit before publish, lost/duplicate/reordered events, and full queue; next startup/cycle repairs from markers with no request failure. |
| Marker race | Barrier a concurrent increment between observed generation and cleanup; compare-and-delete leaves newer generation pending. |
| Current correctness | Empty/tie/month/delete/tag-change and two-user results match Track 04 live raw SQL for fresh, absent, stale, disabled, and unhealthy snapshots. |
| Snapshot concurrency | Barrier concurrent readers against build/swap; no partial/mixed generation; injected SQL/publication failure retains old immutable snapshot and pending work. |
| Worker ownership | Fake clock/manual cycle proves one instance, exact non-daemon name, own sessions, no overlap, interruptible cadence, restart isolation, disabled mode, and bounded shutdown/join timeout. |
| Health | Dead, stuck, never-successful, repeatedly failed, stale, startup-timeout, and backlog-threshold worker states fail readiness while liveness remains independent. |
| Observability | Parse JSON Lines and enforce ADR-004 service/event/thread/process/instance fields plus applicable correlation, duration, and count fields for startup/cycle/retry/overflow/readiness/shutdown/join outcomes; seed safe credential/content/ID sentinels must not appear, and unexpected exceptions appear exactly once at their owning boundary. |
| Migration/recovery | Empty/existing upgrade, constraints/FK/cascade/indexes, atomic upsert, rollback, downgrade/re-upgrade, and restart reconciliation pass on disposable migrated SQLite. |
| Process closure | Planned `scripts/verify-track-06.sh` extends the delivered Track 05 bootstrap with a disposable migrated database, dynamic isolated port, actual API process and named non-daemon worker, real HTTP mutation/current-stats/header/live-ready flows, bounded completion/degradation/recovery observation, snapshot/live parity, queue/dirty recovery, clean shutdown, and cleanup. |

## 9. Risks, limits, and follow-up ownership

- The queue, snapshot cache, and worker are process-local; this local assessment
  supports one Uvicorn worker only. A production deployment needs an outbox/durable
  broker and independently supervised worker or shared cache/materialized view.
- SQLite has bounded local contention only; keep transactions/batches short and do
  not claim multi-process throughput or exactly-once delivery.
- Track 07 owns historical working/developed tables, correction revisions, public
  history decisions, canonical initial historical backfill, and the confirmed
  multi-consumer marker-completion extension described above.
- Track 08 owns final README/process narrative, deployment design, seed data, and
  optional bonuses. Primary engineering owns closure review and the required
  `TEST-REPORT.md` evidence receipt.

## 10. Traceability

| Assessment / preserved requirement | Track 06 requirements | Planned evidence |
| --- | --- | --- |
| EVT-01 | T06-REQ-01,02 | Commit-order, safe DTO, create/update/tag/delete/no-op/rollback tests. |
| EVT-02 | T06-REQ-03,04 | Bounded queue, fake clock/manual-cycle, coalescing, overflow/lost-event recovery tests. |
| EVT-03 | T06-REQ-04,05 | Canonical recomputation, immutable snapshots, live fallback, parity/failure tests. |
| WIN-03 | T06-REQ-02,03,07 | Durable marker migration, post-commit-crash, restart, overflow, generation-race proof. |
| OPS-01 | T06-REQ-04,06,07 | Lifespan/thread/health/log/shutdown/join-timeout evidence. |
| SQL-01 | T06-REQ-05 | Same isolated named parameterized canonical raw-SQL reader remains the fallback authority. |
| SQL-02 | T06-REQ-05 | Exact JSON body/count semantics and ordered aggregates match live reader for every serving source. |
