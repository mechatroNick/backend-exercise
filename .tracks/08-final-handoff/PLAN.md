# Track 08 plan: final hardening, documentation, and assessment handoff

- Specification: [SPEC.md](SPEC.md), version 1.0
- Status: Planned (implementation-gated)
- Active item: None; T08-01 is blocked pending all upstream closures

## Dependency gate and intent check

Before any Track 08 implementation, the primary thread verifies Track 00 is Complete
and Tracks 01–07 are Complete with their actual `TEST-REPORT.md` closure artifacts.
It reconciles each report with the delivered tree and accepted ADRs, rather than
treating a planning artifact as implementation evidence. Stop on missing, stale, or
contradictory evidence; return the defect to its owning track. No external submission,
push, deployment, link/archive creation, or history rewrite is authorized here.

| ID | Work item | Owner | Depends on | Status | Exit evidence |
| --- | --- | --- | --- | --- | --- |
| T08-01 | Verify Track 00–07 closure reports, delivered seams, ADR conformance, and complete assessment inventory before final work. | Primary engineering thread | T01-08, T02-07, T03-08, T04-07, T05-07, T06-08, T07-09 | Blocked | All seven Tracks marked Complete with actual closure reports; every assessment ID has an owner/evidence candidate; no unresolved contract conflict. |
| T08-02 | Rehearse clean-clone Python 3.12/locked-`uv` configure, migration, bootstrap/run, test, OpenAPI/docs, and health workflow. | Smith / implementation | T08-01 | Pending | Disposable clean-clone receipt with exact commands, resolved versions, migration state, service logs, OpenAPI/docs and health responses, and teardown target. |
| T08-03 | Reconcile all assessment and accepted-extension requirements with actual results, defect severity, and evidence locations. | Primary engineering thread | T08-01, T08-02 | Pending | Complete requirement-to-evidence matrix covers GOV-01, ENV-01…DATA-04, AUTH-01…SEC-01, BKM-01…TIME-01, QRY-01…SQL-03, EVT-01…OPS-01, API-01…QUAL-01, DEL-01…DOC-01, and FUT-01. |
| T08-04 | Author and fresh-reader review root README and supporting reader documentation from delivered facts. | Smith / implementation | T08-02, T08-03 | Pending | Setup/configure/migrate/bootstrap/run/API/test/OpenAPI/health guidance; architecture, local deployment, trade-offs, limitations, and production evolution agree with code and reports. |
| T08-05 | Prepare evidence-bounded AI-assisted-work disclosure, walkthrough/demo, and reviewer handoff materials. | Primary engineering thread | T08-03, T08-04 | Pending | Disclosure distinguishes repository evidence from owner-provided private provenance; walkthrough has reproducible selectors and expected outcomes; no private material or invented narrative. |
| T08-06 | Run final security, dependency, secret, generated-artifact, license/hygiene, and coherent-history review. | Smith / implementation | T08-02, T08-03, T08-04 | Pending | No committed secret/generated noise; ignore/lock/dependency receipt, security findings ranked, history reviewed without rewrite/squash, documentation claims checked. |
| T08-07 | Decide explicitly whether BONUS-01/BONUS-02 proceed after mandatory evidence is green. | Primary engineering thread | T08-03, T08-04, T08-05, T08-06 | Pending | Go/no-go record proves mandatory gate is green; decline leaves scope unchanged, approval defines isolated owner, acceptance evidence, and rollback/stop condition. |
| T08-08 | If and only if T08-07 approves it, implement one bounded optional seed or bonus change and re-run mandatory regressions. | Smith / implementation | T08-07 | Pending | Separate green evidence for chosen bonus, deterministic invocation, no mandatory regression, and no public history API/topology drift. |
| T08-09 | Produce final `TEST-REPORT.md`, release/handoff note, closure review, and owner-action checklist. | Primary engineering thread | T08-02, T08-03, T08-04, T08-05, T08-06, T08-07, T08-08 | Pending | Exact final commands/results, requirement traceability, severity disposition, limits, bonus disposition, and explicit owner-owned submission/link/archive step. |

T08-08 is a conditional task: a declined T08-07 records “not selected” as its
non-execution evidence, after which T08-09 may close without a product bonus.

