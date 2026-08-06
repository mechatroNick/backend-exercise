# Track 05 mandatory core evidence matrix

- Inventory date: 2026-08-06
- Gate scope: Required and accepted core rows owned by Tracks 01--05
- Upstream basis: Verified Track 04 merge `8534e98` and Passed Track 01--04 reports
- Excluded extensions: EVT/WIN/OPS behavior owned by Tracks 06--07

This inventory distinguishes already executed upstream evidence from the Track 05
evidence that must still run. A link or a historical report is traceability, not a
substitute for Track 05's current mandatory automation gate.

## Foundation and data

| Row | Classification | Direct evidence | Gate state |
| --- | --- | --- | --- |
| ENV-01 | Required | [Track 01 report](../01-foundation/TEST-REPORT.md), locked-sync and real bootstrap receipts | Upstream Passed |
| ARC-01 | Required | Track 01 module/composition tests and [report](../01-foundation/TEST-REPORT.md) | Upstream Passed |
| DATA-01 | Required | Alembic empty-database lifecycle and migrated schema inventory in the Track 01 report | Upstream Passed |
| DATA-02 | Required | `tests/integration/test_constraints.py` and migrated constraint/index inspection | Upstream Passed |
| DATA-03 | Required | Migrated composite bookmark/tag relationship and key tests | Upstream Passed |
| DATA-04 | Accepted | Engine/Alembic foreign-key policy tests and live migrated-database receipt | Upstream Passed |

## Identity, authentication, and errors

| Row | Classification | Direct evidence | Gate state |
| --- | --- | --- | --- |
| AUTH-01 | Required | Register service/route/runtime-schema tests and [Track 02 report](../02-auth-errors/TEST-REPORT.md) | Upstream Passed |
| AUTH-02 | Required | Login service/route/runtime-schema tests and Track 02 report | Upstream Passed |
| AUTH-03 | Required | Password hash and deterministic JWT issue/verify/expiry/tamper tests | Upstream Passed |
| AUTH-04 | Required | Bearer dependency matrix and all bookmark-operation security inventory | Upstream Passed |
| ERR-01 | Required | Shared handler/envelope tests for validation, auth, conflict, not-found, and unexpected errors | Upstream Passed |
| SEC-01 | Accepted | Canonical identity, Argon2, access-only JWT, non-enumeration, and redaction evidence | Upstream Passed |

## Bookmark behavior and isolation

| Row | Classification | Direct evidence | Gate state |
| --- | --- | --- | --- |
| BKM-01 | Required | CRUD service/repository/route matrices and [Track 03 report](../03-bookmark-crud/TEST-REPORT.md) | Upstream Passed |
| BKM-02 | Required | Strict URL/title/description/timestamp DTO and migrated constraint tests | Upstream Passed |
| BKM-03 | Required | Tag association create/update/remove/deduplicate and native conflict tests | Upstream Passed |
| ISO-01 | Required | Owner-predicate instrumentation plus list/detail/update/delete/statistics cross-user tests | Upstream Passed |
| TAG-01 | Accepted | Canonical trim/lower/deduplicate/reuse/orphan tests | Upstream Passed |
| TIME-01 | Accepted | Fixed-clock create/material/no-op/failure timestamp invariants | Upstream Passed |

## Queries and canonical current statistics

| Row | Classification | Direct evidence | Gate state |
| --- | --- | --- | --- |
| QRY-01 | Required | `tests/integration/test_bookmark_search.py`, route tests, and [Track 04 report](../04-search-stats/TEST-REPORT.md) | Upstream Passed |
| QRY-02 | Accepted | Exact query aliases, UTC bounds, stable pages/order, and OpenAPI tests | Upstream Passed |
| SQL-01 | Required | Protected `/api/bookmarks/stats` route and isolated live raw-SQL reader tests | Upstream Passed |
| SQL-02 | Required | Empty/tie/month/mutation/cross-user aggregate matrices | Upstream Passed |
| SQL-03 | Required | Four-statement bounds, owner/index query plans, association loading, and raw-SQL boundary scan | Upstream Passed |

## Mandatory OpenAPI and quality gate

| Row | Classification | Direct evidence required in Track 05 | Current state |
| --- | --- | --- | --- |
| API-01 | Required | Real `/docs` and OpenAPI 3.1 retrieval plus schema/operation inventory | Open |
| API-02 | Required | API-wide metadata audit; fictional request/success/query/path/error examples; exact statuses/security/content/204 | Metadata fixed at `730ecec`; runtime gate open |
| TEST-01 | Required | Checked-in mandatory node manifest, exact collected count >=10, no skip/xfail/deselection/masking/unrun | Open |
| TEST-02 | Required | Controlled 34 operation/status runtime instances through Schemathesis and Draft 2020-12 validation plus safe generated GETs | Open |
| QUAL-01 | Accepted | Locked sync, static/type/full/coverage/query/migration/bootstrap/harness commands with actual results | Open |

## Track 08 obligations deliberately retained as open

| Rows | Reason they are not closed by Track 05 |
| --- | --- |
| DEL-01 | Repository/link/archive submission, final incremental-history receipt, and external submission action belong to Track 08 and the repository owner. |
| DEL-02, DOC-01 | Completed-architecture/setup/API/testing/deployment/trade-off documentation requires the final Tracks 06--07 design and fresh-reader review. |
| DEL-03 | AI-assisted process disclosure must reflect the completed work and remains external-authorization sensitive. |
| FUT-01 | Final future-work boundaries are documentation-only Track 08 scope. |
| BONUS-01, BONUS-02 | Optional bonuses are decided only after every required and accepted row is green. |

GOV-01 is already closed by Track 00's accepted control plane and remains binding.
Tracks 06--07 cannot begin until every Open Track 05 row above is Passed and no known
critical or high defect remains.
