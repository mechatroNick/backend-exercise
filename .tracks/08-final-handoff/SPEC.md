# Track 08 specification: final hardening, documentation, and assessment handoff

- Status: In progress
- Specification version: 1.3
- Planned: 2026-08-05
- Owner: Primary engineering thread
- Depends on: Completed Tracks 01–07, including the Track 07 weekly-projection closure report
- Governing records: `.docs/ASSESSMENT.md`, `.docs/SOLUTION-DESIGN.md`,
  `.docs/DELIVERY-PLAN.md`, and ADR-001 through ADR-009

## Intent anchor

### 2026-08-10 downstream integration supersession

The prior Track 08 completion receipt is historical evidence for the then-current
Track 07 owner-skip/absence disposition. Track 07 is now Complete with weekly private
projection evidence, so Track 08 is reopened **In progress** until a fresh clean-source
Track 08 run integrates that delivered dependency. This supersedes only the active
closure posture; it preserves the historical exact facts, counts, and clean-source
HEAD recorded in the prior report.

Prepare a reproducible, reviewable local assessment handoff from the *delivered*
repository. Track 08 verifies and documents evidence; it does not invent outcomes,
change accepted product contracts, submit externally, push, deploy, or create a
submission link without later repository-owner authority.

## Must preserve

- All delivered public API, security, data, current-statistics, event, and Track 07
  private-projection contracts. Track 07 adds no public weekly/history API and must
  remain compatible with the same named non-daemon refresher, without an external
  worker or topology change.
- The mandatory quality gate as the prerequisite for bonus work; bonuses are required
  by the current owner decision but cannot weaken, obscure, or substitute for the
  required suite.
- Local Python/SQLite, one-worker, in-process-service assessment scope, private Track
  07 projection persistence, and the required all-current statistics boundary.
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
  against actual Track 00–07 closure evidence, including the exact Track 07 report,
  provenance, and executable harness;
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
- a public weekly-statistics/history API, external worker, or weekly-projection
  topology change; Track 07's delivered private persistence remains in scope for
  compatibility verification; and
- rewriting, squashing, or otherwise mutating history unless the owner later asks.

## Requirements

| ID | Requirement |
| --- | --- |
| T08-REQ-01 | Do not re-close until Tracks 01–07 are Complete with actual closure reports; inspect the exact Track 07 report, provenance ledger, and executable harness. Track 00 remains the completed baseline. |
| T08-REQ-02 | Verify all selected assessment rows, including WIN-01/WIN-02 as delivered by Track 07 evidence, while recording that fresh Track 08 integration proof remains pending: GOV-01; ENV-01, ARC-01, DATA-01…DATA-04; AUTH-01…AUTH-04, ERR-01, SEC-01; BKM-01…BKM-03, ISO-01, TAG-01, TIME-01; QRY-01, QRY-02, SQL-01…SQL-03; EVT-01…EVT-03, WIN-01…WIN-03, OPS-01; API-01, API-02, TEST-01, TEST-02, QUAL-01; DEL-01…DEL-03, DOC-01, BONUS-01, BONUS-02, and FUT-01. |
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

- Tracks 01–07 are Complete and each closure report is inspected; the exact Track 07
  report/provenance/harness and private persistence/Docker compatibility are verified;
  no public weekly/history API or external/second refresher exists; all assessment IDs have a current
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

Track 08 imports the shared [engineering verification guideline](../../.docs/ENGINEERING-VERIFICATION-GUIDELINE.md)
and [ADR-006](../ADR/ADR-006-engineering-verification-and-closure-evidence.md)
closure invariant without changing any accepted product contract: **Complete**
requires recorded passing deterministic, integration, contract, migration, quality,
security, and real-process evidence, including the final
`bash scripts/verify-track-08.sh` receipt and verified cleanup. A planned, unrun,
blocked, or stale prerequisite command/report is never passing evidence. Track 07's
earlier owner-authorized skip remains historical; the current dependency is its Passed
report and executable verifier. The
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

## Closure boundary

The clean-source receipt records the locked dependency-audit and bootstrap commands.
Private authorization/provenance remains outside repository verification and is an
owner-only review item, not a closure blocker for repository evidence.

Stop and return to the owning track if a closure report is missing, a requirement lacks
credible evidence, clean-clone behavior differs from documentation, a secret/higher
severity security defect is found, a bonus threatens the mandatory suite, a requested
claim exceeds evidence, or an apparent fix changes an accepted public contract. Stop
and seek owner direction before submission, push, deployment, link/archive creation,
history rewriting/squashing, or use/disclosure of private correspondence.

## Traceability

| Assessment / delivery ID | Track 08 evidence |
| --- | --- |
| DEL-01 | Coherent incremental-history review, repository hygiene receipt, release/handoff note, and explicit owner-owned submission boundary. |
| DEL-02, DOC-01 | Fresh-clone/fresh-reader README and architecture/deployment/trade-off/limitation review. |
| DEL-03 | Evidence-bounded AI-assisted-work disclosure; private authorization/provenance boundary recorded without copying private material. |
| FUT-01 | README limitations/production-evolution section; no external infrastructure implementation. |
| BONUS-01 | Required by owner decision after mandatory green: deterministic seed command, idempotency/safety evidence, and documented invocation. |
| BONUS-02 | Required by owner decision after mandatory green: Docker setup, rate limiting, and cursor pagination, each with isolated contract/edge evidence. |
| WIN-01, WIN-02 | Delivered by the completed Track 07 report and harness; fresh Track 08 clean-source integration evidence is pending. |
| All remaining assessment IDs | Track 01–07 closure-report inventory, including Track 07 provenance/harness, must be reconciled in a new passing final [TEST-REPORT.md](TEST-REPORT.md), with fresh clean-clone and runtime checks. |
