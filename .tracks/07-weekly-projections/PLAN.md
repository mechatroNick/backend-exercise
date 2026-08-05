# Track 07 plan: weekly event-time projections and correction revisions

- Specification: [SPEC.md](SPEC.md), version 1.1
- Governing ADRs: ADR-001, ADR-004, ADR-005, ADR-006
- Status: Planned (implementation-gated)
- Active item: None; Track06 closure TEST-REPORT.md is required first

## Dependency gate and intent check

Before code, primary verifies Track06 is Complete, reads its actual closure report and
delivered migration/worker/marker/seam behavior, re-reads ADR-001/004/005/006, and confirms the committed staged
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
| T07-07 | Integrate with existing worker/manual cycle, readiness metrics, and redacted logs; retain current-stats independence. | Smith / implementation | T07-04, T07-05, T07-06 | Pending | One-thread/session/non-overlap, health backlog/overdue/baseline, complete base/ADR-004/projection JSON Lines fields, safe correlation/redaction/fail-closed formatter evidence, exactly-once causal exception ownership, ephemeral assertion handling, sentinel/cross-user absence, and current stats body/header parity through projection failure/disabled mode. |
| T07-08 | Run deterministic migration, concurrency, failure, lifecycle, and regression evidence plus the real-process closure harness. | Smith / implementation | T07-02, T07-03, T07-04, T07-05, T07-06, T07-07 | Pending | Full ledger with fake UTC clock/manual cycle/barriers/fault injection, safe private inspection and response/token/debug cleanup, quality/hygiene receipts, and actual `bash scripts/verify-track-07.sh` receipt; no real sleep proves calendar or race invariants. |
| T07-09 | Primary closure, Track08 handoff, and TEST-REPORT.md. | Primary engineering thread | T07-01, T07-02, T07-03, T07-04, T07-05, T07-06, T07-07, T07-08 | Pending | Traceability complete, risks/limits recorded, no critical/high defect, actual deterministic/process-harness commands/results, and verified cleanup. |

## Shared completion gate

The [engineering verification guideline](../../docs/ENGINEERING-VERIFICATION-GUIDELINE.md)
and [ADR-006](../ADR/ADR-006-engineering-verification-and-closure-evidence.md) apply
without changing Track07 status, task IDs/dependencies, baseline
`source_generation=0`, positive dirty generations/two-consumer completion, immutable
correction rules, one-worker topology, current-stats independence, or the no-public-
history boundary. Planned, Ready, or Blocked is not done. T07-09 may mark Track07
Complete only after recorded passing deterministic tests, migrated-database evidence,
JSON-Line/redaction evidence, and actual `bash scripts/verify-track-07.sh` results
with cleanup; planned, skipped, or blocked commands never count as pass.

The future `scripts/verify-track-07.sh` extends the delivered Track06 actual API
process and its same named non-daemon `bookmark-stats-refresher` only. It uses a
disposable database created by the real migration path and a dynamic isolated port,
then makes real mutation, current-stats, `/health/live`, and `/health/ready` requests.
Through delivered configuration and observable seams, it bounds observation of actual
projection processing and uses supported private database/operator inspection of
working, developed, and completion state without a public route. It records developing
replacement and current-surviving-state baseline evidence only if actually observable,
checks projection failure or disabled mode leaves current-stats body and headers
correct, parses complete base/ADR-004/projection JSON Lines with safe correlation,
redaction, fail-closed formatter behavior, causal exception ownership, and
seeded-sentinel/cross-user absence, and verifies clean shutdown and cleanup. Its
credentials/JWT and own user-scoped current-stats/header/safe-health responses remain
ephemeral in memory; tokens are parsed/used without echo/persistence. Private inspection
output is sanitized and ephemeral; debug retention requires an explicit flag and
excludes protected response/token data.

This process proof supplements, rather than proves, Sunday/Monday boundaries, backfill
restart, finalization crashes, revision/concurrent-generation races, correction
immutability, or two-consumer cleanup. Deterministic fake UTC clocks, migrated
integration tests, barriers, and fault injection remain mandatory. The harness adds no
test-only public endpoint, scheduler, process, thread, or public history API.

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

### T07-07 — worker integration, health, and safe observability

