"""Pytest plugin enforcing the checked-in Track 05 mandatory-test manifest."""

from __future__ import annotations

from pathlib import Path

import pytest

_MANIFEST = Path(__file__).with_name("mandatory-nodeids.txt")
_EXPECTED = pytest.StashKey[set[str]]()
_EXECUTED = pytest.StashKey[set[str]]()


def _expected_nodeids() -> set[str]:
    return {
        line.strip()
        for line in _MANIFEST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--mandatory-gate", action="store_true", default=False)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "mandatory: required Track 05 closure evidence")
    if not config.getoption("--mandatory-gate"):
        return
    if config.getoption("maxfail"):
        raise pytest.UsageError("--mandatory-gate does not permit -x or --maxfail")
    expected = _expected_nodeids()
    if not expected:
        raise pytest.UsageError("mandatory node ID manifest must not be empty")
    config.stash[_EXPECTED] = expected
    config.stash[_EXECUTED] = set()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not config.getoption("--mandatory-gate"):
        return
    marked = {item.nodeid for item in items if item.get_closest_marker("mandatory")}
    expected = config.stash[_EXPECTED]
    if marked != expected:
        raise pytest.UsageError(
            "mandatory node IDs differ from tests/contract/mandatory-nodeids.txt"
        )
    for item in items:
        if item.nodeid in expected and any(
            item.get_closest_marker(name) is not None for name in ("skip", "skipif", "xfail")
        ):
            raise pytest.UsageError(f"mandatory node has a masking marker: {item.nodeid}")


def pytest_deselected(items: list[pytest.Item]) -> None:
    """Reject selection filters that remove any required manifest node."""
    if not items or not items[0].config.getoption("--mandatory-gate"):
        return
    expected = items[0].config.stash[_EXPECTED]
    removed = expected.intersection(item.nodeid for item in items)
    if removed:
        raise pytest.UsageError("mandatory node was deselected")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[object]):
    """Turn runtime skip/xfail into a gate failure and record passed calls."""
    outcome = yield
    report = outcome.get_result()
    if not item.config.getoption("--mandatory-gate"):
        return
    if item.nodeid not in item.config.stash[_EXPECTED]:
        return
    if report.when == "call":
        if report.skipped or getattr(report, "wasxfail", False):
            report.outcome = "failed"
            report.longrepr = "mandatory test skipped or xfailed during execution"
        elif report.passed:
            item.config.stash[_EXECUTED].add(item.nodeid)
    elif report.when == "setup" and report.skipped:
        report.outcome = "failed"
        report.longrepr = "mandatory test skipped during setup"


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    config = session.config
    if not config.getoption("--mandatory-gate"):
        return
    if config.getoption("collectonly"):
        return
    unrun = config.stash[_EXPECTED] - config.stash[_EXECUTED]
    if unrun:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
