# Track 07 history

## 2026-08-05 — Sequential planning started

- Planned Track07 after committed Track06 (92d3830) and accepted ADR-001, ADR-004,
  and ADR-005. No product source, dependency, migration, queue, thread, route, health
  behavior, or external action occurred.
- Marked the track Planned (implementation-gated) with T07-01 Blocked until Track06
  is Complete and has its actual TEST-REPORT.md closure evidence.
- Preserved the staged consumer rule: Track06 may have completed markers before a
  historical consumer existed; Track07 first establishes restartable canonical
  surviving-data baseline, then requires current and projection completion for an
  observed generation before marker removal.
- Assigned private working rows, immutable revisions, deterministic version/hash
  policy, baseline/finalization/corrections, existing-worker integration, health/log
  evidence. Kept public history APIs, queue/topology redesign, final docs, bonuses out.
- Primary review reserved source generation zero for installation/backfill state while
  keeping observed dirty generations positive, prohibited blanket completion during
  migration, and required same-user/window immediate-predecessor supersession proof.

## Current state

- Specification: Planned, version 1.0
- Plan: Planned; T07-01 Blocked on Track06 closure TEST-REPORT.md
- Implementation: Not started; dependency-gated
- Material product questions: None known; private completion names/checkpoint mechanics
  remain implementation latitude after Track06 seam review

## Next action

After Track06 closes with real evidence, execute T07-01 to compare its delivered
dirty-marker migration, current completion ordering, raw-SQL reader, worker cycle,
Settings, health, and logs before authoring projection migration or code.
