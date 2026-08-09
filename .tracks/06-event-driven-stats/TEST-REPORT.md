# Track 06 test report

- Status: Passed
- Date: 2026-08-09
- Branch: `codex/track-06-event-driven-stats`
- Validated commits: `f9a7cd6` and `8f1dc4d` on the full Track 06 implementation history
- Scope: Event-driven current-statistics invalidation, durable dirty recovery,
  bounded queue and worker lifecycle, immutable snapshots/live fallback, health,
  structured observability, migrations, deterministic edge tests, and real-process
  closure

This terminal report records actual executable evidence for T06-08. The final
documentation-only commit carries this report and the Complete status; merge and
post-merge verification remain integration actions rather than inferred test results.

## Acceptance matrix

| Requirement | Executable evidence | Result |
| --- | --- | --- |
| T06-REQ-01 | Migrated integration and service tests prove same-transaction dirty marking plus exactly one total post-commit invalidation for each material create/update/tag/delete, with no read/no-op/rollback emission. | Pass |
| T06-REQ-02 | Migration/repository tests plus upgrade, downgrade, re-upgrade, drift, generation-race, rollback, conditional completion, and restart receipts prove the durable marker protocol. | Pass |
| T06-REQ-03 | Capacity-one real-process overflow plus deterministic lost/duplicate/reordered/failing publisher tests prove committed requests remain successful and reconciliation is durable. | Pass |
| T06-REQ-04 | Deterministic lifecycle/concurrency tests and exact process-log counts prove one lifespan-owned named non-daemon worker, per-cycle sessions, non-overlap, retry, cooperative stop, and bounded join-timeout behavior. | Pass |
| T06-REQ-05 | Canonical reader/fallback tests plus two distinguishable real users prove immutable snapshot publication, own-user isolation, exact live/snapshot body parity, source headers, and failure fallback. | Pass |
| T06-REQ-06 | Unit/integration/contract/process evidence proves exact live/ready routes, one-worker configuration enforcement, bounded fail-closed readiness, strict JSON Lines, safe telemetry/correlation, and redaction. | Pass |
| T06-REQ-07 | `scripts/verify-track-06.sh` passed its inherited, deterministic, migration, quality, real-process, log-audit, and cleanup phases; independent post-fix audit found no critical/high/medium defect. | Pass |

No known critical, high, or medium implementation or evidence defect remains. The
branch is ready to merge to `main` and receive post-merge verification.

## Incremental implementation receipts

| Commit | Stabilized boundary |
| --- | --- |
| `bf7546f` | Durable dirty-marker migration, metadata, atomic repository operations, and generation-safe recovery. |
| `4768ceb` | Content-free invalidation DTO, same-transaction marking, and exactly-one post-commit publication seam. |
| `38539c8` | Bounded total queue publisher, reconciliation state, and immutable snapshot store. |
| `58eaa08` | Fresh snapshot serving with unchanged canonical live fallback and documented source headers. |
| `3de2c76` | Lifecycle-owned refresher, bounded reconciliation, per-cycle sessions, generation/epoch-safe publication, and cooperative shutdown. |
| `5b4e489` | Exact liveness/readiness surface, fail-closed operational state, safe transition logs, and 10-operation/37-status-pair contract. |
| `3be39bf` | Inherited harness compatibility and application-qualified worker log attribution. |
| `f9a7cd6` | Actual-thread daemon evidence plus deterministic and JSON unit assertions. |
| `8f1dc4d` | Executable comprehensive Track 06 Bash closure harness. |
| This checkpoint | Terminal report, Complete status, history, and Track 08 handoff. |

Every product and harness row names an actual commit. This report and the Complete
status form the final documentation-only checkpoint.

## Environment

