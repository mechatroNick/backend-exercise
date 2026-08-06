# Track 07 plan: skipped weekly projections

- Specification: [SPEC.md](SPEC.md), version 1.2
- Status: **Skipped (owner decision)**
- Active item: None

## Disposition

All previously planned Track 07 work is skipped. The rows remain visible so a reader
cannot mistake missing code or evidence for unfinished execution.

| ID | Previously planned work | Status | Disposition evidence |
| --- | --- | --- | --- |
| T07-01 | Track 06 compatibility and projection gate | Skipped | Owner removed weekly projections from scope. |
| T07-02 | Working/developed tables and two-consumer completion migration | Skipped | No Track 07 schema or completion columns will be added. |
| T07-03 | Weekly calculator, reader, payload hash, and revision selection | Skipped | No weekly calculation implementation will be added. |
| T07-04 | Historical backfill and developing rows | Skipped | No historical consumer or backfill will run. |
| T07-05 | Boundary finalization and immutable revision 1 | Skipped | No developed points will be persisted. |
| T07-06 | Append-only correction revisions | Skipped | No correction history will be persisted. |
| T07-07 | Worker, readiness, and projection observability integration | Skipped | Track 06 remains current-statistics-only. |
| T07-08 | Deterministic suite and `scripts/verify-track-07.sh` | Skipped | No executable Track 07 evidence is required or permitted. |
| T07-09 | Track 07 closure report | Skipped | Skip record replaces implementation closure; no `TEST-REPORT.md` is created. |

## Downstream handoff

Track 08 consumes this skip record, not a passing Track 07 report. Its upstream gate
is completed Tracks 01–06, the Track 07 skipped status, and confirmation that no
weekly projection artifacts were introduced.

The final harness invokes Track 01–06 harnesses and validates this skip through
`scripts/verify-docs.sh`; it does not invoke or synthesize a Track 07 harness.

## Validation

Only documentation/control-plane validation applies:

```text
bash scripts/verify-docs.sh
git diff --check
```

These commands validate the recorded scope decision. They do not constitute weekly
projection implementation evidence.

## Re-entry condition

No Track 07 task may move out of Skipped without a later explicit owner decision and
a new reviewed dependency/ADR/migration/test plan.
