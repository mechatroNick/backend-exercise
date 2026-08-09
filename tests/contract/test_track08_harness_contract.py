"""Static contracts for the final clean-clone Track 08 evidence harness."""

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def _harness() -> str:
    return (_ROOT / "scripts/verify-track-08.sh").read_text(encoding="utf-8")


def test_docs_migration_contract_preserves_fastapi_docs_route() -> None:
    docs_verifier = (_ROOT / "scripts/verify-docs.sh").read_text(encoding="utf-8")
    harness = _harness()

    for required in (
        ".docs must be a real documentation directory",
        "docs compatibility directory or symlink must not exist",
        "historical_literal_docs_paths",
        "FastAPI's /docs route",
        ".docs/ASSESSMENT.md",
    ):
        assert required in docs_verifier
    assert harness.count("../../docs/") == 2
    permitted_historical_paths_removed = harness.replace("../../docs/", "")
    assert "docs/" not in permitted_historical_paths_removed.replace(".docs/", "")
    assert 'for path in ("/health/live", "/health/ready", "/docs"):' in harness


def test_track08_harness_is_strict_clean_clone_orchestration() -> None:
    source = _harness()

    for required in (
        "set -Eeuo pipefail",
        "IFS=$'\\n\\t'",
        "umask 077",
        'git -C "${source_root}" status --porcelain=v1 --untracked-files=all',
        'git -C "${source_root}" clone --no-local --no-hardlinks',
        "clean clone HEAD differs from reviewed source HEAD",
        'tr -d \'[:space:]\' < "${clone_root}/.python-version")" == 3.12.12',
        "python find 3.12.12",
        "sys.version_info[:3]",
        "lock --check",
        "sync --locked",
        "pip-audit --local --progress-spinner off --desc off",
        "PyPA/PyPI known-vulnerability data",
        "importlib import metadata",
        "License-Expression",
        "unknown_license_count",
        "unknown_license_names",
        "No known vulnerabilities found",
        "bookmarks-api dependency-not-found skip",
        "TRACK08_SELF_TEST_CHILD",
        "scripts/verification-report.sh",
        "verification_report_start",
        "verification_report_cleanup",
        "verification_report_finish",
        'export BUILDX_CONFIG="${workspace}/buildx"',
        "cleanup self-test",
        "signal_tree",
        "capture_process_tree",
        "captured_processes",
        "captured_survivor_count",
        'kill -TERM "${server_pid}"',
        "Uvicorn supervisor TERM, bounded captured-process wait, recursive KILL fallback",
        "no private workspace remained",
        ".docs/WALKTHROUGH.md",
        ".docs/AI-ASSISTED-WORK.md",
        ".docs/RELEASE-HANDOFF.md",
    ):
        assert required in source


def test_track08_harness_invokes_exact_required_evidence_and_quality_gates() -> None:
    source = _harness()

    assert "run_private verify-docs bash scripts/verify-docs.sh" in source
    for track in range(1, 7):
        assert (
            f"run_private verify-track-{track:02d} bash scripts/verify-track-{track:02d}.sh"
            in source
        )
    for required in (
        "coverage run --branch -m pytest -q",
        "coverage report --fail-under=100",
        "skipped|xfailed|xpassed|deselected",
        "run_bonus_focus",
        "bonus-focused",
        "rg -e '[0-9]+ passed'",
        "receipt: command=",
        "exit=0",
        "tests/contract/test_docker_delivery.py",
        "tests/integration/test_seed.py",
        "tests/unit/test_rate_limit.py",
        "tests/integration/test_rate_limit_routes.py",
        "tests/contract/test_rate_limit_openapi.py",
        "tests/unit/test_bookmark_pagination.py",
        "tests/unit/test_bookmark_dependencies.py",
        "tests/integration/test_cursor_pagination.py",
        "focused bonus selector:",
        "alembic downgrade base",
        "alembic-reupgrade-empty",
        "python -m app.seed",
        "seed-second",
        "app.main:create_app --factory",
        'exec "${uv_command}" run uvicorn app.main:create_app --factory',
        "--workers 1",
        "/health/live",
        "/health/ready",
        "/openapi.json",
        "/docs",
        'document.get("openapi") != "3.1.0"',
        "len(operations) != 10",
        "!= 45",
        'get("BearerAuth")',
        '"X-Next-Cursor"',
        "limited_operations",
        "invalid_cursor",
        "rate_limited",
        "Retry-After",
        "Track 07 owner-skipped disposition and absence boundary; exit=0",
        "assert_upstream_provenance",
        "merge-base --is-ancestor",
        "cat-file -e",
        "valid_cited_commit_count",
        "Passed/Complete/provenance chain and current exact harness compatibility exit=0",
        "git diff --check",
        "ls-files",
        "grep -I -q -E",
    ):
        assert required in source
    assert "assert_report_freshness" not in source


