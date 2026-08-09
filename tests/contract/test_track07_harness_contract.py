"""Static safety contract for the Track 07 weekly-projection evidence harness."""

import ast
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_HARNESS = _ROOT / "scripts" / "verify-track-07.sh"


def _source() -> str:
    return _HARNESS.read_text(encoding="utf-8")


def test_track07_harness_is_strict_protected_and_reports_failures() -> None:
    source = _source()
    for required in (
        "set -Eeuo pipefail",
        "IFS=$'\\n\\t'",
        "umask 077",
        "verification-report.sh",
        "verification_report_start",
        "verification_report_gate",
        "verification_report_cleanup",
        "verification_report_finish",
        'mktemp -d "${prefix}XXXXXX"',
        '"${work}" == "${prefix}"*',
        "rm -rf --",
        "descendants",
        "kill -TERM",
        "kill -KILL",
        'wait "${pid}"',
        "TRACK07_SELF_TEST",
        "exit 97",
        "cleanup self-test did not preserve its nonzero status",
    ):
        assert required in source
    assert "RESULT: PASS" not in source
    assert "eval " not in source


def test_cleanup_status_is_not_masked_when_the_body_succeeded() -> None:
    source = _source()
    expected = '''if [[ "${original}" != 0 ]]; then
        exit "${original}"
    fi
    exit "${cleanup_status}"'''
    assert expected in source


def test_track07_harness_requires_exact_inherited_and_quality_gates() -> None:
    source = _source()
    for required in (
        "bash scripts/verify-track-06.sh",
        "tests/integration/test_projection_schema.py",
        "tests/integration/test_projection_baseline.py",
        "tests/integration/test_projection_lifecycle.py",
        "tests/integration/test_projection_corrections.py",
        "tests/integration/test_projection_repository.py",
        "tests/integration/test_bookmark_stats_dirty.py",
        "tests/unit/test_projection_service.py",
        "tests/unit/test_projection_lifecycle.py",
        "tests/unit/test_stats_refresher.py",
        "tests/unit/test_health.py",
        "skipped|xfailed|xpassed|deselected",
        "sync --locked",
        "ruff format --check .",
        "ruff check .",
        "mypy app",
        "pyright app",
        "coverage run --branch -m pytest -q",
        "coverage report --fail-under=100",
        "make check",
        "bash scripts/verify-docs.sh",
        "git diff --check",
        "alembic downgrade base",
        "alembic upgrade head",
        "alembic check",
    ):
        assert required in source


def test_track07_harness_has_dynamic_one_worker_private_runtime_phases() -> None:
    source = _source()
    for required in (
        'listener.bind(("127.0.0.1", 0))',
        "--workers 1",
        "--no-access-log",
        "/health/live",
        "/health/ready",
        "/openapi.json",
        "len(operations) == 10",
        "== 45",
        "public history surface appeared",
        "STATS_PROJECTION_ENABLED",
        "safe disposable historic timestamp preparation",
        "source_generation=0",
        "revision, supersedes_id",
        "dual completion",
        "restart idempotence",
        "disabled retention/fabrication contract",
        "incompatible durable state preparation",
        "auto-rewritten",
        "strict JSON Lines",
        "sensitivities.txt",
        "bookmark-stats-refresher",
        "Authorization",
        "content_hash",
        "payload",
    ):
        assert required in source
    assert "--port 8000" not in source
    assert "localhost:" not in source


def test_track07_harness_is_executable_bash_syntax() -> None:
    assert _HARNESS.exists()
    assert _HARNESS.stat().st_mode & 0o111
    result = subprocess.run(
        ["bash", "-n", str(_HARNESS)], check=False, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_track07_harness_embedded_python_is_syntactically_valid() -> None:
    lines = _source().splitlines()
    parsed_blocks = 0
    index = 0
    while index < len(lines):
        if "<<'PY'" not in lines[index]:
            index += 1
            continue
        start = index + 1
        try:
            end = lines.index("PY", start)
        except ValueError as error:
            raise AssertionError(f"unclosed Python heredoc after line {index + 1}") from error
        ast.parse("\n".join(lines[start:end]), filename=f"{_HARNESS}:{start + 1}")
        parsed_blocks += 1
        index = end + 1
    assert parsed_blocks == 11


def test_correction_postcondition_uses_the_open_http_client() -> None:
    source = _source()
    correction = source.split(" correction <<'PY'", maxsplit=1)[1].split("\nPY", maxsplit=1)[0]
    with_line = correction.index("with httpx.Client")
    stats_line = correction.index('stats = client.get("/api/bookmarks/stats"', with_line)
    final_database_line = correction.rindex("with sqlite3.connect")
    assert stats_line < final_database_line
    assert "\n    stats = None" in correction
    assert '\n        stats = client.get("/api/bookmarks/stats"' in correction
