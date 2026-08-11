# Track 09 final test report

- Status: Ready to push — branch review, merge, and clean merged-main gate passed
- Date: 2026-08-11
- Current clean branch evidence HEAD: `69db96ea3022814629f974881af808b9fde76df6`
- Reviewed branch closure HEAD: `d45894333c1cbd655fb3775f8338e98ba8885825`
- Clean merged-main evidence HEAD: `6e92980a12b2ad1a93d6708f1272bd6fab7a5247`
- Public receipt capture source HEAD: `a9cccc29caff0d21e78835052d2174cc186b1069`
- Current scope: completed Track 07, current Track 08 integration, refreshed
  tamper-evident receipts, modernization standards, exact inherited verification,
  Docker delivery, final-clone cleanliness, and cleanup.

## Current branch result

`bash scripts/verify-track-09.sh` passed from clean committed branch HEAD `69db96e`.
The run used no development seam or Docker skip and returned `FINAL PASS`,
`CLEANUP: PASS`, and `RESULT: PASS`. It proved:

- 867 tests plus 3 subtests with `DeprecationWarning`, `PendingDeprecationWarning`,
  and Starlette deprecations treated as errors;
- 3,932 statements and 910 branches at 100% coverage;
- no application/test-helper standard-library dataclass and no demonstrated
  deprecated project API;
- Ruff, strict application mypy, locked Pyright, dependency, migration lifecycle,
  drift, documentation, report-integrity, security, and hygiene gates;
- exact Tracks 01–07 through Track 08, including real Uvicorn behavior and the full
  Track 07 projection lifecycle; and
- ordered Docker build/post-build/migrate-only/non-root/one-worker/health/JSON Lines/
  SIGTERM/removal evidence plus verified recursive cleanup.

The current `.testing_report/` manifest contains exactly ten safe public receipts.
Track 07 now records `bash scripts/verify-track-07.sh`, `RESULT: PASS`, and `EXIT: 0`;
the obsolete owner-skip receipt is absent. The strict default verifier proved every
bundle file is committed in `HEAD`, byte-matches the worktree, hashes correctly, has
valid ancestor provenance, and contains no protected paths, tokens, or private logs.

## Remaining closure boundary

Independent closure review passed, the branch was merged to `main` with non-fast-forward
merge `6e92980`, and `bash scripts/verify-track-09.sh` passed again on that clean merged
commit with the same warning-fatal 867-test/3-subtest and 100% coverage result, exact
inherited runtime/Docker evidence, final-clone cleanliness, and cleanup. T09-REQ-11 is
not yet complete because the explicitly approved external push remains. No push is
claimed by this receipt.

## Historical pre-revival receipt

- Status: Historical/superseded — preserved for the pre-revival scope
- Date: 2026-08-09
- Clean implementation evidence HEAD: `c92dc353a84aa06cd6496e83543d3828910be746`
- Clean branch closure evidence HEAD: `62780a77431e3f64db9df9f29af133fb736562c0`
- Merged main evidence HEAD: `ce16aa187a8b281873e1b290b3c826d3ad552d1c`
- Historical scope: Track 09 implementation, comprehensive clean-source verification, exact
  inherited Track 08 verification, Docker delivery, merge, post-merge verification,
  and cleanup. Owner-only external release actions are not claimed by this receipt.

The counts, commits, and outcomes below remain exact for the 2026-08-09 scope. They do
not claim the later Track 07 implementation, current Track 08 integration, refreshed
public receipt bundle, current Track 09 branch, or a new merged-main result.

## Historical final result

`bash scripts/verify-track-08.sh` and `bash scripts/verify-track-09.sh` passed from the
recorded clean committed source. No development seam, Docker skip, warning allowance,
coverage waiver, or stale historical receipt was treated as a pass. At that historical
source, Track 07 remained an explicit owner skip and no weekly-history implementation
existed. The branch was
merged with merge commit `ce16aa1`, and the exact Track 09 gate passed again on that
clean merged `main` commit.

## Environment and locked tools