def test_track08_provenance_allows_only_the_authorized_docs_path_migration() -> None:
    source = _harness()

    assert "plan-ancestor-of-report" in source
    assert "path-only-docs-migration-after-report" in source
    assert 'source.replace(b"../../docs/", b"../../.docs/")' in source
    assert 'cmp -s -- "${migrated_plan}" "${committed_plan}"' in source
    assert '"${historic_tree}" == "${committed_tree}"' in source
    assert "changed after its report beyond the authorized docs-path migration" in source
    assert "mode or object type changed after its report" in source
    assert "rg -E '[0-9]+ passed'" not in source
    assert 'signal_tree "${server_pid}" TERM' not in source
    assert 'exercise_runtime "${runtime_port}"\n    stop_server\n    audit_runtime_logs' in source


def test_track08_path_only_provenance_guard_is_byte_and_mode_exact(tmp_path: Path) -> None:
    source = _harness()
    function_start = source.index("assert_path_only_docs_migration() {")
    function_end = source.index("\n}\n\nassert_upstream_provenance()", function_start) + 2
    function_source = source[function_start:function_end]
    shell = (
        "set -Eeuo pipefail\n"
        "fail() { printf 'FAIL: %s\\n' \"$*\" >&2; return 1; }\n"
        f"{function_source}\n"
        'assert_path_only_docs_migration "$1" "$2" "$3" PLAN.md "$4" "$5"\n'
    )

    def git(repository: Path, *arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def commit(repository: Path, message: str) -> str:
        git(repository, "add", "PLAN.md")
        git(repository, "commit", "-m", message)
        return git(repository, "rev-parse", "HEAD")

    def invoke(
        repository: Path, report: str, plan: str, label: str
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "bash",
                "-c",
                shell,
                "track08-provenance-test",
                str(repository),
                report,
                plan,
                str(tmp_path / label),
                sys.executable,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    repository = tmp_path / "repository"
    repository.mkdir()
    git(repository, "init", "-q")
    git(repository, "config", "user.name", "Track 08 Test")
    git(repository, "config", "user.email", "track08@example.invalid")
    plan_path = repository / "PLAN.md"
    plan_path.write_bytes(b"Guide: ../../docs/README.md\n")
    report_commit = commit(repository, "historical plan")

    plan_path.write_bytes(b"Guide: ../../.docs/README.md\n")
    exact_commit = commit(repository, "exact path migration")
    assert invoke(repository, report_commit, exact_commit, "exact").returncode == 0

    plan_path.write_bytes(b"Guide: ../../.docs/README.md\nextra\n")
    content_commit = commit(repository, "extra content")
    content_result = invoke(repository, report_commit, content_commit, "content")
    assert content_result.returncode != 0
    assert "beyond the authorized docs-path migration" in content_result.stderr

    plan_path.write_bytes(b"Guide: ../../.docs/README.md")
    newline_commit = commit(repository, "remove terminal newline")
    newline_result = invoke(repository, report_commit, newline_commit, "newline")
    assert newline_result.returncode != 0
    assert "beyond the authorized docs-path migration" in newline_result.stderr

    plan_path.write_bytes(b"Guide: ../../.docs/README.md\n")
    plan_path.chmod(0o755)
    mode_commit = commit(repository, "change file mode")
    mode_result = invoke(repository, report_commit, mode_commit, "mode")
    assert mode_result.returncode != 0
    assert "mode or object type changed after its report" in mode_result.stderr

    missing_repository = tmp_path / "missing"
    missing_repository.mkdir()
    git(missing_repository, "init", "-q")
    git(missing_repository, "config", "user.name", "Track 08 Test")
    git(missing_repository, "config", "user.email", "track08@example.invalid")
    missing_plan = missing_repository / "PLAN.md"
    missing_plan.write_bytes(b"Guide: ../../.docs/README.md\n")
    missing_report = commit(missing_repository, "already migrated")
    missing_plan.write_bytes(b"Guide: ../../.docs/README.md\nchanged\n")
    missing_current = commit(missing_repository, "later change")
    missing_result = invoke(
        missing_repository, missing_report, missing_current, "missing-historical"
    )
    assert missing_result.returncode != 0
    assert "lacks the authorized historical docs path" in missing_result.stderr

    git(repository, "checkout", "-q", "-b", "report-branch", report_commit)
    plan_path.write_bytes(b"Guide: ../../docs/README.md\nreport branch\n")
    diverged_report = commit(repository, "report branch")
    git(repository, "checkout", "-q", "-b", "plan-branch", report_commit)
    plan_path.write_bytes(b"Guide: ../../.docs/README.md\n")
    diverged_plan = commit(repository, "plan branch")
    diverged_result = invoke(repository, diverged_report, diverged_plan, "diverged")
    assert diverged_result.returncode != 0
    assert "provenance are not ordered" in diverged_result.stderr


def test_track08_harness_requires_real_docker_except_for_labelled_incomplete_development_seam() -> (
    None
):
    source = _harness()

    for required in (
        "TRACK08_SKIP_DOCKER",
        "DEVELOPMENT INCOMPLETE: Docker execution explicitly skipped",
        "Docker is required for final Track 08 evidence",
        "docker info",
        "docker build --tag",
        "migrate-only",
        "docker_migrate_container",
        "wait_for_docker_removal",
        "docker container inspect",
        "seq 1 100",
        "removal visibility wait",
        "docker_env_file",
        '--env-file "${docker_env_file}"',
        'chmod 600 "${docker_env_file}"',
        "seq 1 400",
        'docker exec "${docker_container}" id -u',
        "docker stop --timeout 10",
        "Docker JSON Lines schema and shutdown lifecycle audit passed",
        'docker logs "${docker_container}"',
        "Docker container remained after SIGTERM",
        "development seam was used; this is not a final Track 08 receipt",
        "FINAL PASS: clean-clone Track 08 evidence complete",
    ):
        assert required in source
    assert '--env "JWT_SECRET=' not in source
    docker_verification = source[
        source.index("wait_for_docker_removal") : source.index("run_cleanup_self_test")
    ]
    assert "docker inspect" not in docker_verification


def test_track08_runs_the_exact_docker_contract_after_build_before_runtime() -> None:
    source = _harness()

    build = source.index('docker build --tag "${docker_image}"')
    post_build_contract = source.index(
        'run_private docker-contract-post-build "${uv_command}" run pytest -q '
        "tests/contract/test_docker_delivery.py"
    )
    runtime = source.index('docker run --name "${docker_migrate_container}"')

    assert build < post_build_contract < runtime
    assert "phase=post-docker-build; exit=0" in source
    assert "Docker command is unavailable" in source
    assert "Docker daemon is unavailable" in source


def test_track08_harness_discriminates_live_filter_and_patch_contracts() -> None:
    source = _harness()

    for required in (
        '"Needle title"',
        '"alpha-tag"',
        '"from": "2999-01-01"',
        "from datetime import datetime",
        "nonce = secrets.token_hex(10)",
        '"email": f"{label}-{nonce}@example.com"',
        "runtime safe-driver failed",
        "query filter did not return the exact owner item",
        "tag filter did not return the exact owner item",
        "future created-from filter was ignored",
        "PATCH response did not preserve the documented title/timestamp contract",
        "PATCH response did not advance updated_at",
        "safe_runtime_lifecycle_counts",
        "runtime lifecycle audit failure:",
        "invalid_json_lines",
        "runtime JSON Lines audit failed",
    ):
        assert required in source
    assert "nonce = secrets.token_urlsafe" not in source
    assert '"email": f"{label}-{nonce}@example.test"' not in source
    assert 'password = f"Track08-{secrets.token_urlsafe(24)}"' in source
