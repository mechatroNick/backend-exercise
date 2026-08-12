# Bookmarks API visual teaching curriculum

This directory turns the completed coding challenge into a progressive visual
walkthrough. The files in `prompts/` are self-contained image-generation prompts, not
generated images. They follow the delivered Tracks 00–09 in order and each file
uses the final Generic Illustrator model format: a front-loaded style prime,
spatial composition, concrete visible components, grouped arrow flows, and a final
negative prompt. The only metadata line is `RATIO=16:9`; everything else needed to
generate the illustration is in the prompt itself. The files are paired by track:

- **Architecture view** explains the feature's place in the system and why it was
  introduced at that point in the delivery sequence.
- **Critical implementation view** concentrates on the decisions, state
  transitions, error boundaries, or invariants that make the feature correct.

Use the files in numeric order. Generate each odd-numbered architecture view before its
following even-numbered critical-implementation view. Send the complete contents of a
prompt file—starting with `RATIO=16:9`—to the image-generation model. The prompts use
short labels because image models render prose unreliably, while keeping the bounded
technical context, invariants, flows, and exclusions directly within the model-facing
text. They deliberately distinguish delivered local-assessment behavior from excluded
production infrastructure without referring the model to repository files.

## Sequence

1. Contract baseline: delivery map
2. Contract baseline: decision and evidence controls
3. Foundation: runtime composition
4. Foundation: schema and connection guarantees
5. Authentication: end-to-end boundary
6. Authentication: failure and authorization decisions
7. CRUD: owner-scoped architecture
8. CRUD: mutation state invariants
9. Queries: search and statistics architecture
10. Queries: date, pagination, and SQL correctness
11. Quality: mandatory contract firewall
12. Quality: test-integrity mechanics
13. Current statistics: durable-invalidation architecture
14. Current statistics: generation-race correctness
15. Weekly projections: private event-time architecture
16. Weekly projections: correction and dual-completion invariants
17. Hardening: seed, Docker, rate, and cursor architecture
18. Hardening: safety and verification decisions
19. Closure: modernization and evidence architecture
20. Closure: clean-source integrity state machine

The visual language is intentionally consistent: flat 2D technical schematic,
pure-white background, short labels, and muted colors. Purple represents HTTP or
integration boundaries, blue persistent data, orange computation, red security,
magenta asynchronous workflow, and rose observability. Those colors are visual
categories only; no color code needs to appear in a generated image.
