# Track 07 specification: weekly event-time projections and correction revisions

- Status: Planned (implementation-gated)
- Specification version: 1.1
- Planned: 2026-08-05
- Owner: Primary engineering thread
- Depends on: Track 06 Complete with its closure TEST-REPORT.md
- Governing ADRs: ADR-001, ADR-004, ADR-005, ADR-006
- Assessment requirements: WIN-01, WIN-02; extends WIN-03 and preserves EVT-01..03, OPS-01, SQL-01, and SQL-02 boundaries

## 1. Intent anchor

Install durable weekly event-time projections only after the current-statistics
runtime has actual closure evidence. A weekly point summarizes the user's current
surviving canonical bookmarks whose immutable created_at falls inside one UTC
Monday-to-Monday half-open window. It is not an observation-time snapshot and it
never changes the required all-current /api/bookmarks/stats contract.

Track 07 is Blocked until Track 06 is Complete and its TEST-REPORT.md proves the
publisher, dirty-marker, worker, canonical raw-SQL, snapshot fallback, lifecycle, and
health seams on which this projection depends. This plan is not implementation
authority until that gate closes.

## 2. Must-preserve contracts

- The internal weekly payload has the same aggregate structure and deterministic
  ordering as current stats: total_bookmarks, total_tags, top_tags[{name,count}], and
  bookmarks_per_month[{month,count}]. Its named, parameterized raw SQL is scoped to
  canonical bookmarks with window_start <= created_at < window_end. It is not a public
  DTO and no history route, body, or OpenAPI operation is added.
- Windows are UTC [Monday 00:00:00Z, next Monday 00:00:00Z). A user/window has at
  most one mutable developing row. A close creates immutable developed revision 1;
  a late material delete, tag change, or other material state change to that closed
  window appends a correction only when its canonical payload hash changed.
- Existing developed rows are never edited. supersedes_id links a correction to the
  prior effective revision; the highest valid revision is effective internally.
  Retain all rows except the privacy/lifecycle exception that user deletion cascades
  through working, dirty, and developed rows.
- Reuse the Track06 bookmark-stats-refresher only. It remains the single lifespan
  owned non-daemon thread with one manual/periodic cycle path, per-cycle sessions,
  no overlap, queue as hint, dirty state as authority, and no scheduler/process/broker
  redesign. Projection success/failure, backlog, and overdue windows integrate with
  its existing bounded readiness and low-cardinality logs.
- Preserve Track06 current snapshots/live SQL independently of weekly processing. A
  failed, delayed, disabled, or absent weekly projection cannot change current stats
  JSON, headers, raw-SQL fallback, or its correctness authority.
- Do not claim recovery of deleted pre-install bookmarks or create empty historic
  weeks with no canonical/working/dirty evidence. The installation baseline is an
  honest current-state reconstruction, not an audit reconstruction.
- Exclude a public history API, queue redesign, external scheduler/broker, production
  topology change, final README/process narrative, seed data, and bonuses.

## 3. Scope and decision latitude

### Included

- reviewed Alembic schema for developing rows, immutable points, and installed
  two-consumer dirty completion;
- canonical weekly reader/window calculator, stable payload serialization/content hash,
  initial baseline backfill, developing replacement, finalization, late corrections,
  and effective-revision selection;
- reuse of the Track06 worker/manual cycle, durable recovery, health/log evidence,
  deterministic migration/concurrency/failure tests, and closure TEST-REPORT.md.

### Decision latitude

Track07 may select private module/repository names, exact private completion-column
names, canonical JSON serialization implementation, low-cardinality correction/
baseline reasons, and checkpoint/batch limits. They must remain injected/testable,
produce stable hash bytes, use the Settings boundary, and never disclose payload
content in logs. The calculation-version identifier format and controlled recompute
trigger are private but must be explicit and tested.

Stop for primary/ADR review before changing event-time windows, revision immutability,
correction/effective-selection rules, marker grain/generation, current-statistics
body/headers/raw-SQL ownership, user-cascade privacy behavior, or adding a public
history surface.

## 4. Persistence, payload, and completion protocol

### 4.1 Projection tables and migration

Create an Alembic revision and manually review it. Prove empty/existing upgrade,
downgrade-to-prior, re-upgrade, SQLite foreign-key enforcement, DDL constraints/
indexes, and restart recovery. Application startup never migrates.

bookmark_stats_window_working has this exact logical grain and fields:

