# ADR-004: Event-driven periodic bookmark statistics service

- Status: Accepted
- Date: 2026-08-05
- Decision owners: Repository owner
- Affected tracks: 01, 04, 06, 07, 08
- Affected SPEC versions: Baseline
- Supersedes: Earlier discussion of request-only statistics computation
- Superseded by: None

## Context

The assessment requires an authenticated, user-scoped statistics endpoint backed by
raw SQL. The repository owner additionally requires loose coupling between bookmark
mutations and statistics generation: successful statistics-relevant actions publish
events, and a named in-process service consumes queued events every ten seconds to
generate statistics data points. The service must start with the API without Docker,
produce attributable logs, and contribute meaningful readiness state.

The background execution, queueing, lifecycle, and current-snapshot decisions are
independent from the lifecycle of historical statistics data points. Windowed
developing and developed data points are governed by ADR-005.

## Decision

### Event publication

- Bookmark create, material update, tag-association change, and delete publish a
  `BookmarkStatsInvalidated` event after the database transaction commits.
- Read operations and semantically identical PATCH operations publish no event.
- The event contains only a user ID, affected UTC `window_start`, mutation kind,
  resource ID, occurrence time, and correlation ID. It contains no URL, title,
  description, tag, email, username, or token data.
- Application services depend on a narrow `DomainEventPublisher` interface rather
  than on the queue or refresher implementation.
- Every material stats-relevant mutation inserts or increments its durable
  `(user_id, window_start)` dirty marker inside the same transaction as the canonical
  bookmark mutation. For delete, the affected window is derived before the bookmark
  row is removed.
- The assessed adapter uses a bounded, process-local `queue.Queue`.
- Publishing does not roll back an already committed bookmark mutation. Queue
  overflow marks a thread-safe `full_reconciliation_required` flag and emits a
  sanitized warning.
- The post-commit queue event is a low-latency wake-up hint. Durable dirty-marker
  polling is the recovery authority when an event is lost or the process crashes.

### Queue consumption and recomputation

- FastAPI lifespan constructs and starts one non-daemon thread named exactly
  `bookmark-stats-refresher`.
- The interval defaults to 10 seconds and is configurable through
  `STATS_REFRESH_INTERVAL_SECONDS`.
- Each cycle drains the current queue batch and reads durable dirty markers. Current
  snapshot work is coalesced by user ID; historical projection work is coalesced by
  `(user_id, affected_window_start)`. The worker recomputes canonical state using
  parameterized raw SQL. Events are invalidations, not arithmetic instructions.
- Recalculation from canonical state makes duplicate and reordered events harmless.
- The worker creates and closes its own SQLModel Session for each cycle; it never
  shares a request Session.
- A startup reconciliation builds current statistics before normal periodic cycles.
- A worker clears a dirty marker only when its stored generation still matches the
  generation observed before recomputation. A concurrent increment remains pending
  for the next cycle.
- Configurable periodic full reconciliation provides defense in depth for overflow
  and suspected inconsistency; it is not the primary event-loss recovery mechanism.
- One cycle never overlaps another. Shutdown uses a `threading.Event` and a bounded
  join rather than an uninterruptible sleep.

### Snapshot serving and rubric preservation

- Successful refreshes build results off-lock and atomically publish a complete
  immutable per-user snapshot generation.
- A failed refresh preserves the previous complete generation and keeps affected
  user IDs pending for retry.
- `/api/bookmarks/stats` returns a fresh snapshot for the authenticated user.
- When the user has no snapshot, the snapshot is stale, the queue service is
  disabled, or the worker is unhealthy, the endpoint executes the same canonical
  user-scoped raw SQL synchronously.
- The response body remains the assessment shape. OpenAPI documents
  `X-Stats-Source` and `X-Stats-Generated-At` response headers.
- `TOP_TAGS_LIMIT` defaults to 5 and is configurable and validated in Settings.
- All non-statistics data access continues to use SQLModel ORM.

### Lifecycle, health, and bootstrap

- Application bootstrap starts the API, database integration, event publisher, and
  statistics refresher together through FastAPI lifespan. No service starts at
  module import time.
- `/health/live` reports process liveness independently of statistics refresh
  success.
- `/health/ready` reports database readiness plus statistics-service state.
- Statistics readiness requires a started and alive thread, recent completed cycle,
  at least one successful reconciliation, acceptable failure state, and snapshot
  freshness. `thread.is_alive()` alone is insufficient.
- Health state records generation, queue depth, dirty-marker count and oldest age,
  overdue working-window count, last cycle, last success, consecutive failures,
  in-progress state, and a sanitized low-cardinality error code. It never exposes
  business data, SQL, paths, secrets, or exception text.
- The assessed runtime uses exactly one Uvicorn worker. A configuration requesting
  more than one worker fails validation while the in-process refresher is enabled.

### Logging

- Log records identify `service`, `event`, `thread_name`, `process_id`,
  `service_instance_id`, timestamp, level, and logger.
