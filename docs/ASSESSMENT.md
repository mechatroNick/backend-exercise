# Assessment interpretation and requirement baseline

## Purpose

This document records what the supplied exercise requires, which additional choices
have been accepted, and how completion will be proven. It prevents optional
engineering demonstrations from displacing the scored API behavior.

Authoritative source: [Technical Assessment Senior Software_Engineer.pdf](Technical%20Assessment%20Senior%20Software_Engineer.pdf), pages 1-6.

## Executive interpretation

Build a complete, locally runnable JSON API that lets authenticated users create,
tag, search, filter, inspect, update, and delete only their own bookmarks. The system
must demonstrate relational modelling, migrations, secure password handling, JWT
authentication, efficient SQL, a raw-SQL statistics endpoint, accurate interactive
OpenAPI documentation, consistent errors, and meaningful automated tests.

The solution must be free and self-contained. Python, SQLite, and open-source Python
packages are sufficient. Docker is optional. The repository and its commit history
are part of the submission, and the implementation must be explainable in a follow-up
walkthrough.

The PDF says both "up to 5 days" and "7 calendar days." This schedule discrepancy
does not affect the implementation contract; the project is being delivered over a
few days with quality taking priority.

The exercise originally disallowed AI code generation. The repository owner records
that HR authorized AI use for this submission, with the process to be disclosed later.
Supporting correspondence is external and private and is not stored in this repository.
If that authorization is rescinded or disputed, the original assessment restriction
controls. The final process document must distinguish human decisions, AI assistance,
validation, and reviewer-explainable ownership.

## Requirement matrix

### Governance and delivery

| ID | Classification | Requirement | Owning track | Closure evidence |
| --- | --- | --- | --- | --- |
| GOV-01 | Required support | Preserve explicit requirements, decisions, dependencies, and validation evidence. | 00 | Approved baseline, ADR set, and track traceability. |
| DEL-01 | Required | Submit a Git repository/link or archive with meaningful incremental history. | 08 | Submission-ready repository and documented commit sequence. |
| DEL-02 | Required support | Explain project architecture and deployment architecture in the README. | 08 | Fresh-reader review of the completed README. |
| DEL-03 | User-decided | Disclose the AI-assisted engineering process later using actual evidence. | 08 | Process section accurately reflects completed work. |

### Runtime and data

| ID | Classification | Requirement | Owning track | Closure evidence |
| --- | --- | --- | --- | --- |
| ENV-01 | Required | Run locally using Python 3.10+ and free open-source tooling with no paid/cloud dependency. | 01 | Fresh setup and run commands succeed locally. |
| ARC-01 | Required | Use a clean project and dependency structure with an explainable local deployment architecture. | 01 | Module/dependency review and documented runtime topology. |
| DATA-01 | Required | Persist `User`, `Bookmark`, `Tag`, and `bookmark_tags` with proper relationships and migrations. | 01 | `alembic upgrade head` against an empty database. |
| DATA-02 | Required | Enforce required fields; unique username/email/tag name; 80/200/500/50-character username/title/description/tag limits; foreign keys; and appropriate indexes. | 01 | Migration DDL review plus constraint and index tests. |
| DATA-03 | Required | Model bookmark-to-tag as many-to-many. | 01 | Composite link-table key and relationship tests. |
| DATA-04 | User-decided | Enforce SQLite foreign keys on every application, test, migration, and worker connection. | 01 | `PRAGMA foreign_keys=1` and invalid-FK failure tests. |

### Identity, authentication, and errors

