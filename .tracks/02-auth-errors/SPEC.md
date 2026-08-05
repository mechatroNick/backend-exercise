# Track 02 specification: error contract, registration, login, and JWT authentication

- Status: Planned
- Specification version: 1.0
- Planned: 2026-08-05
- Owner: Primary engineering thread
- Depends on: Track 01 implementation and closure; Track 00 (Complete)
- Governing ADRs: ADR-001, ADR-002, ADR-003
- Assessment requirements: AUTH-01, AUTH-02, AUTH-03, AUTH-04, ERR-01, SEC-01

## 1. Intent anchor

Build the smallest secure authentication capability that later bookmark operations
can depend on: canonical user registration, non-enumerating login, expiring
access-token verification, and one stable JSON error contract.

Detailed planning is permitted after review of Track 01's plan. Implementation is
dependency-gated until Track 01 has delivered and closed its project, configuration,
database, migration, application-factory, and test foundations.

## 2. Must-preserve contracts

- `POST /api/auth/register` accepts JSON, returns `201`, and returns public user
  fields plus an access token. `POST /api/auth/login` accepts JSON, returns `200`,
  and returns the same public response shape.
- Email is trimmed and stored as one lowercase canonical value. Username is trimmed,
  lowercased, unique, and limited to 3--80 ASCII letters, digits, periods,
  underscores, and hyphens.
- Passwords are 15--128 characters; spaces and Unicode are permitted. Passwords are
  NFC-normalized before both hashing and verification, but are never trimmed,
  lowercased, returned, or logged.
- Password hashes use Argon2 through `pwdlib`. JWTs are access-only HS256 tokens
  with stable `sub`, `iat`, and `exp` claims, a Settings-provided signing secret,
  configurable default 30-minute lifetime, and an injected clock.
- Unknown canonical email and invalid password produce the same generic login
  failure. Missing, malformed, tampered, expired, or otherwise invalid bearer
  credentials produce the same stable `401` envelope.
- Authentication resolves a current user subject. Later resource repositories must
  query by authenticated user identity in the database predicate; they must not
  fetch an arbitrary resource and compare ownership afterward.
- Validation, authentication, conflict, not-found, and unexpected failures use
  `{ "error": { "code", "message", "details" } }`. Expected errors are typed and
  transport-independent. A single HTTP translation boundary maps them to statuses;
  unexpected failures are redacted and never reveal stack traces or secrets.
- The database unique constraints remain the authoritative, race-safe identity
  conflict guards. A pre-check may improve ergonomics but cannot replace the insert
  path. Only known username/email uniqueness violations map to `409`; other integrity
  failures remain unexpected after rollback.
- Passwords, password hashes, JWTs, authorization headers, and signing secrets are
  absent from response DTOs, error details, ordinary logs, fixtures, and committed
  artifacts.

## 3. Scope

### Included

- typed expected-error hierarchy and centralized FastAPI exception handlers;
- explicit error-envelope schemas and auth-operation OpenAPI responses/examples;
- registration/login request and public response DTOs with strict untrusted-input
  handling;
- identity/password normalization and validation helpers;
- Argon2 password-hashing and injected-clock JWT ports/adapters;
- user repository and authentication service with transaction ownership outside the
  repository and integrity-conflict translation;
- auth router, bearer scheme, authenticated-user dependency, and current-subject
  resolution;
- deterministic unit, integration, endpoint, and auth-operation OpenAPI tests;
- Track 02 closure evidence, including security/redaction review.

### Non-goals

- bookmark CRUD, bookmark authorization behavior beyond the reusable dependency,
  statistics, tags, filters, or schema redesign;
- refresh tokens, token rotation/revocation, account recovery, account management,
  RBAC, social login, rate limiting, or external identity providers;
- broad cross-operation OpenAPI conformance. Track 02 proves its own registration
  and login operations; Track 05 owns full API-wide OpenAPI conformance;
- dependency installation, product implementation, or any claim of runtime evidence
  while this track remains planned.

## 4. Decision latitude and reserved decisions

Track 02 may choose exact internal module names, typed-error names/codes, DTO field
names that preserve the accepted public response shape, repository method names,
test fixtures, and the location of the single HTTP translation registration.

Stop for an ADR update and repository-owner direction before changing route paths,
success statuses, public response shape, the JSON error envelope, identity or
password normalization, token type/algorithm/claims/lifetime semantics, database
schema, or the authentication failure-disclosure policy.

## 5. Requirements

| ID | Requirement |
| --- | --- |
| T02-REQ-01 | Define transport-independent expected errors and one centralized HTTP boundary that emits the standard error envelope for validation, authentication, conflict, not-found, and redacted unexpected failures. |
| T02-REQ-02 | Validate and canonicalize registration/login identities: lowercase trimmed email, lowercase trimmed 3--80-character ASCII username policy, and password NFC semantics without disclosure. |
| T02-REQ-03 | Hash and verify passwords with Argon2 through `pwdlib`, without persisting or exposing plaintext password data. |
| T02-REQ-04 | Issue and verify access-only HS256 JWTs containing stable `sub`, `iat`, and `exp`, using injected time and Settings-provided secret/TTL. |
| T02-REQ-05 | Register users race-safely: database uniqueness is authoritative, known username/email uniqueness failures become stable `409` errors after rollback, and unrelated integrity failures are not misclassified as conflicts. |
| T02-REQ-06 | Implement JSON-body registration and login routes with their accepted statuses, public user-and-token response shape, and generic login failure. |
| T02-REQ-07 | Provide a reusable bearer-auth dependency that rejects missing, malformed, tampered, expired, invalid, and deleted/missing-subject tokens consistently. |
| T02-REQ-08 | Document and test Track 02 auth operations' bearer security, schemas, statuses, and envelope examples without claiming Track 05's full cross-operation conformance. |
| T02-REQ-09 | Prove secrets and credential-bearing data do not leak through DTOs, error details, ordinary logs, or test artifacts. |