| Tool | Verified version |
| --- | --- |
| Python | 3.12.12 |
| uv | 0.9.15 |
| FastAPI | 0.139.2 |
| pytest | 9.1.1 |
| coverage.py | 7.15.3 |
| Ruff | 0.15.22 |
| mypy | 2.3.0 |
| Alembic | 1.19.0 |
| Uvicorn | 0.51.0 |
| HTTPX | 0.28.1 |

The sole visible test warning remains the locked Starlette TestClient/httpx
deprecation. Real-process HTTP evidence uses HTTPX against Uvicorn and is unaffected.

## Static, full-suite, and coverage evidence

The final-form `bash scripts/verify-track-06.sh` command exited `0` and emitted these
safe receipts from its private workspace:

| Gate | Actual result |
| --- | --- |
| Recursive cleanup self-test | Preserved injected status 97 and verified the nested private workspace was removed. |
| Inherited `bash scripts/verify-track-05.sh` | Pass, including Tracks 01--04, mandatory core, real process, and cleanup. |
| Focused deterministic Track 06 selector | Pass with no accepted skipped, xfailed, xpassed, or deselected result. |
| Explicit topology/retry/join/overflow nodes | Four exact nodes passed. |
| `uv sync --locked` | Exit `0`. |
| `uv run ruff format --check .` | Exit `0`. |
| `uv run ruff check .` | Exit `0`. |
| `uv run mypy app` | Exit `0`. |
| `coverage run -m pytest -q` | Exit `0`; 602 tests passed. |
| `coverage report --fail-under=100` | 2,461 statements, 516 branches, zero misses/partials, 100%. |
| `make check` | Exit `0`. |
| `bash scripts/verify-docs.sh` | Exit `0`; 43 requirement IDs, six accepted ADRs, nine tracks. |
| `git diff --check` | Exit `0`; no whitespace errors. |

The exact observable edge selectors were:

- `tests/unit/test_stats_refresher.py::test_start_once_exact_thread_and_failed_cycle_state`
- `tests/unit/test_stats_refresher.py::test_thread_start_and_join_timeout_failures_are_explicit`
- `tests/unit/test_stats_refresher.py::test_worker_retry_json_logs_keep_application_source_and_safe_context`
- `tests/unit/test_stats_publisher.py::test_overflow_invalidates_sets_reconciliation_and_logs_once_per_episode`

The wider deterministic ledger uses fake clocks, manual cycles, injected sessions and
failures, and controlled barriers rather than elapsed scheduler sleeps for
transaction ordering, generation races, no-overlap, snapshot atomicity, retry, and
failure invariants.

## Migration and durable recovery evidence

The harness created only disposable private SQLite databases and ran `alembic upgrade
head`, `alembic downgrade base`, a second upgrade, and `alembic check`; every command
exited `0`. The migrated integration suite additionally covers exact DDL, foreign key
cascade, unique/index shape, atomic conflict increment, rollback, conditional delete,
bounded observations, corruption rejection, and new/existing-schema migration paths.

In the real overflow process, two committed users each retained durable dirty work
after shutdown. The recovery process reused that database, reconciled the backlog,
returned readiness to 200, and left exactly zero dirty rows. The entire disposable
workspace was then removed and verified absent.

## Real-process harness

The executable [closure harness](../../scripts/verify-track-06.sh) performs the
effective bootstrap operations explicitly: migrate the disposable database, then
launch the real `app.main:create_app` factory through one Uvicorn worker. Migration
output is captured separately so every audited application-output line is genuinely
subject to the JSON Lines contract.

The final passing run reported these non-sensitive dynamic ports:

| Phase | Port | Evidence |
| --- | ---: | --- |
| Parity | 54032 | Live/ready contracts, exact OpenAPI inventory, two-user mutations, live source, bounded snapshot appearance, body/header/schema parity, and worker identity. |
| Overflow | 54046 | Capacity-one overflow, successful committed mutations, live fallback, readiness 503, once-per-episode overflow event, and durable backlog survival. |
| Recovery | 54054 | Startup reconciliation over the prior database, readiness recovery, clean stop, and zero remaining dirty markers. |

