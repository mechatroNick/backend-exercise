# Track 00 specification: contract and architecture baseline

- Status: Complete
- Specification version: 1.1
- Started: 2026-08-05
- Owner: Primary engineering thread
- Depends on: Supplied assessment and repository-owner clarifications
- Governing ADRs: ADR-001 through ADR-006

## 1. Intent anchor

Create a durable, reviewable contract for the Bookmarks API assessment so implementation can proceed without relying on chat history or silently inventing behavior.

The baseline must preserve the assessment's mandatory outcomes, capture every confirmed design choice, keep optional extensions subordinate to the core API, and define how completion will be evidenced.

## 2. Must-preserve behavior

- Every mandatory assessment requirement remains represented and owned by a delivery track.
- FastAPI, synchronous SQLModel, local SQLite, Alembic migrations, database constraints, and enforced relationships remain the accepted core stack.
- ORM is the default persistence mechanism. Raw SQL is restricted to the required statistics subsystem and explicitly documented there.
- All bookmark operations are authenticated and user-scoped.
- `created_at` is immutable; `updated_at` changes only after a committed material scalar or tag-membership update.
- Tag values are normalized and canonicalized.
- The required `/api/bookmarks/stats` endpoint is an all-current canonical view.
- Bookmark actions emit loosely coupled post-commit invalidations to a bounded queue once the extension is implemented.
- A named, lifespan-managed refresher batches invalidations at a configurable default ten-second cadence and has meaningful readiness evidence.
- Weekly historical points use bookmark `created_at` event time: a developing point is replaceable, a developed point is immutable, and late changes append correction revisions.
- One local bootstrap starts the API and its in-process supporting services with service-attributed logs.
- The final README and AI-process explanation describe verified implementation evidence rather than an invented future narrative.

## 3. Decision latitude

Implementation tracks may make local, reversible choices about:

- exact module/file boundaries that preserve the dependency direction;
- names of internal DTOs and repository methods;
- exact bounded defaults not fixed by the assessment or an ADR, provided they are Settings and documented;
- the OpenAPI response-validation library;
- testing fixtures and factories;
- formatting of structured logs and internal health payload detail;
- optional seed and Docker support after the mandatory gate passes.

An ADR update and repository-owner confirmation are required before changing:

- public route paths, status codes, authentication model, or response semantics;
- accepted identity/tag/date/timestamp normalization;
- the one-worker runtime constraint for an in-process queue/cache;
- current-versus-weekly statistics meaning;
- weekly event-time window boundaries or append-only correction semantics;
- ORM/raw-SQL ownership boundaries;
- a decision that materially expands submission scope.

## 4. Scope

### Included

- extract the assessment into a stable requirement matrix;
- classify requirements as required, user-decided, optional, or future-only;
- record accepted architectural decisions and rejected alternatives;
- describe the solution's runtime, modules, API, persistence, security, worker, projection, observability, testing, and evolution;
- divide delivery into manageable dependency-ordered tracks;
- define track-level acceptance evidence and stop conditions;
- create the Track 00 control artifacts and validate the documentation as a fresh reader.

### Excluded

- product code, migrations, or dependency installation;
- speculative final README claims;
- implementation of optional bonuses;
- external infrastructure or deployment;
- public historical-statistics APIs.

## 5. Inputs and authority

When documents conflict, use this precedence:

1. explicit repository-owner clarification;
2. supplied assessment PDF;
3. accepted ADRs;
4. assessment interpretation and solution design;
5. delivery and per-track plans.

Inputs:

- `docs/Technical Assessment Senior Software_Engineer.pdf`;
- clarifications and verification governance recorded in ADR-001 through ADR-006;
- `docs/ASSESSMENT.md`;
- `docs/SOLUTION-DESIGN.md`;
- `docs/DELIVERY-PLAN.md`.

## 6. Requirements