| Tool | Verified version |
| --- | --- |
| Python | 3.12.12 |
| uv | 0.9.15 |
| pytest | 9.1.1 |
| coverage | 7.15.3 |
| Ruff | 0.15.22 |
| mypy | 2.3.0 |
| Pyright | 1.1.411 |
| Alembic | 1.19.0 |
| Uvicorn | 0.51.0 |

`uv lock --check`, locked sync, and the local dependency advisory passed. The local
non-PyPI `bookmarks-api` distribution remains the only dependency without registry
license metadata and requires repository-owner review; it is not a vulnerability or
assessment failure.

## Verification receipt

| Gate | Actual result |
| --- | --- |
| Documentation | `verify-docs` passed with 43 requirement IDs, eight accepted ADRs, ten tracks, resolved links, and exact Markdown EOF newlines. |
| Modernization inventories | No standard-library dataclass remains; lifecycle enum and current lifespan source contracts passed. |
| Static analysis | Ruff format/check, strict application mypy, and locked standard-mode Pyright passed with zero diagnostics. |
| Warning gates | Full tests passed with both general and Starlette deprecations treated as errors. |
| Full regression | 743 tests and 3 subtests passed. |
| Coverage | 2,953 statements and 618 branches, 100%. |
| API and model contracts | OpenAPI 3.1 remained 10 operations / 45 status pairs; Pydantic frozen/mutable, invariant, equality/hash, cursor, event, rate, seed, and statistics edges passed. |
| Migrations and seed | Upgrade, downgrade, re-upgrade, `alembic check`, explicit-target seed, repeat seed, and exact idempotent state passed. |
| Runtime and logs | Real one-worker Uvicorn passed health, auth/ownership, CRUD/filter/cursor/stats/rate flows, JSON Lines schema/redaction, lifecycle ordering, and graceful TERM. |
| Upstream evidence | Exact Tracks 01–06 passed. Their newer PLANs were byte/mode exact after only the authorized `docs/` to `.docs/` link migration. |
| Track 08 | Exact clean-clone Track 08 passed, including its 100 focused bonus tests and all inherited evidence. |
| Docker | Build preceded post-build contract; migrate-only, UID 10001, one worker, live/ready/health, JSON Lines, SIGTERM, removal, and named-volume cleanup passed. |
| Failure and cleanup | Injected-failure reporting/cleanup contracts passed; no disposable clone, process, image, container, or volume remained. |
| Final clone | Track 09 reported final-clone cleanliness and `RESULT: PASS`. |

Protected values and private child receipts were kept ephemeral. The standalone
terminal output retained only safe selectors, counts, versions, and cleanup results.

## Incremental implementation commits

| Commit | Outcome |
| --- | --- |
| `a915400` | Authorized Track 09 and ADR-008. |
| `ecb225c` | Modernized lifecycle and type checks. |
| `bc728b6` | Moved the nine-file durable reader tree to `.docs/`. |
| `d1ac384` | Added the public httpx2/Schemathesis compatibility adapter. |
| `a9bdf15` | Replaced internal/test-helper dataclasses with strict Pydantic models. |
| `364ad0d` | Recorded implementation checkpoints. |
| `93ee83a` | Added standalone verification reports and Track 09 automation. |
| `5e8fe42` | Made root README the SDD-first reader guide. |
| `b113963` | Corrected locked Pyright configuration validation. |
| `4db9410` | Kept additive helper evidence outside the frozen mandatory manifest. |
| `a4992d5` | Made upstream path-migration provenance byte/mode exact and fail closed. |
| `c92dc35` | Kept provenance fixtures compatible with documentation-path hygiene. |

## Historical external action boundary

For the historical version 1.0 scope, T09-REQ-11 was complete: its independently
reviewed branch closure was committed, merged with a merge commit to `main`, and its
exact final gate passed on that clean merged commit. This statement does not close the
current version 1.1 Track 07 integration refresh. External archive, publication,
deployment, submission, or release remained owner-only and was not performed.
