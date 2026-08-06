"""Deterministic edge-ledger tests for centralized JSON Lines logging."""

from __future__ import annotations

import io
import json
import logging
import os
from collections.abc import Iterator
from typing import Any

import pytest

from app.core.config import Settings
from app.core.logging import (
    FailClosedStreamHandler,
    JsonFormatter,
    configure_logging,
    log_event,
    log_exception,
    redact,
)

pytestmark = pytest.mark.mandatory

_SECRET = "track01-secret-sentinel-do-not-emit"
_CONTENT = "track01-submitted-bookmark-sentinel-do-not-emit"


@pytest.fixture
def configured_logger() -> Iterator[tuple[logging.Logger, io.StringIO]]:
    stream = io.StringIO()
    logger = configure_logging(Settings(app_env="test"), stream=stream)
    yield logger, stream
    for handler in tuple(logger.handlers):
        if getattr(handler, "_bookmarks_json_handler", False):
            logger.removeHandler(handler)
            handler.close()


def _records(stream: io.StringIO) -> list[dict[str, Any]]:
    lines = stream.getvalue().splitlines()
    assert lines
    return [json.loads(line) for line in lines]


def _wrapped_event(logger: logging.Logger) -> None:
    log_event(logger, logging.INFO, "wrapped.event", message="wrapped", stacklevel=2)


def _direct_error() -> None:
    raise ValueError(f"{_SECRET} {_CONTENT} https://private.example/bookmark")