| Field / constraint | Contract |
| --- | --- |
| user_id, window_start | Non-null user FK/cascade and unique (user_id, window_start) key. |
| window_end | Non-null exact next UTC Monday; validate half-open one-week boundary. |
| payload | Non-null canonical serialized internal aggregate payload. |
| calculated_at | Non-null UTC canonical calculation time. |
| source_generation | Non-null generation used for the result. Zero is reserved for installation backfill or an evidenced empty next-window row; positive values identify an observed dirty-marker generation. |
| calculation_version | Non-null explicit aggregate/version identity. |
| content_hash | Non-null deterministic hash of versioned canonical payload. |

bookmark_stats_window_point stores id, user_id, window_start, window_end, revision,
supersedes_id, payload, calculated_at, developed_at, correction_reason,
source_generation, calculation_version, and content_hash. It has revision >= 1,
non-null required canonical/time/version/hash fields, UNIQUE(user_id, window_start,
revision), a self FK for supersedes_id, user FK cascade, and indexes for user/window/
effective-revision reads and overdue/finalization shapes. Prove cascade and constraint
behavior rather than inferring it. A correction's predecessor must belong to the same
user/window and be revision N-1; enforce this in the service transaction and tests,
and use a composite database constraint if it remains portable and migration-safe.

Use deterministic canonical serialization: a documented schema/version wrapper,
stable aggregate key order, arrays already ordered by canonical query semantics, no
whitespace or environment/time/random fields, UTF-8 bytes, and a cryptographic hash
of those exact bytes plus calculation_version. Hash equality is compared only when
versions match. A TOP_TAGS_LIMIT or algorithm change requires a new calculation
version and deliberate scoped backfill/recompute policy with recorded baseline reason;
never silently compare hashes across versions or rewrite immutable history in place.

### 4.2 Installed two-consumer dirty completion

Extend bookmark_stats_window_dirty with private names such as
current_completed_generation and projection_completed_generation; exact names are
implementation latitude. Migrate existing rows to a safe incomplete/unreconciled
state, represented by zero while dirty generations remain positive, while preserving
grain, generation upsert, reason, timestamps, FK/cascade, and recovery authority. Do
not blanket-mark an existing generation complete during migration. Baseline and then
normal consumer cycles must reconcile it before two-consumer deletion is enabled.

For observed generation g, each installed consumer writes its own completion only
under a guarded generation = g predicate. A newer increment wins and remains pending.
Current completion remains Track06-owned after snapshot publication. Projection
completion becomes visible only on the successful transaction commit that persists a
working replacement, developed revision/finalization, or intentional no-change result
for g. Delete a marker only when generation = g, both installed consumer completion
values equal g, and deletion occurs in the owning successful durable completion
transaction or guarded retry. Therefore a concurrent increment cannot be erased and a
crash before projection durability leaves recovery work pending.

This replaces Track06 pre-projection current-only deletion only after Track07 baseline
completes. The committed staged rule is: backfill bridges markers Track06 legitimately
cleared before historical processing existed; once installed, both consumers
participate in every later cleanup.

## 5. Canonical baseline and weekly lifecycle

### 5.1 Installation backfill

Before normal two-consumer marker consumption, run a restartable, idempotent,
checkpointed canonical historical backfill. It scans only current canonical bookmarks
grouped by immutable creation window, recomputes each eligible user/window through the
weekly raw-SQL reader, and in bounded transactions:

- appends developed revision 1 for closed windows with surviving canonical data;
- creates/replaces current-window developing rows for users/windows with current
  canonical evidence; and
- records safe baseline reason, version/hash, aggregate counts, and checkpoint
  progress without logging IDs or payload content.

Baseline rows use reserved source_generation 0. Dirty-marker generations begin at 1,
so later consumer completion cannot confuse reconstructed installation state with an
observed event generation.

It creates no developed row for an empty elapsed calendar week and makes no claim to
reconstruct a bookmark deleted before installation. Restart/retry selects existing
deterministic version/hash/revision state and appends no duplicate. The backfill is
the current-surviving-state bridge for Track06-cleared markers, not pre-install audit
evidence.

### 5.2 Developing and boundary finalization

On coalesced dirty work, recompute canonical weekly payload and replace the single
developing row for an open window; never append periodic observations. Detect overdue
developing windows even with no event or after an injected clock jump. For each due
window, final-recompute canonical state, append immutable revision 1 when absent, and
create or refresh the next developing window atomically as ADR-005 requires. A working
row or dirty/baseline evidence is the basis for processing; it does not synthesize a
broad series of empty historical weeks. Finalization is idempotent after crash/retry.

### 5.3 Late corrections and effective selection

For a late material change affecting a closed window, recompute the original
created_at window. In a small transaction, allocate the next revision safely using
the unique key, load the effective revision, and append N+1 pointing to it only if the
version-compatible deterministic hash changed. Identical replay, duplicate/reordered
events, no-op mutation, and unchanged canonical result append nothing. A unique-race
conflict reloads the committed effective row and re-evaluates hash; it creates neither
duplicate revision numbers nor an in-place update.

