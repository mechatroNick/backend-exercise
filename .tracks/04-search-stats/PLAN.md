# Track 04 plan: search, pagination, and canonical current statistics

- Specification: [SPEC.md](SPEC.md), version 1.1
- Governing ADRs: ADR-001, ADR-002, ADR-004, ADR-006
- Status: Ready
- Active item: T04-02 query DTO/date policy after the passed T04-01 compatibility gate

| ID | Work item | Owner | Depends on | Status | Exit evidence |
| --- | --- | --- | --- | --- | --- |
| T04-01 | Verify Track 03 closure and delivered auth/error/CRUD/query seams. | Primary engineering thread / Scout | Track 03 closure | Complete | Track 03 merge `4df99c9` is clean and fully evidenced; existing auth/session, CRUD DTO/repository/service/router, UTC storage, indexes, top-tag setting, and harness seams are compatible. No migration or ADR change is justified. |
| T04-02 | Add filter DTO/date-range policy and response metadata. | Smith / implementation | T04-01 | Pending | Boundary/reversed/UTC tests. |
| T04-03 | Implement owner-scoped ORM items/total query in one read transaction, eager strategy, pagination, literal-substring escaping, and duplicate-safe tag predicate. | Smith / implementation | T04-01, T04-02 | Pending | Shared-snapshot/predicate/order/page/query-count evidence. |
| T04-04 | Implement isolated parameterized raw-SQL stats reader in one read transaction. | Smith / implementation | T04-01 | Pending | Empty/populated/tie/month/cross-user aggregate tests. |
| T04-05 | Wire protected list/stats routes and operation OpenAPI; register static stats before dynamic ID. | Smith / implementation | T04-02, T04-03, T04-04 | Pending | Route/schema/status/security tests. |
| T04-06 | Add correctness, EXPLAIN, query-count, raw-SQL-isolation regression tests, and Track 04 process-harness assertions. | Smith / implementation | T04-03, T04-04, T04-05 | Pending | Deterministic ledger, query-count, and EXPLAIN receipts; `scripts/verify-track-04.sh` proves real filter/stats HTTP flows, relevant supported DB inspection, base JSON-Line fields/safe correlation/redaction/exactly-one-owning-boundary exception behavior, ephemeral response/token handling and sentinel absence, and cleanup without claiming N+1 from process smoke alone. |
| T04-07 | Closure validation and evidence recording. | Primary engineering thread | T04-01, T04-02, T04-03, T04-04, T04-05, T04-06 | Pending | Actual passing deterministic filter/date/pagination/query-count/raw-SQL tests, quality/diff/hygiene review, and `bash scripts/verify-track-04.sh`; TEST-REPORT records commands/results/versions/selectors/cleanup, guideline conformance, EXPLAIN/query-count evidence, gaps, and retained Track 05 boundary. |

## Shared completion gate

The [engineering verification guideline](../../docs/ENGINEERING-VERIFICATION-GUIDELINE.md)
and [ADR-006](../ADR/ADR-006-engineering-verification-and-closure-evidence.md) apply
without changing Track 04's ORM/raw-SQL boundary, public DTO, or Track 05 ownership.
Planned, Ready, or Blocked is not done. T04-07 may mark Track 04 Complete only after
recorded passing deterministic evidence, actual real-process harness proof, and
documented cleanup; planned, skipped, or blocked commands never count as pass.

The future `scripts/verify-track-04.sh` extends the delivered bootstrap, never a fake
server. It uses a verified disposable migrated database and dynamic isolated port,
bounded-polls a delivered observable seam, creates actual authenticated data, and
asserts real list filters (literal wildcard, inclusive/boundary dates, stable pages/
total, exact tag) plus exact current-statistics body/tie/month/cross-user isolation.
Own-user fixture/JWT/list/stat response values are ephemeral/in-memory direct
assertions only: never print or persist them; use strictly protected disposable state
only if unavoidable and remove it during cleanup. It performs relevant supported
database inspection; validates JSON Lines `source`, service/component, event, level,
UTC timestamp, logger, `process_id`, and execution/thread identifier where applicable;
uses safe correlation not based on token/user/body/content; proves redaction, no raw
exception text indexed field, and exactly one owning-boundary unexpected exception.
It asserts URL/title/description/tag/token/content sentinel absence from application
logs, indexed fields, command diagnostics, assertion failures, unsafe debug bundles,
and retained artifacts, including cross-user values on failures, and verifies trap
cleanup. Deterministic query-count instrumentation and recorded `EXPLAIN QUERY PLAN`
evidence remain mandatory for N+1/index claims.

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
bash scripts/verify-track-04.sh
git diff --check
git status --short
```

Record actual SQLite `EXPLAIN QUERY PLAN` output and query-count measurements at
implementation. Validate Track 04 operations only; Track 05 owns global conformance.
