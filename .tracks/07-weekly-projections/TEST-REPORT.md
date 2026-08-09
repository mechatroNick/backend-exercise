# Track 07 test report: weekly event-time projections and correction revisions

- Status: Passed
- Evidence commit: `08a86b3`
- Verification date: 2026-08-10
- Governing ADRs: ADR-004, ADR-005, ADR-006, ADR-009
- Scope: Track 07 only; no post-merge or downstream Track 08/09 validation is claimed.

## Actual closure receipt

The primary completed one continuous `bash scripts/verify-track-07.sh` run on commit
`08a86b3` with `RESULT: PASS`.

The harness passed the exact inherited Track 06 verifier; focused
weekly/schema/baseline/lifecycle/correction/dirty/refresher/health selectors; locked
dependency sync; Ruff format and lint; mypy; Pyright; `make check`; documentation and
whitespace gates; and full branch coverage. The full deterministic suite passed with
**862 tests plus 3 subtests**, and the coverage receipt reported **3,922 statements**,
**908 branches**, and **100%** coverage.

The disposable migration lifecycle passed upgrade, downgrade, re-upgrade, and Alembic
drift check. No skipped, xfailed, xpassed, or deselected result was accepted by the
harness receipts.

## Real-process evidence

Using isolated migrated SQLite databases, dynamic loopback ports, and a real one-worker
Uvicorn process, the harness proved:

- projection-disabled public bootstrap, clean shutdown, and a protected operator-only
  backdate of the sole disposable bookmark into a prior closed Monday;
- default-enabled restart recovering redacted readiness, preserving the 10-operation/
  45-response-pair OpenAPI inventory and absence of a public history API, creating a
  closed baseline root with `source_generation=0`, and later processing a public current
  mutation into positive-generation working state with durable completion;
- current statistics totals changing from 1 to 2 after the current mutation, then to 1
  after a public historic deletion; the deletion appended revision 2 with its immediate
  predecessor and removed completed dirty work;
- a post-correction restart retaining active state, exactly two point rows, no dirty
  rows, readiness recovery, and current total 1 without duplicate history;
- an independent disabled-projection process where public mutation/current statistics/
  liveness worked, readiness was redacted 503, projection work remained pending, and no
  projection state, working, or point rows were fabricated;
- an incompatible durable calculation version where current mutation/current statistics/
  liveness remained available, readiness failed closed, and projection rows were not
  automatically rewritten; and
- strict JSON Lines output with UTC timestamps and absolute application source fields,
  safe redaction, exact one named non-daemon refresher lifecycle, expected projection
  lifecycle events, clean SIGTERM handling, and disposable process/workspace cleanup.

## Incremental implementation ledger

The verified Track 07 change sequence is:

1. `472867b`
2. `194050d`
3. `26b4fae`
4. `db87448`
5. `86d7207`
6. `f9f4152`
7. `4879a3a`
8. `49992d7`
9. `08a86b3`

## Downstream handoff and boundary

Track 07 is complete. Tracks 08 and 09 still describe the archived pre-revival
skip/absence disposition, so they are reopened/stale downstream work. They need their
own document update and validation before they can consume Track 07 as a completed
dependency. This report records neither a post-merge verification run nor any
downstream validation.
