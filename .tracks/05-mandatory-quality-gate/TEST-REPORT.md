# Track 05 test report

- Status: Passed
- Date: 2026-08-06
- Branch: `codex/track-05-quality-gate`
- Scope: Mandatory OpenAPI metadata and runtime conformance, exact no-masking
  evidence selection, query-count/raw-SQL/logging gates, full coverage, clean
  migrations, and secret-safe real-process verification

## Acceptance matrix

| Requirement | Executable evidence | Result |
| --- | --- | --- |
| T05-REQ-01 | `CORE-EVIDENCE-MATRIX.md` maps every required or accepted core row owned by Tracks 01--05 and keeps Track 08 delivery rows open. | Pass |
| T05-REQ-02 | Generated OpenAPI 3.1 inventory, eight operations/five paths, bearer security, exact parameters/statuses/content, fictional examples, and bodyless 204 metadata. | Pass |
| T05-REQ-03 | Controlled real application responses for all 34 operation/status pairs, validated by Schemathesis and Draft 2020-12; three bounded generated GET subtests. | Pass |
| T05-REQ-04 | Exact 79-node mandatory selector covering contract, metadata, query/search/stats/logging evidence; adversarial no-skip/no-xfail/no-deselection/no-unrun tests. | Pass |
| T05-REQ-05 | Populated query counts/plans, consistent WAL read generations, exactly three named owner-bound raw-SQL statements, and source-boundary tests inside the mandatory selector. | Pass |
| T05-REQ-06 | Locked/static/type/full/coverage/documentation/migration gates plus `scripts/verify-track-05.sh` and all four upstream process harnesses. | Pass |

No critical or high defect remains. Track 06 is unblocked only after this branch is
merged to `main` and the merge itself passes the required post-merge checks.

## Incremental implementation receipts

| Commit | Stabilized boundary |
| --- | --- |
| `f50bbb4` | Opened Track 05 from the verified Track 04 merge. |
| `730ecec` | Completed fictional OpenAPI request, response, query, and path examples without runtime drift. |
| `8a1c7ff` | Added the mandatory core evidence inventory and retained Track 08 obligations. |
| `6a510d1` | Exactly pinned Schemathesis 4.24.3 and deterministic generation policy. |
| `135dfaa` | Added the controlled contract matrix, generated safe GETs, exact manifest gate, and adversarial plugin tests. |
| `0c86a56` | Added the mandatory real-process Track 05 Bash harness. |
| `a0959c9` | Closed audit findings for complete evidence scope, teardown masking, and abnormal cleanup. |

Each write wave was inspected and passed focused validation before commit. This report
and the Complete status updates form the final documentation-only checkpoint.

## Pinned contract tool and deterministic scope

Schemathesis is exactly pinned at `4.24.3`. The verified environment reports FastAPI
`0.139.2`, pytest `9.1.1`, and Schemathesis `4.24.3`. `schemathesis.toml` fixes seed
`20260806`, uses positive-only fuzzing with three examples, and disables examples,
coverage probes, and stateful generation. The lazy pytest schema includes only:

- `GET /api/bookmarks`
- `GET /api/bookmarks/stats`
- `GET /api/bookmarks/{bookmark_id}`

The generated ledger proves all three paths execute and no mutation or unexpected
method executes. This is deliberately bounded generation; the controlled 34-status
matrix is the completeness authority.

## Runtime contract matrix

The public schema contains exactly eight operations and 34 documented status pairs:

| Operation | Runtime statuses |
| --- | --- |
| Register | 201, 409, 422, 500 |
| Login | 200, 401, 422, 500 |
| Create bookmark | 201, 401, 422, 500 |
| List bookmarks | 200, 401, 422, 500 |
| Bookmark statistics | 200, 401, 500 |
| Bookmark detail | 200, 401, 404, 422, 500 |
| Update bookmark | 200, 401, 404, 422, 500 |
| Delete bookmark | 204, 401, 404, 422, 500 |

Every pair receives a controlled real ASGI response. JSON instances validate through
both Schemathesis operation validation and the existing Draft 2020-12 validator.
Injected dependency failures reach each documented 500 boundary and are always
cleared. The 204 instance additionally has an empty body, no media type, and no
OpenAPI content entry.

## Mandatory selector and anti-bypass evidence

`tests/contract/mandatory-nodeids.txt` contains exactly 79 meaningful nodes. The
selector includes:

- the exact schema inventory and all 34 controlled runtime pairs;
- the bounded three-operation Schemathesis node and its runtime ledger;
- detailed OpenAPI metadata;
- populated search filters, query counts, query plans, out-of-range behavior, and
  concurrent snapshot consistency;
- current-statistics isolation, ties, months, mutation, three-statement bounds,
  raw-SQL source boundaries, and concurrent snapshot consistency;
- base JSON Lines schema, caller attribution, recursive redaction, serialization
  failure, complete cause/context/ExceptionGroup evidence, and handler deduplication;
