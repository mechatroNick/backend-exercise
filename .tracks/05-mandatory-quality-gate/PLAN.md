# Track 05 plan: mandatory quality and contract gate

- Specification: [SPEC.md](SPEC.md), version 1.1
- Governing ADRs: ADR-001, ADR-002, ADR-003, ADR-006; ADR-004/005 excluded extension boundaries
- Status: Ready
- Active item: T05-02 mandatory evidence inventory after the passed T05-01 compatibility gate

| ID | Work item | Owner | Depends on | Status | Exit evidence |
| --- | --- | --- | --- | --- | --- |
| T05-01 | Verify closure receipts and current contracts for Tracks 01--04. | Smith / implementation | Tracks 01--04 closure | Complete | Verified Track 04 merge `8534e98`, passed Track 01--04 reports, current eight-operation OpenAPI inventory, 427 collected tests, query/raw-SQL/logging seams, and bounded metadata/tooling gaps. |
| T05-02 | Build the core requirement-to-evidence inventory and separate still-open Track 08 delivery obligations. | Smith / implementation | T05-01 | Pending | Every required/accepted core row owned by Tracks 01--05 maps to evidence; no delivery-only row is falsely closed. |
| T05-03 | Audit/fix operation OpenAPI metadata and `/docs`. | Smith / implementation | T05-01, T05-02 | Pending | Security/schema/status/example/content-type/204 audit. |
| T05-04 | Select/pin contract harness and validate real responses/errors. | Smith / implementation | T05-03 | Pending | Generated-schema instance evidence. |
| T05-05 | Add deterministic integration/performance/raw-SQL boundary matrix, real-instance contract suite, and logging schema/redaction audit. | Smith / implementation | T05-02, T05-04 | Pending | Exact collected mandatory-test count >=10 and selector/suite scope; fail any mandatory skip/xfail/deselection/masking/unrun case; record owner/reason for intentional nonmandatory skips; pinned contract-tool command, deterministic query-count suite, coverage-record command, OpenAPI real-instance validation, N+1/query-count/parameterization evidence, and complete base JSON Lines/causal-exception evidence. |
| T05-06 | Clean migration, bootstrap, mandatory-core process harness, coverage recording, and quality rehearsal. | Smith / implementation | T05-05 | Pending | `scripts/verify-track-05.sh` starts the actual server from disposable clean/migrated state on a dynamic port; directly invokes `scripts/verify-track-01.sh` through `scripts/verify-track-04.sh`, or a named in-repo orchestrator that invokes each; fails missing/stale/unrun/nonzero upstream receipts and records every selector/result; validates auth/CRUD/search/canonical-live-stats/errors/docs/OpenAPI, base JSON Lines/redaction/exception ownership, safe ephemeral assertions, and cleanup. |
| T05-07 | Primary defect/risk review and TEST-REPORT closure. | Primary engineering thread | T05-01, T05-02, T05-03, T05-04, T05-05, T05-06 | Pending | Actual passing deterministic/contract/performance/logging evidence and `bash scripts/verify-track-05.sh`; TEST-REPORT records exact commands/results/versions/selectors/cleanup, exact collected-test count and mandatory scope, upstream selector/result receipts, pinned contract-tool, deterministic query-count, and coverage-record commands, no critical/high defect, and Track 06 remains blocked unless the gate is green. |

## Shared completion gate

The [engineering verification guideline](../../docs/ENGINEERING-VERIFICATION-GUIDELINE.md)
and [ADR-006](../ADR/ADR-006-engineering-verification-and-closure-evidence.md) apply
without changing the mandatory-core scope or the Track 06 stop. Planned, Ready, or
Blocked is not done. T05-07 may mark Track 05 Complete only after recorded passing
deterministic tests, real-instance OpenAPI validation, performance/raw-SQL and
logging-redaction evidence, actual process-harness proof, and documented cleanup;
planned, skipped, or blocked commands never count as pass.

The future `scripts/verify-track-05.sh` is the mandatory-core automation gate. It
uses a verified disposable clean/migrated state and dynamic isolated port, starts the
actual server, directly invokes `scripts/verify-track-01.sh` through
`scripts/verify-track-04.sh` or a named in-repo orchestrator that invokes every one,
and records each selector/result. Missing, stale/unrun, or nonzero upstream receipts
fail closure. It then exercises auth/CRUD/search/canonical-live-stats/errors/docs/
OpenAPI flows; Track 06-owned health flows are excluded. It validates actual
statuses/bodies against generated OpenAPI and parses JSON Lines for `source`,
service/component, event, level, UTC timestamp, logger, `process_id`, execution/thread
identifier where applicable, safe non-sensitive correlation, redaction, and exactly
one owning-boundary unexpected-exception record with complete causal evidence.
Own-user public bookmark fields/counts and returned JWTs are ephemeral in-memory
assertion inputs: parse/use tokens without echoing or persistent storage, never expose
cross-user data, and keep those values out of logs, indexed log fields, command output,
assertion failures, debug bundles, and retained artifacts. Verify trap cleanup.
Deterministic query-count and complete-contract tests remain separate mandatory
evidence; smoke cannot substitute for them.

## Edge-case/evidence ledger

| Area | Evidence |
| --- | --- |
| Contract | Every success/documented error, content type, bearer requirement, example, and `204` bodylessness validates at runtime. |
| Core matrix | Foundation, auth, isolation, CRUD/tags/timestamps, query pages/dates, stats, errors, and API requirements owned by Tracks 01--05 each have direct evidence; Track 08 rows remain visible and open. |
| Performance/safety | Query-count/N+1 regressions; raw SQL only in stats reader, named parameters, owner scope. |
| Reproducibility | Empty migration build, bootstrap, representative HTTP smoke, collected count, coverage record, lint/type/test pass. |
| Mandatory execution | Record exact collected count >=10 and mandatory selector/suite scope; fail skip/xfail/deselection/masking/unrun mandatory tests. An intentional nonmandatory skip records owner/reason and is not evidence. |
| Logging/disclosure | Complete base JSON Lines/causal-exception proof; own-user fields/counts/JWT stay ephemeral and all sensitive/cross-user data is absent from unsafe receipt surfaces. |
| Defects | No skip/xfail masking; owning-track fix or ADR/SPEC escalation, then rerun affected evidence. |

## Planned validation commands

```text
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run mypy app
uv run pytest --collect-only
uv run pytest
uv run pytest -k 'query_count or explain'
uv run alembic upgrade head
uv run alembic downgrade base
uv run alembic upgrade head
uv run alembic check
make check
bash scripts/verify-track-05.sh
git diff --check
git status --short
```

Add the selected pinned contract-tool command and coverage-record command at
implementation time; record their exact commands/results alongside the deterministic
query-count suite, collected mandatory-test count/scope, upstream harness
selector/results, and documented bootstrap/HTTP smoke in `TEST-REPORT.md`.