- Add work to existing named worker/manual cycle only: no scheduler/process/queue,
  request session, or import-time service. Preserve bounded sessions, batches, stop,
  join, and one-worker behavior.
- Readiness receives safe baseline/backlog/overdue/projection freshness state; liveness
  remains independent. Logs retain structured service attribution and low cardinality:
  no user/window IDs, payload/hash, SQL, content, credentials, or secrets.
- Parse captured JSON Lines for `source`, service/component, event, level, UTC
  timestamp, logger, `process_id`, execution/thread identity including `thread_name`,
  ADR-004 `service_instance_id`, and applicable safe projection duration/count/
  generation/completion/baseline/checkpoint/failure/calculation-version fields.
  Correlation is supplied/generated only, never token/user ID/body/content derived.
  Capture ADR-004 lifecycle outcomes plus baseline, developing, finalization,
  correction, retry, backlog/overdue, and completion events. Redact sentinels; final
  owning boundaries log once with structured type/safe message/ordered frames/cause/
  context/no locals, intermediates re-raise without duplicates, raw exception text is
  not indexed, and formatter/redactor failure emits one minimal schema-valid redacted
  JSON record. Harness assertion values remain ephemeral; unsafe receipt surfaces and
  cross-user responses remain clean.
- Prove internal weekly work leaves current stats JSON body and source headers
  independent when projection processing fails or is disabled.

### T07-08 — deterministic and real-process evidence

- Keep UTC boundaries, backfill restart, finalization crashes, revision and
  concurrent-generation races, correction immutability, and two-consumer cleanup under
  fake UTC clocks, disposable migrated integration databases, controlled barriers, and
  fault injection. A process harness cannot establish these invariants through wall
  clock or scheduler timing, and no real sleep is valid evidence.
- Deliver `scripts/verify-track-07.sh` only after the Track06 process harness exists.
  It extends the delivered actual API process and its same named non-daemon refresher
  thread with a verified disposable migrated database and dynamic isolated port. Use
  bounded polling and delivered configuration/observable seams; do not add a test-only
  public endpoint, scheduler, process, thread, or public history API.
- Make real mutation, current-stats, `/health/live`, and `/health/ready` requests.
  Inspect working/developed/two-consumer-completion state only through supported
  private database/operator tooling, record developing replacement and current-
  surviving-state baseline evidence only if observable, parse actual JSON Lines and
  sentinel/cross-user absence, then verify projection failure/disabled current-stats
  body/header independence, clean shutdown, and trap cleanup. Own response/header/
  safe-health values and JWTs are in-memory only; remove response/token/private-
  inspection/debug state and retain debug artifacts only under an explicit safe flag.

### T07-09 — closure and Track 08 handoff

- Primary creates `TEST-REPORT.md` only from actual deterministic, migrated-database,
  quality, and `bash scripts/verify-track-07.sh` results, including versions,
  selectors, inspected private artifacts, selected non-sensitive port, cleanup, gaps,
  and preserved debug artifacts where applicable.
- Hand Track08 only confirmed Track07 closure evidence, limitations, and the retained
  no-public-history/current-stats independence boundary; do not expand final delivery
  scope or reinterpret immutable historical semantics.

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
    bash scripts/verify-track-07.sh
    git diff --check
    git status --short

Focused tests use fake UTC clocks, manual worker-cycle controls, disposable migrated
SQLite databases, failure injection, and barriers. They must not use real ten-second
waits or timing-dependent scheduler assertions. The planned harness extends delivered
Track06 process evidence but cannot substitute for deterministic calendar, restart,
crash, race, correction, or two-consumer proof. Add exact payload/hash, DDL, race, and
current-stats-independence checks when implemented; never mark planned commands passed.

## Review checkpoints and commit boundary

1. Track06 report/staged completion gate; 2. schema/completion protocol; 3. weekly
SQL/window/hash/version; 4. baseline limitations/restart; 5. finalization/correction/
revision race; 6. worker/health/current-independence; 7. primary closure/Track08 handoff.

Preferred green-boundary commit: feat: add durable weekly statistics projections.
Do not commit secrets, payload/user content, generated databases/caches/coverage, a
public history route, queue/topology redesign, bonuses, final narrative, or failing
intermediate state.