| ID | Classification | Requirement | Owning track | Closure evidence |
| --- | --- | --- | --- | --- |
| AUTH-01 | Required | `POST /api/auth/register` returns 201 with public user fields and token. | 02 | Endpoint, OpenAPI, and contract tests. |
| AUTH-02 | Required | `POST /api/auth/login` returns 200 with public user fields and token. | 02 | Endpoint, OpenAPI, and contract tests. |
| AUTH-03 | Required | Hash passwords and issue signed, verified, expiring JWTs. | 02 | Hash, login, tampered-token, and expiry tests. |
| AUTH-04 | Required | Protect every bookmark endpoint and separate auth concerns from route logic. | 02 | Dependency/route review and missing/invalid-token tests. |
| ERR-01 | Required | Return every error using a consistent JSON envelope. | 02 | Validation, auth, conflict, not-found, and unexpected-error tests. |
| SEC-01 | User-decided | Canonicalize identities, use Argon2, access-only JWTs, environment secrets, and non-enumerating errors. | 02 | Security-focused tests and log/DTO review. |

### Bookmark behavior and isolation

| ID | Classification | Requirement | Owning track | Closure evidence |
| --- | --- | --- | --- | --- |
| BKM-01 | Required | Implement bookmark create, list, detail, partial update, and delete. | 03 | Happy-path, validation, no-op, and deletion tests. |
| BKM-02 | Required | Store valid URL, required title, optional description, and timestamps. | 03 | DTO and database constraint tests. |
| BKM-03 | Required | Attach one or more tags through the many-to-many relationship. | 03 | Create/update/remove/deduplicate tag tests. |
| ISO-01 | Required | Users can see and mutate only their own bookmarks. | 03 | Cross-user list/detail/update/delete/statistics tests. |
| TAG-01 | User-decided | Trim and lowercase tags, reject empty tags, deduplicate input, and retain orphan tag rows. | 03 | Normalization, uniqueness, and association tests. |
| TIME-01 | User-decided | Preserve immutable `created_at`; advance `updated_at` only for material scalar or tag changes. | 03 | Controllable-clock timestamp invariant tests. |

### Queries and current statistics

| ID | Classification | Requirement | Owning track | Closure evidence |
| --- | --- | --- | --- | --- |
| QRY-01 | Required | Filter list by exact normalized tag, title keyword, `from`/`to` date range, and pagination. | 04 | Combination and boundary tests. |
| QRY-02 | User-decided | Add `updated_from`/`updated_to`, UTC inclusive calendar dates, stable ordering, page size 20/max 100. | 04 | OpenAPI examples and range/order tests. |
| SQL-01 | Required | Implement authenticated `GET /api/bookmarks/stats` using raw SQL. | 04 | Named parameterized SQL reader and endpoint integration test. |
| SQL-02 | Required | Return `total_bookmarks`, `total_tags`, and ordered `top_tags`/`bookmarks_per_month` items using the assessment's public `count` field. | 04 | Hand-calculated multi-user/multi-tag/month tests. |
| SQL-03 | Required | Avoid N+1 behavior, use efficient joins/aggregation, and return pagination total. | 04 | Query review and eager-loading/aggregation evidence. |

### Event-driven statistics extension

| ID | Classification | Requirement | Owning track | Closure evidence |
| --- | --- | --- | --- | --- |
| EVT-01 | User-decided | Publish non-sensitive post-commit invalidation events for material bookmark mutations. | 06 | Transaction-order and event-content tests. |
| EVT-02 | User-decided | Drain a bounded in-process queue every configurable 10 seconds and coalesce affected users. | 06 | Deterministic queue/clock tests without real sleeps. |
| EVT-03 | User-decided | Recompute canonical statistics with raw SQL and atomically publish snapshots with live fallback. | 06 | Snapshot/live parity, failure, stale, and disabled-worker tests. |
| WIN-01 | User-decided | Recalculate one developing UTC weekly event-time point per user. | 07 | Monday boundary and replacement tests. |
| WIN-02 | User-decided | Append immutable developed points and correction revisions for late changes. | 07 | Finalization, late-delete/tag-change, and idempotency tests. |
| WIN-03 | User-decided | Use durable dirty-window markers to recover queue loss and post-commit crash windows. | 06 | Restart/overflow recovery tests. |
| OPS-01 | User-decided | Start services together, name the worker thread, expose meaningful liveness/readiness, and attribute logs by service. | 06 | Lifespan, health-state, shutdown, and log-capture tests. |

