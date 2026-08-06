# Track 02 test report

- Status: Passed
- Date: 2026-08-06
- Branch: `codex/track-02-auth-errors`
- Scope: Stable error envelope, registration/login, canonical identity, Argon2,
  access-only JWTs, current-subject dependency, auth OpenAPI, and process verification

## Acceptance matrix

| Requirement | Executable evidence | Result |
| --- | --- | --- |
| T02-REQ-01 | Expected-error hierarchy, safe validation details, centralized handlers, and one owning unexpected HTTP log/response boundary | Pass |
| T02-REQ-02 | Username/email boundary and canonicalization matrices plus NFC password tests | Pass |
| T02-REQ-03 | Argon2 format/verify, composed/decomposed equivalence, malformed-hash, backend-failure, and no-plaintext persistence tests | Pass |
| T02-REQ-04 | Deterministic issue/verify tests for exact `sub`/`iat`/`exp`, HS256 pinning, zero-leeway expiry, secret length, claim types, and backend failures | Pass |
| T02-REQ-05 | Real SQLite canonical duplicates, two-session race, rollback/reuse, and unrelated-integrity fail-closed tests | Pass |
| T02-REQ-06 | JSON register/login endpoint success, strict/malformed body, duplicate, non-enumeration, and exact public-shape tests | Pass |
| T02-REQ-07 | Missing/wrong-scheme/malformed/tampered/expired/invalid/noncanonical/deleted-subject bearer tests | Pass |
| T02-REQ-08 | Runtime `201`/`200`/`409`/`422`/`401`/`500` bodies validated against generated auth-operation schemas and exact route/security inventory | Pass |
| T02-REQ-09 | Secret-safe DTO/repr tests, safe validation errors, unrelated `IntegrityError` redaction, live seeded-sentinel scan, and repository-hygiene scan | Pass |

## Runtime and tool versions

| Tool | Resolved version |
| --- | --- |
| Python | 3.12.12 |
| uv | 0.9.15 |
| pytest | 9.1.1 |
| Coverage.py | 7.15.3 with C extension |
| Ruff | 0.15.22 |
| mypy | 2.3.0 compiled |
| Alembic | 1.19.0 |
| Bash | 3.2.57(1)-release |
| FastAPI | 0.139.2 |
| pwdlib | 0.3.0 |
| PyJWT | 2.13.0 |
| jsonschema | 4.26.0 |

The repository's `uv.lock` and Python 3.12 constraint are the dependency authority.
No external identity provider, network service, developer database, live credential,
or wall-clock sleep participates in the deterministic suite.

## Incremental implementation receipts

| Commit | Stabilized boundary |
| --- | --- |
| `6aae608` | Opened Track 02 only after verified Track 01 closure. |
| `17256e4` | Added typed error contracts and safe centralized translation. |
| `368b3d8` | Added identity, Argon2, and access-token primitives. |
| `cadaed8` | Added transactional auth repository/service behavior and race evidence. |
| `ed2b672` | Restored inert database package imports after cold-import verification. |
| `14e8683` | Added auth routes/dependencies, OpenAPI validation, edge tests, and live harness. |

Each implementation wave passed its focused tests and primary inspection before the
next wave. This report and status update are the final documentation-only closure
commit on the same dedicated track branch.

## Deterministic and static validation

| Command | Actual result |
| --- | --- |
| `uv lock --check` | Exit `0`; 56 packages resolved and lockfile current. |
| `uv sync --locked` | Exit `0`; 54 packages audited from the lockfile. |
| `.venv/bin/ruff format --check app tests` | Exit `0`; all 47 Python files formatted. |
| `.venv/bin/ruff check app tests` | Exit `0`; all checks passed. |
| `.venv/bin/mypy app` | Exit `0`; no issues in 25 source files. |
| Focused Track 02 pytest selector listed below | Exit `0`; 109 tests passed, one upstream warning. |
| `.venv/bin/coverage run --branch -m pytest -q` | Exit `0`; 236 tests passed, one upstream warning. |
| `.venv/bin/coverage report --fail-under=100` | Exit `0`; 866 statements and 166 branches, no misses or partial branches, 100%. |
| `bash scripts/verify-docs.sh` | Exit `0`; 43 requirement IDs, six accepted ADRs, and nine tracks. |
| `rg -n 'metadata\.create_all\|create_all\(' app tests alembic` | No match; no application/test schema creation. |
| `git diff --check` and `git diff main...HEAD --check` | Exit `0`; no whitespace errors. |

The exact focused selector was:

```text
.venv/bin/pytest -q -p no:cacheprovider \
  tests/unit/test_api_errors.py \
  tests/unit/test_auth_dependencies.py \
  tests/unit/test_auth_schemas.py \
  tests/unit/test_auth_service.py \
  tests/unit/test_identity.py \
  tests/unit/test_passwords.py \
  tests/unit/test_security.py \
  tests/integration/test_auth_service.py \
  tests/integration/test_auth_routes.py
```

