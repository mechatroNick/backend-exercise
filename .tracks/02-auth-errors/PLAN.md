# Track 02 plan: error contract and authentication

- Specification: [SPEC.md](SPEC.md), version 1.0
- Status: Planned
- Active item: None; implementation is dependency-gated on Track 01 closure

## Execution plan

| ID | Work item | Owner | Depends on | Status | Exit evidence |
| --- | --- | --- | --- | --- | --- |
| T02-01 | Verify the Track 01 closure receipt and inspect delivered composition, Settings, clock, session, users schema, migrations, and tests before auth changes. | Smith / implementation | Track 01 closure | Blocked | Written compatibility checkpoint; no auth work starts if the required seams are absent or contradictory. |
| T02-02 | Define application-owned expected errors, stable error DTOs/codes, and the one centralized FastAPI HTTP translation boundary. | Smith / implementation | T02-01 | Pending | Error matrix tests prove envelope/status behavior for validation, auth, conflict, not-found, and redacted unexpected failures. |
| T02-03 | Add identity/password normalization, Argon2 hashing, and injected-clock access-only JWT security primitives. | Smith / implementation | T02-01 | Pending | Deterministic unit tests prove username/email policy, NFC handling, Argon2 verify, required claims, expiry, and secret-safe behavior. |
| T02-04 | Add auth repository/service operations for register, generic login failure, canonical user lookup, and race-safe uniqueness translation with transaction rollback. | Smith / implementation | T02-02, T02-03 | Pending | Integration tests prove canonical duplicate conflicts, no user enumeration, rollback, and public/persistence separation. |
| T02-05 | Add JSON auth routes, bearer authenticated-user dependency, composition wiring, and scoped auth-operation OpenAPI metadata. | Smith / implementation | T02-02, T02-03, T02-04 | Pending | Endpoint tests prove `201` register, `200` login, standard `401`s, current-subject resolution, and generated-schema agreement for auth operations. |
| T02-06 | Add the focused auth/error test matrix and credential-redaction regression checks. | Smith / implementation | T02-02, T02-03, T02-04, T02-05 | Pending | Unit, integration, and endpoint cases cover the edge-case ledger; test output and ordinary logs contain no credential-bearing values. |
| T02-07 | Run Track 02 closure validation, inspect the diff/OpenAPI, record evidence, and determine readiness of Track 03. | Primary engineering thread | T02-01, T02-02, T02-03, T02-04, T02-05, T02-06 | Pending | Actual quality commands, auth-operation schema validation, hygiene review, and HISTORY/TEST-REPORT receipt; full cross-operation OpenAPI conformance remains Track 05. |

## Work-wave detail

### T02-01 — Baseline and dependency gate

- Confirm that Track 01's final status is Complete and that its closed evidence
  demonstrates the exact integration seams: injectable Settings and clock, a
  non-mutating app factory, per-request synchronous sessions, the migrated `users`
  table with canonical unique identity fields and password-hash capacity, and test
  databases created only through Alembic.
- Select `pwdlib[argon2]` and a JWT library only after checking their current primary
  documentation against the locked Track 01 toolchain. Add dependencies in the
  owning track rather than anticipating them in Track 01.
- Stop rather than silently adapting if an upstream result changes a reserved auth,
  error, identity, token, or schema contract.

### T02-02 — Error model and HTTP boundary

- Define a small transport-independent hierarchy rooted in an expected application
  error. Include typed validation, authentication, conflict, and not-found errors;
  preserve causes when translating driver failures.
- Keep the error envelope DTO explicit. `details` is safe structured validation
  information only; auth/conflict/unexpected details must not disclose credentials,
  account existence, database internals, configuration, or tracebacks.
- Install one handler registration point for expected errors, framework validation
  errors, and unexpected errors. Routers/services/repositories must not replicate
  route-local `try`/`except` mappings. Unexpected errors are logged only through the
  established redaction-safe logging boundary and return a generic envelope.

### T02-03 — Security primitives

- Implement one email helper and one username helper that return canonical stored
  values; reject rather than silently repair invalid username characters/length.
- Normalize password input with Unicode NFC immediately before hashing and before
  verification. Count the 15--128-character policy after NFC normalization; preserve
  original password data only transiently for the current boundary operation.
- Wrap Argon2 hash/verify and JWT issue/verify behind narrow injected collaborators.
  JWT verification must pin HS256, require/validate `sub`, `iat`, and `exp`, and use
  the injected clock instead of sleeps or wall-clock monkeypatching.
- Treat a configured secret as secret-bearing at every boundary. Do not include it,
  derived tokens, raw authorization values, or hashes in exceptions, logs, fixtures,
  OpenAPI examples, or public DTOs.

### T02-04 — Repository and service

- The registration service owns normalization, hash creation, persistence request,
  and transaction outcome; repositories expose only explicit canonical-user lookup
  and user-creation operations and never commit independently.
