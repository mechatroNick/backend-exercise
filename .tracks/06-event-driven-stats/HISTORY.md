# Track 06 history

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

- Specification: Planned, version 1.0
- Plan: Planned; T06-01 Blocked on Track 05 closure
- Implementation: Not started; dependency-gated
- Material product questions: None known

## Next action

After Track 05 closes with actual `TEST-REPORT.md` evidence, execute T06-01 to compare
delivered publisher, transaction, raw-SQL, Settings, lifespan, and logging seams and
confirm the staged completion handoff remains traceable before writing product code.
