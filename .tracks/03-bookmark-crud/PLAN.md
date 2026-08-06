# Track 03 plan: protected bookmark CRUD, tags, ownership, and timestamps

- Specification: [SPEC.md](SPEC.md), version 1.1
- Governing ADRs: ADR-001, ADR-002, ADR-004, ADR-006
- Status: Complete
- Active item: None; Track 03 passed closure validation and is ready to merge

## Execution plan

| ID | Work item | Owner | Depends on | Status | Exit evidence |
| --- | --- | --- | --- | --- | --- |
| T03-01 | Verify Track 01/02 closure receipts and delivered sessions, models/migration, clock, auth dependency, error boundary, composition, and tests. | Primary engineering thread / Scout | Track 01 and Track 02 closure | Complete | Track 02 merge `adb0e8c`; committed Track 01/02 passing reports; existing tables/constraints, session, clock, current-subject, errors, and composition match; 48 focused compatibility tests passed with no material mismatch. |
| T03-02 | Implement strict bookmark/tag create, PATCH, public, and compatible list DTOs plus normalization/material-change helpers. | Smith / implementation | T03-01 | Complete | Strict DTO/policy matrices cover validation, omitted/null, equivalence, canonical tags, materiality, and disclosure at 100% branch coverage. |
| T03-03 | Implement explicit owner-scoped bookmark and canonical-tag repository operations without repository commits. | Smith / implementation | T03-01, T03-02 | Complete | Migrated-SQLite tests prove owner predicates, deterministic association reads, tag reuse, rollback, cascades, and orphan retention. |
| T03-04 | Implement service-owned create/detail/baseline-list/PATCH/delete transactions with timestamp and rollback semantics. | Smith / implementation | T03-02, T03-03 | Complete | Fixed-clock and fault tests prove atomicity, duplicate URLs, material/no-op time, native tag-conflict recovery, unrelated-integrity fail-closed behavior, and post-commit publication. |
| T03-05 | Add an inert `DomainEventPublisher` injection port/no-op adapter at the explicit post-commit extension point, without a concrete event contract. | Smith / implementation | T03-04 | Complete | Unit/composition tests and bounded source scans prove the no-op seam is inert and no Track 06 runtime exists. |
| T03-06 | Add protected CRUD routes, authenticated owner injection, response/error/OpenAPI metadata, and route order review. | Smith / implementation | T03-01, T03-02, T03-04, T03-05 | Complete | Endpoint tests prove bearer protection, accepted statuses, identical concealed `404`, positive IDs, exact public bodies, bodyless `204`, and bounded operation schemas. |
| T03-07 | Add edge-case regression, disclosure, lazy-loading boundary checks, and Track 03 process-harness assertions. | Smith / implementation | T03-02, T03-03, T03-04, T03-05, T03-06 | Complete | The deterministic ledger passes; `scripts/verify-track-03.sh` proves the real bootstrap/CRUD/isolation/tag/timestamp/OpenAPI/log-redaction/cleanup flow without claiming Track 04 performance. |
| T03-08 | Run closure validation and record evidence/readiness for Track 04. | Primary engineering thread | T03-01, T03-02, T03-03, T03-04, T03-05, T03-06, T03-07 | Complete | `TEST-REPORT.md` records 348 full tests, 100% application statement/branch coverage, disposable migrations, all three live harnesses, independent review/correction, hygiene, and retained downstream boundaries. |

## Work-wave detail

### T03-01 — Gate

Confirm migrated model constraints, UTC clock/session/factory seams, Track 02 bearer
current-user resolution and centralized errors. No migration or upstream-contract
change; stop if a required invariant is absent.

### T03-02 through T03-04 — DTOs, repositories, services

- Forbid extra untrusted fields. Create requires HTTP(S), title 1--200, optional
  description <=500, non-empty normalized tags. PATCH uses unset semantics; null URL/
  title fail; null description clears; supplied tags cannot normalize empty.
- Normalize tags once (trim/lowercase/maximum-50/non-empty/dedup); compare membership as a
  set, making reorder a no-op. Public DTOs exclude `user_id` and persistence-only data.
- Every repository method accepts user ID; repositories do ORM work only and never
  commit. Services own one transaction for bookmark/tag/link/timestamp state.
- Reuse global tags; resolve only known unique-tag races after rollback/reload. Do not
  delete orphan tag rows. Capture one creation instant; later time only for material change.

### T03-05 through T03-08 — seam, HTTP, evidence

- The port/no-op publisher seam is injected at the explicit post-commit extension
  point. Track 03 does not name, construct, publish, or count a real event and does not
  implement a queue, marker, worker, or statistics path.
- CRUD routes rely on bearer auth/error translation. Do not add inert `/stats`; Track
  04 must register static stats before dynamic ID route when it implements it.
