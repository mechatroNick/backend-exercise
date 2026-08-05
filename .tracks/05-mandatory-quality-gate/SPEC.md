# Track 05 specification: mandatory quality and contract gate

- Status: Planned
- Specification version: 1.0
- Planned: 2026-08-05
- Owner: Primary engineering thread
- Depends on: Tracks 01--04 implemented and closed (01 transitive; 02--04 explicit gate)
- Governing ADRs: ADR-001, ADR-002, ADR-003; ADR-004/005 define excluded extension boundaries
- Assessment requirements: every required or accepted core row owned by Tracks 01--05; primary owners API-01, API-02, TEST-01, TEST-02, QUAL-01

## Intent, scope, and contracts

Demonstrate a complete mandatory assessment before any extension work. Track 05 adds
no product feature: implementation defects return to their owning track-compatible
scope; a semantic change requires ADR/SPEC review. Mandatory behavior cannot be
masked, skipped, or xfailed.

- Serve interactive `/docs` and accurate OpenAPI 3.0+ (accept FastAPI-generated 3.1
  when applicable). Audit every operation for schemas, required bearer security,
  parameters, statuses, reusable models, examples, content types, standard errors,
  and bodyless `204`.
- Validate actual runtime success and documented-error instances against generated
  OpenAPI, not only schema reachability. Select a current compatible primary-docs
  contract tool at implementation time (Schemathesis baseline) and pin it in lockfile.
- Run migrated-DB integration coverage across auth, isolation, CRUD, tags, timestamps,
  filters, pagination, stats, errors, and migrations. Collect >=10 meaningful tests,
  record count, target above minimum without inventing a coverage percentage, and leave
  no untested critical/high-risk accepted behavior.
- Prove N+1/query-count regression controls and raw-SQL boundary/parameterization;
  rehearse clean DB migration, format/lint/mypy/full suite, documented bootstrap, and
  representative HTTP smoke. Produce `TEST-REPORT.md` at closure.
- Track 06 is a hard stop until all mandatory evidence passes and no known critical or
  high defect remains. Exclude events/workers/snapshots/history/bonuses/final narrative.

## Requirements and acceptance

| ID | Requirement |
| --- | --- |
| T05-REQ-01 | Build requirement-to-evidence closure inventory for every required or accepted core row owned by Tracks 01--05; identify delivery-only Track 08 obligations without falsely closing them. |
| T05-REQ-02 | Audit `/docs` and generated schema operation-by-operation for complete accurate contract metadata. |
| T05-REQ-03 | Validate runtime response instances, including documented errors/content types/bodyless `204`, against published OpenAPI. |
| T05-REQ-04 | Run migrated-DB integration and collected-test evidence across all mandatory behavior. |
| T05-REQ-05 | Prove query-count/N+1 and raw-SQL parameterization/isolation controls. |
| T05-REQ-06 | Rehearse clean migration/bootstrap/smoke and local quality commands; close TEST-REPORT with defects/risks. |

Closure requires passing traceability for every required or accepted core row owned by
Tracks 01--05, actual schema-validation results, >=10 collected meaningful tests, a
clean migrated DB, no critical/high defect, and actual quality/smoke receipts. `DEL-01`
and documentation/submission obligations owned by Track 08 remain explicitly open; no
product requirement may be relabeled as delivery-only to pass this gate. Stop/reframe
on upstream contract conflict, a semantic change, unreproducible clean migration, or
any missing core evidence.

## Traceability and defect routing

API-01/02 map to T05-REQ-02/03; TEST-01 to T05-REQ-04; TEST-02 to T05-REQ-03;
QUAL-01 to T05-REQ-05/06. The closure matrix covers all remaining required and
accepted core rows owned by Tracks 01--05 and separately lists still-open Track 08
delivery/documentation rows.
An implementation defect is fixed in its owning-track-compatible scope and retested;
a semantic/public change requires ADR/SPEC update; no xfail/skip substitutes for proof.
