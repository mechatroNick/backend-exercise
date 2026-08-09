# Track 08 specification: final hardening, documentation, and assessment handoff

- Status: Ready (implementation authorized)
- Specification version: 1.3
- Planned: 2026-08-05
- Owner: Primary engineering thread
- Depends on: Completed Tracks 01–06 and the recorded Track 07 skip decision
- Governing records: `docs/ASSESSMENT.md`, `docs/SOLUTION-DESIGN.md`,
  `docs/DELIVERY-PLAN.md`, and ADR-001 through ADR-007

## Intent anchor

Prepare a reproducible, reviewable local assessment handoff from the *delivered*
repository. Track 08 verifies and documents evidence; it does not invent outcomes,
change accepted product contracts, submit externally, push, deploy, or create a
submission link without later repository-owner authority.

## Must preserve

- All delivered public API, security, data, current-statistics, and event contracts
  accepted by Tracks 00–06. Track 07 weekly projections are explicitly not selected.
- The mandatory quality gate as the prerequisite for bonus work; bonuses are required
  by the current owner decision but cannot weaken, obscure, or substitute for the
  required suite.
- Local Python/SQLite, one-worker, in-process-service assessment scope and the
  required current-statistics boundary without private weekly projection data.
- No public statistics-history API by default.
- Honest evidence: documentation, AI-assisted-work disclosure, walkthrough, and
  release note state only what the repository and owner-provided evidence support.

## Decision latitude

After the gate, Track 08 may select concise documentation structure, the exact
disposable clean-clone rehearsal directory, non-sensitive demo data, and a useful
walkthrough format. It may repair an in-scope documentation or hygiene defect. A
product-contract, dependency, migration, route, security, deployment-topology, or
bonus decision requires the owning implementation track/ADR review first.

## Scope

Included:

- final verification of every selected assessment requirement and accepted extension
  against actual Track 00–06 closure evidence plus the Track 07 skip record;
- a clean-clone Python 3.12 and locked-`uv` rehearsal for configuration, migration,
  bootstrap/run, tests, OpenAPI/docs, and health evidence;
- a root README that reflects delivered setup, migration, run, API, testing,
  architecture, local deployment, trade-offs, limitations, and future evolution;
- an accurate AI-assisted-work disclosure bounded by actual repository history and
  owner-provided authorization/provenance evidence;
- security, dependency, secret, generated-artifact, and repository-hygiene review;
- a reviewer walkthrough/demo, final `TEST-REPORT.md`, release/handoff note, and
  coherent-history review; and
- deterministic seed data, Docker setup, rate limiting, and cursor pagination, each
  implemented after the mandatory gate with isolated evidence and regression checks.

Excluded:

- external submission/link creation, pushing, release publication, or deployment;
- external workers/brokers, multi-process coordination, PostgreSQL, and production
  infrastructure (FUT-01 is documentation-only);
- weekly developing/developed tables, correction revisions, historical consumers, or
  a public weekly-statistics API; and
- rewriting, squashing, or otherwise mutating history unless the owner later asks.

## Requirements

| ID | Requirement |
| --- | --- |
| T08-REQ-01 | Do not begin hardening until Tracks 01–06 are Complete with actual closure `TEST-REPORT.md` artifacts and Track 07 is recorded Skipped; Track 00 remains the completed baseline. |
| T08-REQ-02 | Verify all selected assessment rows and record WIN-01/WIN-02 as owner-skipped without fabricated evidence: GOV-01; ENV-01, ARC-01, DATA-01…DATA-04; AUTH-01…AUTH-04, ERR-01, SEC-01; BKM-01…BKM-03, ISO-01, TAG-01, TIME-01; QRY-01, QRY-02, SQL-01…SQL-03; EVT-01…EVT-03, WIN-03, OPS-01; API-01, API-02, TEST-01, TEST-02, QUAL-01; DEL-01…DEL-03, DOC-01, BONUS-01, BONUS-02, and FUT-01. |
| T08-REQ-03 | Rehearse the delivered project from a clean clone with Python 3.12 and the committed `uv` lock: configure, migrate, bootstrap/run, exercise tests, OpenAPI/docs, and health without undocumented manual setup. |
| T08-REQ-04 | Deliver documentation based on facts: root README quickstart/API/testing, project and local deployment architecture, design choices, trade-offs, limitations, and production evolution. |
| T08-REQ-05 | Deliver DEL-03 disclosure based only on actual assistance/process evidence and the owner-provided private authorization/provenance boundary; do not store private correspondence or make unsupported claims. |
| T08-REQ-06 | Produce a reproducible walkthrough/demo and final `TEST-REPORT.md` plus release/handoff note that map requirements to commands, results, selectors, artifacts, known limits, and owner action. |
| T08-REQ-07 | Review history, dependencies, secrets, generated artifacts, ignored files, licenses/security advisories as applicable, and documentation claims without rewriting history or exposing sensitive data. |
| T08-REQ-08 | After mandatory evidence is green, implement all owner-selected bonus scope: deterministic seed data, Docker setup, rate limiting, and cursor pagination. Stabilize each change independently, update its public/configuration contract and tests, and rerun the mandatory/full final harness after the complete bonus set. |
| T08-REQ-09 | Keep FUT-01 explicitly documentary: explain production evolution and local limitations without adding a production dependency or public history API. |

