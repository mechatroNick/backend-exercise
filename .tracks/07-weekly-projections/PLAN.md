# Track 07 plan: weekly event-time projections and correction revisions

- Specification: [SPEC.md](SPEC.md), version 1.0
- Status: Planned (implementation-gated)
- Active item: None; Track06 closure TEST-REPORT.md is required first

## Dependency gate and intent check

Before code, primary verifies Track06 is Complete, reads its actual closure report and
delivered migration/worker/marker/seam behavior, and confirms the committed staged
completion rule: canonical initial historical backfill first, then two installed
consumers complete the same observed generation before cleanup. Stop on a mismatch,
missing Track06 evidence, or a proposed public/current-statistics change.

| ID | Work item | Owner | Depends on | Status | Exit evidence |
| --- | --- | --- | --- | --- | --- |
| T07-01 | Verify Track06 closure and delivered seams; confirm staged consumer completion, Settings, raw SQL, and lifespan compatibility. | Smith / implementation | Track06 Complete plus TEST-REPORT.md | Blocked | Gate receipt; no unresolved durable-contract or current-stats conflict. |
| T07-02 | Create/review migration for working/developed tables and installed two-consumer dirty completion. | Smith / implementation | T07-01 | Pending | Empty/existing upgrade, DDL/FK/cascade/key/index, completion-state, rollback, downgrade/re-upgrade, recovery. |
| T07-03 | Implement UTC week calculator, parameterized weekly reader, deterministic versioned payload/hash, and effective-revision selection. | Smith / implementation | T07-01, T07-02 | Pending | Monday/calendar/owner/ordering/hash/version tests; no public route. |
| T07-04 | Implement restartable idempotent canonical initial historical backfill and baseline checkpoint semantics. | Smith / implementation | T07-02, T07-03 | Pending | Closed surviving rev1/current developing baseline, restart/partial crash, Track06 bridge, no-audit/no-empty-week proof. |
| T07-05 | Implement developing replacement, overdue detection, atomic boundary finalization, and next developing creation/refresh. | Smith / implementation | T07-03, T07-04 | Pending | One-row replacement, no-event/clock-jump behavior, rev1/next transaction, finalization replay/crash proof. |
| T07-06 | Implement late corrections, immutable supersession/revision allocation, and projection-side marker completion. | Smith / implementation | T07-02, T07-03, T07-04, T07-05 | Pending | Changed-hash N+1, identical/no-op no append, revision race, concurrent generation, guarded cleanup, restart. |
| T07-07 | Integrate with existing worker/manual cycle, readiness metrics, and redacted logs; retain current-stats independence. | Smith / implementation | T07-04, T07-05, T07-06 | Pending | One-thread/session/non-overlap, health backlog/overdue/baseline, safe logs, current stats parity. |
| T07-08 | Run deterministic migration, concurrency, failure, lifecycle, and regression evidence. | Smith / implementation | T07-02, T07-03, T07-04, T07-05, T07-06, T07-07 | Pending | Full ledger with fake clock/manual cycle/barriers; quality/hygiene receipts. |
| T07-09 | Primary closure, Track08 handoff, and TEST-REPORT.md. | Primary engineering thread | T07-01, T07-02, T07-03, T07-04, T07-05, T07-06, T07-07, T07-08 | Pending | Traceability complete, risks/limits recorded, no critical/high defect, actual commands/results. |

## Work-wave detail

### T07-01/T07-02 — gate and durable schema protocol

- Inspect Track06 exact migration/repository API rather than assuming column or
  transaction names. Preserve marker upsert and current-completion ownership.
- Add working and immutable point rows only after review. Prove UTC window/revision
  constraints, user/self FKs, cascade privacy cleanup, access indexes, and compatibility
  with Track06 databases.
- Extend marker completion with two private per-consumer generation values. Existing
  rows migrate with zero/incomplete completion values; dirty generations remain
  positive and migration must not blanket-mark existing work complete. Baseline and
  normal consumer cycles reconcile rows before two-consumer deletion is enabled.
  Completion observes generation g; deletion requires generation g and both completion
  values g. Projection writes and its completion become durable only on the same
  successful transaction commit.

### T07-03/T07-04 — canonical weekly baseline

- Isolate weekly raw SQL in statistics code, bind parameters, scope by user and
  half-open window, and reuse aggregate semantics without a route. Canonical bytes
  plus calculation version determine hash; never compare across versions.
