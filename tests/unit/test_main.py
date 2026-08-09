"""Tests for the inert FastAPI composition root and explicit lifespan wiring."""

from __future__ import annotations

import importlib
import io
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.lifecycle import ApplicationLifecycleEvent
from app.main import create_app

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _records(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_main_module_is_inert_and_has_no_application_instance(tmp_path: Path) -> None:
    database_path = tmp_path / "unmigrated.sqlite3"
    environment = os.environ | {"DATABASE_URL": f"sqlite:///{database_path}"}
    completed = subprocess.run(
        [sys.executable, "-c", "import app.main; assert not hasattr(app.main, 'app')"],
        cwd=_REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert not database_path.exists()


def test_factory_honors_injected_settings_and_openapi_without_schema_mutation(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "unmigrated.sqlite3"
    settings = Settings(
        app_env="test",
        database_url=f"sqlite:///{database_path}",
        stats_refresh_enabled=False,
    )
    app = create_app(settings)

    assert app.state.settings is settings
    with TestClient(app) as client:
        response = client.get("/openapi.json")
        assert response.status_code == 200
        assert response.json()["info"] == {
            "title": "Bookmarks API",
            "description": "Foundation runtime for the Bookmarks API.",
            "version": "0.1.0",
        }
        assert client.get("/openapi.json").json() == response.json()
        assert app.state.session_factory is not None
        assert not hasattr(app.state, "bookmark_stats_refresher")
        assert not hasattr(app.state, "bookmark_stats_store")
        assert not hasattr(app.state, "bookmark_stats_publisher")
    assert not database_path.exists()


def test_lifespan_emits_json_lifecycle_events_redacts_and_disposes_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "unmigrated.sqlite3"
    stream = io.StringIO()
    secret = "track01-secret-sentinel-do-not-emit"
    settings = Settings(
        app_env="test",
        database_url=f"sqlite:///{database_path}",
        jwt_secret=secret,
        stats_refresh_enabled=False,
    )
    app = create_app(settings)
    import app.main as main

    original_configure_logging = main.configure_logging
    disposed = False

    class DisposableEngine:
        def dispose(self) -> None:
            nonlocal disposed
            disposed = True

    def configure_to_stream(value: Settings, *, component: str) -> Any:
        return original_configure_logging(value, stream=stream, component=component)

    monkeypatch.setattr(main, "configure_logging", configure_to_stream)
    monkeypatch.setattr(main, "create_database_engine", lambda _settings: DisposableEngine())
    monkeypatch.setattr(main, "create_session_factory", lambda _engine: object())
    with TestClient(app):
        assert isinstance(app.state.engine, DisposableEngine)
    assert disposed is True
    assert not database_path.exists()
    assert secret not in stream.getvalue()

    records = _records(stream)
    assert [record["event"] for record in records] == [
        ApplicationLifecycleEvent.STARTING,
        ApplicationLifecycleEvent.STARTED,
        ApplicationLifecycleEvent.STOPPING,
        ApplicationLifecycleEvent.STOPPED,
    ]
    assert all(record["component"] == "lifecycle" for record in records)
    assert all(record["source"]["module"] == "app.main" for record in records)


def test_zero_argument_factory_reads_environment_only_when_called(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "configured.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    module = importlib.import_module("app.main")

    app = module.create_app()

    assert app.state.settings.database_url == f"sqlite:///{database_path}"
    assert not database_path.exists()


def test_starting_against_unmigrated_database_does_not_create_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "unmigrated.sqlite3"
    app = create_app(
        Settings(
            app_env="test",
            database_url=f"sqlite:///{database_path}",
            stats_refresh_enabled=False,
        )
    )

    with TestClient(app):
        pass

    if database_path.exists():
        with sqlite3.connect(database_path) as connection:
            assert (
                connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
                == []
            )


def test_test_fault_is_logged_once_and_returns_fastapis_default_500(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stream = io.StringIO()
    import app.main as main

    original_configure_logging = main.configure_logging

    def configure_to_stream(value: Settings, *, component: str) -> Any:
        return original_configure_logging(value, stream=stream, component=component)

    monkeypatch.setattr(main, "configure_logging", configure_to_stream)
    app = create_app(
        Settings(
            app_env="test",
            database_url=f"sqlite:///{tmp_path / 'unmigrated.sqlite3'}",
            stats_refresh_enabled=False,
        )
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/openapi.json", headers={"X-Track01-Harness-Fault": "1"})

    assert response.status_code == 500
    assert "track01-secret-sentinel-do-not-emit" not in response.text
    assert "track01-submitted-bookmark-sentinel-do-not-emit" not in response.text
    unexpected = [
        record
        for record in _records(stream)
        if record["event"] == "http.request.unexpected_exception"
    ]
    assert len(unexpected) == 1
    assert unexpected[0]["exception"]["type"] == "RuntimeError"
    assert unexpected[0]["exception"]["frames"]
    assert "track01-secret-sentinel-do-not-emit" not in stream.getvalue()
    assert "track01-submitted-bookmark-sentinel-do-not-emit" not in stream.getvalue()


def test_normal_responses_and_non_test_fault_header_do_not_log_unexpected_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stream = io.StringIO()
    import app.main as main

    original_configure_logging = main.configure_logging

    def configure_to_stream(value: Settings, *, component: str) -> Any:
        return original_configure_logging(value, stream=stream, component=component)

    monkeypatch.setattr(main, "configure_logging", configure_to_stream)
    app = create_app(
        Settings(
            app_env="development",
            database_url=f"sqlite:///{tmp_path / 'unmigrated.sqlite3'}",
            stats_refresh_enabled=False,
        )
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        assert (
            client.get("/openapi.json", headers={"X-Track01-Harness-Fault": "1"}).status_code == 200
        )
        assert client.get("/not-a-route").status_code == 404

    assert not [
        record
        for record in _records(stream)
        if record["event"] == "http.request.unexpected_exception"
    ]


def test_test_fault_returns_redacted_envelope_after_exactly_one_owning_boundary_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stream = io.StringIO()
    import app.main as main

    original_configure_logging = main.configure_logging

    def configure_to_stream(value: Settings, *, component: str) -> Any:
        return original_configure_logging(value, stream=stream, component=component)

    monkeypatch.setattr(main, "configure_logging", configure_to_stream)
    app = create_app(
        Settings(
            app_env="test",
            database_url=f"sqlite:///{tmp_path / 'unmigrated.sqlite3'}",
            stats_refresh_enabled=False,
        )
    )

    with TestClient(app) as client:
        response = client.get("/openapi.json", headers={"X-Track01-Harness-Fault": "1"})

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Internal server error.", "details": None}
    }
    assert [record["event"] for record in _records(stream)].count(
        "http.request.unexpected_exception"
    ) == 1


def test_startup_initialization_failure_logs_once_and_disposes_partial_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stream = io.StringIO()
    import app.main as main

    original_configure_logging = main.configure_logging
    disposed = False

    class DisposableEngine:
        def dispose(self) -> None:
            nonlocal disposed
            disposed = True

    def configure_to_stream(value: Settings, *, component: str) -> Any:
        return original_configure_logging(value, stream=stream, component=component)

    def fail_session_factory(_engine: object) -> object:
        raise RuntimeError("track01-secret-sentinel-do-not-emit")

    monkeypatch.setattr(main, "configure_logging", configure_to_stream)
    monkeypatch.setattr(main, "create_database_engine", lambda _settings: DisposableEngine())
    monkeypatch.setattr(main, "create_session_factory", fail_session_factory)
    app = create_app(
        Settings(
            app_env="test",
            database_url=f"sqlite:///{tmp_path / 'unmigrated.sqlite3'}",
            stats_refresh_enabled=False,
        )
    )

    with pytest.raises(RuntimeError), TestClient(app):
        pass

    assert disposed is True
    startup_failures = [
        record
        for record in _records(stream)
        if record["event"] == ApplicationLifecycleEvent.STARTUP_FAILED
    ]
    assert len(startup_failures) == 1
    assert startup_failures[0]["exception"]["type"] == "RuntimeError"
    assert startup_failures[0]["exception"]["frames"]
    assert "track01-secret-sentinel-do-not-emit" not in stream.getvalue()


def test_startup_engine_creation_failure_is_logged_once_without_partial_disposal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stream = io.StringIO()
    import app.main as main

    original_configure_logging = main.configure_logging

    def configure_to_stream(value: Settings, *, component: str) -> Any:
        return original_configure_logging(value, stream=stream, component=component)

    def fail_engine_creation(_settings: Settings) -> object:
        raise RuntimeError("track01-secret-sentinel-do-not-emit")

    monkeypatch.setattr(main, "configure_logging", configure_to_stream)
    monkeypatch.setattr(main, "create_database_engine", fail_engine_creation)
    app = create_app(
        Settings(
            app_env="test",
            database_url=f"sqlite:///{tmp_path / 'unmigrated.sqlite3'}",
            stats_refresh_enabled=False,
        )
    )

    with pytest.raises(RuntimeError), TestClient(app):
        pass

    assert [record["event"] for record in _records(stream)].count(
        ApplicationLifecycleEvent.STARTUP_FAILED
    ) == 1
    assert "track01-secret-sentinel-do-not-emit" not in stream.getvalue()


@pytest.mark.parametrize("stop_mode", ["stopped", "raises", "deferred"])
def test_enabled_refresher_startup_failure_stops_before_disposing_engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stop_mode: str,
) -> None:
    import app.main as main

    operations: list[str] = []

    class DisposableEngine:
        def dispose(self) -> None:
            operations.append("dispose")

    class FailingRefresher:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def start(self) -> bool:
            operations.append("start")
            return True

        def wait_initial(self, _timeout: int) -> bool:
            raise RuntimeError("track01-secret-sentinel-do-not-emit")

        def stop(self, _timeout: int) -> bool:
            operations.append("stop")
            if stop_mode == "raises":
                raise RuntimeError("track01-stop-secret-sentinel-do-not-emit")
            return stop_mode == "stopped"

        def defer_until_stopped(self, callback: object) -> None:
            if stop_mode != "deferred":
                raise RuntimeError("track01-defer-secret-sentinel-do-not-emit")
            operations.append("defer")
            assert callable(callback)
            callback()

        def snapshot_healthy(self) -> bool:
            return False

    monkeypatch.setattr(main, "create_database_engine", lambda _settings: DisposableEngine())
    monkeypatch.setattr(main, "create_session_factory", lambda _engine: object())
    monkeypatch.setattr(main, "StatsRefresher", FailingRefresher)
    app = create_app(
        Settings(
            app_env="test",
            database_url=f"sqlite:///{tmp_path / 'unmigrated.sqlite3'}",
            stats_refresh_enabled=True,
        )
    )

    with pytest.raises(RuntimeError, match="track01-secret"), TestClient(app):
        pass

    expected = ["start", "stop"]
    if stop_mode == "deferred":
        expected.append("defer")
    expected.append("dispose")
    assert operations == expected


def test_shutdown_timeout_defers_engine_disposal_until_worker_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.main as main

    operations: list[str] = []

    class DisposableEngine:
        def dispose(self) -> None:
            operations.append("dispose")

    class TimedOutRefresher:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def start(self) -> bool:
            operations.append("start")
            return True

        def wait_initial(self, _timeout: int) -> bool:
            return True

        def stop(self, _timeout: int) -> bool:
            operations.append("stop")
            return False

        def defer_until_stopped(self, callback: object) -> None:
            operations.append("defer")
            assert callable(callback)
            callback()

        def snapshot_healthy(self) -> bool:
            return False

    monkeypatch.setattr(main, "create_database_engine", lambda _settings: DisposableEngine())
    monkeypatch.setattr(main, "create_session_factory", lambda _engine: object())
    monkeypatch.setattr(main, "StatsRefresher", TimedOutRefresher)
    app = create_app(
        Settings(
            app_env="test",
            database_url=f"sqlite:///{tmp_path / 'unmigrated.sqlite3'}",
            stats_refresh_enabled=True,
        )
    )

    with TestClient(app):
        assert operations == ["start"]

    assert operations == ["start", "stop", "defer", "dispose"]
