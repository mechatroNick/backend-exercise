# Track 08 specification: final hardening, documentation, and assessment handoff

- Status: Planned (implementation-gated)
- Specification version: 1.0
- Planned: 2026-08-05
- Owner: Primary engineering thread
- Depends on: Completed Tracks 01–07 and their closure `TEST-REPORT.md` artifacts
- Governing records: `docs/ASSESSMENT.md`, `docs/SOLUTION-DESIGN.md`,
  `docs/DELIVERY-PLAN.md`, and ADR-001 through ADR-005

## Intent anchor

Prepare a reproducible, reviewable local assessment handoff from the *delivered*
repository. Track 08 verifies and documents evidence; it does not invent outcomes,
change accepted product contracts, submit externally, push, deploy, or create a
submission link without later repository-owner authority.

## Must preserve

- All public API, security, data, current-statistics, event, and weekly-projection
  contracts accepted by Tracks 00–07 and ADR-001 through ADR-005.
- The mandatory quality gate as the prerequisite for optional work; optional work
  cannot weaken, obscure, or substitute for the required suite.
- Local Python/SQLite, one-worker, in-process-service assessment scope and the
  separation of required current statistics from private weekly projection data.
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

- final verification of every assessment requirement and accepted extension against
  actual Track 00–07 closure evidence;
- a clean-clone Python 3.12 and locked-`uv` rehearsal for configuration, migration,
  bootstrap/run, tests, OpenAPI/docs, and health evidence;
- a root README that reflects delivered setup, migration, run, API, testing,
  architecture, local deployment, trade-offs, limitations, and future evolution;
- an accurate AI-assisted-work disclosure bounded by actual repository history and
  owner-provided authorization/provenance evidence;
- security, dependency, secret, generated-artifact, and repository-hygiene review;
- a reviewer walkthrough/demo, final `TEST-REPORT.md`, release/handoff note, and
  coherent-history review; and
- an explicit post-mandatory-gate go/no-go for optional seed data and bonus work.

Excluded:

- external submission/link creation, pushing, release publication, or deployment;
- external workers/brokers, multi-process coordination, PostgreSQL, and production
  infrastructure (FUT-01 is documentation-only);
- history routes or another public weekly-statistics API;
- automatic addition of seed data, Docker, rate limiting, or cursor pagination; and
- rewriting, squashing, or otherwise mutating history unless the owner later asks.

## Requirements

| ID | Requirement |
| --- | --- |
| T08-REQ-01 | Do not begin hardening until Tracks 01–07 are Complete and each has an actual closure `TEST-REPORT.md`; Track 00 remains the completed baseline. |
| T08-REQ-02 | Verify all assessment rows: GOV-01; ENV-01, ARC-01, DATA-01…DATA-04; AUTH-01…AUTH-04, ERR-01, SEC-01; BKM-01…BKM-03, ISO-01, TAG-01, TIME-01; QRY-01, QRY-02, SQL-01…SQL-03; EVT-01…EVT-03, WIN-01…WIN-03, OPS-01; API-01, API-02, TEST-01, TEST-02, QUAL-01; and DEL-01…DEL-03, DOC-01, FUT-01. |
| T08-REQ-03 | Rehearse the delivered project from a clean clone with Python 3.12 and the committed `uv` lock: configure, migrate, bootstrap/run, exercise tests, OpenAPI/docs, and health without undocumented manual setup. |
| T08-REQ-04 | Deliver documentation based on facts: root README quickstart/API/testing, project and local deployment architecture, design choices, trade-offs, limitations, and production evolution. |
| T08-REQ-05 | Deliver DEL-03 disclosure based only on actual assistance/process evidence and the owner-provided private authorization/provenance boundary; do not store private correspondence or make unsupported claims. |
| T08-REQ-06 | Produce a reproducible walkthrough/demo and final `TEST-REPORT.md` plus release/handoff note that map requirements to commands, results, selectors, artifacts, known limits, and owner action. |
| T08-REQ-07 | Review history, dependencies, secrets, generated artifacts, ignored files, licenses/security advisories as applicable, and documentation claims without rewriting history or exposing sensitive data. |
| T08-REQ-08 | Consider BONUS-01/BONUS-02 only after mandatory evidence is green through an explicit go/no-go; any accepted bonus has isolated evidence and cannot jeopardize mandatory closure. |
| T08-REQ-09 | Keep FUT-01 explicitly documentary: explain production evolution and local limitations without adding a production dependency or public history API. |

## Acceptance evidence threshold

Track 08 closes only when the following are actual, recorded results rather than
planned claims:

- Tracks 01–07 are Complete and each closure report is inspected; all assessment
  requirement IDs have a current evidence row or an explicit owner-authorized limit;
- a clean clone on Python 3.12 succeeds with the committed lock and documented
  configuration/migration/bootstrap/run/test workflow;
- OpenAPI/docs and health checks are exercised against the running service, and the
  documented commands agree with the delivered repository;
- the root README, architecture/deployment explanation, trade-offs, limitations,
  walkthrough, AI disclosure, and release note are fresh-reader accurate;
- mandatory security/dependency/hygiene checks are green, no secret or generated
  artifact is staged, and no critical/high unresolved defect remains;
- optional work is absent or separately green after an explicit go/no-go; and
- the final report identifies the repository owner as the sole owner of submission
  link/archive creation and any external submission.

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
| BONUS-01, BONUS-02 | Explicit go/no-go after mandatory green; if approved, isolated implementation and regression evidence. |
| All remaining assessment IDs | Track 01–07 closure-report inventory reconciled in final `TEST-REPORT.md`, with final clean-clone and runtime checks. |
