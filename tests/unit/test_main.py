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
    settings = Settings(app_env="test", database_url=f"sqlite:///{database_path}")
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
        assert app.state.session_factory is not None
    assert not database_path.exists()


def test_lifespan_emits_json_lifecycle_events_redacts_and_disposes_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "unmigrated.sqlite3"
    stream = io.StringIO()
    secret = "track01-secret-sentinel-do-not-emit"
    settings = Settings(
        app_env="test", database_url=f"sqlite:///{database_path}", jwt_secret=secret
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
        "application.starting",
        "application.started",
        "application.stopping",
        "application.stopped",
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
    app = create_app(Settings(app_env="test", database_url=f"sqlite:///{database_path}"))

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
        Settings(app_env="test", database_url=f"sqlite:///{tmp_path / 'unmigrated.sqlite3'}")
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
        Settings(app_env="development", database_url=f"sqlite:///{tmp_path / 'unmigrated.sqlite3'}")
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
        Settings(app_env="test", database_url=f"sqlite:///{tmp_path / 'unmigrated.sqlite3'}")
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
        Settings(app_env="test", database_url=f"sqlite:///{tmp_path / 'unmigrated.sqlite3'}")
    )

    with pytest.raises(RuntimeError), TestClient(app):
        pass

    assert disposed is True
    startup_failures = [
        record for record in _records(stream) if record["event"] == "application.startup_failed"
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
        Settings(app_env="test", database_url=f"sqlite:///{tmp_path / 'unmigrated.sqlite3'}")
    )

    with pytest.raises(RuntimeError), TestClient(app):
        pass

    assert [record["event"] for record in _records(stream)].count("application.startup_failed") == 1
    assert "track01-secret-sentinel-do-not-emit" not in stream.getvalue()
