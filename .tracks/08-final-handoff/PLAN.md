# Track 08 plan: final hardening, documentation, and assessment handoff

- Specification: [SPEC.md](SPEC.md), version 1.3
- Governing records: `docs/ASSESSMENT.md`, `docs/SOLUTION-DESIGN.md`, `docs/DELIVERY-PLAN.md`, ADR-001 through ADR-007
- Status: Complete
- Active item: None

## Dependency gate and intent check

Before any Track 08 implementation, the primary thread verifies Track 00 is Complete,
Tracks 01–06 are Complete with their actual `TEST-REPORT.md` closure artifacts, and
Track 07 is explicitly Skipped with no weekly projection artifacts.
It reconciles each report with the delivered tree and accepted ADRs (including ADR-006), rather than
treating a planning artifact as implementation evidence. Stop on missing, stale, or
contradictory evidence; return the defect to its owning track. No external submission,
push, deployment, link/archive creation, or history rewrite is authorized here.

| ID | Work item | Owner | Depends on | Status | Exit evidence |
| --- | --- | --- | --- | --- | --- |
| T08-01 | Verify Track 00–06 closure reports, the Track 07 skip record/absence boundary, delivered seams, ADR conformance, and complete assessment inventory before final work. | Primary engineering thread | T01-08, T02-07, T03-08, T04-07, T05-07, T06-08 | Complete | `EVIDENCE-MATRIX.md`; every Track 00–06 report Passed/plan Complete; Track 07 skip and absence verified; 43 unique IDs inventoried as delivered, skipped, partial, or open; docs gate passed; no unresolved upstream contract conflict. |
| T08-02 | Deliver `scripts/verify-track-08.sh` and rehearse its clean-clone Python 3.12/locked-`uv` configure, migration, bootstrap/run, full test, OpenAPI/docs, and health workflow. | Smith / implementation | T08-01 | Complete | Passing clean-source receipt at `ff32511e9cc0e2df8d7681e2c16b3dddb579faae`; exact commands, runtime selectors, and cleanup are in `TEST-REPORT.md`. |
| T08-03 | Reconcile all assessment and accepted-extension requirements with actual results, defect severity, and evidence locations. | Primary engineering thread | T08-01, T08-02 | Complete | Final matrix and report reconcile all 43 IDs, including Track 07 skipped rows. |
| T08-04 | Author and fresh-reader review root README and supporting reader documentation from delivered facts. | Smith / implementation | T08-02, T08-03 | Complete | The pre-closure reader package was verified by the clean-source harness; closure documents received a subsequent documentation-verifier pass. |
| T08-05 | Prepare evidence-bounded AI-assisted-work disclosure, walkthrough/demo, and reviewer handoff materials. | Primary engineering thread | T08-03, T08-04 | Complete | Disclosure, walkthrough, and release handoff are recorded without private material. |
| T08-06 | Run final security, dependency, secret, generated-artifact, license/hygiene, JSON Lines, and coherent-history review. | Smith / implementation | T08-02, T08-03, T08-04 | Complete | Audit/hygiene, JSON Lines, and cleanup passed; local project license metadata remains owner review. |
| T08-07 | Establish the mandatory-green bonus preflight, exact acceptance contracts, isolation order, and rollback/stop conditions for all bonus work. | Primary engineering thread | T08-03, T08-04, T08-05, T08-06 | Complete | ADR-007, preflight, and final clean-source evidence passed. |
| T08-08 | Implement all bonus work in isolated green checkpoints: deterministic seed data, Docker setup, rate limiting, and cursor pagination; then rerun the mandatory/full final harness. | Smith / implementation | T08-07 | Complete | Checkpoints and final full harness passed; no weekly-history drift. |
| T08-09 | Produce final `TEST-REPORT.md`, release/handoff note, closure review, and owner-action checklist. | Primary engineering thread | T08-02, T08-03, T08-04, T08-05, T08-06, T08-07, T08-08 | Complete | `TEST-REPORT.md`, handoff, closure evidence, and owner-only external-action boundary are recorded. |