- Validate Track 03 operations against generated schemas only; Track 05 owns global
  conformance. Use disposable migrated SQLite, fixed clocks, and the inert no-op
  publisher composition.
- Deliver `scripts/verify-track-03.sh` through that actual bootstrap, never a fake
  server. Use a disposable migrated database and dynamic isolated port, then
  bounded-poll a delivered observable seam before real HTTP registration/auth,
  create/list/detail/PATCH/delete, two-user concealed `404`, normalized/deduplicated
  tags, material/no-op timestamp, and bodyless `204` checks. Intended own-user
  response URL/title/description/tags/timestamps and returned JWT are assertion inputs
  only: keep them ephemeral/in-memory, or strictly protected disposable state only if
  unavoidable; parse/use without echoing and remove response/token state during
  cleanup. Never expose cross-user data. Capture JSON Lines for `source`,
  service/component, event, level, UTC timestamp, logger, `process_id`, and
  execution/thread identifier where applicable, safe request correlation not based on
  token/user/content, redaction, and exactly one unexpected-exception record at the
  owning HTTP boundary. Seed only safe token/URL/title/description/tag sentinels and
  assert their absence from application logs, indexed fields, diagnostics/command
  output, assertion failures, unsafe debug bundles, and retained artifacts. Verify
  trap cleanup and that the injected no-op publisher seam cannot change CRUD outcomes,
  without naming or asserting concrete Track 06 publication behavior.

## Shared completion gate

The [engineering verification guideline](../../docs/ENGINEERING-VERIFICATION-GUIDELINE.md)
and [ADR-006](../ADR/ADR-006-engineering-verification-and-closure-evidence.md) apply
without changing Track 03 contracts or downstream ownership. Planned, Ready, or
Blocked is not done. T03-08 may mark Track 03 Complete only after recorded passing
deterministic tests, actual real-process harness evidence, and documented cleanup;
planned, skipped, or blocked commands never count as pass.

## Edge-case ledger

| Dimension | Case | Planned proof |
| --- | --- | --- |
| Success | Authenticated create/list/detail/scalar PATCH/tag PATCH/delete. | T03-04/06 integration and endpoint tests. |
| Cross-user/missing | Other user's and absent IDs have identical `404`; list excludes other users. | T03-03/06 two-user tests. |
| Invalid input | Extra fields; bad URL; title/description limits; null URL/title; empty normalized tags. | T03-02/06 DTO/envelope tests. |
| Tags/races | Whitespace/case/dedup/order/reuse/orphans/overlong/global unique race. | T03-02/03/04 SQLite tests. |
| Optional data | Omitted/set/cleared description; duplicate URLs. | T03-02/04 tests. |
| Clock/no-op | One creation instant; immutable creation; material tag/scalar update; empty/equivalent/reorder unchanged. | T03-04 fixed-clock tests. |
| Rollback | Association/tag failure rolls back state/time; delete leaves tag orphan. | T03-04 forced-failure tests. |
| Publisher seam | No-op injection is inert; no concrete event/payload/count, queue, worker, or marker exists. | T03-05 composition test and source scan. |
| HTTP | `201`/`200`, error envelope, bodyless `204`, bounded OpenAPI agreement. | T03-06 tests. |
| Lazy/N+1 | Baseline list returns tags; query-count performance is Track 04. | T03-07 functional test and explicit deferral. |
| Leakage | Own-user response URL/title/description/tags/timestamps and returned JWT are ephemeral assertion inputs only; no credentials, headers, cross-user values, submitted content, internals, or stacks enter application logs, indexed fields, diagnostics/output, assertion failures, unsafe debug bundles, or retained artifacts. | T03-07 response-handling/redaction tests, harness scan, cleanup, and status review. |

## Planned validation commands

```text
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run mypy app
uv run pytest tests/unit tests/integration tests/contract -k 'bookmark or tag or ownership or timestamp'
uv run pytest
uv run alembic upgrade head
uv run alembic check
make check
bash scripts/verify-track-03.sh
rg -n 'queue\.Queue|bookmark-stats-refresher|StatsDirty|dirty.marker' app tests
git diff --check
git status --short
```

Exact spelling is inherited from delivered Track 01/02 tooling and must be recorded
when authorized. This plan does not claim Track 04 performance/pagination or Track 05
all-operation conformance.

## Review checkpoints and commit boundary

1. Gate; 2. DTO/null/normalization review; 3. owner/tag race/atomic timestamp review;
4. post-commit seam review; 5. operation OpenAPI review; 6. primary closure/deferred-work review.

Preferred green-boundary commit: `feat: implement isolated bookmark CRUD and normalized tags`.
Never commit credentials, tokens, headers, generated artifacts, queue/worker/marker,
or a failing intermediate state.