- Backfill only surviving canonical data: closed windows get rev1; current-window
  evidence gets developing. Use restartable checkpoints and bounded transactions;
  repeat/catch-up selects same version/hash state without duplicate append. Never claim
  deleted pre-install audit history or create empty historical calendar weeks. Reserve
  source generation zero for this installation baseline; observed dirty generations
  begin at one.

### T07-05/T07-06 — lifecycle and correction semantics

- Recompute/replace developing rows. Detect overdue window without a queue event; on
  closure final recompute, append rev1 once, and atomically create/refresh next
  developing row as ADR-005 requires. Retry/crash behavior remains idempotent.
- A late material change uses original creation window and appends linked N+1 only when
  effective version-compatible hash changes. Unique conflicts reload effective state;
  no old revision is edited and duplicate/reordered/no-op work appends nothing.
- After baseline completes, projection completion joins Track06 current completion. Do
  not remove a marker after only one consumer succeeds.

### T07-07/T07-09 — operations, regressions, closure

- Add work to existing named worker/manual cycle only: no scheduler/process/queue,
  request session, or import-time service. Preserve bounded sessions, batches, stop,
  join, and one-worker behavior.
- Readiness receives safe baseline/backlog/overdue/projection freshness state; liveness
  remains independent. Logs retain structured service attribution and low cardinality:
  no user/window IDs, payload/hash, SQL, content, credentials, or secrets.
- Primary proves internal weekly work leaves current stats independent, records actual
  migration/test/health/log evidence, and hands final hardening only to Track08.

## Deterministic edge-case/evidence ledger

| Area | Cases and planned proof |
| --- | --- |
| UTC calendar | Sunday/Monday exact bounds, leap day, month/year crossing, clock jump use one half-open calculator. |
| Baseline | Empty/no-data user, surviving closed/current data, interrupted/restarted chunks, checkpoint resume, Track06 bridge, no deleted-preinstall claim, no empty series. |
| Developing/finalization | Repeated replacement, one-row uniqueness, no-event overdue detection, atomic rev1/next transition, crash points, idempotent retry. |
| Late correction | Delete/tag/material late changes, changed hash append/supersession, identical/no-op/reordered retry no append, effective highest revision, same-user/window immediate-predecessor integrity, unique revision race. |
| Version policy | Top-tag limit/algorithm transition never compares old/new hash; explicit controlled recompute/backfill is required. |
| Completion/recovery | Both completion orders, concurrent generation barrier, crash before/at commit, duplicate/lost events, backlog/restart, guarded deletion retain new work. |
| Migration/privacy | Empty/existing upgrade, constraints/FKs/indexes/cascade, downgrade/re-upgrade, user cascade through working/dirty/points. |
| Worker/health/logs | Existing one thread/manual cycle/own session; failure/stuck/backlog/overdue/baseline state, readiness/liveness, disabled mode, safe logs. |
| Compatibility | No history endpoint/OpenAPI path; required current stats JSON/source behavior is unchanged despite projection failure. |

## Planned validation commands

Run after Track06 establishes actual tooling; record exact output, paths/selectors,
migration DDL inspection, health responses, and blocked commands in TEST-REPORT.md.

    uv sync --locked
    uv run ruff format --check .
    uv run ruff check .
    uv run mypy app
    uv run pytest tests/unit tests/integration tests/contract -k 'weekly or projection or dirty or stats or health or lifecycle'
    uv run pytest
    uv run alembic upgrade head
    uv run alembic downgrade -1
    uv run alembic upgrade head
    uv run alembic check
    make check
    git diff --check
    git status --short

Focused tests use fake UTC clocks, manual worker-cycle controls, disposable migrated
SQLite databases, failure injection, and barriers. They must not use real ten-second
waits or timing-dependent scheduler assertions. Add exact payload/hash, DDL, race, and
current-stats-independence checks when implemented; never mark planned commands passed.

## Review checkpoints and commit boundary

1. Track06 report/staged completion gate; 2. schema/completion protocol; 3. weekly
SQL/window/hash/version; 4. baseline limitations/restart; 5. finalization/correction/
revision race; 6. worker/health/current-independence; 7. primary closure/Track08 handoff.

Preferred green-boundary commit: feat: add durable weekly statistics projections.
Do not commit secrets, payload/user content, generated databases/caches/coverage, a
public history route, queue/topology redesign, bonuses, final narrative, or failing
intermediate state.