## 6. Worker, health, and observability integration

The existing named worker consumes marker work by user/window after its current
snapshot work. It runs baseline before multi-consumer cleanup, uses existing bounded
manual/periodic/full reconciliation, and does not add a thread, scheduler, or process.
Projection SQL/persistence failure retains marker/backlog state for retry; restart and
queue loss recover from durable rows.

Add only safe aggregate health state: overdue working-window count/age, projection
backlog/completion freshness, baseline state, failure count, and sanitized error code.
They feed existing readiness; liveness remains independent. Emit distinct
low-cardinality baseline, developing, finalization, correction, retry, backlog/overdue,
and completion events with duration/count/version but never IDs, windows, payload/hash,
bookmark/tag content, SQL, paths, credentials, or secrets.

Tests and the process harness parse captured application logs as JSON Lines and retain
`source`, service/component, event, level, UTC timestamp, logger, `process_id`, and
execution/thread identity including `thread_name`; ADR-004 adds `service_instance_id`
plus applicable safe projection duration/count/generation/completion/baseline/checkpoint/
failure/calculation-version fields. Correlation is supplied/generated only, never token,
user ID, body, or content derived. Required outcomes include ADR-004 startup, cycle,
retry, overflow, readiness, shutdown, and join events together with baseline,
developing replacement, finalization, correction, backlog/overdue, and projection
completion outcomes. Harness credentials/JWTs and own user-scoped current-stats
bodies/headers and safe health responses are ephemeral in-memory assertions only;
tokens are parsed/used without echoing or persistence. Own values/tokens/IDs/content
sentinels and all cross-user data are absent from logs, indexed fields, command or
diagnostic/private-inspection output, assertion failures, unsafe debug bundles, retained
artifacts, and cross-user responses. Health is sanitized: no SQL, paths, raw exceptions,
credentials, or content. Debug retention needs an explicit flag and excludes protected
response/token data; cleanup removes disposable response/token/private-inspection/debug
state. Under the shared [engineering verification guideline](../../docs/ENGINEERING-VERIFICATION-GUIDELINE.md)
and [ADR-006](../ADR/ADR-006-engineering-verification-and-closure-evidence.md), a final
owning request/task/thread/process boundary logs each unexpected exception once with
redacted structured type, safe message, ordered frames, cause/context, and no locals;
intermediates add safe context and re-raise without duplicate logs; raw exception text
is not indexed. Formatter/redactor failure fails closed to one minimal schema-valid
redacted JSON record, never plaintext or the unsafe original. This adds projection
evidence without duplicating or weakening ADR-004.

## 7. Requirements and acceptance threshold

| ID | Requirement |
| --- | --- |
| T07-REQ-01 | Implement parameterized canonical weekly event-time calculation, stable payload serialization/hash, calculation-version policy, and UTC window invariants. |
| T07-REQ-02 | Migrate working/developed rows and extend dirty state for durable two-consumer generation completion with constraints, cascade, indexes, and recovery. |
| T07-REQ-03 | Run restartable idempotent canonical initial backfill that truthfully establishes post-install baseline without audit-history claims. |
| T07-REQ-04 | Replace developing rows, detect overdue windows, and atomically final-recompute, append revision 1, and create/refresh next developing work. |
| T07-REQ-05 | Append immutable corrections only for changed compatible canonical results, preserve effective selection/history, and handle revision concurrency. |
| T07-REQ-06 | Reuse existing worker, durable recovery, health, and safe logs without changing current stats or runtime topology. |
| T07-REQ-07 | Prove migration, boundaries, idempotency, crash/restart, generation concurrency, correction, privacy cascade, and current-statistics independence deterministically; run the real-process closure harness and close TEST-REPORT.md. |

Closure requires Track06 report review; migrated schema/recovery evidence; controlled
version/hash policy; restartable baseline receipts; Sunday/Monday and calendar boundary
proof; atomic/idempotent finalization; correction/no-op/revision-race proof;
two-consumer completion race proof; user-cascade/privacy proof; health/log evidence;
and exact current-stats independence evidence. The planned
`scripts/verify-track-07.sh` extends the delivered Track06 actual API process and its
same named non-daemon `bookmark-stats-refresher` only, using a disposable migrated
database and dynamic isolated port. It makes real mutation, current-stats, liveness,
and readiness flows; bounds observation of actual projection processing through
delivered configuration and observable seams; and uses supported private
database/operator inspection of working/developed/completion state, never a public
route. It proves developing replacement and current-surviving-state baseline evidence
only when those states are actually observable, verifies projection failure or disabled
mode leaves current-stats JSON body and headers correct, parses expected JSON Lines,
and proves clean shutdown and cleanup.