T08-08 is mandatory under the current owner decision. If a bonus threatens correctness
or security, stop and fix/reframe it; do not silently mark it not selected or close
Track 08 without it.

## Shared completion gate

The [engineering verification guideline](../../docs/ENGINEERING-VERIFICATION-GUIDELINE.md)
and [ADR-006](../ADR/ADR-006-engineering-verification-and-closure-evidence.md) apply
to Track 08 without changing its status, task IDs/dependencies, mandatory bonus
boundary, FUT-01/documentation-only boundary, no-public-history boundary, or the
repository owner's exclusive submission authority. Planned, Ready, Blocked, skipped,
or unrun work is not done. T08-09 may mark Track 08 Complete only after current,
recorded, passing evidence for every required upstream closure and final check, with
no secret, unresolved critical/high defect, dirty generated artifact, orphan process,
or cleanup failure. T08-08 requires isolated green checkpoints and a new
mandatory/full final-harness receipt after the combined bonus set.

[ADR-007](../ADR/ADR-007-local-rate-limiting-and-cursor-pagination.md) is the binding
rate-limit and cursor contract for T08-08; implementation may not weaken its isolation,
compatibility, bounded-state, signing, or fixed-error requirements.

`scripts/verify-track-08.sh` passed as the final clean-clone real
automation/orchestrator at the recorded clean source HEAD. Its design required it to
verify the committed Python 3.12.12 pin and locked `uv` without ambient database,
credentials, or mutable repair; invoke `bash scripts/verify-docs.sh` and every exact
delivered `bash scripts/verify-track-01.sh` through `bash scripts/verify-track-06.sh`
in dependency order, directly or through a named in-repo orchestrator whose
implementation demonstrably invokes each exact harness. Equivalent selectors cannot
replace them. It records every exact command/selector, exit result, report/plan/cited-
commit provenance and ancestry, inspected artifact, and cleanup result; missing,
contradictory, skipped, unrun, or
nonzero evidence fails. It must run the actual migration, bootstrap, and
server flows plus the complete deterministic unit, integration, and contract suite;
exercise OpenAPI, `/docs`, and delivered health/walkthrough selectors; and audit JSON
Lines schema, redaction, and exactly-once exception ownership. It must also perform
the delivered security/dependency/secret/generated-artifact/hygiene checks and cleanup.
It fails if any required harness is skipped or unrun, a required `TEST-REPORT.md` is
missing or provenance-invalid, a secret or unresolved critical/high defect is found,
a generated artifact is dirty, an orphan process remains, or cleanup fails. It must never push,
archive, create a link, upload, deploy, or submit externally.

## Deterministic edge/failure ledger