## Acceptance evidence threshold

Track 08 closes only when the following are actual, recorded results rather than
planned claims:

- Tracks 01–06 are Complete and each closure report is inspected; Track 07 is verified
  Skipped with no weekly artifacts; all assessment requirement IDs have a current
  evidence row or an explicit owner-authorized skip/limit;
- a clean clone on Python 3.12 succeeds with the committed lock and documented
  configuration/migration/bootstrap/run/test workflow;
- OpenAPI/docs and health checks are exercised against the running service, and the
  documented commands agree with the delivered repository;
- the root README, architecture/deployment explanation, trade-offs, limitations,
  walkthrough, AI disclosure, and release note are fresh-reader accurate;
- mandatory security/dependency/hygiene checks are green, no secret or generated
  artifact is staged, and no critical/high unresolved defect remains;
- seed data, Docker, rate limiting, and cursor pagination each have separately green
  focused evidence and the combined final regression remains green; and
- the final report identifies the repository owner as the sole owner of submission
  link/archive creation and any external submission.

Track 08 imports the shared [engineering verification guideline](../../docs/ENGINEERING-VERIFICATION-GUIDELINE.md)
and [ADR-006](../ADR/ADR-006-engineering-verification-and-closure-evidence.md)
closure invariant without changing any accepted product contract: **Complete**
requires recorded passing deterministic, integration, contract, migration, quality,
security, and real-process evidence, including the final
`bash scripts/verify-track-08.sh` receipt and verified cleanup. A planned, unrun,
blocked, or stale prerequisite command/report is never passing evidence. Track 07's
owner-authorized skip is a scope disposition, not a passing report. The
final harness is an automation/orchestration gate, not a replacement for the
track-owned deterministic proof or a basis for a public history API. Its final JSON
audit validates `source`, service/component, event, level, UTC timestamp, logger,
`process_id`, execution/thread ID where applicable, and governing extension fields;
correlation is supplied/generated only, never identity/body/token derived. It requires
redaction and exactly one final-owning-boundary unexpected-exception record with
redacted type, safe message, ordered frames, cause/context, and no locals; intermediates
re-raise without duplicates, raw exception text is not indexed, and formatter/redactor
failure produces one minimal schema-valid redacted JSON record, never plaintext or the
unsafe original. Own authenticated response/header/sanitized-health assertion inputs
remain ephemeral in memory; JWTs are parsed/used without echo/persistence; private
inspection is sanitized/ephemeral; debug retention is explicit-flag-only and excludes
protected response/token data. API/health output never exposes tracebacks, SQL, paths,
credentials, or content, and cleanup removes disposable token/response/private-
inspection/debug state.

[ADR-007](../ADR/ADR-007-local-rate-limiting-and-cursor-pagination.md) governs the
selected rate-limiting and cursor-pagination product changes; their focused and full
evidence is required before Track 08 can close.

## Assumptions, unknowns, and stop conditions

The owner will provide any necessary non-repository authorization/provenance evidence
privately; the repository cannot verify it. Exact dependency-audit and bootstrap
commands remain implementation-dependent until the locked project exists.

Stop and return to the owning track if a closure report is missing, a requirement lacks
credible evidence, clean-clone behavior differs from documentation, a secret/higher
severity security defect is found, a bonus threatens the mandatory suite, a requested
claim exceeds evidence, or an apparent fix changes an accepted public contract. Stop
and seek owner direction before submission, push, deployment, link/archive creation,
history rewriting/squashing, or use/disclosure of private correspondence.

## Traceability

| Assessment / delivery ID | Track 08 evidence |
| --- | --- |
| DEL-01 | Coherent incremental-history review, repository hygiene receipt, release/handoff note, and explicit owner-owned submission action. |
| DEL-02, DOC-01 | Fresh-clone/fresh-reader README and architecture/deployment/trade-off/limitation review. |
| DEL-03 | Evidence-bounded AI-assisted-work disclosure; private authorization/provenance boundary recorded without copying private material. |
| FUT-01 | README limitations/production-evolution section; no external infrastructure implementation. |
| BONUS-01 | Required by owner decision after mandatory green: deterministic seed command, idempotency/safety evidence, and documented invocation. |
| BONUS-02 | Required by owner decision after mandatory green: Docker setup, rate limiting, and cursor pagination, each with isolated contract/edge evidence. |
| WIN-01, WIN-02 | Explicit Track 07 owner-skipped disposition; no implementation evidence claimed. |
| All remaining assessment IDs | Track 01–06 closure-report inventory plus the Track 07 skip record reconciled in final `TEST-REPORT.md`, with final clean-clone and runtime checks. |
