# Track 07 history

## 2026-08-09 — T07-05/T07-06 lifecycle and corrections implemented

- Added one caller-transaction-owned projection processor for dirty generations and
  overdue developing rows. Current rows are replaceable; closed rows are developed
  from a fresh canonical read; a boundary transaction guarded-deletes the exact old
  working row and creates only the window containing `now`.
- Added same-hash no-op completion, append-only `late_recalculation` revisions, exact
  immediate predecessors, zero corrections after last-bookmark deletion, compatible
  positive-generation preservation, active/version guards, and atomic projection
  success plus generation acknowledgement. Stale acknowledgement rolls every
  candidate write back.
- Proved actual developing-row rollover at the exact boundary, corrupted-working
  canonical recalculation, absent/non-overdue/deferred paths, multi-week skips, A-B-A,
  user deletion without recreation, and read/acknowledgement/caller-commit/guarded-
  delete failures. Real Barrier-controlled SQLite races proved generation increment
  rollback/retry and one revision winner followed by an immediate-predecessor retry.
- Full formatting/lint, mypy, and Pyright passed. The focused 95-test projection gate
  covered both changed modules at 100% statement and branch coverage; the full suite
  passed with 831 tests plus 3 subtests and 100% coverage over 3,697 statements and
  840 branches. Worker, readiness, logs, and process-harness integration remain T07-07
  and T07-08 work.

## 2026-08-09 — T07-04 restartable surviving-data baseline implemented

- Added a durable pending/running/active/failed projection state and a bounded
  lexicographic `(user_id, window_start)` checkpoint query over surviving bookmarks.
  Each baseline step owns one short-lived session and commits its projection rows and
  checkpoint or terminal activation atomically.
- Closed windows create only absent revision-1 points; current-window evidence creates
  or replaces one working row. Baseline rows use `source_generation=0`, synthesize no
  empty weeks, make no deleted pre-install audit claim, and never acknowledge or delete
  dirty markers.
- Proved empty activation, bounded pages, restart/rewind, rollback and session cleanup,
  deleted-data absence, no duplicate roots, working replay, Unicode payloads, future and
  malformed candidates, transition races, typed calculation-version mismatch, and
  dirty-marker noninterference in migrated SQLite.
- Full formatting/lint, mypy, and Pyright passed. The full suite passed with 802 tests
  plus 3 subtests and 100% branch coverage over 3,537 statements and 780 branches.
  Developing-row finalization, dirty corrections, and worker integration remain
  pending under T07-05 through T07-07.

## 2026-08-09 — T07-03 canonical weekly domain and repository implemented

- Added the sole UTC Monday-to-Monday calculator and a separate private weekly
  raw-SQL reader with bound user/start/end/limit parameters. The all-current Track 04
  statements and public statistics route remain unchanged.
- Added compact schema-wrapped UTF-8 payload bytes, the explicit
  `weekly-v1;payload-schema=1;top-tags-limit=N` calculation version, domain-separated
  SHA-256 hashes, and explicit same/changed/version-mismatch comparison.
- Added caller-transaction-owned working/effective-point repository operations with
  immediate-predecessor validation, append-only A-B-A history, bounded overdue reads,
  and low-cardinality correction reasons enforced at both Python and SQLite bounds.
- UTC/leap/month/year boundaries, exact half-open inclusion, user isolation, ties and
  ordering, Unicode/SQL-like content safety, deterministic bytes, version mismatch,
  rollback, malformed persistence, immutable revisions, and no public route were
  tested. The full suite passed with 774 tests plus 3 subtests and 100% coverage over
  3,294 statements and 684 branches. Baseline and worker integration remain pending.

## 2026-08-09 — T07-02 durable schema and completion protocol implemented

- Added Alembic revision `0003_weekly_stats_projections` with working rows,
  immutable point revisions, a singleton restartable projection-state record, and
  zero-initialized current/projection completion generations on existing dirty rows.
- Replaced current-only dirty deletion with generation-guarded consumer
  acknowledgements. Either consumer may delete only after both acknowledgements and
  the stored generation equal its observed generation; increments reset both values.
- Proved empty/populated upgrade, downgrade/re-upgrade, named constraints/indexes,
  self/user foreign keys, user cascade, both completion orders, stale generations,
  rollback, A-B-A revision history, and inert model imports in migrated SQLite.
- The full deterministic suite passed with 754 tests plus 3 subtests. Application
  coverage remained 100% across 3,031 statements and 622 branches; Ruff, mypy, and
  Pyright passed. No calculator, baseline runner, projection consumer, harness, or
  closure report is claimed by this checkpoint.

## 2026-08-09 — Revival authorized; implementation dependency review started

- Repository owner revived Track 07 from the active **Skipped (owner decision)**
  disposition to **In progress**. This supersedes only that active disposition;
  it does not erase the 2026-08-06 skip record or claim implementation evidence.
- Accepted ADR-009 selects ADR-005's event-time weekly design for implementation while
  preserving ADR-004's one-worker/current-statistics invariants. Track 06 closure
  evidence was reviewed against its delivered migration, dirty-marker repository,
  mutation publisher, refresher, current raw-SQL/snapshot path, health, logs, and
  deterministic seams. T07-01 is complete; T07-02 is the first product-code boundary.
- No Track 07 application code, migration, tests, `TEST-REPORT.md`, or
  `scripts/verify-track-07.sh` was created or run by this governance checkpoint.
