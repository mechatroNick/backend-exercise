# Track 04 history

## 2026-08-05 — Sequential planning started

- Planned Track 04 after committed Track 03 (`f0dd994`), preserving ORM search,
  isolated raw-SQL current stats, owner scoping, and later-track boundaries.
- Status is **Planned**, not Ready: Track 03 remains unimplemented and must close
  before its CRUD/query seams can be consumed.
- No code, dependency, migration, installation, or source-PDF change was made.

## Current state

- Specification: Planned
- Plan: Planned
- Implementation: Dependency-gated; not started

## Next action

After Track 03 closes, run T04-01 before implementation.

## 2026-08-05 — Shared verification-guideline adoption

- Adopted the committed engineering verification guideline in Track 04 planning
  without changing status, task IDs/dependencies, the ORM-versus-raw-SQL boundary,
  public DTO, or Track 05 ownership.
- Planned (but did not create or run) `scripts/verify-track-04.sh` for real filtered
  list/current-statistics HTTP evidence, supported database inspection, JSON-Line
  attribution/redaction checks, and cleanup via the delivered bootstrap.
- Retained deterministic query-count instrumentation and recorded `EXPLAIN QUERY PLAN`
  evidence as the only basis for N+1/index claims; a process smoke alone is not proof.
- No Track 04 test, application process, migration, harness, or runtime validation
  was executed by this planning-only change.

## 2026-08-06 — Incremental verification-governance review correction

- Bumped the SPEC/PLAN planning contract to version 1.1 and added ADR-006 as an
  Accepted evidence-and-closure dependency only; status, task IDs/dependencies,
  raw-SQL/query/DTO contracts, and Track 05 ownership remain unchanged.
- Expanded pending harness evidence to validate inherited JSON Lines fields, safe
  correlation not based on token/user/body/content, redaction, no raw exception text
  indexed field, and exactly one unexpected exception at its owning boundary.
- Clarified that own-user fixture/JWT/list/stat responses are ephemeral assertion
  inputs only and that sensitive/content sentinels and cross-user values never reach
  logs, diagnostics, assertion failures, unsafe debug bundles, or retained artifacts.
- Retained deterministic query-count instrumentation and recorded `EXPLAIN QUERY PLAN`
  as the only N+1/index proof; no Track 04 test, process, migration, harness, or
  runtime validation was executed by this planning-only correction.
