# Track 05 plan: mandatory quality and contract gate

- Specification: [SPEC.md](SPEC.md), version 1.0
- Status: Planned
- Active item: None; blocked until Tracks 01--04 close

| ID | Work item | Owner | Depends on | Status | Exit evidence |
| --- | --- | --- | --- | --- | --- |
| T05-01 | Verify closure receipts and current contracts for Tracks 01--04. | Smith / implementation | Tracks 01--04 closure | Blocked | Compatibility/mandatory-inventory checkpoint. |
| T05-02 | Build the core requirement-to-evidence inventory and separate still-open Track 08 delivery obligations. | Smith / implementation | T05-01 | Pending | Every required/accepted core row owned by Tracks 01--05 maps to evidence; no delivery-only row is falsely closed. |
| T05-03 | Audit/fix operation OpenAPI metadata and `/docs`. | Smith / implementation | T05-01, T05-02 | Pending | Security/schema/status/example/content-type/204 audit. |
| T05-04 | Select/pin contract harness and validate real responses/errors. | Smith / implementation | T05-03 | Pending | Generated-schema instance evidence. |
| T05-05 | Add deterministic integration/performance/raw-SQL boundary matrix, real-instance contract suite, and logging schema/redaction audit. | Smith / implementation | T05-02, T05-04 | Pending | >=10 collected meaningful unit/integration/contract tests, OpenAPI real-instance validation, N+1/query-count/parameterization evidence, and no skip/xfail masking of mandatory behavior. |
| T05-06 | Clean migration, bootstrap, mandatory-core process harness, coverage recording, and quality rehearsal. | Smith / implementation | T05-05 | Pending | `scripts/verify-track-05.sh` starts the actual server from disposable clean/migrated state on a dynamic port, runs/invokes Tracks 01--04 harnesses or equivalent non-duplicative selectors, validates representative complete flows/OpenAPI/logging/redaction, and verifies cleanup with actual command results. |
| T05-07 | Primary defect/risk review and TEST-REPORT closure. | Primary engineering thread | T05-01, T05-02, T05-03, T05-04, T05-05, T05-06 | Pending | Actual passing deterministic/contract/performance/logging evidence and `bash scripts/verify-track-05.sh`; TEST-REPORT records commands/results/versions/selectors/cleanup, no critical/high defect, and Track 06 remains blocked unless the gate is green. |

## Shared completion gate

The [engineering verification guideline](../../docs/ENGINEERING-VERIFICATION-GUIDELINE.md)
applies without changing the mandatory-core scope or the Track 06 stop. Planned,
Ready, or Blocked is not done. T05-07 may mark Track 05 Complete only after recorded
passing deterministic tests, real-instance OpenAPI validation, performance/raw-SQL and
logging-redaction evidence, actual process-harness proof, and documented cleanup;
planned, skipped, or blocked commands never count as pass.

The future `scripts/verify-track-05.sh` is the mandatory-core automation gate. It
uses a verified disposable clean/migrated state and dynamic isolated port, starts the
actual server, runs or invokes Tracks 01--04 harnesses or equivalent non-duplicative
selectors, then exercises representative complete auth/CRUD/search/stats/error/docs/
health flows. It validates actual statuses/bodies against generated OpenAPI, parses
JSON Lines for attribution/correlation and safe seeded credential/content absence, and
verifies trap cleanup. Deterministic query-count and complete-contract tests remain
separate mandatory evidence; smoke cannot substitute for them.

## Edge-case/evidence ledger

| Area | Evidence |
| --- | --- |
| Contract | Every success/documented error, content type, bearer requirement, example, and `204` bodylessness validates at runtime. |
| Core matrix | Foundation, auth, isolation, CRUD/tags/timestamps, query pages/dates, stats, errors, and API requirements owned by Tracks 01--05 each have direct evidence; Track 08 rows remain visible and open. |
| Performance/safety | Query-count/N+1 regressions; raw SQL only in stats reader, named parameters, owner scope. |
| Reproducibility | Empty migration build, bootstrap, representative HTTP smoke, collected count, coverage record, lint/type/test pass. |
| Defects | No skip/xfail masking; owning-track fix or ADR/SPEC escalation, then rerun affected evidence. |

## Planned validation commands

```text
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run mypy app
uv run pytest --collect-only
uv run pytest
uv run alembic upgrade head
uv run alembic downgrade base
uv run alembic upgrade head
uv run alembic check
make check
bash scripts/verify-track-05.sh
git diff --check
git status --short
```

Add the selected pinned contract-tool command, coverage command, query-count suite,
and documented bootstrap/HTTP smoke command at implementation time; record exact
results in `TEST-REPORT.md`.
