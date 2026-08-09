# Track 09 plan: final cleanup, documentation migration, and test reports

- Specification: [SPEC.md](SPEC.md), version 1.0
- Governing records: ADR-006, ADR-008, and completed Tracks 00–08
- Status: In progress
- Active item: T09-06 and T09-07 integration checkpoints

## Dependency and intent gate

Track 08 is Complete at `9092f30`. Baseline `uv run pytest -q` passes 723 tests and
3 subtests with one demonstrated Starlette warning requiring `httpx2`; Ruff and
strict application mypy are green. Track 09 preserves all Track 08 product evidence
and the Track 07 skip. No external action or history rewrite is authorized.

| ID | Work item | Owner | Depends on | Status | Exit evidence |
| --- | --- | --- | --- | --- | --- |
| T09-01 | Inventory documentation paths, dataclasses, lifecycle events, actual deprecations, type suppressions, automation output, Docker ordering, and acceptance risks. | Primary + Scout | Track 08 | Complete | Read-only code/docs inventories, current official framework guidance, and 723-test baseline receipt. |
| T09-02 | Accept the Track 09 SPEC/PLAN and ADR-008 internal-model/lifecycle contract. | Primary | T09-01 | Complete | Accepted artifacts committed at `a915400`; documentation and diff checks passed. |
| T09-03 | Atomically move `docs/` to `.docs/`; repair live links, verifier roots, harness contracts, ignore rules, indexes, and reader navigation without changing historical outcomes. | Smith | T09-02 | Complete | Nine-file rename and live-path repairs committed at `bc728b6`; docs/link/contract gates passed. |
| T09-04 | Convert immutable and mutable dataclasses to strict behavior-preserving Pydantic v2 models, including event/current-stats validators and rate-bucket concurrency. | Smith High | T09-02 | Complete | Pydantic conversion committed at `a9bdf15`; focused/full tests, model inventory, types, and 100% branch coverage passed. |
| T09-05 | Add lifecycle `StrEnum`, migrate plain-httpx TestClient support to `httpx2`, and resolve reasonable typed third-party/application boundaries. | Smith | T09-04 | Complete | Lifecycle/type work committed at `ecb225c` and public compatibility adapter at `d1ac384`; warning-fatal tests and type checks passed. |
| T09-06 | Add consistent safe standalone reporting to every verification script, strengthen post-build Docker tests, and implement `verify-track-09.sh`. | Smith High | T09-03, T09-05 | In progress | Implementation and focused/static/working-tree Docker evidence are green; incremental commit and clean-source final receipt remain. |
| T09-07 | Rewrite root README and update `.docs`/track indexes with SDD Mermaid first, current requirement/limitation/test-report guidance, and Tracks 00–09 status. | Smith | T09-03, T09-06 | In progress | Reader rewrite and docs/fresh-reader audits are green; incremental commit remains. |
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
