# Track 09 branch test report

- Status: Passed (clean-source branch gate; merged-main rerun pending)
- Date: 2026-08-09
- Clean source HEAD: `c92dc353a84aa06cd6496e83543d3828910be746`
- Scope: Track 09 implementation, comprehensive clean-source verification, exact
  inherited Track 08 verification, Docker delivery, and cleanup. Merge/post-merge
  evidence and owner-only external release actions are not claimed by this receipt.

## Branch result

`bash scripts/verify-track-08.sh` and `bash scripts/verify-track-09.sh` passed from the
recorded clean committed source. No development seam, Docker skip, warning allowance,
coverage waiver, or stale historical receipt was treated as a pass. Track 07 remains
an explicit owner skip and no weekly-history implementation exists.

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

## Remaining closure action

T09-REQ-11 is not complete at this branch receipt. The primary thread must review
this closure wave, commit it, merge the branch with a merge commit to `main`, rerun
the exact Track 09 gate on the merged commit, update statuses to Complete, and verify
the final clean `main` HEAD. External push, archive, publication, deployment,
submission, or release remains owner-only and was not performed.
