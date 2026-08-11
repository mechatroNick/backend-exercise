# Engineering verification guideline

## Purpose and authority

This is the shared policy for logging, automated tests, process-level verification,
evidence receipts, and track closure. [ADR-006](../.tracks/ADR/ADR-006-engineering-verification-and-closure-evidence.md)
makes it binding for Tracks 00-08. It governs how evidence is produced and recorded;
it does not change API or product semantics. The supplied assessment, accepted ADRs,
and a track SPEC's stricter rule prevail when they conflict with this guideline.

`scripts/verify-docs.sh` is documentation-only: it proves documentation integrity,
not unit, API, migration, database, log, or runtime behavior. The repository also
contains executable Tracks 01–06 and completed Track 08 work, each of which needs
its own recorded executable evidence.

## Evidence and track closure

Every executable track must provide both deterministic unit tests and a
real-process Bash harness at `scripts/verify-track-<NN>.sh`, or be invoked by a
final orchestrator that invokes that per-track harness. The harness supplements,
rather than replaces, unit, integration, contract, migration, static-analysis, and
security checks required by the track SPEC and accepted ADRs.

A test report records the exact command, exit result, relevant tool/runtime
versions, requirement selectors, artifacts inspected, cleanup result, known gaps,
and any preserved debug-artifact location. A planned, blocked, skipped, or unrun
command is never a passing result. A work item or track is **Complete** only when
its stated evidence exists and passes; **Ready**, **Pending**, and **Blocked** are
not done. A track may not close with missing executable evidence. The revived Track 07
therefore has its own deterministic and real-process harness plus a truthful report;
its earlier owner-skip remains historical context only.

## Structured logging

Application logs are JSON Lines: one valid UTF-8 JSON object per physical record,
using one centralized schema/formatter. Logs are attributable, level-appropriate,
and low-cardinality. Each event includes an event name, service or component identity,
level, UTC timestamp, logger, process identity, and execution/thread identity where
applicable. Request or event correlation identifiers are included when a request or
asynchronous flow has one. Log only aggregate, bounded operational dimensions; do
not make user IDs, URLs, bookmark text, tags, credentials, tokens, request bodies,
SQL, environment-specific filesystem paths, or raw exception text into indexed
fields. Framework and third-party application logs use the same formatter or are
deliberately disabled when equivalent application telemetry exists.

Tests capture expected events and required fields at the owning boundary, and prove
that seeded secrets and submitted-content sentinels are absent. Worker-specific
fields, services, and event names remain governed by
[ADR-004](../.tracks/ADR/ADR-004-event-driven-statistics-service.md); this guideline
does not duplicate that contract. Use levels consistently: `DEBUG` for bounded
diagnostic detail, `INFO` for expected lifecycle and state transitions, `WARNING`
for recoverable degradation, and `ERROR` for failed operations requiring attention.

The final owning request, task, thread, or process boundary logs an unexpected
exception exactly once. Its structured exception object preserves type, safe message,
ordered frames, and cause/context without capturing frame locals; intermediate layers
add safe context and re-raise without duplicate exception logs. API errors and health
responses never expose tracebacks. Formatter/redactor failure must fail closed to a
minimal schema-valid redacted record rather than plaintext or the unsafe original.

## Deterministic test layers

Every executable track maps its acceptance and edge/failure ledger to named tests.
Unit tests cover success, boundary, malformed input, dependency failure, and regression
behavior proportional to the track's risk. They isolate domain/application logic from
FastAPI, SQLite, the network, process state, and wall-clock time by injecting clocks,
repositories, publishers, and other collaborators. They do not use real sleeps or
order-dependent shared state.

When a track owns persistence, its focused integration tests use disposable databases
built by the real Alembic migration path and assert constraints, transactions,
rollbacks, ownership, and cleanup. When it owns HTTP, contract tests exercise real
request/response instances, standard errors, security, and generated OpenAPI agreement.
Concurrency and lifecycle behavior use controlled barriers, fake clocks, or explicit
manual-cycle hooks in deterministic tests; the Bash harness separately proves the
delivered process can actually start and expose the intended observable seam.

Tests must fail for a broken invariant and must not hide mandatory behavior behind
unconditional skips, expected failures, swallowed exceptions, or assertion-free smoke.
Focused tests run before the full applicable suite. Coverage is measured and recorded
as evidence, but no arbitrary percentage substitutes for requirement and edge-case
traceability.

## Real-process Bash harnesses

Each executable-track harness must:

- start with `#!/usr/bin/env bash`, `set -euo pipefail`, and an explicit safe `IFS`;
- derive the repository root from the script location, use only disposable
  directories/databases, choose a dynamic isolated port, and never delete a
  caller-supplied path;
- invoke the documented bootstrap process rather than a fake server, use bounded
  readiness polling rather than sleep as proof, and fail on bootstrap, readiness,
  assertion, timeout, or cleanup error;
- make real `curl`/HTTP requests and relevant database and structured-log
  assertions, including a seeded redaction sentinel;
- use `trap` cleanup to stop child processes and remove only verified disposable
  resources; preserve artifacts only when an explicit debug flag requests it; and
- print an evidence receipt sufficient to transfer into `TEST-REPORT.md` without
  exposing secrets or submitted content.

The harness must be portable across the documented local support matrix. It must
bound all polling, use a process group or explicit child PID management, and report
the selected port and selectors only when those values are non-sensitive. Tests
remain deterministic: injected clocks, controlled fakes, and explicit lifecycle
signals are preferred to wall-clock sleeps.

## Documentation-only verification

`bash scripts/verify-docs.sh` is the current repository-level documentation gate.
It checks the expected documentation and Track 00 artifacts, requirement and ADR
inventories, track inventory, URL-decoded local Markdown targets, trailing
whitespace, and `git diff --check`. It performs no writes and makes no runtime
claim. Its result can close a documentation work item only when recorded with the
actual command and result.