The process harness supplements rather than proves Sunday/Monday boundaries, backfill
restart, finalization crashes, revision or concurrent-generation races, correction
immutability, or two-consumer cleanup. Those claims require deterministic fake UTC
clocks, disposable migrated integration tests, controlled barriers, and fault
injection, with no real sleeps. The harness adds no test-only public endpoint,
scheduler, process, thread, or public history API. No critical/high defect may remain.

## 8. Edge-case and failure ledger

| Dimension | Required deterministic proof |
| --- | --- |
| Window boundaries | Sunday/Monday UTC, exact start/end exclusion, leap day, year/month crossing, and injected clock jump use the one half-open calculator. |
| Canonical data | Empty/no-data user, current/closed surviving data, deletion/tag changes, top-tag ties, and aggregate ordering use scoped canonical SQL. |
| Initial baseline | Interrupted/restarted backfill, checkpoint resume, Track06-cleared-marker bridge, no deleted-preinstall audit claim, and no unsupported empty weeks. |
| Developing/finalization | One working row, repeated replacement, overdue no-event detection, finalization crash points, atomic next-developing creation/refresh, and replay idempotence. |
| Corrections | Late delete/tag/material change appends N+1/supersession only on changed compatible hash; identical/no-op/retry append none; highest revision selection is stable. |
| Supersession integrity | A correction cannot supersede a point for another user/window or skip the immediately prior revision. |
| Calculation version | Version/hash mismatch never silently compares; deliberate top-limit/algorithm change follows recorded backfill/recompute policy. |
| Dirty concurrency | Duplicate/reordered/lost events, concurrent increment, completion ordering, crash before/at completion commit, and restart leave recovery work intact. |
| Revision concurrency | Barrier/forced unique conflict proves no duplicate revision and retry selects committed effective revision. |
| Lifecycle/health | Existing one thread/manual cycle; projection failure, stalled/backlog/overdue/baseline failure, disabled mode, restart, readiness/liveness behavior. |
| Privacy/compatibility | User deletion cascades projection rows; no IDs/content/secrets in logs; no history route; current stats remain exact and independent. |
| Observability | Parse JSON Lines for complete base/ADR-004/projection fields and events, supplied/generated safe correlation, redaction, exactly-once final-owning-boundary structured causal exceptions without locals/raw indexed text, and fail-closed formatter/redactor output. Own assertion data remains ephemeral; sentinels and cross-user data are absent from all unsafe receipt surfaces. |
| Process closure | Planned `scripts/verify-track-07.sh` extends the delivered Track06 process and same named worker with a disposable migrated database, dynamic isolated port, real mutation/current-stats/live-ready flows, bounded observable processing, private DB/operator projection-state inspection, current-stats independence on failure/disabled mode, clean shutdown, and cleanup; it adds no public history route or test-only topology. |

## 9. Risks, limits, and follow-up ownership

- Installation backfill represents only currently surviving canonical state. It cannot
  recover pre-install deleted contribution; record that limit instead of fabricating
  audit accuracy.
- SQLite, one worker, and the process-local queue/thread remain local bounded design
  and do not provide exactly-once processing. Production outbox/durable-consumer/shared
  storage evolution is outside Track07.
- Empty next developing rows created atomically for an evidenced user/window do not
  authorize empty developed history without working/dirty/canonical evidence. Stop for
  primary decision if an ADR interpretation conflicts with this distinction.
- Track08 owns final documentation, deployment evolution, seed data, bonuses, and
  final narrative. Primary engineering owns Track07 closure and TEST-REPORT.md.

## 10. Traceability

| Requirement | Track07 requirements | Planned evidence |
| --- | --- | --- |
| WIN-01 | T07-REQ-01,03,04 | UTC calculator, developing replacement, Monday boundary, no-event overdue, next-window tests. |
| WIN-02 | T07-REQ-01,04,05 | Final rev1, immutable correction/supersession, versioned hash/idempotency, late delete/tag and revision-race tests. |
| WIN-03 | T07-REQ-02,03,06,07 | Two-consumer generation migration, crash/restart/backlog/queue-loss recovery. |
| EVT-01..03 | T07-REQ-02,06,07 | Existing safe post-commit queue/worker reused; canonical duplicate/reorder-safe projection. |
| OPS-01 | T07-REQ-06,07 | One lifecycle worker, readiness backlog/overdue, service-attributed redacted logs. |
| SQL-01/SQL-02 | T07-REQ-01,06,07 | Weekly SQL remains private; required current endpoint/body remains independent and unchanged. |
