# Track 07 specification: weekly event-time projections and correction revisions

- Status: **Skipped (owner decision)**
- Specification version: 1.2
- Originally planned: 2026-08-05
- Skipped: 2026-08-06
- Owner: Repository owner
- Depends on: None; no Track 07 implementation will run
- Governing records: ADR-004, ADR-005, ADR-006
- Assessment disposition: WIN-01 and WIN-02 are not selected; WIN-03 remains owned by Track 06

## Decision

Track 07 is intentionally skipped. The repository will not implement weekly
developing points, developed points, append-only correction revisions, historical
backfill, a historical consumer, or a statistics-history API.

This is an explicit scope decision, not passing implementation evidence. Track 07
must never be shown as Complete, verified, or implemented, and it does not receive a
runtime harness or `TEST-REPORT.md`.

## Consequences

- Track 06 current statistics remain the only statistics runtime. Its canonical raw
  SQL, optional current snapshots, durable dirty-marker recovery, health, and
  observability contracts remain unchanged.
- Track 06's current-only generation completion is the terminal dirty-marker policy.
  No retention/backfill/dual-consumer cutover is required.
- `bookmark_stats_window_working`, `bookmark_stats_window_point`, projection
  completion columns, calculation versions, historical payload hashes, and correction
  revisions must not be added.
- ADR-005 remains an archived accepted design describing how the feature could be
  implemented if explicitly revived. It is not delivered architecture.
- Track 08 depends on completed Tracks 01–06 plus this recorded skip decision. It
  must not require Track 07 code, a Track 07 closure report, or
  `scripts/verify-track-07.sh`.
- Final documentation must disclose that WIN-01/WIN-02 and weekly historical
  projections were deliberately not selected; it must not claim their evidence.

## Scope guard

Any later request to revive weekly projections is a new scope decision. It requires
an updated Track 07 specification and plan, review of ADR-004/ADR-005 against the
then-current Track 06 implementation, a new migration design, deterministic tests,
and its own real-process evidence before implementation begins.

## Skip acceptance

The skip is correctly represented when:

1. every current control-plane and reader document identifies Track 07 as skipped;
2. Track 08 has no Track 07 completion, report, branch, or harness dependency;
3. Track 06 documents current-only dirty completion as final;
4. weekly tables, routes, consumers, and correction behavior remain absent; and
5. documentation verification rejects a return to Planned/Complete wording or an
   accidental Track 07 harness requirement.
