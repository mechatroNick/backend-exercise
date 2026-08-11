# Track 09 specification: final cleanup, documentation migration, and test reports

- Status: In progress
- Specification version: 1.1
- Planned: 2026-08-09
- Owner: Primary engineering thread
- Depends on: Completed Track 08 merge `a9cccc2` and current report at clean source `d6c08e0`
- Governing records: `.docs/ASSESSMENT.md`, `.docs/SOLUTION-DESIGN.md`,
  `.docs/DELIVERY-PLAN.md`, ADR-001 through ADR-009, and every Track 00–08
  closure record

## Intent anchor

Finish the repository as a modern, type-safe, fresh-reader-friendly assessment
without changing its accepted HTTP, persistence, security, statistics, one-worker,
or delivered private Track 07 projection contracts. The refreshed work is complete
only when the renamed durable
documentation, product refactors, terminal reports, Docker path, and clean-source
verification agree.

## Must preserve

- The exact 10-operation public API, 45 documented operation/status pairs, response
  bodies/headers, ownership isolation, error envelope, auth behavior, migration
  history, seed guarantees, cursor compatibility, rate-limit policy, and current
  statistics semantics delivered through Track 08.
- One Uvicorn worker, process-local rate/snapshot state, the single named statistics
  refresher, graceful lifecycle cleanup, Alembic-only schema ownership, and SQLite
  assessment scope.
- JSON Lines-only safe logging with service/component/source attribution, redaction,
  bounded exception evidence, exactly-once owning-boundary failure logging, and no
  identity, token, body, SQL, path, bookmark content, or private material disclosure.
- Track 07 private weekly working/point/state persistence, correction revisions,
  dual-generation completion, readiness, and the exact existing named non-daemon
  refresher; no public history API, second worker, external worker, or fabricated evidence.
- Historical receipts as truthful records. Editorial link/path repairs may keep old
  evidence reachable, but must not change recorded outcomes, dates, commits, counts,
  or statuses.

## Decision latitude

Track 09 may choose the internal Pydantic model layout, a typed lifecycle event
module, typed third-party adapters, a reusable Bash report formatter, and the exact
README organization. It may update locked test-only dependencies when a current
upstream deprecation warning proves the replacement is required. It may not change a
public API/schema, database migration, security policy, runtime topology, or bonus
contract without a new accepted ADR and primary-thread review.

## Scope

Included:

- atomically move the entire tracked `docs/` tree, including the supplied assessment
  PDF, to `.docs/`; update every live reader link, verifier, retained harness
  contract, ignore rule, and durable Markdown target;
- replace all production and test-helper standard-library dataclasses with Pydantic
  v2 models while deliberately preserving frozen/mutable state, strict invariants,
  equality, hashing, concurrency, serialization, cursor, event, seed, and stats
  behavior;
- define the five `application.*` lifecycle log event names as `StrEnum` values and
  use those members at lifecycle call sites without changing emitted JSON values;
- replace only warning-backed deprecated APIs/dependencies with their current
  supported equivalents; explicitly retain FastAPI lifespan plus
  `@asynccontextmanager`, which current FastAPI guidance recommends;
- remove reasonable application type suppressions or replace them with typed
  adapters, add a repository Pyright/Pylance-compatible check if it can be locked and
  made deterministic, and document any justified third-party boundary suppressions;
- make every verification script emit a readable standalone terminal report with
  identity, gates, pass/fail/incomplete status, useful summaries, and cleanup outcome while
  preserving nonzero failure propagation and safe/private output handling;
- ensure Docker-focused tests execute after the image build and prove image/runtime
  delivery before a final Docker pass is printed;
- add a Track 09 final clean-source automation entry point and high-coverage unit,
  integration, contract, edge, failure, and real-process evidence; and
- make root `README.md` the only first-stop reader document, beginning with the SDD
  Mermaid workflow, then requirements/limitations, setup, functional-test report
  commands, Docker verification, architecture/security, and Tracks 00–09 status.

Excluded:

- external push, archive, pull request, release publication, deployment, submission,
  or private-correspondence access/disclosure;
- new weekly/public-history behavior, production infrastructure, PostgreSQL, Redis/
  broker, multi-worker support, public API expansion, or additional schema changes;
- replacing a supported API merely because it was named as an example; and
- weakening a test, coverage threshold, manifest, cleanup check, redaction rule, or
  previous harness so a refactor appears green.

## Requirements

