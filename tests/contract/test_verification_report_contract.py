"""Terminal-report and final-harness contracts for Track 09 automation."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_HELPER = _ROOT / "scripts/verification-report.sh"
_REPORT_VERIFIER = _ROOT / "scripts/verify-testing-reports.sh"
_TESTING_REPORT_DIR = _ROOT / ".testing_report"
_REPORT_RECEIPTS = (
    "00-contract-baseline.txt",
    "01-foundation.txt",
    "02-auth-errors.txt",
    "03-bookmark-crud.txt",
    "04-search-stats.txt",
    "05-mandatory-quality-gate.txt",
    "06-event-driven-stats.txt",
    "07-weekly-projections.txt",
    "08-final-handoff.txt",
    "09-final-cleanup-docs.txt",
)
_VERIFY_SCRIPTS = (
    "verify-docs.sh",
    "verify-testing-reports.sh",
    "verify-track-01.sh",
    "verify-track-02.sh",
    "verify-track-03.sh",
    "verify-track-04.sh",
    "verify-track-05.sh",
    "verify-track-06.sh",
    "verify-track-07.sh",
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


def _write_test_manifest(bundle: Path) -> None:
    source_head = re.search(
        r"^SOURCE_HEAD: ([0-9a-f]{40})$",
        (bundle / _REPORT_RECEIPTS[0]).read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    assert source_head is not None
    lines = [
        "# Verification report manifest",
        f"- Capture source HEAD: `{source_head.group(1)}`",
        "- Hash algorithm: `SHA-256`",
        "| Receipt | SHA-256 |",
        "| --- | --- |",
    ]
    for receipt in _REPORT_RECEIPTS:
        checksum = hashlib.sha256((bundle / receipt).read_bytes()).hexdigest()
        lines.append(f"| `{receipt}` | `{checksum}` |")
    (bundle / "MANIFEST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _copy_report_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / ".testing_report"
    bundle.mkdir()
    for receipt in _REPORT_RECEIPTS:
        shutil.copy2(_TESTING_REPORT_DIR / receipt, bundle / receipt)
    _write_test_manifest(bundle)
    return bundle


def _verify_report_bundle(bundle: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["VERIFY_TESTING_REPORTS_DIR"] = str(bundle)
    environment["VERIFY_TESTING_REPORTS_TEST_SEAM"] = "1"
    return subprocess.run(
        ["bash", str(_REPORT_VERIFIER)],
        cwd=_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
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
        "error::PendingDeprecationWarning",
        "error::starlette.exceptions.StarletteDeprecationWarning",
        "coverage run --branch -m pytest -q",
        "coverage report --fail-under=100",
        "alembic downgrade base",
        "verify-docs",
        "verify-testing-reports bash scripts/verify-testing-reports.sh",
        "inherited-track-contract",
        "for track in 01 02 03 04 05 06 07",
        "current-track07-boundary",
        "0003_weekly_stats_projections.py",
        "adr-inventory",
        "= 9",
        "verify-track-08 bash scripts/verify-track-08.sh",
        "final-clone-cleanliness",
        "clean clone changed during final verification",
        "TRACK09_DEVELOPMENT_STATIC",
        "TRACK09_SELF_TEST_CHILD",
        "cleanup self-test",
        "FINAL PASS: clean-source Track 09 evidence complete",
    ):
        assert required in source

    inherited_source = (_ROOT / "scripts" / "verify-track-08.sh").read_text(encoding="utf-8")
    for track in range(1, 8):
        assert f"bash scripts/verify-track-{track:02d}.sh" in inherited_source


def test_testing_report_verifier_declares_a_strict_tamper_evident_contract() -> None:
    source = _REPORT_VERIFIER.read_text(encoding="utf-8")

    for required in (
        "set -Eeuo pipefail",
        "MANIFEST.md must contain the 15-line checksum contract",
        "must not contain checksum-table rows beyond the ten receipts",
        "Capture\\ source\\ HEAD",
        "Hash algorithm: `SHA-256`",
        "shasum -a 256",
        "merge-base --is-ancestor",
        "VERIFY_TESTING_REPORTS_TEST_SEAM",
        "is not tracked",
        'cat-file -e "HEAD:.testing_report/${expected_file}"',
        'diff --quiet HEAD -- ".testing_report/${expected_file}"',
        "is not committed at HEAD",
        "differs from committed HEAD",
        "^RESULT: PASS$",
        "^EXIT: 0$",
        "require_exact_count '^DISPOSITION:' 0",
        "runtime .log files are forbidden",
        "absolute local /Users or /private path leaked",
        "private-key or known token pattern leaked",
        "token-like assignment leaked",
    ):
        assert required in source


def test_testing_report_verifier_accepts_a_complete_rehashed_copy(tmp_path: Path) -> None:
    result = _verify_report_bundle(_copy_report_bundle(tmp_path))

    receipt = result.stdout + result.stderr
    assert result.returncode == 0, receipt
    assert "RESULT: PASS" in receipt
    assert "committed testing-report bundle is complete" in receipt


def test_testing_report_verifier_rejects_a_receipt_changed_after_manifesting(
    tmp_path: Path,
) -> None:
    bundle = _copy_report_bundle(tmp_path)
    receipt_path = bundle / "01-foundation.txt"
    receipt_path.write_text(
        receipt_path.read_text(encoding="utf-8") + "tampered after manifest\n",
        encoding="utf-8",
    )

    result = _verify_report_bundle(bundle)

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "SHA-256 mismatch for 01-foundation.txt" in output
    assert "RESULT: PASS" not in output


def test_testing_report_verifier_rejects_an_absolute_path_even_when_rehashed(
    tmp_path: Path,
) -> None:
    bundle = _copy_report_bundle(tmp_path)
    receipt_path = bundle / "00-contract-baseline.txt"
    receipt_path.write_text(
        receipt_path.read_text(encoding="utf-8") + "leaked path: /private/unsafe\n",
        encoding="utf-8",
    )
    _write_test_manifest(bundle)

    result = _verify_report_bundle(bundle)

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "absolute local /Users or /private path leaked" in output
    assert "RESULT: PASS" not in output


def test_testing_report_verifier_rejects_the_stale_track07_skip_filename(
    tmp_path: Path,
) -> None:
    bundle = _copy_report_bundle(tmp_path)
    stale_name = "07-weekly-projections-skipped.txt"
    (bundle / "07-weekly-projections.txt").rename(bundle / stale_name)
    manifest = bundle / "MANIFEST.md"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("07-weekly-projections.txt", stale_name),
        encoding="utf-8",
    )

    result = _verify_report_bundle(bundle)

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "expected 07-weekly-projections.txt" in output
    assert "RESULT: PASS" not in output


def test_testing_report_verifier_rejects_a_track07_owner_skip_disposition(
    tmp_path: Path,
) -> None:
    bundle = _copy_report_bundle(tmp_path)
    receipt_path = bundle / "07-weekly-projections.txt"
    receipt_path.write_text(
        receipt_path.read_text(encoding="utf-8") + "DISPOSITION: SKIPPED (owner decision)\n",
        encoding="utf-8",
    )
    _write_test_manifest(bundle)

    result = _verify_report_bundle(bundle)

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "07-weekly-projections.txt must contain 0 match(es) for ^DISPOSITION:" in output
    assert "RESULT: PASS" not in output


def test_track09_pyright_inventory_matches_the_locked_toml_shape() -> None:
    source = (_ROOT / "scripts/verify-track-09.sh").read_text(encoding="utf-8")

    assert r"pyright\\[nodejs\\]==1\\.1\\.411" in source
    assert "^\\\\[tool\\\\.pyright\\\\]$" in source
    assert 'name = \\"pyright\\"' in source


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