| Area | Planned proof and stop condition |
| --- | --- |
| Clean clone/toolchain | `scripts/verify-track-08.sh` starts from a verified disposable clone, uses Python 3.12 and `uv sync --locked`, and has no ambient database or credentials; stop on missing lock, ambient-PATH dependence, undocumented setting, or mutable install step. |
| Upstream automation | Invoke `bash scripts/verify-docs.sh` and every exact delivered `bash scripts/verify-track-01.sh` through `bash scripts/verify-track-06.sh` directly, or a named in-repo orchestrator demonstrably invoking each exact harness; verify Track 07's skip/absence contract; record command/selector, exit, report/plan/cited-commit provenance and ancestry, inspected artifact, and cleanup result. Stop on missing/contradictory/unrun/nonzero evidence or failed cleanup; equivalent selectors cannot replace harnesses. |
| Migration/bootstrap | Empty database upgrade and documented bootstrap/server flow use only supported commands; stop on implicit schema creation, stale migration, multi-worker conflict, orphan process, or non-attributed service startup. |
| Runtime contract | `/docs`/OpenAPI, auth-protected API examples, current stats, and health are checked against actual routes; stop on documentation/schema/runtime divergence. |
| Statistics boundaries | Current stats remain correct without weekly projections; no weekly tables/consumer or public history path is added; stop on accidental Track 07 implementation. |
| Requirement evidence | Reconcile every assessment ID with Track 00–06 receipts, the Track 07 skip record, and fresh final evidence; stop on an unproven selected row or unsupported “pass” claim. |
| Documentation/disclosure | README, architecture/deployment, trade-offs, limitations, walkthrough, and AI disclosure derive from inspected facts; stop on a claim needing private/proprietary evidence not supplied by the owner. |
| Deterministic proof | Record focused and full deterministic-suite commands/results; fail required skip/xfail/deselection/alternate-selector hiding/swallowed failure/assertion-free smoke. Final process evidence supplements each track-owned deterministic proof. |
| Security/hygiene | Inspect staged/tracked files, ignore rules, config/examples/logs, lock/dependency advisories as supported, generated DB/cache/coverage artifacts, full JSON Lines/redaction/exception ownership/fail-closed formatter behavior, and history; stop on secret exposure, dirty generated artifact, or unresolved critical/high issue. |
| Bonus scope | After mandatory green, implement deterministic seed data, Docker, rate limiting, and cursor pagination in isolated checkpoints. Prove idempotent/safe seed behavior, container migration/start/health/cleanup, deterministic 429 policy/isolation, and cursor stability/tamper/boundary behavior. Re-run the full final harness after all four; stop and correct any reliability, contract, security, or hygiene regression. |
| Submission boundary | Prepare an owner checklist only; stop before remote push, archive/upload, submission-link creation, deployment, or history rewrite without new authority. |

## Historical planned validation commands (fulfilled by the final receipt)

This preserved planning ledger shows the commands anticipated after T08-01. The
actual passing selectors, environment, summaries, and cleanup evidence are recorded
in `TEST-REPORT.md`:

```text
git clone <local-reviewed-repository> <disposable-clean-clone>
cd <disposable-clean-clone>
test "$(cat .python-version)" = "3.12.12"
uv python find 3.12.12
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
bash scripts/verify-track-08.sh
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
`scripts/verify-track-08.sh` is the recorded final entry point: it must invoke
`bash scripts/verify-docs.sh` and every exact delivered `bash scripts/verify-track-01.sh`
through `bash scripts/verify-track-06.sh` itself, or a named in-repo orchestrator whose
implementation demonstrably invokes each exact harness; no equivalent selector can
replace them. It retains every command/selector, exit result, report/plan/cited-commit
provenance and ancestry, inspected artifact, and cleanup receipt; records focused and
full deterministic-suite commands/results; rejects required skip/xfail/deselection/alternate-selector hiding/
swallowed failures/assertion-free smoke; and runs migration/bootstrap/server,
JSON-Lines/security/dependency/hygiene, and cleanup checks. It cannot accept unrun
evidence as pass or perform an owner-only external action.

## Risks, limitations, and closure threshold

The largest closure risks were a false sense of upstream completion, documentation
that exceeded the code, and bonus work consuming the mandatory gate. The final
clean-source receipt resolved the toolchain, dependency-audit, and service-command
unknowns. FUT-01 remains a documented production-evolution path, not a deployment
promise.

Close only when T08-01 through T08-09 have actual green evidence, including all four
bonus checkpoints and the combined regression. No critical/high defect,
secret, requirement-evidence gap, or unresolved documentation contradiction may
remain. The final note must name the owner as next actor for any submission artifact
or external action.

## Review checkpoints and commit boundary

1. Upstream closure/inventory gate; 2. clean-clone runtime rehearsal; 3. requirement
matrix and docs accuracy; 4. security/history/hygiene review; 5. bonus preflight and
four isolated bonus checkpoints; 6. combined final regression and owner handoff.

Preferred mandatory green-boundary commit: `docs: add reproducible assessment handoff`.
Each bonus is an isolated later green commit. Do not commit secrets, private
correspondence, credentials, databases, caches, coverage, generated artifacts, a
submission link, an external deployment configuration, or failing intermediate state.