| ID | Requirement |
| --- | --- |
| T09-REQ-01 | Move all nine tracked documentation files from `docs/` to `.docs/` with no compatibility duplicate/symlink and no stale operational `docs/` path. Update all live links, verification roots, Docker ignore rules, and path contract tests. |
| T09-REQ-02 | Preserve historical evidence truthfully while making every current Markdown link resolve in a clean checkout; distinguish the FastAPI `/docs` endpoint from repository documentation paths. |
| T09-REQ-03 | Replace every standard-library dataclass in production and test helpers with explicit Pydantic v2 models. Preserve each model's actual immutability/mutability, strict validation, invariant, equality/hash, positional-call migration, serialization, state, and concurrency semantics. |
| T09-REQ-04 | Represent `application.starting`, `application.startup_failed`, `application.started`, `application.stopping`, and `application.stopped` as lifecycle `StrEnum` members at call sites while emitting the same JSON strings and lifecycle ordering. Keep the generic logging boundary extensible. |
| T09-REQ-05 | Run warning-enabled tests and source/API inventories. Replace every demonstrated deprecated project use with the current supported replacement. Preserve the already-current FastAPI lifespan `@asynccontextmanager` pattern and record why no replacement occurred where no deprecation exists. |
| T09-REQ-06 | Resolve reasonable application Pylance/Pyright/type diagnostics with typed code or narrowly justified adapters, without casts/ignores that conceal a behavior defect. Record the checker/version/configuration and residual third-party boundaries. |
| T09-REQ-07 | Every `verify-*.sh` script prints a consistently formatted standalone report that identifies the script, executed gates/selectors, result, relevant summary, and cleanup. Formatting must not swallow failures, leak private logs, or claim skipped/unrun work passed. |
| T09-REQ-08 | Docker automation builds first, then runs the Docker contract/focused tests and real image migration/start/health/SIGTERM/cleanup evidence before printing a Docker or final pass. A missing daemon is a nonzero incomplete result, not a pass/skip. |
| T09-REQ-09 | Root README begins with the SDD Mermaid workflow; accurately summarizes requirement satisfaction, functional test-report generation, Docker checks, limitations, completed private Track 07, and Tracks 00–09 status; detailed specifications are referenced rather than duplicated. |
| T09-REQ-10 | Deliver comprehensive Track 09 Bash automation plus high-coverage/full-edge unit, integration, contract, migration, runtime, logging, documentation, dependency, security, and cleanup tests. Final evidence runs from a clean committed source and preserves 100% statement and branch coverage. |
| T09-REQ-11 | Make incremental green commits on the Track 09 branch, review every write wave, merge with a merge commit to `main` only after the complete branch gate passes, and rerun the final gate on merged `main`. |

## Acceptance evidence threshold

Track 09 closes only with recorded current evidence that:

- the 865-test/3-subtest Track 08 baseline is preserved or intentionally expanded,
  no warning remains, and full repository statement/branch coverage is 100%;
- no Python standard-library dataclass import/decorator remains in application or
  tests, and focused tests prove strict/frozen/mutable/invariant/concurrency edges;
- public OpenAPI/runtime manifests, migrations, cursor compatibility, auth/ownership,
  seed idempotency/safety, rate-limit isolation/capacity, current stats, health,
  JSON Lines logging, startup-failure disposal, and shutdown behavior remain exact;
- the full documentation tree exists only at `.docs/`, all local links resolve, the
  documentation gate counts 43 assessment IDs, nine accepted ADRs, and ten tracks,
  and fresh-reader claims match current code/evidence;
- every automation script passes its shell/static contract and emits a readable
  terminal receipt in both success and injected-failure paths;
- Docker builds before Docker tests; migration-only, normal startup, liveness,
  non-root/one-worker, graceful stop, logs, and recursive cleanup pass without an
  orphan image/container/volume or hidden skip;
- `scripts/verify-track-09.sh` passes from the reviewed committed source, every
  inherited Track 01–07/08 gate remains green, and cleanup is verified;
  and
- the exact merged `main` commit passes the final Track 09 gate with a clean worktree.

## Stop conditions

Stop and reframe on any public-schema/response drift, cursor incompatibility,
validation coercion that weakens an invariant, rate/state race, statistics
correctness change, logging disclosure, historical-evidence alteration, secret,
unresolved critical/high defect, coverage reduction, hidden Docker skip, orphan
resource, or cleanup failure. Stop before any external action or history rewrite.
Seek owner direction if a requested Pylance change requires an unbounded dependency
or if a demonstrated deprecation has no behavior-preserving supported replacement.

## Traceability

| Track 09 evidence area | Governing requirement |
| --- | --- |
| Documentation relocation and reader entry point | T09-REQ-01, T09-REQ-02, T09-REQ-09 |
| Pydantic internal models and lifecycle events | T09-REQ-03, T09-REQ-04, ADR-008 |
| Deprecation and type modernization | T09-REQ-05, T09-REQ-06 |
| Standalone Bash reports and Docker order | T09-REQ-07, T09-REQ-08 |
| Comprehensive final proof and Git closure | T09-REQ-10, T09-REQ-11, ADR-006 |
