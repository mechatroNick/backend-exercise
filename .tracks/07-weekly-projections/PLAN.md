# Track 07 plan: weekly event-time projections and correction revisions

- Specification: [SPEC.md](SPEC.md), version 2.0
- Status: **Complete**
- Governing ADRs: ADR-004, ADR-005, ADR-006, ADR-009
- Active item: Closure complete — T07-09 evidence report and downstream handoff recorded

## Dependency gate

T07-01 may proceed only after the primary reviews Track 06's actual closure report,
dirty-marker migration, current completion transaction, worker/manual cycle, Settings,
raw-SQL reader, health, and logs. Stop on a missing Track 06 receipt or any conflict
with its fixed current-statistics invariants. The 2026-08-09 revival does not authorize
rewriting Track 06 or treating this plan as evidence.

| ID | Work item | Depends on | Status | Exit evidence |
| --- | --- | --- | --- | --- |
| T07-01 | Review delivered Track 06 seams and record implementation compatibility. | Track 06 closure evidence | Complete | Reviewed the delivered migration, dirty repository, mutation publisher, refresher, current raw-SQL/snapshot path, health, logs, deterministic seams, and Track 06 `TEST-REPORT.md`; ADR-009 records the compatible cutover. |
| T07-02 | Add Alembic working/point rows, singleton baseline checkpoint, and dual-completion dirty columns. | T07-01 | Complete | Migration `0003_weekly_stats_projections`; exact DDL/FK/index/cascade and populated downgrade/re-upgrade tests; guarded acknowledgement orders/reset/rollback tests; 754-test full suite and 100% branch coverage. |
| T07-03 | Implement Monday UTC calculator, scoped canonical reader, versioned compact JSON bytes, SHA-256 hash, and effective-revision selection. | T07-01, T07-02 | Complete | Private `weekly.py` and `projection_repository.py`; UTC/boundary/owner/order/injection/version/hash/immutable-revision tests; 774-test suite and 100% branch coverage. |
| T07-04 | Implement bounded restartable surviving-data user-page backfill and checkpoint status. | T07-02, T07-03 | Complete | Exclusive user/window checkpoint paging, resume/rewind/rollback, surviving-data/no-empty-week behavior, version failure, dirty noninterference, and `source_generation=0`; 802-test full suite and 100% branch coverage. |
| T07-05 | Implement developing replacement, overdue detection, finalization, and next-window creation. | T07-03, T07-04 | Complete | Exact-boundary atomic finalization, fresh canonical recalculation, guarded working deletion, pending-dirty deferral, next-current creation, and multi-week/no-empty-intermediate proof. |
| T07-06 | Implement append-only late corrections and projection generation completion. | T07-02 through T07-05 | Complete | No-op and zero corrections, A-B-A immediate predecessors, real barrier revision/generation races, stale rollback/retry, fault and user-cascade proof; 831-test suite and 100% branch coverage. |
| T07-07 | Integrate the existing worker, readiness, and redacted observability without changing current stats. | T07-04 through T07-06 | Complete | Same named worker and isolated short sessions; default-enabled baseline/dirty processing, disabled retention, projection-only failure/recovery, authoritative readiness, safe logs, current/liveness/API independence; 855-test suite and 100% branch coverage. |
| T07-08 | Run deterministic, migrated-database, and real-process evidence. | T07-02 through T07-07 | Complete | Continuous `bash scripts/verify-track-07.sh` receipt at `08a86b3`: inherited Track 06, focused selectors, quality gates, 862 tests plus 3 subtests, 100% branch coverage, migration lifecycle, and real-process evidence passed. |
| T07-09 | Produce closure report and downstream integration handoff. | T07-01 through T07-08 | Complete | Truthful `TEST-REPORT.md` records the actual receipt and incremental ledger; Tracks 08/09 are explicitly handed off as reopened/stale pending their own update and validation. |

## Evidence ledger

| Area | Required proof |
| --- | --- |
| Calendar/canonical data | Sunday/Monday bounds, leap/month/year boundaries, owner scope, top-tag ties, ordering, empty data, and multi-week jump with no empty intermediate weeks. |
| Baseline | Bounded page checkpoint, restart/crash, surviving-data-only bridge, no deleted-preinstall claim, no empty historical series. |
| Lifecycle/corrections | One developing row, overdue no-event detection, finalization replay/crash, changed correction, unchanged/no-op replay, immediate predecessor. |
| Version/hash | Compact UTF-8 canonical bytes; domain-separated SHA-256; comparison only within version; mismatch degrades readiness and cannot auto-write; later explicit recompute is restartable and append-only. |
| Concurrency/recovery | Lost/duplicate events, both consumer orders, concurrent generation, completion crash, revision conflict, restart. |
| Compatibility | User cascade; no history route; default-enabled projection; disabled marker retention; current-statistics body/header parity when projection fails or is disabled; readiness versus liveness. |
| Observability | Safe low-cardinality JSON Lines; no IDs/content/payload/hash/SQL/secrets; baseline/backlog/overdue/failure completion events. |

## Validation and completion rule

At implementation, use fake UTC clocks, manual cycle controls, disposable migrated
SQLite databases, barriers, and fault injection—never wall-clock sleeps for calendar
or race claims. Run the focused and full project checks, Alembic lifecycle checks,
`bash scripts/verify-track-07.sh`, `bash scripts/verify-docs.sh`, and `git diff --check`.
Record only commands actually run in `TEST-REPORT.md`.

The downstream Track 08/09 documents are outside this plan's write scope. They remain
active pre-revival records, are stale for this completed dependency, and must be
reopened/updated at the later integration checkpoint. This closure does not claim that
downstream update, post-merge verification, or any final-track validation.