### OpenAPI and verification

| ID | Classification | Requirement | Owning track | Closure evidence |
| --- | --- | --- | --- | --- |
| API-01 | Required | Serve complete interactive OpenAPI 3.0+ documentation at `/docs` or `/api/docs`. | 05 | Running docs and schema inspection. |
| API-02 | Required | Document request/response schemas, status codes, examples, security, and reusable models. | 05 | Operation-by-operation contract audit. |
| TEST-01 | Required | Provide at least ten tests across happy paths, edge cases, auth, and contract validation. | 05 | Collected suite count and passing report. |
| TEST-02 | Required | Validate actual API responses against the published OpenAPI schema. | 05 | Schemathesis response/status/content-type/schema checks. |
| QUAL-01 | User-decided | Pass formatting, linting, typing, migration, and focused coverage checks locally. | 05 | Reproducible local quality command results. |

### Submission and optional scope

| ID | Classification | Requirement | Owning track | Closure evidence |
| --- | --- | --- | --- | --- |
| DOC-01 | Required support | Provide setup, migration, run, API, testing, architecture, deployment, and trade-off documentation. | 08 | Fresh-clone and fresh-reader verification. |
| BONUS-01 | Optional | Seed script. | 08 | Deterministic sample data and documented invocation. |
| BONUS-02 | Optional | Docker setup, rate limiting, or cursor pagination. | 08 | Implemented only after all required evidence is green. |
| FUT-01 | Future only | External worker/broker, multi-process coordination, PostgreSQL, and production infrastructure. | 08 | Documentation only; no assessment dependency. |

## Accepted decisions

| Decision | Record | Practical effect |
| --- | --- | --- |
| FastAPI + synchronous SQLModel + SQLite + Alembic | [ADR-001](../.tracks/ADR/ADR-001-application-stack-and-data-access.md) | Small local modular monolith, ORM by default, raw SQL limited to statistics. |
| Explicit REST, filters, tags, and timestamp rules | [ADR-002](../.tracks/ADR/ADR-002-api-contract-and-timestamps.md) | Deterministic API and test behavior. |
| Canonical identity, Argon2, and access-only JWT | [ADR-003](../.tracks/ADR/ADR-003-identity-and-token-security.md) | Proportionate local authentication without refresh-token scope. |
| Event queue and managed statistics thread | [ADR-004](../.tracks/ADR/ADR-004-event-driven-statistics-service.md) | Eventual snapshot acceleration while preserving a canonical live raw-SQL path. |
| UTC weekly event-time windows and immutable corrections | [ADR-005](../.tracks/ADR/ADR-005-windowed-statistics-data-points.md) | Mutable open point, append-only closed revisions, durable dirty-marker recovery. |

## Completion invariant

Track 04 must provide a complete, current, user-scoped raw-SQL statistics endpoint,
and Track 05 must close the mandatory quality gate before Track 06 overlays queueing,
snapshots, or history. Disabling or failing the background extension must not break
the core endpoint or change its response body.

## Non-goals

- A frontend or public historical-statistics endpoint.
- Supporting more than one database dialect in the assessment runtime.
- Multiple Uvicorn workers while queue/cache state is in process.
- Refresh-token rotation, RBAC, social login, or account-management features.
- An external broker, distributed scheduler, or cloud deployment.
- Treating Docker, rate limiting, or cursor pagination as prerequisites.
- Inventing the final engineering-process narrative before implementation evidence
  exists.

## Acceptance threshold

The submission is complete only when every required row above has direct evidence,
all accepted extensions preserve the required contracts under failure/disablement,
the repository is runnable from a fresh local checkout, and the author can explain
the design and trade-offs without relying on hidden tooling context.
