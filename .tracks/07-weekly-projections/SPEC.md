# Track 07 specification: weekly event-time projections and correction revisions

- Status: **Complete**
- Specification version: 2.0
- Originally planned: 2026-08-05
- Revived: 2026-08-09
- Owner: Primary engineering thread
- Depends on: Track 06 Complete with reviewed closure evidence
- Governing ADRs: ADR-004, ADR-005, ADR-006, ADR-009
- Assessment requirements: WIN-01 and WIN-02; preserves WIN-03 and the current-statistics boundaries

## Intent and scope

The 2026-08-09 repository-owner revival supersedes only the prior Track 07 skip
disposition. It authorizes implementation planning and dependency review; it is not
implementation, test, migration, harness, or closure evidence. ADR-005's event-time
weekly design is selected for implementation. `/api/bookmarks/stats` remains the
canonical all-current, user-scoped view, and no public history route or OpenAPI
operation is in scope.

Track 06's one-worker, named non-daemon `bookmark-stats-refresher`, canonical raw-SQL
fallback, current snapshot behavior, liveness, and generation-safe current completion
remain fixed. Projection failure, backlog, incompleteness, or overdue state degrades
readiness only; it must not affect liveness or current-statistics correctness, JSON,
or headers.

## Persistence and canonical payload contract

- Add private `bookmark_stats_window_working` rows at unique `(user_id, window_start)`
  grain and append-only `bookmark_stats_window_point` revisions at unique
  `(user_id, window_start, revision)` grain. User deletion cascades through working,
  dirty, and point rows. A correction points only to the immediate predecessor for the
  same user/window; the effective point is the highest valid revision.
- Windows are UTC `[Monday 00:00:00Z, next Monday 00:00:00Z)`. The canonical weekly
  aggregate includes `total_bookmarks`, `total_tags`, deterministically ordered
  `top_tags`, and deterministically ordered `bookmarks_per_month`, calculated from
  surviving canonical bookmarks whose immutable `created_at` is in that window.
- Persist a private canonical JSON payload with an explicit schema wrapper and schema
  version. Serialize stable key/array order as compact UTF-8 bytes. `content_hash` is
  SHA-256 over domain-separated calculation-version text and those exact bytes.
- `calculation_version` explicitly identifies the aggregate algorithm, payload schema,
  and `TOP_TAGS_LIMIT`. Compare hashes only inside the same version. A version change
  or stored/runtime mismatch fails projection readiness and requires a future explicit,
  restartable recomputation decision. It never auto-rewrites or auto-appends solely for
  a mismatch; any later authorized recompute remains append-only for developed history.

## Baseline, lifecycle, and durable completion

Before normal projection consumption, install a durable singleton baseline checkpoint
with observable status. A bounded, restartable, user-page backfill scans only surviving
canonical data. Closed windows get revision 1; current-window evidence gets a
developing row; empty elapsed weeks and deleted pre-install data are not synthesized.
Baseline rows use `source_generation = 0`; observed dirty-marker generations are
strictly positive. A multi-week clock jump finalizes only evidenced working windows,
creates the window containing now, and skips empty intermediate weeks.

Extend durable dirty rows with `current_completed_generation` and
`projection_completed_generation`, initialized to zero. For observed generation `g`,
each consumer guarded-completes only the row still at generation `g`. Remove a marker
only when its generation and both completion values equal `g`, in a successful durable
transaction. A newer increment therefore stays pending, and a crash before projection
durability is recoverable. Developing rows are replaced; boundary finalization appends
revision 1; late material changes append a correction only when the compatible
canonical payload changed.

`STATS_PROJECTION_ENABLED` defaults to `true`. If current refresh remains enabled but
projection is disabled, retain durable markers and report readiness degraded; current
statistics remain correct and live independently.

## Acceptance evidence and stop conditions

Implementation must prove migrations and FK/cascade behavior; Monday boundaries;
stable payload/hash/version behavior; restartable baseline; idempotent developing,
finalization, and correction paths; revision and generation races; projection
failure/readiness versus liveness/current-stats independence; JSON-Line safe logs; and
no public history surface. Completion additionally requires deterministic tests, a
real-process `scripts/verify-track-07.sh`, and a truthful `TEST-REPORT.md` under
ADR-006. Those deterministic, migration, and real-process receipts were completed by
the continuous Track 07 verification run recorded in `TEST-REPORT.md` at commit
`08a86b3`; this track is **Complete**. That receipt does not claim a post-merge run
or downstream Track 08/09 validation.

Stop for ADR/owner review before changing event-time semantics, immutability,
supersession, marker generation semantics, user-cascade privacy behavior, Track 06
current-statistics contracts, or adding a public history surface.

## Downstream integration boundary

Track 08 has now consumed this dependency and passed its clean-source/Docker integration
at `d6c08e0`. Track 09's historical receipt preserves the former skip/absence state,
while its active control plane now records a passing report-bundle and clean branch
validation. Track 09's independent review, non-fast-forward merge, and exact merged-main
rerun also passed. This Track 07 report does not claim an external push itself; the
current Track 09 record separately observes the configured origin at merged main.