The full suite covers success, boundaries, malformed JSON and fields, normalization,
NFC equivalence, missing/wrong/tampered/expired claims, wrong algorithms,
noncanonical/deleted subjects, non-enumeration, duplicate races, rollback/reuse,
unrelated integrity failures, backend/configuration failures, response-schema
agreement, cold imports, and lifecycle failure/cleanup paths.

## Migration lifecycle

The primary ran these operations against one unique file under `/private/tmp`, with a
validated trap removing only that exact task-prefixed path:

```text
DATABASE_URL=sqlite:///<disposable> uv run alembic upgrade head
DATABASE_URL=sqlite:///<disposable> uv run alembic downgrade base
DATABASE_URL=sqlite:///<disposable> uv run alembic upgrade head
```

Every command exited `0`. A final SQLite inspection found exactly one Alembic head
row and the required `users`, `bookmarks`, `tags`, and `bookmark_tags` tables. The
file was removed. The unchanged Track 01 suite separately retains exact migration,
constraint, index, foreign-key, and autogenerate-check evidence.

## Auth-operation OpenAPI proof

Endpoint tests and the live harness loaded the generated document through
`referencing.Registry` and `Draft202012Validator`. Actual register/login success,
conflict, validation, generic authentication, and injected-unexpected bodies all
validated against the operation's response schema. The public path set contained only
`/api/auth/register` and `/api/auth/login`; both operations remained unsecured, while
the reusable `BearerAuth` component declared HTTP bearer JWT. Password request fields
were `writeOnly`; response schemas contained no password or hash field.

This is deliberately the Track 02 auth-operation proof. Track 05 still owns exhaustive
cross-operation status/content-type/schema conformance.

## Real-process Bash harnesses

| Command | Actual result |
| --- | --- |
| `bash -n scripts/verify-track-02.sh` | Exit `0`; Bash syntax valid. |
| `bash scripts/verify-track-02.sh` | Exit `0`; `Track 02 process evidence: bootstrap, auth contract, protected bearer, redacted owning fault`. |
| `bash scripts/verify-track-01.sh` | Exit `0`; inherited factory/lifecycle/error-boundary receipt passed. |

Track 02's harness uses the actual `make bootstrap`, `mktemp -d`, a dynamic loopback
port, a disposable Alembic database, bounded readiness polling, generated signing
material, protected `0600` request/token files, and real HTTP register, login,
protected-success, duplicate-conflict, generic-authentication, and injected-fault
requests. Runtime bodies validate against generated schemas.

The captured JSON Lines contain one each of starting/started/stopping/stopped, one
owning `http.request.unexpected_exception`, absolute source path and line, service,
component, event, level, UTC timestamp, logger, process and thread IDs, a same-process
UUID correlation value unrelated to credentials, complete safe exception frames, and
no raw indexed exception text. The generic `500` response contains no stack or detail.

The harness scans raw output for its generated password, returned token, submitted
sentinel, identity inputs, bearer/authorization value, Argon2 marker, password-hash
term, and inherited Track 01 fault sentinels. All were absent. It then terminated and
waited for the child, removed the verified prefix-bounded temporary directory, and
printed `Track 02 harness cleanup: removed verified disposable resources`. The
inherited Track 01 harness also passed and removed its disposable resources.

## Independent review and repository hygiene

- Mason inspected the full `main...HEAD` delta plus the uncommitted transport wave,
  governing SPEC/PLAN/ADRs, auth/error modules, session scope, OpenAPI, tests, and both
  process harnesses. It independently reran 109 focused tests, the 236-test full
  100%-coverage gate, Ruff, mypy, both harnesses, Bash syntax, and diff checks.
- The review returned PASS for requirements, security/redaction, test completeness,
  process/cleanup safety, and inherited Track 01 preservation. Its sole initial
  changes-required finding was the absence of this report and stale control-plane
  statuses; no implementation defect was found.
- Repository scans found no tracked database, coverage, virtual-environment, cache,
  JSON-Line, log, private-key, bearer-token, or literal long JWT-secret artifact.
  `git status` contained only the intended closure documents before their commit.
- The test-only protected/fault seams remain absent outside `APP_ENV=test` and are
  excluded from public OpenAPI. Importing `app.main` or the database packages remains
  inert, and all schema creation remains Alembic-owned.

## Known gaps and retained boundaries

- The suite emits one Starlette deprecation warning from locked FastAPI's TestClient
  compatibility import recommending `httpx2`. It is upstream, unsuppressed, and
  non-blocking; live process harnesses independently cover real HTTP behavior.
- SQLite and one application worker remain the accepted scope. Refresh tokens,
  revocation, account lifecycle, rate limiting, bookmark authorization routes, and
  statistics are outside Track 02.
- The private protected route exists only to exercise the reusable dependency in a
  real process before Track 03 delivers public protected routes.
- This report closes only Track 02. It does not count as implementation evidence for
  Tracks 03-08, and it does not claim Track 05's global OpenAPI quality gate.
