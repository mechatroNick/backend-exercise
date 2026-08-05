# Bookmarks API documentation

This directory contains the reader-facing interpretation and design for the backend
assessment. Durable execution state and architecture decisions live under
`.tracks/`.

## Documents

| Document | Audience | Purpose |
| --- | --- | --- |
| [Technical assessment](Technical%20Assessment%20Senior%20Software_Engineer.pdf) | Candidate and reviewer | Authoritative source exercise |
| [Assessment interpretation](ASSESSMENT.md) | Implementer and reviewer | Requirements, constraints, scope, and traceability |
| [Solution design](SOLUTION-DESIGN.md) | Senior engineer and reviewer | API, data, runtime, event, statistics, security, health, and deployment design |
| [Delivery plan](DELIVERY-PLAN.md) | Implementer and reviewer | Ordered tracks, dependencies, validation, and commit boundaries |

## Decision and execution records

- [Track index](../.tracks/README.md)
- [ADR-001: Application stack and data access](../.tracks/ADR/ADR-001-application-stack-and-data-access.md)
- [ADR-002: API contract and timestamps](../.tracks/ADR/ADR-002-api-contract-and-timestamps.md)
- [ADR-003: Identity and token security](../.tracks/ADR/ADR-003-identity-and-token-security.md)
- [ADR-004: Event-driven statistics service](../.tracks/ADR/ADR-004-event-driven-statistics-service.md)
- [ADR-005: Windowed statistics data points](../.tracks/ADR/ADR-005-windowed-statistics-data-points.md)
- [Track 00: closed contract baseline](../.tracks/00-contract-baseline/SPEC.md)
- [Track 00: validation report](../.tracks/00-contract-baseline/TEST-REPORT.md)
- [Track 01: foundation specification](../.tracks/01-foundation/SPEC.md)
- [Track 01: foundation execution plan](../.tracks/01-foundation/PLAN.md)
- [Track 02: auth and error specification](../.tracks/02-auth-errors/SPEC.md)
- [Track 02: auth and error execution plan](../.tracks/02-auth-errors/PLAN.md)
- [Track 03: bookmark CRUD specification](../.tracks/03-bookmark-crud/SPEC.md)
- [Track 03: bookmark CRUD execution plan](../.tracks/03-bookmark-crud/PLAN.md)
- [Track 04: search and statistics specification](../.tracks/04-search-stats/SPEC.md)
- [Track 04: search and statistics execution plan](../.tracks/04-search-stats/PLAN.md)

Detailed downstream artifacts may be planned sequentially after upstream plan review;
their presence does not make implementation ready until each stated dependency closes
with the required evidence.

## Authority

When documents conflict, apply this order:

1. Explicit repository-owner clarification.
2. The supplied assessment.
3. Accepted ADRs.
4. Approved track SPECs.
5. This reader-facing design and delivery plan.
6. Implementation details and examples.

Semantic changes require an ADR and corresponding SPEC, PLAN, HISTORY, and index
updates. Editorial clarification may update these docs without changing contracts.

The engineering-process narrative requested for the final submission will be written
later from actual implementation evidence. It is intentionally not invented during
planning.
