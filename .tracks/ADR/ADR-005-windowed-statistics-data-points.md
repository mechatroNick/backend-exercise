# ADR-005: Windowed statistics data-point lifecycle

- Status: Accepted
- Date: 2026-08-05
- Decision owners: Repository owner
- Affected tracks: 06, 08; Track 07 skip record
- Affected SPEC versions: Baseline
- Supersedes: ADR-004 open question about snapshot versus historical persistence
- Superseded by: None
- Implementation disposition: **Not selected; Track 07 skipped by owner on 2026-08-06**

> This ADR remains an accepted design record for possible future revival. Its weekly
> tables, consumers, backfill, and correction revisions are not part of the delivered
> scope. Track 06 current-only generation completion is terminal.

## Context

ADR-004 defines the post-commit event queue and configurable ten-second background
statistics service. The repository owner has clarified that persistence depends on
the lifecycle of a time-window data point:

- A `developing` data point belongs to an open time window and is recalculated.
- A `developed` data point belongs to a closed time window and is appended as an
  immutable historical observation.

The ten-second thread interval is a batching and recalculation cadence. It is not the
historical data-point resolution. The accepted historical resolution is one UTC
Monday-to-Monday event-time week over immutable bookmark `created_at`.

## Decision established so far

- Model the lifecycle explicitly as `DEVELOPING` and `DEVELOPED` rather than treating
  every refresh tick as an append.
- Maintain at most one mutable developing row per user and logical window.
- Recalculate a developing row from canonical bookmark tables using the statistics
  raw-SQL reader after coalesced invalidation events.
- At the window boundary, perform a final canonical recalculation, append the
  developed point, and create the next developing window atomically.
- Never update a developed row during ordinary projection processing.
- Do not append a new historical row every ten seconds. Repeated refreshes within an
  open window replace the developing calculation.
- Use UTC half-open windows: `window_start <= timestamp < window_end`.
- Keep the current all-time `/api/bookmarks/stats` response and its live raw-SQL
  fallback separate from historical window points. The assessment endpoint remains
  correct even when historical projection processing is delayed.
- Retain all developed weekly revisions for the local assessment dataset. No public
  history endpoint is added because the assessment does not request one.
- If user deletion is added later, deletion cascades through working, dirty, and
  developed statistics rows as a privacy exception to ordinary immutability.

## Event-time design

The accepted interpretation is that a weekly point summarizes bookmarks whose
immutable `created_at` falls in a UTC Monday-to-Monday window.

```text
ABSENT
  -> DEVELOPING

DEVELOPING
  -> DEVELOPING
     event batch: recalculate and replace working result

DEVELOPING
  -> DEVELOPED revision 1
     window closes: final calculation and append

DEVELOPED revision N
  -> DEVELOPED revision N+1
     late change affects the closed window and changes its result
```

Immutable does not mean uncorrectable. Deleting a bookmark
or changing its tags after its creation week has closed can change the truthful
aggregate for that historical week. The proposed policy is therefore:

- preserve every developed row unchanged;
- append a correction revision for the same user/window;
- link it to the superseded revision;
- select the latest revision as effective historical truth;
- append nothing when a deterministic content hash is unchanged.

A durable dirty-window marker written in the same transaction as a late mutation is
required in addition to the in-memory queue. Otherwise, a crash between commit and
queue publication could permanently lose a correction, especially after deletion.

## Persistence model

### Developing working row

```text
bookmark_stats_window_working
- user_id
- window_start
- window_end
- payload
- calculated_at
- source_generation
- calculation_version
- content_hash
```

Unique key: `(user_id, window_start)`.

### Developed immutable revision

```text
bookmark_stats_window_point
- id
- user_id
- window_start
- window_end
- revision
- supersedes_id
- payload
- calculated_at
- developed_at
- correction_reason
- source_generation
- calculation_version
- content_hash
```

Required uniqueness includes `(user_id, window_start, revision)` and a content
identity that makes retries idempotent.

### Durable dirty marker

```text
bookmark_stats_window_dirty
- user_id
- window_start
- generation
- reason
- first_marked_at
- last_marked_at
```

Unique key: `(user_id, window_start)`. Marker completion is generation-safe. Because
Track 07 is skipped, only the current-snapshot consumer is installed: successful
canonical recomputation may complete and remove its observed generation under
ADR-004, while a concurrent increment remains pending. The historical backfill and
dual-consumer protocol described by this ADR are archived and not implemented.

## Rejected alternative: observation-time snapshot

A weekly point could instead mean "all current statistics as observed at the end of
this week." That point is an audit observation, not an aggregate of activity that
occurred within the week.

Under observation-time semantics:

- the point is naturally immutable;
- later changes do not create correction revisions because they do not change what
  was observed at the original time;
- the point must be labelled with `as_of` semantics;
- historical rows cannot answer how many bookmarks were created in a particular
  week.

## Alternatives considered

| Alternative | Benefits | Costs and risks | Position |
| --- | --- | --- | --- |
| Event-time windows with correction revisions | Historical aggregates remain correct and revisions are auditable | Requires dirty markers, revision selection, and more tests | Selected |
| Observation-time weekly snapshots | Simple immutable history | Answers a different business question | Rejected by the accepted event-time definition |
| Update developed rows in place | Simple latest view | Contradicts append-only developed semantics | Rejected |
| Append every ten seconds | Maximum observation detail | Rapid growth and little assessment value | Rejected |
| Ignore late changes to event-time windows | Simple finalization | Closed aggregates become incorrect | Rejected |

## Consequences of the recommended interpretation

### Positive

- Developing and developed semantics are explicit.
- Historical aggregates can be corrected without destroying prior observations.
- Queue retries and projection finalization can be idempotent.
- The ten-second background cadence does not cause unbounded historical growth.

### Negative and risks

- Adds working, developed, and durable-dirty persistence concepts beyond the base
  assessment.
- Every stats-affecting mutation must identify and mark the correct original window.
- Historical reads must select the latest revision by default.
- Calculation changes and `TOP_TAGS_LIMIT` changes require a new calculation version
  and deliberate recomputation.
- User deletion must cascade through historical data as a privacy exception to
  ordinary immutability.

### Follow-up

- Test UTC boundaries, atomic finalization, late deletes, correction idempotency,
  queue-loss recovery, and selection of the latest effective revision.
- Revisit retention only if measured local data growth or a future history API
  creates an actual requirement.

## Evidence and references

- [ADR-004](ADR-004-event-driven-statistics-service.md)
- [Assessment](../../docs/Technical%20Assessment%20Senior%20Software_Engineer.pdf)
