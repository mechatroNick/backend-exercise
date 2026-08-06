# Track 06 history

## 2026-08-07 — T06-06 health/readiness checkpoint complete

- Stabilized the exact public health surface in commit `5b4e489`: static
  unauthenticated `/health/live` and database/service-aware `/health/ready`, both
  cache-disabled and limited to fixed redacted response bodies.
- Readiness now fails closed across database/probe/session cleanup, missing or
  malformed worker/publisher state, startup and shutdown failures, dead/stuck/overdue
  work, never-successful or stale reconciliation, consecutive failures, reconciliation
  suspicion, dirty backlog count/age, and future-clock evidence. Disabled refresh
  intentionally requires the database only.
- Added transition-only low-cardinality JSON readiness logs plus distinct refresher
  started/retrying events with lifecycle instance, interval, queue/count/age, and
  failure telemetry. No user, resource, content, SQL, path, credential, token, or raw
  exception detail is returned or added to the new log contexts.
- Expanded the controlled public contract to 10 operations and 37 documented status
  pairs, including runtime schema validation for ready `200`/`503` and explicit
  unauthenticated OpenAPI evidence.
- Primary validation passed: Ruff format/check, strict `mypy app`, 601 tests plus
  three generated subtests, 2,461 statements and 516 branches at 100%, and
  `git diff --check`. Independent Scout review returned PASS with no critical, high,
  or medium finding; its fractional-time hardening observation was fixed and
  independently rechecked before commit.
- T06-07 is now active. The real-process harness, complete deterministic ledger,
  migration lifecycle, cleanup evidence, and final Track 06 report remain open.

## 2026-08-06 — T06-04 and T06-05 serving/lifecycle checkpoints complete

- Stabilized bounded invalidation and immutable serving in commits `38539c8` and
  `58eaa08`. Publication invalidates a per-user epoch before one nonblocking enqueue,
  overflow/failure remains total and recoverable, snapshot reads are atomic, and
  every untrusted source falls back to the unchanged canonical raw-SQL body.
- Stabilized the lifecycle-owned refresher in commit `3de2c76`: one exact named
  non-daemon thread, interruptible cadence, one session per non-overlapping cycle,
  bounded user cursor and dirty backlog, epoch-conditional reconciliation
  acknowledgment, generation-safe delete/CAS/commit ordering, and deferred engine
  disposal after a join timeout.
- Added deterministic and migrated-SQLite evidence for lost/duplicate hints, baseline
  generation zero, multi-batch backlog, reconciliation-epoch and generation races,
  CAS rejection, compute/publication/commit/rollback/close failure, prior-snapshot
  retention, lifecycle startup/stop, and disabled live-only composition.
- Closed the independent gate's backlog-acknowledgment, prior-snapshot retention,
  shutdown resource-ordering, and CAS-test findings. The post-fix verdict is **PASS**
  with no critical/high/medium issue in T06-05 scope.
- Actual final checkpoint evidence: 556 tests plus three generated subtests passed;
  repository statement and branch coverage both remained 100%; Ruff format/check,
  mypy, and diff checks passed. The sole warning remains the known Starlette
  TestClient/httpx deprecation.
- Marked T06-04 and T06-05 **Complete** and advanced T06-06 to **In progress**. Health
  routes/readiness decisions, their JSON-Line audit, and the process harness remain
  explicit unclosed gates.

## 2026-08-06 — Track 07 skip incorporated

- Replaced the staged future historical-consumer handoff with terminal current-only
  generation completion after the owner skipped Track 07.
- Confirmed that Track 06 will not add weekly working/developed tables, backfill,
  dual-consumer completion, correction revisions, or a history API.
- Changed the closure handoff to Track 08, which consumes Track 06 evidence plus the
  explicit Track 07 skip/absence record.
- This control-plane update does not change Track 06's current statistics body,
  raw-SQL authority, event ordering, worker topology, or verification threshold.

## 2026-08-06 — T06-03 transaction and typed-event checkpoint complete

- Stabilized commit `4768ceb` with the frozen, content-free
  `BookmarkStatsInvalidated` DTO, bounded mutation/publication enums, typed total
  publisher port, and deterministic UUID-correlation factory injection.
- Integrated one dirty upsert into the request-owned transaction for material create,
  scalar/tag/mixed patch, and delete; each path builds its detached result/event,
  commits once, then makes exactly one typed publication attempt. Reads and semantic
  no-ops remain inert, and delete uses the pre-delete creation window.
- Added real migrated-SQLite proof that a publisher observes committed canonical state
  and its marker from another session, and that failure after a real dirty upsert
  rolls both bookmark and marker back with no publication. Safe unavailable outcomes
  preserve the successful result.
- Focused Ruff, mypy, and 73 tests passed. Full coverage execution passed 509 tests
  plus three generated subtests at 100% statements and branches. Independent post-fix
  audit is **PASS** with no critical/high/medium defect.
- Marked T06-03 **Complete** and advanced T06-04 to **In progress**. Concrete queue
  totality, overflow logging/reconciliation, snapshot invalidation, and lifespan
  installation remain explicit T06-04/T06-05 gates.

## 2026-08-06 — T06-02 durable invalidation checkpoint complete

- Stabilized commit `bf7546f` with the sole Track 06 dirty-marker migration, matching
  SQLModel metadata, and a caller-session-owned repository. The atomic SQLite upsert
  increments generation without read-then-write, preserves the first mark, and
  updates only bounded reason and the final mark.
- Added fixed-width UTC timestamps, schema-enforced Monday-midnight windows, strict
  corruption handling, composite-key and generation-conditional completion, typed
  bounded observations/backlog, cascade behavior, and query-shape indexes.
- Closed independent audit findings for fractional-second lexical misordering,
  persisted-key normalization, stale-generation deletion, conditional-delete
  rollback, and restart recovery. The post-fix independent verdict is **PASS** with
  no critical/high/medium blocker.
- Actual focused evidence: Ruff and mypy passed; 22 migration/repository/metadata
  tests passed; upgrade from an existing core schema, downgrade to `0001`, re-upgrade,
  and `alembic check` passed in a disposable database. Full coverage execution passed
  484 tests plus three generated subtests at 100% statements and branches.
- Marked T06-02 **Complete** and advanced T06-03 to **In progress**. No event,
  publisher, worker, snapshot, health, or Track 07 behavior is claimed by this
  checkpoint.

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

## ADR-005 staged consumer clarification (superseded by Track 07 skip)

Reconciled ADR-004 current cleanup with ADR-005 historical projection using an
installed-consumer rule. Track 06 may complete a generation after successful canonical
current recomputation while no historical consumer exists. Track 07 must first run a
canonical historical backfill, then require both current and historical consumers to
complete the observed generation before cleanup. This changes no public statistics or
weekly event-time semantics and prevents unbounded inert markers before Track 07.

## Historical state at 2026-08-05 planning

- Specification: Planned, version 1.1
- Plan: Planned; T06-01 Blocked on Track 05 closure
- Implementation: Not started; dependency-gated
- Material product questions: None known

## Historical next action

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
