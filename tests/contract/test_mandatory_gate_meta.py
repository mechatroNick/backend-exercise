"""Subprocess evidence for the mandatory-gate plugin's failure modes."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_CONTRACT_DIR = Path(__file__).parent
_PLUGIN = _CONTRACT_DIR / "mandatory_gate.py"


def _run_gate(
    tmp_path: Path, source: str, manifest: str, *arguments: str
) -> subprocess.CompletedProcess[str]:
    """Run a private pytest process with only a copied mandatory-gate plugin."""
    shutil.copy2(_PLUGIN, tmp_path / "mandatory_gate.py")
    (tmp_path / "mandatory-nodeids.txt").write_text(manifest, encoding="utf-8")
    (tmp_path / "test_target.py").write_text(source, encoding="utf-8")
    environment = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "mandatory_gate",
            "--mandatory-gate",
            "--strict-config",
            "--strict-markers",
            *arguments,
            "test_target.py",
        ],
        check=False,
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
    )


_PASSING_SOURCE = """\
import pytest


@pytest.mark.mandatory
def test_target():
    assert True
"""
_TARGET_NODEID = "test_target.py::test_target\n"


@pytest.mark.mandatory
def test_gate_accepts_an_exact_manifest_and_passing_call(tmp_path: Path) -> None:
    result = _run_gate(tmp_path, _PASSING_SOURCE, _TARGET_NODEID)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.mandatory
def test_gate_rejects_missing_extra_and_deselected_manifest_nodes(tmp_path: Path) -> None:
    cases = (
        ("test_target.py::test_other\n", (), "mandatory node IDs differ"),
        (_TARGET_NODEID + "test_target.py::test_other\n", (), "mandatory node IDs differ"),
        (_TARGET_NODEID, ("-k", "not test_target"), "mandatory node was deselected"),
    )
    for manifest, arguments, message in cases:
        result = _run_gate(tmp_path, _PASSING_SOURCE, manifest, *arguments)
        assert result.returncode == pytest.ExitCode.USAGE_ERROR
        assert message in result.stderr


@pytest.mark.mandatory
def test_gate_rejects_collection_time_masking_markers(tmp_path: Path) -> None:
    cases = (
        "@pytest.mark.skip",
        "@pytest.mark.skipif(True, reason='masked')",
        "@pytest.mark.xfail(reason='masked')",
    )
    for marker in cases:
        source = f"""\
import pytest


@pytest.mark.mandatory
{marker}
def test_target():
    assert True
"""
        result = _run_gate(tmp_path, source, _TARGET_NODEID)
        assert result.returncode == pytest.ExitCode.USAGE_ERROR
        assert "mandatory node has a masking marker" in result.stderr


@pytest.mark.mandatory
@pytest.mark.parametrize(
    "statement",
    ("pytest.skip('dynamic')", "pytest.xfail('dynamic')"),
)
def test_gate_rejects_runtime_dynamic_skip_and_xfail(tmp_path: Path, statement: str) -> None:
    source = f"""\
import pytest


@pytest.mark.mandatory
def test_target():
    {statement}
"""
    result = _run_gate(tmp_path, source, _TARGET_NODEID)
    assert result.returncode == pytest.ExitCode.TESTS_FAILED
    assert "mandatory test skipped or xfailed during execution" in result.stdout


@pytest.mark.mandatory
def test_gate_rejects_early_termination_options(tmp_path: Path) -> None:
    for arguments in (("-x",), ("--maxfail=2",)):
        result = _run_gate(tmp_path, _PASSING_SOURCE, _TARGET_NODEID, *arguments)
        assert result.returncode == pytest.ExitCode.USAGE_ERROR
        assert "does not permit -x or --maxfail" in result.stderr


@pytest.mark.mandatory
def test_gate_fails_an_expected_node_without_a_passing_call_phase(tmp_path: Path) -> None:
    source = """\
import pytest


@pytest.fixture
def abort_before_call():
    pytest.exit('stop before call')


@pytest.mark.mandatory
def test_target(abort_before_call):
    assert True
"""
    result = _run_gate(tmp_path, source, _TARGET_NODEID)
    assert result.returncode == pytest.ExitCode.TESTS_FAILED
    assert "stop before call" in result.stdout
