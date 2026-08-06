# Track 06 history

## 2026-08-06 — Dependency gate closed and implementation authorized

- Verified Track 05 Complete on merged `main` at `001056c`. Its report records 473
  tests, 100% statement/branch coverage, the exact 79-node mandatory selector, clean
  migration lifecycle, and the passing real-process harness with no critical/high
  defect. Primary post-merge Track 05 harness, documentation, and cleanup checks also
  passed.
- Completed T06-01 read-only compatibility and architecture review across delivered
  transaction/publisher, canonical raw-SQL, Settings, lifespan, logging, migration,
  contract, and harness seams. No incompatible seam or unowned public-contract change
  was found.
- Authorized implementation on `codex/track-06-event-driven-stats`; set the track
  **Ready**, T06-01 **Complete**, and T06-02 **In progress**. This status authorizes
  work but makes no implementation or acceptance claim.
- Added the reviewed high-risk invariant: a candidate snapshot requires local
  invalidation-epoch and observed durable-generation agreement during finalization,
  so a concurrent mutation cannot make a computed-old snapshot observable even when
  conditional marker deletion correctly fails.
- Preserved current-only completion before Track 07. Track 07 must activate retention,
  perform canonical backfill, then transition to dual-consumer completion without a
  concurrent-write gap; no historical table or API is authorized in Track 06.

## 2026-08-05 — Sequential planning started

- Planned Track 06 after committed Track 05 planning record (`47864e7`) and the
  accepted ADR-001/004/005 design. No product source, dependencies, migration,
  schema, queue, worker, lifecycle, health route, or external action occurred.
- Marked the track **Planned (implementation-gated)** and its first work item
  **Blocked**: Track 05 must be Complete with mandatory core quality evidence and no
  known critical/high defect before this optional runtime is implemented.
- Preserved Track 04's current statistics raw-SQL result as correctness authority:
  snapshots are optional accelerators and all missing/stale/disabled/unhealthy paths
  must synchronously use the same user-scoped reader and exact JSON body.
- Assigned durable dirty-marker creation, same-transaction generation increment,
  safe post-commit invalidation, bounded queue recovery, lifecycle worker, snapshots,
  health, and logs to Track 06. Kept working/developed weekly data, corrections, and
  history APIs out of scope for Track 07.

## ADR-005 staged consumer clarification

Reconciled ADR-004 current cleanup with ADR-005 historical projection using an
installed-consumer rule. Track 06 may complete a generation after successful canonical
current recomputation while no historical consumer exists. Track 07 must first run a
canonical historical backfill, then require both current and historical consumers to
complete the observed generation before cleanup. This changes no public statistics or
weekly event-time semantics and prevents unbounded inert markers before Track 07.

## Current state

- Specification: Planned, version 1.1
- Plan: Planned; T06-01 Blocked on Track 05 closure
- Implementation: Not started; dependency-gated
- Material product questions: None known

## Next action

After Track 05 closes with actual `TEST-REPORT.md` evidence, execute T06-01 to compare
delivered publisher, transaction, raw-SQL, Settings, lifespan, and logging seams and
confirm the staged completion handoff remains traceable before writing product code.

## 2026-08-05 — Shared verification-gate adoption

- Adopted the committed shared logging, deterministic-test, and real-process closure
  gate in Track 06 planning only. Status, task IDs/dependencies, marker generations,
  transaction/publication ordering, current-stats fallback contract, one-worker
  topology, ADR-004 log-field contract, and the Track 07 staged handoff remain
  unchanged.
- Planned (but did not create or run) `scripts/verify-track-06.sh` to extend the
  delivered Track 05 mandatory bootstrap with a disposable migrated database, dynamic
  isolated port, actual API process and named non-daemon refresher thread, real HTTP
  mutation/current-stats/header/live-ready flows, bounded worker
  completion/degradation/recovery observation, snapshot/live parity, queue/dirty
  recovery, clean shutdown, and cleanup.
- Retained fake-clock/manual-cycle/barrier/fault-injection tests as the required proof
  for generation and concurrency invariants; the future process harness supplements
  rather than proves those claims, and no real ten-second sleep is planned.
- No Track 06 test, application process, migration, harness, runtime validation, or
  `TEST-REPORT.md` receipt was executed or created by this planning-only change.

## 2026-08-06 — Incremental verification-governance planning correction

- Bumped the SPEC/PLAN planning contract to version 1.1 and added ADR-006 to the
  governing evidence/closure records; Track 06 remains Planned (implementation-gated)
  and T06-01 remains Blocked on Track 05 Complete.
- Completed inherited and ADR-004 JSON Lines evidence, safe-correlation, redaction,
  causal exactly-once owning-boundary exception, health, and safe assertion-output
  rules without changing current-stats raw-SQL authority, marker/generation/event
  ordering, worker/health routes, or the Track 07 staged handoff.
- This correction is planning only: no Track 06 test, process, migration, harness,
  runtime validation, artifact, or `TEST-REPORT.md` receipt was created or executed.
