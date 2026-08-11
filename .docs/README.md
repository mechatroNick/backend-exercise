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
| [Engineering verification guideline](ENGINEERING-VERIFICATION-GUIDELINE.md) | Implementer and reviewer | Shared logging, testing, harness, evidence, and closure policy |
| [Walkthrough](WALKTHROUGH.md) | Reviewer | Safe reproducible local service demonstration |
| [AI-assisted work disclosure](AI-ASSISTED-WORK.md) | Reviewer and owner | Evidence-bounded provenance boundary |
| [Release handoff](RELEASE-HANDOFF.md) | Repository owner | Completed repository evidence and external-action boundary. |

## Decision and execution records

- [Track index](../.tracks/README.md)
- [ADR-001: Application stack and data access](../.tracks/ADR/ADR-001-application-stack-and-data-access.md)
- [ADR-002: API contract and timestamps](../.tracks/ADR/ADR-002-api-contract-and-timestamps.md)
- [ADR-003: Identity and token security](../.tracks/ADR/ADR-003-identity-and-token-security.md)
- [ADR-004: Event-driven statistics service](../.tracks/ADR/ADR-004-event-driven-statistics-service.md)
- [ADR-005: Windowed-statistics implementation design](../.tracks/ADR/ADR-005-windowed-statistics-data-points.md)
- [ADR-006: Engineering verification and closure evidence](../.tracks/ADR/ADR-006-engineering-verification-and-closure-evidence.md)
- [ADR-007: Local rate limiting and cursor pagination](../.tracks/ADR/ADR-007-local-rate-limiting-and-cursor-pagination.md)
- [ADR-008: Pydantic internal models and typed lifecycle events](../.tracks/ADR/ADR-008-pydantic-internal-models-and-lifecycle-events.md)
- [ADR-009: Track 07 weekly-projection revival](../.tracks/ADR/ADR-009-track-07-weekly-projection-revival.md)
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
- [Track 05: mandatory quality-gate specification](../.tracks/05-mandatory-quality-gate/SPEC.md)
- [Track 05: mandatory quality-gate execution plan](../.tracks/05-mandatory-quality-gate/PLAN.md)
- [Track 06: event-driven statistics specification](../.tracks/06-event-driven-stats/SPEC.md)
- [Track 06: event-driven statistics execution plan](../.tracks/06-event-driven-stats/PLAN.md)
- [Track 07: weekly-projections specification](../.tracks/07-weekly-projections/SPEC.md)
- [Track 07: weekly-projections plan](../.tracks/07-weekly-projections/PLAN.md)
- [Track 07: weekly-projections test report](../.tracks/07-weekly-projections/TEST-REPORT.md)
- [Track 08: final handoff specification](../.tracks/08-final-handoff/SPEC.md)
- [Track 08: final handoff execution plan](../.tracks/08-final-handoff/PLAN.md)
- [Track 08: final test report](../.tracks/08-final-handoff/TEST-REPORT.md)
- [Track 09: final cleanup specification](../.tracks/09-final-cleanup-docs/SPEC.md)
- [Track 09: final cleanup execution plan](../.tracks/09-final-cleanup-docs/PLAN.md)
- [Track 09: final cleanup history](../.tracks/09-final-cleanup-docs/HISTORY.md)
- [Track 09: final test report](../.tracks/09-final-cleanup-docs/TEST-REPORT.md)

Track 07 is **Complete** under ADR-009 with private weekly projections, an executable
harness, and closure evidence. Track 08 is **Complete** with fresh clean-source/Docker
integration, and Track 09's pre-revival completion remains historical until its final
downstream refresh inherits that passing gate. External release actions remain owner-
only and were not performed.

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

The engineering-process disclosure is now recorded in
[AI-assisted work](AI-ASSISTED-WORK.md), bounded to repository and owner-provided
evidence. It records no private material and does not replace the passed Track 08
verification evidence.
