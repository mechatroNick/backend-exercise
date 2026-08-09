# Engineering tracks and decisions

This directory is the durable control plane for the Bookmarks API assessment. The
assessment source is stored in `../.docs/Technical Assessment Senior
Software_Engineer.pdf`.

## Intent anchor

Fulfil every functional and non-functional assessment requirement with a small,
explainable backend that demonstrates correctness, security, SQL competence,
observability, test discipline, and deliberate scope control.

## Architecture

```mermaid
flowchart LR
    Client["API client"] --> API["FastAPI API service"]
    API --> Domain["Application services"]
    Domain --> ORM["SQLModel ORM repositories"]
    ORM --> DB[("SQLite")]

    Domain --> Events["Stats event publisher"]
    Events --> Queue["Bounded in-process queue"]
    Queue --> Worker["bookmark-stats-refresher thread"]
    Worker --> RawSQL["Canonical raw SQL stats reader"]
    RawSQL --> DB
    Worker --> Snapshots["Atomic per-user stats snapshots"]
    API --> Snapshots
    API -. "missing or stale fallback" .-> RawSQL

    Health["Liveness and readiness"] --> API
    Health --> Worker
    Logs["Service-attributed logging"] --> API
    Logs --> Worker
```

## Architecture decisions

| ADR | Status | Decision |
| --- | --- | --- |
| [ADR-001](ADR/ADR-001-application-stack-and-data-access.md) | Accepted | FastAPI, synchronous SQLModel, SQLite, Alembic, constraints, and ORM/raw-SQL boundary |
| [ADR-002](ADR/ADR-002-api-contract-and-timestamps.md) | Accepted | REST contract, filters, PATCH semantics, tag normalization, and timestamp behavior |
| [ADR-003](ADR/ADR-003-identity-and-token-security.md) | Accepted | Identity normalization, password hashing, and access-only JWTs |
| [ADR-004](ADR/ADR-004-event-driven-statistics-service.md) | Accepted | Queue-driven periodic statistics service, snapshots, health, bootstrap, and logs |
| [ADR-005](ADR/ADR-005-windowed-statistics-data-points.md) | Accepted | Selected weekly developing-window and append-only correction design |
| [ADR-006](ADR/ADR-006-engineering-verification-and-closure-evidence.md) | Accepted | Binding engineering verification, evidence, and closure process |
| [ADR-007](ADR/ADR-007-local-rate-limiting-and-cursor-pagination.md) | Accepted | Local one-worker rate limiting and authenticated keyset cursors |
| [ADR-008](ADR/ADR-008-pydantic-internal-models-and-lifecycle-events.md) | Accepted | Strict Pydantic internal models and typed application lifecycle events |
| [ADR-009](ADR/ADR-009-track-07-weekly-projection-revival.md) | Accepted | Revives Track 07 implementation while preserving Track 06 invariants |

## Planned delivery tracks

| Order | Track | Depends on | State |
| --- | --- | --- | --- |
| 00 | Contract and ADR baseline | None | Complete |
| 01 | Foundation, configuration, schema, and migrations | 00 | Complete |
| 02 | Error contract, registration, login, and JWT authentication | 01 | Complete |
| 03 | Bookmark CRUD, tag relationships, and ownership isolation | 01, 02 | Complete |
| 04 | Search, date filters, pagination, and raw-SQL statistics | 03 | Complete |
| 05 | Mandatory OpenAPI, integration tests, and quality gate | 02-04 | Complete |
| 06 | Event queue, durable dirty recovery, current snapshots, health, and observability | 05 | Complete |
| 07 | Weekly developing points and append-only correction revisions | 06 closure evidence | **In progress** |
| 08 | Final hardening, documentation, assessment handoff, and all bonuses | Historical record; downstream re-open/update pending | Complete (pre-revival record) |
| 09 | Final cleanup, documentation migration, and standalone test reports | Historical record; downstream re-open/update pending | Complete (pre-revival record) |

Detailed `SPEC.md`, `PLAN.md`, and `HISTORY.md` artifacts may be created
sequentially after review of upstream plans, so a downstream track can be prepared
without waiting to repeat discovery. Their presence records planning only: a track is
implementation-ready only when its stated upstream implementation and closure gates
are satisfied. Decisions that change observable behavior require an ADR update before
implementation.

Current scope decision: Track 07 is Complete under ADR-009 with private projection
persistence, the existing one-worker integration, a harness, and a closure report.
Track 08 is reopened for downstream clean-source/Docker verification; Track 09 retains
a pre-revival completion record until it inherits that fresh gate. External push,
archive, sharing, deployment, and
submission remain owner-only actions outside repository completion.

Track completion uses the shared
[engineering verification guideline](../.docs/ENGINEERING-VERIFICATION-GUIDELINE.md):
Complete means the track's recorded evidence actually passed. Planned, Ready, and
Blocked states are not completion, and executable tracks also require their
deterministic tests and real-process harness evidence.

### Detailed planned artifacts

- [Track 02 specification](02-auth-errors/SPEC.md)
- [Track 02 execution plan](02-auth-errors/PLAN.md)
- [Track 02 history](02-auth-errors/HISTORY.md)
- [Track 03 specification](03-bookmark-crud/SPEC.md)
- [Track 03 execution plan](03-bookmark-crud/PLAN.md)
- [Track 03 history](03-bookmark-crud/HISTORY.md)
- [Track 03 test report](03-bookmark-crud/TEST-REPORT.md)
- [Track 04 specification](04-search-stats/SPEC.md)
- [Track 04 execution plan](04-search-stats/PLAN.md)
- [Track 04 history](04-search-stats/HISTORY.md)
- [Track 04 test report](04-search-stats/TEST-REPORT.md)
- [Track 05 specification](05-mandatory-quality-gate/SPEC.md)
- [Track 05 execution plan](05-mandatory-quality-gate/PLAN.md)
- [Track 05 history](05-mandatory-quality-gate/HISTORY.md)
- [Track 05 mandatory core evidence matrix](05-mandatory-quality-gate/CORE-EVIDENCE-MATRIX.md)
- [Track 05 test report](05-mandatory-quality-gate/TEST-REPORT.md)
- [Track 06 specification](06-event-driven-stats/SPEC.md)
- [Track 06 execution plan](06-event-driven-stats/PLAN.md)
- [Track 06 history](06-event-driven-stats/HISTORY.md)
- [Track 07 weekly-projection specification](07-weekly-projections/SPEC.md)
- [Track 07 weekly-projection plan](07-weekly-projections/PLAN.md)
- [Track 07 decision history](07-weekly-projections/HISTORY.md)
- [Track 07 test report](07-weekly-projections/TEST-REPORT.md)
- [Track 08 specification](08-final-handoff/SPEC.md)
- [Track 08 execution plan](08-final-handoff/PLAN.md)
- [Track 08 history](08-final-handoff/HISTORY.md)
- [Track 08 final test report](08-final-handoff/TEST-REPORT.md)
- [Track 09 specification](09-final-cleanup-docs/SPEC.md)
- [Track 09 execution plan](09-final-cleanup-docs/PLAN.md)
- [Track 09 history](09-final-cleanup-docs/HISTORY.md)
- [Track 09 final test report](09-final-cleanup-docs/TEST-REPORT.md)
