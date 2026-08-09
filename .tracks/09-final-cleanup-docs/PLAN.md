# Track 09 plan: final cleanup, documentation migration, and test reports

- Specification: [SPEC.md](SPEC.md), version 1.0
- Governing records: ADR-006, ADR-008, and completed Tracks 00–08
- Status: In progress
- Active item: T09-02

## Dependency and intent gate

Track 08 is Complete at `9092f30`. Baseline `uv run pytest -q` passes 723 tests and
3 subtests with one demonstrated Starlette warning requiring `httpx2`; Ruff and
strict application mypy are green. Track 09 preserves all Track 08 product evidence
and the Track 07 skip. No external action or history rewrite is authorized.

| ID | Work item | Owner | Depends on | Status | Exit evidence |
| --- | --- | --- | --- | --- | --- |
| T09-01 | Inventory documentation paths, dataclasses, lifecycle events, actual deprecations, type suppressions, automation output, Docker ordering, and acceptance risks. | Primary + Scout | Track 08 | Complete | Read-only code/docs inventories, current official framework guidance, and 723-test baseline receipt. |
| T09-02 | Accept the Track 09 SPEC/PLAN and ADR-008 internal-model/lifecycle contract. | Primary | T09-01 | In progress | Reviewed durable artifacts; docs verifier and diff checks pass; planning commit. |
| T09-03 | Atomically move `docs/` to `.docs/`; repair live links, verifier roots, harness contracts, ignore rules, indexes, and reader navigation without changing historical outcomes. | Smith | T09-02 | Pending | No stale operational paths; docs/link/contract tests pass; clean rename commit. |
| T09-04 | Convert immutable and mutable dataclasses to strict behavior-preserving Pydantic v2 models, including event/current-stats validators and rate-bucket concurrency. | Smith High | T09-02 | Pending | Focused edge suites, Ruff, mypy, Pyright/Pylance-compatible check, OpenAPI/runtime regressions, and model inventory pass. |
| T09-05 | Add lifecycle `StrEnum`, migrate plain-httpx TestClient support to `httpx2`, and resolve reasonable typed third-party/application boundaries. | Smith | T09-04 | Pending | Warning-enabled focused/full suites are clean; lifecycle JSON/order unchanged; type receipts pass. |
| T09-06 | Add consistent safe standalone reporting to every verification script, strengthen post-build Docker tests, and implement `verify-track-09.sh`. | Smith High | T09-03, T09-05 | Pending | Shell/static/injected-failure tests plus actual Docker ordered receipt and cleanup pass. |
| T09-07 | Rewrite root README and update `.docs`/track indexes with SDD Mermaid first, current requirement/limitation/test-report guidance, and Tracks 00–09 status. | Smith | T09-03, T09-06 | Pending | Fresh-reader review, Mermaid/link/docs gates, and claims-to-evidence audit pass. |
| T09-08 | Run focused and complete deterministic, branch-coverage, type, warning, migration, runtime, security, dependency, documentation, inherited-harness, Docker, and cleanup validation. | Primary | T09-04, T09-05, T09-06, T09-07 | Pending | Clean committed branch passes `bash scripts/verify-track-09.sh`; exact receipt retained. |
| T09-09 | Independent closure review; publish TEST-REPORT/HISTORY/status, merge branch to main, and rerun the exact final gate on merged main. | Primary + Mason | T09-08 | Pending | No unresolved defect; report and closure commit; merge commit; post-merge clean-source pass. |

## Ordered validation ledger

1. Focused tests for each converted model/event/type boundary.
2. Ruff format/check, strict mypy, and locked Pyright/Pylance-compatible analysis.
3. Warning-as-error focused and full deterministic suites with 100% statement/branch
   coverage.
4. Docs/link/path/static shell contracts and success/injected-failure report output.
5. Alembic upgrade/downgrade/re-upgrade/check, real service/API/OpenAPI/logging, seed,
   rate, cursor, health, stats, and cooperative shutdown.
6. Docker build, then Docker tests, migration-only/start/health/SIGTERM/log/cleanup.
7. Exact inherited verifiers and final Track 09 clean-source orchestration.
8. Independent review, closure docs, merge commit, and exact post-merge rerun.

Each write wave must end green and be committed independently. If a downstream wave
invalidates earlier evidence, rerun and repair the owning gate before proceeding.