## Deterministic edge/failure ledger

| Area | Planned proof and stop condition |
| --- | --- |
| Clean clone/toolchain | Fresh disposable clone uses Python 3.12 and `uv sync --locked`; stop on missing lock, ambient-PATH dependence, undocumented setting, or mutable install step. |
| Migration/bootstrap | Empty database upgrade and documented bootstrap use only supported commands; stop on implicit schema creation, stale migration, multi-worker conflict, or non-attributed service startup. |
| Runtime contract | `/docs`/OpenAPI, auth-protected API examples, current stats, and health are checked against actual routes; stop on documentation/schema/runtime divergence. |
| Statistics boundaries | Current stats remain correct if weekly projection is unavailable; no public history path is added; stop on any API/topology drift. |
| Requirement evidence | Reconcile every assessment ID with Track 00–07 receipts and fresh final evidence; stop on an unproven mandatory row or unsupported “pass” claim. |
| Documentation/disclosure | README, architecture/deployment, trade-offs, limitations, walkthrough, and AI disclosure derive from inspected facts; stop on a claim needing private/proprietary evidence not supplied by the owner. |
| Security/hygiene | Inspect staged/tracked files, ignore rules, config/examples/logs, lock/dependency advisories as supported, generated DB/cache/coverage artifacts, and history; stop on secret exposure or unresolved critical/high issue. |
| Optional scope | Seed or BONUS-02 begins only after explicit green go/no-go and runs full mandatory regression after change; stop on time, reliability, contract, or hygiene regression. |
| Submission boundary | Prepare an owner checklist only; stop before remote push, archive/upload, submission-link creation, deployment, or history rewrite without new authority. |

## Planned validation commands

Run only after T08-01 establishes the delivered commands and record exact environment,
paths, output summaries, endpoint selectors, and failures in `TEST-REPORT.md`. These
are planned, not passed:

```text
git clone <local-reviewed-repository> <disposable-clean-clone>
cd <disposable-clean-clone>
test "$(cat .python-version)" = "3.12"
uv python find 3.12
uv sync --locked
uv run python --version
uv lock --check
uv run alembic upgrade head
make bootstrap
uv run pytest
uv run ruff format --check .
uv run ruff check .
uv run mypy app
uv run alembic check
make check
curl --fail-with-body http://127.0.0.1:<port>/openapi.json
curl --fail-with-body http://127.0.0.1:<port>/docs
curl --fail-with-body http://127.0.0.1:<port>/health/live
curl --fail-with-body http://127.0.0.1:<port>/health/ready
git diff --check
git status --short
```

The exact bootstrap target, settings file/env names, port, test selectors, dependency
audit command, and service lifecycle procedure must be copied from the delivered
project—not guessed from this plan. Use a vetted scanner appropriate to the locked
toolchain for dependency/secret review; redact any sensitive output. Do not claim a
clean clone when uncommitted local files, a developer database, cached environment, or
owner credentials made the result possible. The rehearsal verifies the committed
Python pin; it must not create or silently repair `.python-version` in the clean clone.

## Risks, limitations, and closure threshold

The largest risks are a false sense of upstream closure, documentation that exceeds
the code, and bonus work consuming the mandatory gate. Python 3.12 availability,
dependency-audit support, and final service commands remain unknown until delivery.
FUT-01 stays a documented production-evolution path, not a deployment promise.

Close only when T08-01 through T08-07 and T08-09 have actual green evidence; T08-08
is either separately green or explicitly not selected. No critical/high defect,
secret, requirement-evidence gap, or unresolved documentation contradiction may
remain. The final note must name the owner as next actor for any submission artifact
or external action.

## Review checkpoints and commit boundary

1. Upstream closure/inventory gate; 2. clean-clone runtime rehearsal; 3. requirement
matrix and docs accuracy; 4. security/history/hygiene review; 5. explicit optional
go/no-go; 6. final report and owner handoff.

Preferred mandatory green-boundary commit: `docs: add reproducible assessment handoff`.
Any approved bonus is an isolated later green commit. Do not commit secrets, private
correspondence, credentials, databases, caches, coverage, generated artifacts, a
submission link, an external deployment configuration, or failing intermediate state.
