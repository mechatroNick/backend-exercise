# Track 00 history

## 2026-08-05 — Assessment discovery

- Inspected the repository and the supplied six-page technical assessment.
- Preserved the repository owner's move of the source PDF into `docs/`.
- Identified mandatory API, data, authentication, raw SQL, OpenAPI, testing, and delivery expectations.
- Recorded the PDF's conflicting five-day/seven-day wording as non-behavioral and accepted a quality-first few-day delivery approach.

## 2026-08-05 — Architecture clarification

- Confirmed FastAPI, synchronous SQLModel, local SQLite, Alembic, enforced relationships/constraints, and ORM-by-default access.
- Confirmed DTO/table-model separation, PATCH semantics, OpenAPI examples, tag normalization, timestamp invariants, identity normalization, Argon2, and access-only JWTs.
- Confirmed that statistics-affecting actions should emit loosely coupled invalidation events.
- Reframed the proposed cron/subprocess as one named, lifecycle-managed in-process refresher thread started with the API.
- Confirmed configurable ten-second batching, service-attributed logs, and readiness that evaluates progress rather than thread existence alone.

## 2026-08-05 — Weekly point decision

- Distinguished the mandatory all-current statistics endpoint from historical data points.
- Confirmed event-time semantics: a weekly point summarizes bookmarks whose immutable `created_at` falls in that UTC Monday-to-Monday week.
- Confirmed that an open/developing point is recalculated and replaced.
- Confirmed that a closed/developed point is append-only and a late delete or tag change creates a correction revision rather than mutating history.
- Accepted ADR-005 with durable dirty-window recovery and idempotent correction rules.

## 2026-08-05 — Durable documentation

- Created the requirement baseline, documentation index, five accepted ADRs, solution design, delivery plan, and Track 00 control artifacts.
- Ordered delivery so the complete mandatory API and contract suite pass before event-driven snapshot and weekly-projection extensions begin.
- Deferred the final README process narrative until implementation provides real commands, diffs, validation, and decision evidence.

## 2026-08-05 — Validation and closure

- Re-extracted all six PDF pages and compared the source exercise with the requirement and response contracts.
- Corrected the nested statistics result field to the assessment's exact `count` name.
- Promoted the required 80/200/500/50 username/title/description/tag lengths into the stable requirement and persistence contracts.
- Reconciled Track 06 with ADR-004 by making it own the durable dirty marker, same-transaction generation update, recovery, and generation-safe cleanup. Track 07 consumes that mechanism for weekly projections.
- Standardized statistics Settings names to the accepted ADR-004 configuration baseline.
- Verified 43 unique assessment requirement IDs, five accepted ADRs, nine delivery tracks, local Markdown link targets, terminology, and whitespace.
- Addressed every blocking and substantive non-blocking finding from an independent fresh-reader audit. The focused re-audit passed all repaired items.
- Closed Track 00 with no known material product ambiguity and made Track 01 ready for detailed planning.

## 2026-08-05 — Sequential re-review and stabilization

- Performed a bounded, read-only fresh-reader re-review of the completed Track 00
  record before Track 01 review; it did not assert an external identity or create
  evidence outside the repository.
- Clarified that the HR AI-use authorization is recorded by the repository owner,
  that its supporting correspondence is external/private and not stored here, and
  that the original assessment restriction controls if the authorization is rescinded
  or disputed.
- Corrected ADR-005 ownership to include Track 06, which implements the shared
  durable dirty-marker mechanism consumed by Tracks 07 and 08.
- Re-ran the portable documentation checks recorded in `TEST-REPORT.md`: 43 unique
  requirement IDs, five accepted ADRs, nine delivery-track sections, resolved local
  Markdown links, no trailing whitespace, and a clean `git diff --check`.

## 2026-08-05 — Verification-policy adoption

- Added the authoritative documentation-scope engineering verification guideline and
  indexed it from the reader and track control planes.
- Added `scripts/verify-docs.sh`, a read-only Bash documentation verifier for the
  expected artifacts, inventories, URL-decoded local Markdown links, whitespace,
  and diff hygiene.
- Kept Track 00 Complete only for documentation scope: the new checker makes no
  unit, API, database, structured-log, or runtime claim. Future executable tracks
  must add their own deterministic tests and real-process harness evidence.

## 2026-08-06 — Verification-governance correction

- Accepted ADR-006 to bind the shared engineering verification guideline as the
  Tracks 00-08 closure and evidence process without changing product semantics or
  overriding the assessment, accepted ADRs, or stricter track rules.
- Bumped the Track 00 specification to 1.1, added T00-10, and revalidated the
  documentation-only gate with six accepted ADRs.
- Preserved Track 00's documentation-only exception and its explicit absence of
  executable runtime claims.

## Open items

- Author the Track 01 specification and plan before foundation implementation.