| ID | Requirement |
| --- | --- |
| T00-REQ-01 | The assessment interpretation identifies every mandatory behavior and non-functional expectation with a stable ID, classification, owning track, and closure evidence. |
| T00-REQ-02 | Accepted decisions are recorded as ADRs with context, decision, consequences, alternatives, and follow-up evidence. |
| T00-REQ-03 | ADR-005 states that a weekly point summarizes bookmarks whose `created_at` falls in that UTC week and that late changes append correction revisions. |
| T00-REQ-04 | The solution design separates all-current required statistics from weekly historical event-time points. |
| T00-REQ-05 | The solution design describes the complete local runtime, dependency boundaries, data model, API behavior, background lifecycle, health, security, testing, and production evolution. |
| T00-REQ-06 | The delivery plan reaches a mandatory API quality gate before the event-driven and historical extensions. |
| T00-REQ-07 | Every delivery track declares an outcome, scope, acceptance evidence, dependencies, and a proposed commit boundary. |
| T00-REQ-08 | Material ambiguities are resolved with the repository owner rather than silently assumed. Local reversible implementation choices remain documented as decision latitude. |
| T00-REQ-09 | A fresh-reader audit can understand the assignment, decisions, solution, and next implementation step without chat history. |

## 7. Acceptance evidence threshold

Track 00 closes only when:

- all T00 requirements have file-and-section evidence;
- links among `docs/` and `.tracks/` resolve;
- ADR status and track ownership agree across indexes and documents;
- there is no unresolved material product ambiguity known to the primary thread;
- a reader-oriented review identifies no blocking contradiction or missing assumption;
- the primary thread reviews and addresses the reader's findings;
- the next track can be planned from the durable artifacts alone.

## 8. Assumptions and confirmed context

- The repository owner records that HR authorized AI coding tool use for this
  assessment; supporting correspondence is external and private and is not stored in
  this repository. The final disclosure will be written from actual evidence.
- Delivery may take a few days and prioritizes quality.
- Local SQLite and one Uvicorn worker are acceptable for the assessment.
- The background service is an in-process thread, not a second operating-system process.
- The ten-second refresh interval is configurable and is not the weekly history resolution.
- No external broker, cron daemon, Docker runtime, or cloud service is required.

## 9. Unknowns

There are no currently known material product ambiguities blocking Track 01 planning.
The repository cannot independently verify the external/private HR correspondence. A
later implementation discovery must be raised if it would change public behavior or an
accepted ADR.

## 10. Stop conditions

Stop and request direction if:

- the assessment and a repository-owner decision cannot be reconciled;
- the repository-owner-recorded AI authorization is rescinded or disputed; in that
  case, the original assessment restriction controls;
- a newly discovered requirement changes the public API or statistics meaning;
- the design would require multiple Uvicorn workers while retaining process-local authoritative state;
- a proposed extension threatens the mandatory quality gate;
- implementation is requested before a material ambiguity is recorded and resolved.

## 11. Traceability

| Requirement | Primary evidence |
| --- | --- |
| T00-REQ-01 | `docs/ASSESSMENT.md` requirement matrix |
| T00-REQ-02 | `.tracks/ADR/ADR-001...ADR-006`, including ADR-006 closure evidence process |
| T00-REQ-03 | `.tracks/ADR/ADR-005-windowed-statistics-data-points.md`, Event-time design |
| T00-REQ-04 | `docs/SOLUTION-DESIGN.md`, sections 10 and 12 |
| T00-REQ-05 | `docs/SOLUTION-DESIGN.md`, sections 3–19 |
| T00-REQ-06 | `docs/DELIVERY-PLAN.md`, delivery strategy and Track 05 stop condition |
| T00-REQ-07 | `docs/DELIVERY-PLAN.md`, Tracks 00–08 |
| T00-REQ-08 | ADR decision records and this specification's decision latitude |
| T00-REQ-09 | Reader audit recorded in `TEST-REPORT.md` |

## 12. Post-closure governance addendum

Track 00 remains Complete for its documentation-contract scope. Its shared
[engineering verification guideline](../../docs/ENGINEERING-VERIFICATION-GUIDELINE.md)
sets evidence and closure rules for future executable tracks without asserting that
this baseline contains unit, API, database, log, or runtime proof. [ADR-006](../ADR/ADR-006-engineering-verification-and-closure-evidence.md)
makes that process binding while preserving the assessment, accepted ADRs, stricter
track rules, and existing product semantics.