## 6. Dependencies and readiness gate

| Dependency | Required state before Track 02 implementation | Reason |
| --- | --- | --- |
| Track 00 | Complete | Provides accepted routes, status/error semantics, and ADR baseline. |
| Track 01 | Implemented and closed | Provides Python 3.12 locked environment, Settings, injected clock, app factory, synchronous sessions, users table, Alembic test database, and quality commands. |
| ADR-002 | Accepted | Fixes auth paths, `409` uniqueness, `401` credential behavior, and envelope shape. |
| ADR-003 | Accepted | Fixes identity, password, Argon2, JWT, secret, and non-enumeration contracts. |

Track 02 remains **Planned**, not Ready, until the Track 01 closure gate supplies
actual implementation evidence. If that implementation differs materially from
Track 01's planned extension seams, revise this plan before writing auth code.

## 7. Acceptance evidence threshold

Track 02 may close only when a clean Track 01-built test database and locked
environment demonstrate all of the following:

- valid JSON registration returns `201`, canonical public identity fields, and a
  verifiable access token; valid login returns `200` with the same public shape;
- case/whitespace variants of duplicate email or username are conflict-safe and
  return `409` in the standard envelope, including the integrity-race path;
- malformed or extra input, invalid username, invalid email, short/overlong password,
  and NFC-equivalent password handling receive the documented validation behavior;
- Argon2 hashes verify correctly, plaintext is never persisted, and wrong-password
  versus unknown-email login responses are indistinguishable;
- issued JWTs have only the accepted access-token semantics and required claims;
  valid tokens resolve the current user, while missing/malformed/tampered/expired
  tokens and deleted/missing subjects return the consistent `401` envelope;
- validation, authentication, conflict, not-found, and injected unexpected failures
  all return the standard envelope, with unexpected responses redacted;
- auth operation responses validate against the generated OpenAPI schema, whose
  auth-operation security, statuses, envelopes, and examples agree with runtime;
- focused unit/integration/endpoint tests plus format, lint, type-check, and full
  suite commands pass; logs/DTOs/test output are reviewed for credential leakage;
- no secrets, hashes, tokens, generated databases, caches, or coverage artifacts
  appear in repository status.

## 8. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Track 01 is not actually compatible with the planned injection seams | Do not begin implementation before closure; inspect delivered Settings, clock, sessions, factory, and migration fixtures first. |
| Identity pre-check races allow duplicates or cause wrong status | Treat the database constraint as authoritative; translate only the insert integrity failure after rollback. |
| Route-local exceptions create divergent envelopes | Register one HTTP translation boundary and prohibit duplicated route mappings. |
| Unicode normalization differs between registration and login | Use one NFC helper before both hash and verify; test composed/decomposed equivalents. |
| Token parsing leaks implementation details or accepts unsafe claims | Verify algorithm and claims explicitly with injected time; map every credential failure to generic `401`. |
| Credential data leaks in diagnostics | Keep credential values out of DTOs/errors/log context and add focused redaction tests/review. |

## 9. Stop conditions

Stop and reframe before implementation if:

- Track 01 is not closed or does not provide the planned Settings, clock, migration,
  session, app-factory, and quality foundations;
- a required auth behavior conflicts with ADR-002 or ADR-003;
- the delivered users schema cannot store safe Argon2 hashes or does not enforce
  canonical unique identities without a proposed schema decision;
- a dependency cannot provide secure Argon2 or HS256 verification in the locked,
  locally runnable stack;
- a request requires refresh tokens, account lifecycle, rate limiting, or another
  excluded capability;
- implementation would expose a credential or require a material public-contract
  change.

## 10. Traceability

| Assessment requirement | Track 02 requirements | Planned evidence |
| --- | --- | --- |
| AUTH-01 | T02-REQ-02, T02-REQ-03, T02-REQ-05, T02-REQ-06, T02-REQ-08 | Registration endpoint/OpenAPI contract tests and duplicate-conflict integration tests. |
| AUTH-02 | T02-REQ-02, T02-REQ-03, T02-REQ-04, T02-REQ-06, T02-REQ-08 | Login endpoint/OpenAPI contract tests and generic-failure tests. |
| AUTH-03 | T02-REQ-03, T02-REQ-04, T02-REQ-07, T02-REQ-09 | Hash/verify, injected-clock JWT, invalid-token, and redaction tests. |
| AUTH-04 | T02-REQ-07, T02-REQ-08 | Bearer dependency tests and later Track 03 route integration review. |
| ERR-01 | T02-REQ-01, T02-REQ-05, T02-REQ-07, T02-REQ-08 | Error-handler matrix tests for `422`, `401`, `409`, `404`, and redacted `500`. |
| SEC-01 | T02-REQ-02 through T02-REQ-09 | Canonicalization, Argon2, access-only JWT, non-enumeration, race, and no-leak evidence. |
