# Bookmarks API visual teaching curriculum

This directory turns the completed coding challenge into a progressive visual
walkthrough. The files in `prompts/` are image-generation context files, not
generated images. They follow the delivered Tracks 00–09 in order and each file
contains two complementary prompts:

- **Architecture view** explains the feature's place in the system and why it was
  introduced at that point in the delivery sequence.
- **Critical implementation view** concentrates on the decisions, state
  transitions, error boundaries, or invariants that make the feature correct.

Use the files in numeric order. Generate the architecture view before the critical
implementation view for a given track. The prompts deliberately use short labels:
image models render prose unreliably, so keep the cited source documentation open for
exact wording and contracts.

Each prompt is grounded in `.docs/ASSESSMENT.md`, `.docs/SOLUTION-DESIGN.md`,
`.docs/DELIVERY-PLAN.md`, the matching `.tracks/*/SPEC.md`, and the code/tests named
within the prompt. It deliberately distinguishes delivered local-assessment behavior
from excluded production infrastructure.

## Sequence

1. Contract baseline and delivery discipline
2. Foundation, configuration, migrations, and SQLite constraints
3. Error contract and authentication
4. Bookmark CRUD, tags, ownership, and timestamps
5. Search, pagination, and canonical current statistics
6. Mandatory OpenAPI and engineering quality gate
7. Event-driven invalidation, current snapshots, health, and logs
8. Private weekly projections and immutable corrections
9. Hardening: seed data, Docker, rate limiting, and cursor pagination
10. Final modernization, evidence reports, and clean-source closure

The visual language is intentionally consistent: flat 2D technical schematic,
pure-white background, short labels, and muted colors. Purple represents HTTP or
integration boundaries, blue persistent data, orange computation, red security,
magenta asynchronous workflow, and rose observability. Those colors are visual
categories only; no color code needs to appear in a generated image.