def test_event_is_exactly_one_json_line_with_required_schema(
    configured_logger: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = configured_logger

    log_event(
        logger,
        logging.INFO,
        "foundation.started",
        message="foundation started",
        context={"operation": "startup", "attempt": 1},
        correlation_id="correlation-123",
        trace_id="trace-456",
        component="lifecycle",
    )

    raw = stream.getvalue()
    assert raw.count("\n") == 1
    record = _records(stream)[0]
    assert record["schema_version"] == "1.0"
    assert record["level"] == record["severity"] == "INFO"
    assert record["application"] == record["service"] == "bookmarks-api"
    assert record["environment"] == "test"
    assert record["component"] == "lifecycle"
    assert record["event"] == "foundation.started"
    assert record["outcome"] == "success"
    assert record["message"] == "foundation started"
    assert record["context"] == {"operation": "startup", "attempt": 1}
    assert record["correlation_id"] == "correlation-123"
    assert record["trace_id"] == "trace-456"
    assert record["process_id"] == os.getpid()
    assert record["thread_name"]
    assert isinstance(record["thread_id"], int)
    assert record["timestamp"].endswith("Z")
    assert record["source"]["pathname"] == os.path.abspath(__file__)
    assert record["source"]["lineno"] > 0
    assert record["source"]["package"] == "tests.unit"
    assert record["source"]["module"] == __name__
    assert (
        record["source"]["function"] == "test_event_is_exactly_one_json_line_with_required_schema"
    )


def test_wrapper_stacklevel_attributes_the_application_caller(
    configured_logger: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = configured_logger

    _wrapped_event(logger)

    source = _records(stream)[0]["source"]
    assert source["pathname"] == os.path.abspath(__file__)
    assert source["module"] == __name__
    assert source["function"] == "test_wrapper_stacklevel_attributes_the_application_caller"


def test_recursive_redaction_preserves_safe_context_and_removes_sentinels(
    configured_logger: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = configured_logger

    log_event(
        logger,
        logging.WARNING,
        "foundation.redaction_checked",
        message=f"Bearer {_SECRET}",
        context={
            "safe_count": 2,
            "password": _SECRET,
            "nested": {"jwt": _SECRET, "safe": "kept"},
            "tags": [_CONTENT],
            "database_url": "sqlite:///private.db",
        },
    )

    raw = stream.getvalue()
    assert _SECRET not in raw
    assert _CONTENT not in raw
    record = _records(stream)[0]
    assert record["message"] == "[REDACTED]"
    assert record["context"] == {
        "safe_count": 2,
        "password": "[REDACTED]",
        "nested": {"jwt": "[REDACTED]", "safe": "kept"},
        "tags": "[REDACTED]",
        "database_url": "[REDACTED]",
    }


def test_direct_message_values_redact_submitted_content_sentinels_and_http_urls(
    configured_logger: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = configured_logger

    log_event(
        logger,
        logging.INFO,
        "foundation.message_redaction_checked",
        message=f"submitted {_CONTENT} https://private.example/bookmark",
    )

    raw = stream.getvalue()
    assert _CONTENT not in raw
    assert "https://private.example/bookmark" not in raw
    assert _records(stream)[0]["message"] == "[REDACTED]"


def test_redactor_handles_value_patterns_bytes_secret_values_and_collections() -> None:
    class SecretStr:
        pass

    assert redact(f"jwt {_SECRET}") == "[REDACTED]"
    assert redact(_CONTENT) == "[REDACTED]"
    assert redact("https://private.example/bookmark") == "[REDACTED]"
    assert redact(b"binary secret") == "[REDACTED]"
    assert redact(SecretStr()) == "[REDACTED]"
    assert redact(["kept", _SECRET]) == ["kept", "[REDACTED]"]
    assert redact(("kept",)) == ["kept"]


def test_nonserializable_context_fails_closed_without_unsafe_representation(
    configured_logger: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = configured_logger

    class NonSerializable:
        def __repr__(self) -> str:
            return _SECRET

    log_event(
        logger,
        logging.INFO,
        "foundation.nonserializable",
        context={"safe": NonSerializable()},
        correlation_id="correlation-123",
    )

    raw = stream.getvalue()
    assert _SECRET not in raw
    assert "--- Logging error ---" not in raw
    record = _records(stream)
    assert len(record) == 1
    assert record[0]["event"] == "logging.serialization_failed"
    assert record[0]["correlation_id"] == "correlation-123"
    assert "context" not in record[0]


def test_redactor_failure_fails_closed_to_one_safe_json_line(
    configured_logger: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = configured_logger

    def failed_redactor(value: Any, key: str | None = None) -> Any:
        raise RuntimeError(_SECRET)

    logger.handlers[0].setFormatter(JsonFormatter(failed_redactor))
    log_event(logger, logging.INFO, "foundation.redactor_failed", message=_SECRET)

    raw = stream.getvalue()
    assert _SECRET not in raw
    assert "--- Logging error ---" not in raw
    assert _records(stream) == [
        {
            "schema_version": "1.0",
            "timestamp": _records(stream)[0]["timestamp"],
            "level": "ERROR",
            "severity": "ERROR",
            "application": "bookmarks-api",
            "service": "bookmarks-api",
            "environment": "test",
            "component": "application",
            "logger": "app",
            "event": "logging.serialization_failed",
            "outcome": "failure",
            "message": "structured log serialization failed",
            "process_id": os.getpid(),
            "thread_name": _records(stream)[0]["thread_name"],
            "thread_id": _records(stream)[0]["thread_id"],
            "source": _records(stream)[0]["source"],
        }
    ]


def test_serialization_fallback_redacts_sensitive_correlation_and_trace_identifiers(
    configured_logger: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = configured_logger

    def failed_redactor(value: Any, key: str | None = None) -> Any:
        raise RuntimeError(_SECRET)

    logger.handlers[0].setFormatter(JsonFormatter(failed_redactor))
    log_event(
        logger,
        logging.INFO,
        "foundation.identifier_fallback",
        correlation_id=f"Bearer {_SECRET}",
        trace_id=_CONTENT,
    )

    raw = stream.getvalue()
    assert _SECRET not in raw
    assert _CONTENT not in raw
    record = _records(stream)[0]
    assert record["event"] == "logging.serialization_failed"
    assert record["correlation_id"] == "[REDACTED]"
    assert record["trace_id"] == "[REDACTED]"


def test_handler_itself_fails_closed_when_a_non_json_formatter_raises(
    capsys: pytest.CaptureFixture[str],
) -> None:
    class BrokenFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            raise RuntimeError(_SECRET)

    stream = io.StringIO()
    handler = FailClosedStreamHandler(stream)
    handler.setFormatter(BrokenFormatter())
    handler.handle(logging.LogRecord("app", logging.ERROR, __file__, 1, _SECRET, (), None))

    assert _SECRET not in stream.getvalue()
    assert "--- Logging error ---" not in capsys.readouterr().err
    assert _records(stream)[0]["event"] == "logging.serialization_failed"


def test_handler_drops_a_record_when_both_primary_and_fallback_stream_writes_fail(
    capsys: pytest.CaptureFixture[str],
) -> None:
    class PermanentlyFailingStream:
        def write(self, value: str) -> int:
            raise RuntimeError(_SECRET)

        def flush(self) -> None:
            raise RuntimeError(_SECRET)

    handler = FailClosedStreamHandler(PermanentlyFailingStream())
    handler.setFormatter(JsonFormatter())

    handler.handle(logging.LogRecord("app", logging.ERROR, __file__, 1, _SECRET, (), None))

    assert "--- Logging error ---" not in capsys.readouterr().err


def test_direct_exception_is_complete_redacted_and_exactly_once(
    configured_logger: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = configured_logger

    try:
        _direct_error()
    except ValueError:
        log_exception(logger, "foundation.unexpected_exception", context={"bookmark": _CONTENT})

    raw = stream.getvalue()
    assert _SECRET not in raw
    assert _CONTENT not in raw
    records = _records(stream)
    assert len(records) == 1
    exception = records[0]["exception"]
    assert exception["type"] == "ValueError"
    assert exception["module"] == "builtins"
    assert exception["message"] == "[REDACTED]"
    assert exception["frames"]
    assert exception["frames"][-1]["function"] == "_direct_error"
    assert all("locals" not in frame for frame in exception["frames"])
    assert records[0]["context"]["bookmark"] == "[REDACTED]"


def test_cyclic_exception_cause_terminates_with_a_redacted_cycle_marker(
    configured_logger: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = configured_logger

    try:
        raise RuntimeError(_SECRET)
    except RuntimeError as exception:
        exception.__cause__ = exception
        log_exception(logger, "foundation.cyclic_exception", exception=exception)

    raw = stream.getvalue()
    assert _SECRET not in raw
    cycle = _records(stream)[0]["exception"]["cause"]
    assert cycle["cycle"] is True
    assert cycle["message"] == "[REDACTED]"


def test_explicit_exception_preserves_redacted_notes_and_optional_identifiers(
    configured_logger: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = configured_logger

    try:
        raise RuntimeError("safe failure")
    except RuntimeError as exception:
        exception.add_note(f"note with {_SECRET} {_CONTENT} https://private.example/bookmark")
        log_exception(
            logger,
            "foundation.explicit_exception",
            exception=exception,
            correlation_id="correlation-123",
            trace_id="trace-456",
            component="worker",
        )

    record = _records(stream)[0]
    assert _SECRET not in stream.getvalue()
    assert _CONTENT not in stream.getvalue()
    assert "https://private.example/bookmark" not in stream.getvalue()
    assert record["component"] == "worker"
    assert record["correlation_id"] == "correlation-123"
    assert record["trace_id"] == "trace-456"
    assert record["exception"]["notes"] == ["[REDACTED]"]


def test_exception_helper_requires_an_active_or_explicit_exception(
    configured_logger: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, _ = configured_logger

    with pytest.raises(ValueError, match="active or explicit"):
        log_exception(logger, "foundation.invalid_exception_call")


def test_cause_context_and_suppressed_context_are_serialized_correctly(
    configured_logger: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = configured_logger

    try:
        try:
            raise ValueError("cause value")
        except ValueError as cause:
            raise RuntimeError("translated") from cause
    except RuntimeError:
        log_exception(logger, "foundation.translated")
    try:
        try:
            raise KeyError("context value")
        except KeyError:
            raise RuntimeError("context outer")  # noqa: B904 - tests implicit exception context.
    except RuntimeError:
        log_exception(logger, "foundation.context")
    try:
        try:
            raise LookupError("suppressed value")
        except LookupError:
            raise RuntimeError("suppressed outer") from None
    except RuntimeError:
        log_exception(logger, "foundation.suppressed")

    translated, contextual, suppressed = _records(stream)
    assert translated["exception"]["cause"]["type"] == "ValueError"
    assert "context" not in translated["exception"]
    assert contextual["exception"]["context"]["type"] == "KeyError"
    assert "cause" not in contextual["exception"]
    assert "cause" not in suppressed["exception"]
    assert "context" not in suppressed["exception"]


def test_nested_exception_group_keeps_every_member_and_frame(
    configured_logger: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = configured_logger
    members: list[ValueError] = []
    for index in range(20):
        try:
            raise ValueError(f"member secret {_SECRET} {index}")
        except ValueError as member:
            members.append(member)

    try:
        raise ExceptionGroup("outer group", [ExceptionGroup("nested", members[:2]), *members[2:]])
    except ExceptionGroup:
        log_exception(logger, "foundation.exception_group")

    raw = stream.getvalue()
    assert _SECRET not in raw
    records = _records(stream)
    assert len(records) == 1
    exception = records[0]["exception"]
    assert len(exception["members"]) == 19
    nested = exception["members"][0]
    assert len(nested["members"]) == 2
    leaves = [*nested["members"], *exception["members"][1:]]
    assert len(leaves) == 20
    assert all(member["frames"] for member in leaves)
    assert all(member["message"] == "[REDACTED]" for member in leaves)


def test_reconfigure_replaces_only_our_handler_and_avoids_duplicate_child_records() -> None:
    first_stream = io.StringIO()
    second_stream = io.StringIO()
    logger = configure_logging(Settings(app_env="test"), stream=first_stream)
    try:
        configure_logging(Settings(app_env="test"), stream=second_stream)
        framework_logger = logging.getLogger("app.framework")
        log_event(framework_logger, logging.INFO, "framework.access", message="one record")

        assert first_stream.getvalue() == ""
        assert len(_records(second_stream)) == 1
        assert (
            len(
                [
                    handler
                    for handler in logger.handlers
                    if getattr(handler, "_bookmarks_json_handler", False)
                ]
            )
            == 1
        )
    finally:
        for handler in tuple(logger.handlers):
            if getattr(handler, "_bookmarks_json_handler", False):
                logger.removeHandler(handler)
                handler.close()