- Service values include `bootstrap`, `api`, `database`, and
  `bookmark_stats_refresher`.
- Refresh logs may include generation, duration, queue depth, affected-user count,
  interval, and consecutive failures, but never user IDs or submitted content.
- Startup, refresh, retry, queue overflow, readiness transition, shutdown, and join
  timeout are distinct low-cardinality events.

### Configuration baseline

| Setting | Default | Constraint |
| --- | ---: | --- |
| `STATS_REFRESH_ENABLED` | `true` | Boolean |
| `STATS_REFRESH_INTERVAL_SECONDS` | `10` | 1-3600 |
| `STATS_STALE_AFTER_SECONDS` | `30` | At least the refresh interval |
| `STATS_INITIAL_REFRESH_TIMEOUT_SECONDS` | `5` | 0-60 |
| `STATS_SHUTDOWN_TIMEOUT_SECONDS` | `5` | 1-60 |
| `STATS_FULL_RECONCILIATION_SECONDS` | `300` | At least the refresh interval |
| `STATS_EVENT_QUEUE_CAPACITY` | `1000` | Positive bounded integer |
| `STATS_DIRTY_MAX_AGE_SECONDS` | `60` | At least the refresh interval |
| `STATS_DIRTY_MAX_COUNT` | `1000` | Positive bounded integer |
| `TOP_TAGS_LIMIT` | `5` | 1-100 |
| `APP_WORKER_COUNT` | `1` | Must equal 1 in this mode |

## Alternatives considered

| Alternative | Benefits | Costs and risks | Reason not selected |
| --- | --- | --- | --- |
| Recalculate on every mutation | Immediately current | Couples write latency and rollback behavior to aggregation | Explicitly rejected by the owner |
| Poll all data every ten seconds without events | Simple worker | Recomputes unchanged users and does not demonstrate the requested event boundary | Queue-driven targeted refresh selected |
| Increment counters from event payloads | Cheap refresh | Duplicate, lost, or reordered events corrupt totals | Events trigger canonical recomputation instead |
| FastAPI-managed `subprocess.Popen()` | Stronger process boundary | Supervision, duplicated startup, shutdown, and IPC complexity | A managed thread is explicitly preferred |
| External durable broker and worker | Durable delivery and multi-process scaling | Requires extra local infrastructure and exceeds the exercise | Deferred production evolution |
| Readiness based only on thread liveness | Easy to implement | A live loop can repeatedly fail or serve stale snapshots | Freshness and success state are required |

## Consequences

### Positive

- Bookmark mutation logic is decoupled from aggregation implementation.
- Events are small, non-sensitive, and safe to coalesce.
- Canonical recomputation is idempotent and resists duplicate or reordered events.
- The service demonstrates lifecycle, threading, synchronization, health,
  configuration, recovery, and observability discipline.
- Live fallback keeps `/stats` correct and visibly connected to the required raw SQL.

### Negative and risks

- In-process queue delivery is not durable, but the transactional dirty marker
  preserves pending projection work across process failure.
- Snapshots are eventually consistent for up to the configured interval plus query
  duration.
- The queue, cache, and thread are process-local, so one application worker is an
  explicit deployment constraint.
- The background service expands testing and walkthrough scope beyond the base
  assessment.
- A live raw-SQL fallback and snapshot path must remain contract-equivalent.

### Follow-up

- Implement windowed historical data points in Track 07 according to accepted
  ADR-005; Track 06 first establishes the shared durable dirty-marker mechanism.
- Create deterministic lifecycle, queue, concurrency, fallback, health, logging, and
  shutdown tests without real ten-second sleeps.
- Document a future durable-outbox and external-worker evolution without
  implementing extra infrastructure.

## Acceptance evidence

- Only successful material bookmark transactions publish events.
- Events appear after commit, contain no sensitive data, and are coalesced by user.
- Every material mutation commits its dirty marker with canonical data before its
  post-commit event is published.
- Queue overflow retains durable work and triggers reconciliation without failing the
  committed request.
- Marker cleanup uses generation comparison and cannot erase a newer invalidation.
- Startup and periodic reconciliation repair missed invalidations.
- The named thread starts once, refreshes immediately, drains on schedule, retries
  failures, and stops cleanly.
- Snapshot publication is atomic; concurrent readers never see partial generations.
- Fresh snapshot, missing snapshot, stale snapshot, disabled service, and failed
  worker paths return identical OpenAPI-conforming bodies.
- Cross-user, empty, tag-tie, deletion, month-boundary, and configurable top-tag
  cases are correct.
- Readiness fails for a dead, stuck, never-successful, or stale worker while liveness
  remains independent.
- Captured logs identify services and contain none of the seeded sensitive values.

## Evidence and references

- [Assessment](../../docs/Technical%20Assessment%20Senior%20Software_Engineer.pdf)
- [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/)
- [Python threading](https://docs.python.org/3/library/threading.html)
- [Python synchronized queues](https://docs.python.org/3/library/queue.html)
- [SQLite isolation](https://www.sqlite.org/isolation.html)