The two parity users intentionally had different bookmark counts. Each initial live
body was saved only in memory, each authenticated snapshot was compared with its own
live body, and the ordered pair was checked again to reject swapped/cross-user state.
Both sources validated against the delivered OpenAPI schema. JWTs and response bodies
were never written to receipts.

## Worker, health, and structured-log evidence

Each of the three process logs contains exactly one application starting, started,
stopping, and stopped event and exactly one refresher starting, started, stopping, and
stopped event. The actual worker start record proves thread name
`bookmark-stats-refresher` and boolean `worker_is_daemon=false`; no real-process join
timeout occurred. Deterministic edge tests separately prove retry and join-timeout
events and state without making the successful shutdown path fail.

Every nonblank application line parsed as one JSON object. The audit requires full
source pathname/line/package/module/function, service/component/event/level, UTC
timestamp, logger, process ID, thread name/ID, and exact UUID service instance. It
also validates UUID correlations when present, successful-cycle duration,
affected-user/marker/failure/full-reconciliation telemetry, and overflow
capacity/depth/reconciliation/overflow/failure telemetry.

Liveness remained 200 during service degradation. Readiness proved initial 200,
overflow-driven 503 with fixed redacted body and `no-store`, then post-restart 200.
The deterministic health suite covers database failure, malformed/missing state,
dead/stuck/overdue/never-successful/stale/future-clock workers, failure and backlog
threshold boundaries, disabled refresh, and transition-only logging.

## Secret safety, artifacts, and cleanup

The harness generates private usernames, emails, URLs, titles, descriptions, tags,
passwords, JWTs, correlation values, JWT secret, databases, and workspace paths. It
asserts that none enter captured logs; it also rejects authorization/Bearer material,
user/bookmark/resource identifier keys, raw exception fields, SQL/content detail, and
invalid source attribution. Assertion messages and stdout contain only fixed safe
text, exact public selectors, aggregate test/coverage counts, and loopback ports.

`umask 077`, guarded `mktemp`, known-descendant termination, TERM/KILL fallback,
bounded polling, original-status preservation, and prefix-validated removal protect
the disposable state. No response, token, database, coverage, log, or debug artifact
was retained. The harness has mode `100755`.

## Independent review and retained boundaries

Mason Medium's initial audit found a high two-user isolation gap and medium
worker-topology and observability gaps. The final script added distinguishable
two-user live/snapshot mapping, exact lifecycle counts, actual-thread daemon evidence,
explicit retry/join/overflow nodes, safe telemetry, and correlation validation. The
post-fix verdict was **PASS-WITH-NOTES**, with no critical, high, or medium finding.

Retained low-risk boundaries:

- The harness duplicates the two effective `make bootstrap` operations so migration
  text cannot contaminate the strict application JSON stream. Its Uvicorn arguments
  currently match the Makefile and must be reviewed if that recipe changes.
- Dynamic select-then-bind ports have a small detectable race. A collision fails the
  bounded launch; it cannot create a false pass.
- Queue, snapshot, and worker state remain process-local and valid only for the
  enforced one-worker deployment. Production multi-process delivery remains an
  outbox/broker/shared-cache design concern, not a Track 06 claim.
- Track 07 is owner-skipped. This track implements terminal current-only generation
  completion and claims no historical points, corrections, backfill, or history API.

## Integration ledger

| Integration action | Branch evidence |
| --- | --- |
| Actual daemon-evidence incremental commit | `f9a7cd6`. |
| Actual harness incremental commit | `8f1dc4d`. |
| Final documentation/status checkpoint | This report and Complete status are staged only after their documentation gate passes. |
| Track 06 merge to `main` | Required immediately after the final documentation commit. |
| Post-merge Track 06 harness/docs/clean-worktree receipt | Required on merged `main` before Track 08 implementation begins. |

The final two rows are merge-sequence controls. They do not replace or weaken the
passing branch evidence above.
