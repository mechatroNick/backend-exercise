# ADR-009: Track 07 weekly-projection revival

- Status: Accepted
- Date: 2026-08-09
- Decision owners: Repository owner
- Affected tracks: 07; downstream integration required for 08 and 09
- Supersedes: Only the 2026-08-06 Track 07 skip disposition
- Superseded by: None

## Context

ADR-005 selected event-time weekly windows and append-only corrections, but Track 07
was later placed out of scope. The repository owner has now authorized implementation
planning again. Existing Track 06 current-statistics behavior is already accepted and
must remain independent.

## Decision

Track 07 is **In progress**. ADR-005 is selected for implementation, subject to the
Track 06 closure/seam gate and ADR-006 evidence rules. The prior skip remains an
append-only historical record; this ADR supersedes only its active disposition.

Weekly projections are private: no public history route is added. Use the fixed
event-time Monday UTC half-open lifecycle, developing replacement, immutable developed
revisions, immediate-predecessor corrections, user cascade, durable baseline checkpoint,
and two-consumer generation completion defined by the Track 07 v2.0 specification.
Canonical compact UTF-8 JSON is schema-wrapped/versioned and hashed with domain-
separated SHA-256. Calculation version includes algorithm, schema, and
`TOP_TAGS_LIMIT`; cross-version hashes are incomparable and version changes require a
deliberate scoped recompute with append-only corrections. A stored/runtime version
mismatch fails projection readiness; it cannot auto-rewrite or auto-append and needs a
future explicit restartable recomputation decision.

`STATS_PROJECTION_ENABLED` defaults to `true`. With current refresh enabled and
projection disabled, durable markers remain pending and readiness degrades, while
liveness and current statistics remain correct. On a multi-week clock jump, finalize
only evidenced working windows, create the window containing now, and skip empty
intermediate weeks.

## Consequences

- Track 06 one-worker/current-statistics invariants remain fixed. Projection problems
  degrade readiness but not liveness or `/api/bookmarks/stats` correctness.
- There is no implementation, migration, test report, or Track 07 harness evidence at
  this governance checkpoint.
- Track 08 and Track 09 documents retain historical pre-revival claims until a later,
  separately reviewed downstream integration checkpoint reopens and updates them.

## Evidence required before completion

The future implementation must provide deterministic migration, lifecycle, race,
recovery, privacy, and compatibility tests; a real-process harness; and a truthful
Track 07 `TEST-REPORT.md`. Documentation validation alone cannot establish runtime
behavior.