- adversarial gate tests for exact/missing/extra/deselected manifests, collection and
  dynamic skip/xfail, setup/call/teardown masking, early termination, and unrun calls.

The plugin rejects `-x` and `--maxfail`, any masking marker, any deselected mandatory
node, and any skipped or xfailed setup/call/teardown report. A node enters the executed
ledger only after a passing call and clean teardown. Collection-only mode verifies the
manifest without falsely claiming execution.

Actual selector receipts:

| Command | Actual result |
| --- | --- |
| `pytest --collect-only -q -m mandatory -p tests.contract.mandatory_gate --mandatory-gate --strict-config --strict-markers <nine evidence files>` | Exit `0`; exactly 79 nodes collected. |
| `pytest -q -m mandatory -p tests.contract.mandatory_gate --mandatory-gate --strict-config --strict-markers <nine evidence files>` | Exit `0`; 79 passed, three Schemathesis subtests passed, no skipped/xfailed/deselected/unrun node. |
| `pytest -q tests/contract/test_mandatory_gate_meta.py` | Exit `0`; nine adversarial meta-tests passed. |

## Static, full-suite, and coverage evidence

| Command | Actual result |
| --- | --- |
| `uv lock --check` | Exit `0`; 73 packages resolved. |
| `uv sync --locked` | Exit `0`; 71 packages audited. |
| `uv run ruff format --check .` | Exit `0`; all 79 files formatted. |
| `uv run ruff check .` | Exit `0`; all checks passed. |
| `uv run mypy app` | Exit `0`; no issues in 35 source files. |
| `uv run pytest` | Exit `0`; 473 tests passed, one warning, no skips or xfails. |
| `coverage erase && coverage run -m pytest -q && coverage report --fail-under=100` | Exit `0`; 1,492 statements and 292 branches, no misses or partial branches, 100%. |
| `make check` | Exit `0`; format, lint, typing, and all 473 tests passed. |
| `bash scripts/verify-docs.sh` | Exit `0`; 43 requirement IDs, six accepted ADRs, and nine tracks. |
| `git diff --check` | Exit `0`; no whitespace errors. |

The sole warning is the locked FastAPI/Starlette TestClient deprecation recommending
`httpx2`. It remains visible and non-blocking: the locked stack is green, and the real
process harness exercises HTTP without TestClient.

## Migration lifecycle

Against the explicit disposable database under
`/private/tmp/backend-sample-track05-final.rQVGLG`, the primary ran upgrade head,
downgrade base, upgrade head, and `alembic check`. Every command exited `0`, and the
final check reported no new upgrade operations. The complete disposable directory was
removed and verified absent. Track 05 adds no migration.

## Real-process mandatory harness

`bash scripts/verify-track-05.sh` exited `0` after the audit corrections. It records
safe pass receipts for every upstream harness:

| Upstream selector | Result |
| --- | --- |
| `scripts/verify-track-01.sh` | Pass |
| `scripts/verify-track-02.sh` | Pass |
| `scripts/verify-track-03.sh` | Pass |
| `scripts/verify-track-04.sh` | Pass |

It then collects and executes all 79 mandatory nodes, rejects masked summaries, runs
the full suite through coverage with a 100% threshold, starts actual `make bootstrap`
on a dynamic loopback port and clean migrated SQLite database, and validates live
docs/OpenAPI, two-user auth and concealment, CRUD/tag mutation, UTC timestamps,
pagination/search, canonical current stats, standard errors, exact 204 behavior, and
one injected 500.

Passwords, bearer tokens, request/response bodies, OpenAPI, and docs exist only in one
in-memory HTTP verifier process. The raw bootstrap output is scanned for every token,
private submitted string, JWT secret, database URL, and workspace path. Every JSON
record has full source, service/component/event/level/timestamp/logger/process/thread
fields. The owning unexpected exception appears exactly once with a safe UUID
correlation and recursively complete redacted frames, causes, contexts, and members.

All retained harness receipts, coverage data, logs, and the migrated database have
private permissions. Descendant termination is checked. A fast injected child status
42 makes a nested harness exit with its original status 97 while still deleting the
private sentinel workspace. The normal harness also verifies complete cleanup and
exposes no debug-retention mode.

## Independent review and retained boundaries

Sage High's first advisory audit found three gate-integrity defects: required
query/raw-SQL/logging/metadata evidence outside the manifest, teardown skip/xfail
masking, and an abnormal shutdown path that could exit before cleanup. Commit
`a0959c9` corrected every finding, and all affected focused and full-process evidence
was rerun. The post-fix advisory verdict is **PASS**, with no code-level blocker.

Retained non-blocking boundaries:

- Generated fuzzing stays narrow and read-only; the 34-pair controlled matrix owns
  response completeness.
- The TestClient deprecation remains an explicit future dependency-upgrade check.
- Dynamic port selection has a small bind race that can produce a detectable failure,
  never a false pass.
- Queue/dirty recovery/snapshots/health remain Track 06; weekly projections and
  append-only corrections remain Track 07; delivery/documentation obligations remain
  visibly open for Track 08.
