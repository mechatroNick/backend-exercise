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
| T05-05 | Add integration/performance/raw-SQL boundary matrix. | Smith / implementation | T05-02, T05-04 | Pending | >=10 collected tests, N+1/query-count/parameterization evidence. |
| T05-06 | Clean migration, bootstrap, smoke, coverage recording, and quality rehearsal. | Smith / implementation | T05-05 | Pending | Actual clean-environment command results. |
| T05-07 | Primary defect/risk review and TEST-REPORT closure. | Primary engineering thread | T05-01, T05-02, T05-03, T05-04, T05-05, T05-06 | Pending | No critical/high defect; Track 06 go/no-go. |

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
git diff --check
git status --short
```

Add the selected pinned contract-tool command, coverage command, query-count suite,
and documented bootstrap/HTTP smoke command at implementation time; record exact
results in `TEST-REPORT.md`.
