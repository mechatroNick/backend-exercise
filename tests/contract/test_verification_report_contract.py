"""Terminal-report and final-harness contracts for Track 09 automation."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_HELPER = _ROOT / "scripts/verification-report.sh"
_VERIFY_SCRIPTS = (
    "verify-docs.sh",
    "verify-track-01.sh",
    "verify-track-02.sh",
    "verify-track-03.sh",
    "verify-track-04.sh",
    "verify-track-05.sh",
    "verify-track-06.sh",
    "verify-track-08.sh",
    "verify-track-09.sh",
)


def _bash(source: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", source],
        check=False,
        capture_output=True,
        text=True,
    )


def test_every_verification_script_uses_the_safe_structured_report_helper() -> None:
    helper = _HELPER.read_text(encoding="utf-8")

    assert "eval" not in helper
    assert "captured command output" in helper
    for script_name in _VERIFY_SCRIPTS:
        source = (_ROOT / "scripts" / script_name).read_text(encoding="utf-8")
        assert "set -Eeuo pipefail" in source
        assert (
            "scripts/verification-report.sh" in source
            or "script_dir}/verification-report.sh" in source
        )
        assert "verification_report_start" in source
        assert "verification_report_gate" in source
        assert "verification_report_finish" in source


@pytest.mark.parametrize(
    ("source", "expected_status", "expected_cleanup", "expected_result"),
    [
        (
            'source "$1"; verification_report_start test success; '
            "verification_report_gate selector; verification_report_summary complete; "
            "verification_report_cleanup 0 removed; verification_report_finish 0 0",
            0,
            "CLEANUP: PASS",
            "RESULT: PASS",
        ),
        (
            'source "$1"; verification_report_start test failure; '
            "verification_report_gate selector; verification_report_cleanup 0 removed; "
            "verification_report_finish 23 0",
            0,
            "CLEANUP: PASS",
            "RESULT: FAIL (exit=23)",
        ),
        (
            'source "$1"; verification_report_start test incomplete; '
            "verification_report_gate docker; verification_report_incomplete skipped; "
            "verification_report_cleanup 0 removed; verification_report_finish 86 0",
            0,
            "CLEANUP: PASS",
            "RESULT: INCOMPLETE (exit=86)",
        ),
        (
            'source "$1"; verification_report_start test cleanup-failure; '
            "verification_report_gate cleanup; verification_report_cleanup 5 retained; "
            "verification_report_finish 0 5",
            0,
            "CLEANUP: FAIL",
            "RESULT: FAIL (cleanup exit=5)",
        ),
        (
            'source "$1"; verification_report_start test incomplete-cleanup-failure; '
            "verification_report_gate docker; verification_report_incomplete skipped; "
            "verification_report_cleanup 5 retained; verification_report_finish 86 5",
            0,
            "CLEANUP: FAIL",
            "RESULT: FAIL (cleanup exit=5)",
        ),
    ],
)
def test_terminal_report_never_converts_failure_or_incomplete_to_pass(
    source: str, expected_status: int, expected_cleanup: str, expected_result: str
) -> None:
    result = _bash(source.replace('"$1"', f'"{_HELPER}"'))

    assert result.returncode == expected_status
    receipt = result.stdout + result.stderr
    assert "=== Verification report ===" in receipt
    assert "SCRIPT: test" in receipt
    assert "START: " in receipt
    assert "GATE: " in receipt
    assert expected_cleanup in receipt
    assert expected_result in receipt
    if "PASS" not in expected_result:
        assert "RESULT: PASS" not in receipt


def test_make_typecheck_runs_the_locked_mypy_and_pyright_tools() -> None:
    makefile = (_ROOT / "Makefile").read_text(encoding="utf-8")

    typecheck_target = makefile.split("typecheck:\n", maxsplit=1)[1].split(
        "\n\nmigrate:", maxsplit=1
    )[0]
    assert "$(UV) run mypy app" in typecheck_target
    assert "$(UV) run pyright" in typecheck_target


def test_docs_verifier_rejects_missing_or_surplus_markdown_eof_newlines() -> None:
    source = (_ROOT / "scripts/verify-docs.sh").read_text(encoding="utf-8")

    assert 'not contents.endswith(b"\\n")' in source
    assert 'contents.endswith(b"\\n\\n")' in source
    assert "Markdown files must end with exactly one newline" in source


def test_track09_final_harness_is_clean_source_and_imports_exact_track08_gate() -> None:
    source = (_ROOT / "scripts/verify-track-09.sh").read_text(encoding="utf-8")

    for required in (
        'git -C "${source_root}" status --porcelain=v1 --untracked-files=all',
        "clone --no-local --no-hardlinks",
        "clean clone HEAD differs from reviewed source HEAD",
        "lock --check",
        "sync --locked",
        "pip-audit --local --progress-spinner off --desc off",
        "no-dataclasses",
        "ApplicationLifecycleEvent",
        "@asynccontextmanager",
        "lifespan=",
        "pyright-locked",
        "ruff format --check .",
        "ruff check .",
        "make typecheck",
        "error::DeprecationWarning",
        "error::starlette.exceptions.StarletteDeprecationWarning",
        "coverage run --branch -m pytest -q",
        "coverage report --fail-under=100",
        "alembic downgrade base",
        "verify-docs",
        "verify-track-08 bash scripts/verify-track-08.sh",
        "final-clone-cleanliness",
        "clean clone changed during final verification",
        "TRACK09_DEVELOPMENT_STATIC",
        "TRACK09_SELF_TEST_CHILD",
        "cleanup self-test",
        "FINAL PASS: clean-source Track 09 evidence complete",
    ):
        assert required in source


def test_track09_static_seam_is_explicitly_nonzero_and_cannot_print_final_pass() -> None:
    source = (_ROOT / "scripts/verify-track-09.sh").read_text(encoding="utf-8")
    seam_start = source.index('if [[ "${development_static}" == 1 ]]; then')
    seam_end = source.index("fi\n    require_clean_source", seam_start)
    seam = source[seam_start:seam_end]

    assert "verification_report_incomplete" in seam
    assert "return 86" in seam
    assert "FINAL PASS" not in seam


def test_all_verification_scripts_have_valid_bash_syntax() -> None:
    for script_name in (*_VERIFY_SCRIPTS, "verification-report.sh"):
        result = subprocess.run(
            ["bash", "-n", str(_ROOT / "scripts" / script_name)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