- Track 08 and Track 09 active records still describe the pre-revival state. Their
  downstream integration update is explicitly pending and outside this change.

## 2026-08-09 — Dedicated archived-skip branch verified

- Created `codex/track-07-archived-skip` from the verified Track 06-integrated
  `main` state so the owner's per-track branch requirement remains explicit even
  though no Track 07 implementation is authorized.
- `bash scripts/verify-docs.sh` passed with 43 requirement IDs, six accepted ADRs,
  and nine tracks. The verifier confirmed the skipped SPEC/PLAN statuses, Track 08's
  absence-based dependency, and the prohibition on a Track 07 test report or harness.
- Direct absence checks confirmed there is no
  `.tracks/07-weekly-projections/TEST-REPORT.md`, no
  `scripts/verify-track-07.sh`, and no weekly working/point table, projection class,
  history route, revision, calculation-version, or payload-hash implementation under
  `app` or `alembic/versions`.
- `git diff --check` passed. This branch changes documentation history only and does
  not claim passing weekly-projection behavior, tests, migrations, or runtime
  evidence. The Track remains **Skipped (owner decision)** rather than Complete.

## 2026-08-06 — Track skipped by owner decision

- Changed Track 07 from **Planned (implementation-gated)** to **Skipped (owner
  decision)**. No weekly developing/developed table, backfill, historical consumer,
  correction revision, route, worker extension, harness, or test report will be
  implemented.
- Kept all prior entries below as planning history only. They are superseded by this
  scope decision and are not implementation authority.
- Made Track 06 current-only dirty-marker completion the terminal runtime policy.
- Removed Track 07 completion/report/harness as a Track 08 dependency. Track 08 now
  consumes this skip record and verifies the absence of weekly projection artifacts.
- This documentation decision does not claim passing Track 07 evidence and does not
  modify product source, migrations, tests, or runtime behavior.

## 2026-08-05 — Sequential planning started

- Planned Track07 after committed Track06 (92d3830) and accepted ADR-001, ADR-004,
  and ADR-005. No product source, dependency, migration, queue, thread, route, health
  behavior, or external action occurred.
- Marked the track Planned (implementation-gated) with T07-01 Blocked until Track06
  is Complete and has its actual TEST-REPORT.md closure evidence.
- Preserved the staged consumer rule: Track06 may have completed markers before a
  historical consumer existed; Track07 first establishes restartable canonical
  surviving-data baseline, then requires current and projection completion for an
  observed generation before marker removal.
- Assigned private working rows, immutable revisions, deterministic version/hash
  policy, baseline/finalization/corrections, existing-worker integration, health/log
  evidence. Kept public history APIs, queue/topology redesign, final docs, bonuses out.
- Primary review reserved source generation zero for installation/backfill state while
  keeping observed dirty generations positive, prohibited blanket completion during
  migration, and required same-user/window immediate-predecessor supersession proof.

## Historical state before the 2026-08-06 skip decision

- Specification: Planned, version 1.1
- Plan: Planned; T07-01 Blocked on Track06 closure TEST-REPORT.md
- Implementation: Not started; dependency-gated
- Material product questions: None known; private completion names/checkpoint mechanics
  remain implementation latitude after Track06 seam review

## Historical next action

After Track06 closes with real evidence, execute T07-01 to compare its delivered
dirty-marker migration, current completion ordering, raw-SQL reader, worker cycle,
Settings, health, and logs before authoring projection migration or code.

## 2026-08-05 — Shared verification-gate adoption

- Adopted the committed shared logging, deterministic-test, and real-process closure
  gate in Track07 planning only. Status, task IDs/dependencies, reserved baseline
  `source_generation=0`, positive dirty generations/two-consumer completion, immutable
  correction rules, one-worker topology, current-stats independence, and no-public-
  history boundary remain unchanged.
- Planned (but did not create or run) `scripts/verify-track-07.sh` to extend the
  delivered Track06 actual API process and its same named non-daemon refresher thread
  with a disposable migrated database, dynamic isolated port, real
  mutation/current-stats/live-ready flows, bounded observable projection processing,
  supported private database/operator inspection, observable developing/baseline
  evidence where available, projection failure/disabled current-stats independence,
  JSON-Line sentinel checks, clean shutdown, and cleanup.
- Retained deterministic fake UTC clock, migration, barrier, and fault-injection
  tests as the required proof for UTC boundaries, restart/crash, revision/generation
  races, correction immutability, and two-consumer cleanup. The future process harness
  supplements rather than proves those claims and adds no public history route or
  test-only topology.
- No Track07 test, application process, migration, harness, runtime validation, or
  `TEST-REPORT.md` receipt was executed or created by this planning-only change.

## 2026-08-06 — Incremental evidence-governance planning correction

- Bumped the SPEC/PLAN planning contract to version 1.1 and added ADR-006 to the
  governing/re-read/closure records without changing the Planned gate, Track06
  Complete-plus-report hard stop, or any event-time/projection boundary.
- Completed base/ADR-004 projection logging, safe correlation, redaction, causal
  exactly-once exception, fail-closed formatter/redactor, and safe ephemeral harness
  assertion/disclosure requirements.
- Preserved `source_generation=0`, positive generation/two-consumer completion,
  immutable corrections, the same worker, current-stats independence, no public
  history, Track08 boundary, and deterministic/process evidence separation.
- This correction is planning only: no Track07 test, process, migration, harness,
  runtime validation, artifact, or `TEST-REPORT.md` receipt was created or executed.