- Insert first or treat any optional pre-check as advisory. After rollback, translate
  only recognized username/email uniqueness failures to a typed conflict error using
  exception chaining; unrelated integrity failures remain unexpected. Prove a
  simultaneous/forced duplicate race cannot escape as a generic `500` and a different
  integrity failure cannot be mislabeled `409`.
- Login looks up only the canonical email, verifies the submitted NFC password, and
  returns the same generic expected authentication error for absent user and failed
  verification. Never return `None` or a boolean to represent those expected failures.

### T02-05 — Transport, dependency, and bounded OpenAPI proof

- Declare JSON request bodies and distinct public response models. Registration is
  `201`; login is `200`; neither exposes password fields or hashes.
- Define bearer security and a reusable authenticated-user dependency. It maps
  missing, wrong-scheme, malformed, tampered, expired, wrong-algorithm, missing-claim,
  and deleted/missing-subject credentials to the standard `401` response.
- Resolve user identity once for the request. Track 03 must pass that authenticated
  subject into query-scoped repository calls; this track does not add bookmark CRUD.
- Ensure generated OpenAPI accurately describes the two auth operations, their
  request/response schemas, statuses, error envelope, examples, and bearer scheme.
  Validate those two operations now; Track 05 remains owner of full API-wide response
  conformance.

### T02-06/T02-07 — Tests and closure

- Use fake clock/security adapters for deterministic primitives and disposable
  Alembic-migrated SQLite databases for persistence/route tests. Avoid live secrets,
  sleeps, external services, or real user databases.
- Cover every applicable ledger entry below. Keep credential values out of assertion
  failure messages and captured logs where practical; inspect snapshots/response
  bodies/log records for prohibited fields.
- Run the Track 01-established formatting, lint, type, migration, and suite commands
  plus focused auth tests. The primary records actual output and decides only then
  whether Track 02 becomes Complete and Track 03 may begin.

## Edge-case ledger

| Dimension | Case | Planned proof |
| --- | --- | --- |
| Success | Register canonical new identity; login valid credentials; decode issued valid access token. | T02-03 unit tests; T02-04/05 integration and endpoint tests. |
| Boundary | Username length 3/80; password length 15/128 after NFC; permitted ASCII username punctuation. | T02-03 parameterized unit tests and DTO tests. |
| Malformed input | Extra fields, invalid/missing JSON fields, invalid email, unsupported username characters, username/password too short/long. | T02-02/05 validation-envelope endpoint tests. |
| Normalization | Trim/case duplicate email and username; composed/decomposed Unicode password comparison; no password trim/lowercase. | T02-03/04 unit and integration tests. |
| Authentication | Missing/wrong-scheme/malformed/tampered/expired/wrong-algorithm/missing-claim token. | T02-03/05 injected-clock token and dependency tests. |
| Subject state | Validly signed token whose user was deleted or is absent. | T02-05 dependency integration test returns generic `401`. |
| Non-enumeration | Unknown email and wrong password receive identical status, code, message, and safe details. | T02-04/05 comparative test. |
| Concurrency | Duplicate normalized identities race; database uniqueness wins; transaction rolls back before subsequent use; unrelated integrity failures are not mapped to `409`. | T02-04 real SQLite or forced integrity-path integration test. |
| Failure | Hash/JWT dependency failure preserves cause internally and reaches the centralized redacted unexpected/expected boundary. | T02-02/03 focused failure-injection tests. |
| Compatibility | Auth routes keep accepted JSON paths, statuses, public response shape, and envelope; no bookmark endpoint is introduced. | T02-05 OpenAPI/route-manifest and response tests. |
| Cleanup/hygiene | No secret/hash/token/header in DTOs, ordinary logs, test fixtures/output, or repository status. | T02-06 redaction tests, review scan, and status check. |

## Planned validation commands

Exact command spelling is inherited from the delivered Track 01 toolchain and must
be recorded when implementation is authorized. The closure interface must include:

```text
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run mypy app
uv run pytest tests/unit tests/integration tests/contract -k 'auth or error'
uv run pytest
uv run alembic upgrade head
uv run alembic check
make check
git diff --check
git status --short
```

The auth-operation OpenAPI proof must validate actual registration/login success and
documented error responses against the generated schema. It is deliberately scoped:
the exhaustive all-operation response/status/content-type/schema gate belongs to
Track 05.

## Review checkpoints

1. After T02-01: primary confirms the Track 01 evidence and dependency seams.
2. After T02-02: review the one-boundary error matrix and safe `details` policy.
3. After T02-03: review identity/password/JWT semantics and no-leak surfaces.
4. After T02-04: review database-race and rollback evidence.
5. After T02-05: compare runtime auth contract to generated OpenAPI.
6. At T02-07: primary runs closure, reviews diff/logging hygiene, and records gaps.

## Commit boundary

Preferred single-track commit after the closure gate:

`feat: add secure authentication and error contracts`

If reviewability benefits from two commits, split only at a green boundary:

1. `feat: add typed API error contracts`
2. `feat: add secure registration and JWT authentication`

Do not commit a usable secret, password/hash/token/header fixture, generated database,
cache, coverage output, or a failing intermediate state.
