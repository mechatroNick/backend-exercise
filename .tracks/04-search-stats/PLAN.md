# Track 04 plan: search, pagination, and canonical current statistics

- Specification: [SPEC.md](SPEC.md), version 1.0
- Status: Planned
- Active item: None; dependency-gated on Track 03 closure

| ID | Work item | Owner | Depends on | Status | Exit evidence |
| --- | --- | --- | --- | --- | --- |
| T04-01 | Verify Track 03 closure and delivered auth/error/CRUD/query seams. | Smith / implementation | Track 03 closure | Blocked | Compatibility receipt; stop on mismatch. |
| T04-02 | Add filter DTO/date-range policy and response metadata. | Smith / implementation | T04-01 | Pending | Boundary/reversed/UTC tests. |
| T04-03 | Implement owner-scoped ORM items/total query in one read transaction, eager strategy, pagination, literal-substring escaping, and duplicate-safe tag predicate. | Smith / implementation | T04-01, T04-02 | Pending | Shared-snapshot/predicate/order/page/query-count evidence. |
| T04-04 | Implement isolated parameterized raw-SQL stats reader in one read transaction. | Smith / implementation | T04-01 | Pending | Empty/populated/tie/month/cross-user aggregate tests. |
| T04-05 | Wire protected list/stats routes and operation OpenAPI; register static stats before dynamic ID. | Smith / implementation | T04-02, T04-03, T04-04 | Pending | Route/schema/status/security tests. |
| T04-06 | Add correctness, EXPLAIN, query-count, and raw-SQL-isolation regression tests. | Smith / implementation | T04-03, T04-04, T04-05 | Pending | Ledger, EXPLAIN receipts, bounded-query tests. |
| T04-07 | Closure validation and evidence recording. | Primary engineering thread | T04-01, T04-02, T04-03, T04-04, T04-05, T04-06 | Pending | Actual quality/diff/hygiene review; Track 05 boundary retained. |

## Edge-case ledger

| Dimension | Case | Planned proof |
| --- | --- | --- |
| Filters | Exact normalized tag, literal title substring including `%`/`_` input, combined/open/reversed date ranges, UTC upper bound. | T04-02/03 tests. |
| Pages | 1/default 20/max 100, invalid bounds, stable page boundary/no duplicate/missing item | T04-02/03 tests. |
| Ownership | list/stats two-user isolation and all stats statements bind user ID | T04-03/04 tests/review. |
| Loading | Tags return without N+1; tag join cannot duplicate items; items/total predicates and read snapshot match. | T04-03/06 instrumentation and concurrent-write tests. |
| Stats | empty, multi-tag distinct total, ties, chronological month/year, deletion/tag change | T04-04/06 tests. |
| SQL safety | named TextClause parameters, no interpolation, one consistent read snapshot | T04-04 source/integration tests. |
| Performance | no substring-index assertion without `EXPLAIN QUERY PLAN`; schema change requires review | T04-06 receipt. |
| Boundaries | no queue/snapshot/history/API-wide conformance | T04-06 source/contract review. |

## Planned validation commands

```text
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run mypy app
uv run pytest tests/unit tests/integration tests/contract -k 'search or pagination or stats'
uv run pytest
uv run alembic upgrade head
uv run alembic check
uv run python -m pytest -k 'query_count or explain'
git diff --check
git status --short
```

Record actual SQLite `EXPLAIN QUERY PLAN` output and query-count measurements at
implementation. Validate Track 04 operations only; Track 05 owns global conformance.
