"""Safe, centralized JSON Lines logging for application ownership boundaries.

The module deliberately has no import-time logging configuration.  The composition
root calls :func:`configure_logging` and application boundaries use
:func:`log_event` or :func:`log_exception` so caller attribution remains accurate.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from types import FrameType, TracebackType
from typing import Any, Protocol, TextIO

_SCHEMA_VERSION = "1.0"
_REDACTED = "[REDACTED]"
_SENSITIVE_KEY = re.compile(
    r"(?:pass(?:word)?|secret|hash|token|jwt|bearer|authori[sz]ation|credential|"
    r"api[_-]?key|database(?:[_-]?url)?|connection(?:[_-]?string)?|"
    r"request(?:[_-]?body)?|body|bookmark|url|text|tag)",
    re.IGNORECASE,
)
_SENSITIVE_VALUE = re.compile(
    r"(?:bearer\s+\S+|\b(?:jwt|secret|password|token|authorization|credential)\b|"
    r"(?:postgres(?:ql)?|mysql|sqlite|mongodb)(?:\+\w+)?://|"
    r"https?://\S+|"
    r"\b(?:track0?1|redaction|submitted)[-_][a-z0-9_-]*sentinel\b|"
    r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)",
    re.IGNORECASE,
)


class LoggingSettings(Protocol):
    """Narrow settings required by the logging composition root."""

    @property
    def app_env(self) -> str:
        """Return the non-secret environment label emitted with every log event."""
        ...

    @property
    def log_level(self) -> str:
        """Return the validated root severity used to configure application logging."""
        ...


class Redactor(Protocol):
    """Callable contract for the centrally injected redaction policy."""

    def __call__(self, value: Any, key: str | None = None) -> Any: ...


def redact(value: Any, key: str | None = None) -> Any:
    """Recursively replace credentials and submitted content with a fixed marker."""
    if key is not None and _SENSITIVE_KEY.search(key):
        return _REDACTED
    if isinstance(value, str):
        return _REDACTED if _SENSITIVE_VALUE.search(value) else value
    if isinstance(value, bytes):
        return _REDACTED
    if value.__class__.__name__ in {"SecretStr", "SecretBytes"}:
        return _REDACTED
    if isinstance(value, Mapping):
        return {
            str(item_key): redact(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [redact(item) for item in value]
    return value


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _source_from_frame(frame: FrameType) -> dict[str, Any]:
    module = str(frame.f_globals.get("__name__", "__main__"))
    package_value = frame.f_globals.get("__package__")
    package = str(package_value) if package_value else module.rpartition(".")[0]
    return {
        "pathname": os.path.abspath(frame.f_code.co_filename),
        "lineno": frame.f_lineno,
        "package": package or module,
        "module": module,
        "function": frame.f_code.co_name,
    }


def _caller_source(stacklevel: int) -> dict[str, Any]:
    frame = sys._getframe(stacklevel + 1)
    return _source_from_frame(frame)


def _source_from_record(record: logging.LogRecord) -> dict[str, Any]:
    source = getattr(record, "structured_source", None)
    if isinstance(source, dict):
        return source
    module = record.name if "." in record.name else "__main__"
    package = module.rpartition(".")[0] or module
    return {
        "pathname": os.path.abspath(record.pathname),
        "lineno": max(record.lineno, 1),
        "package": package,
        "module": module,
        "function": record.funcName,
    }


def _safe_fallback_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    if _SENSITIVE_VALUE.search(value):
        return _REDACTED
    return value


def _fallback_record(record: logging.LogRecord) -> dict[str, Any]:
    """Build a minimal record without the configurable redactor or JSON formatter."""
    payload: dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "timestamp": _utc_timestamp(),
        "level": "ERROR",
        "severity": "ERROR",
        "application": _safe_fallback_text(getattr(record, "application", None)) or "bookmarks-api",
        "service": _safe_fallback_text(getattr(record, "service", None)) or "bookmarks-api",
        "environment": _safe_fallback_text(getattr(record, "environment", None)) or "unknown",
        "component": _safe_fallback_text(getattr(record, "component", None)) or "application",
        "logger": _safe_fallback_text(record.name) or "app",
        "event": "logging.serialization_failed",
        "outcome": "failure",
        "message": "structured log serialization failed",
        "process_id": os.getpid(),
        "thread_name": threading.current_thread().name,
        "thread_id": threading.get_ident(),
        "source": _source_from_record(record),
    }
    for identifier in ("correlation_id", "trace_id"):
        safe_value = _safe_fallback_text(getattr(record, identifier, None))
        if safe_value is not None:
            payload[identifier] = safe_value
    return payload


def _exception_payload(exception: BaseException, active: set[int] | None = None) -> dict[str, Any]:
    """Serialize an exception tree without locals, limits, or default pretty formatting."""
    active = set() if active is None else active
    exception_id = id(exception)
    payload: dict[str, Any] = {
        "type": exception.__class__.__qualname__,
        "module": exception.__class__.__module__,
        "message": redact(str(exception)),
        "frames": [],
    }
    if exception_id in active:
        payload["cycle"] = True
        return payload

    active.add(exception_id)
    try:
        traceback_frames: list[dict[str, Any]] = []
        trace: TracebackType | None = exception.__traceback__
        while trace is not None:
            traceback_frames.append(
                _source_from_frame(trace.tb_frame) | {"lineno": trace.tb_lineno}
            )
            trace = trace.tb_next
        payload["frames"] = traceback_frames
        if exception.__cause__ is not None:
            payload["cause"] = _exception_payload(exception.__cause__, active)
        elif exception.__context__ is not None and not exception.__suppress_context__:
            payload["context"] = _exception_payload(exception.__context__, active)
        if isinstance(exception, BaseExceptionGroup):
            payload["members"] = [
                _exception_payload(member, active) for member in exception.exceptions
            ]
        notes = getattr(exception, "__notes__", None)
        if notes:
            payload["notes"] = [redact(str(note)) for note in notes]
    finally:
        active.remove(exception_id)
    return payload


class JsonFormatter(logging.Formatter):
    """Versioned JSON formatter that converts all formatting failures to one safe line."""

    def __init__(self, redactor: Redactor = redact) -> None:
        super().__init__()
        self._redactor = redactor

    def format(self, record: logging.LogRecord) -> str:
        """Serialize one record as JSON Lines, falling back only to the safe minimal schema."""
        try:
            message = self._redactor(record.getMessage())
            payload: dict[str, Any] = {
                "schema_version": _SCHEMA_VERSION,
                "timestamp": _utc_timestamp(),
                "level": record.levelname,
                "severity": record.levelname,
                "application": self._redactor(getattr(record, "application", "bookmarks-api")),
                "service": self._redactor(getattr(record, "service", "bookmarks-api")),
                "environment": self._redactor(getattr(record, "environment", "unknown")),
                "component": self._redactor(getattr(record, "component", "application")),
                "logger": self._redactor(record.name),
                "event": self._redactor(getattr(record, "event", "logging.message")),
                "outcome": self._redactor(getattr(record, "outcome", "unknown")),
                "message": message,
                "process_id": record.process,
                "thread_name": self._redactor(record.threadName),
                "thread_id": record.thread,
                "source": self._redactor(_source_from_record(record)),
            }
            for identifier in ("correlation_id", "trace_id"):
                value = getattr(record, identifier, None)
                if value is not None:
                    payload[identifier] = self._redactor(value, identifier)
            context = getattr(record, "structured_context", None)
            if context is not None:
                payload["context"] = self._redactor(context)
            if record.exc_info and record.exc_info[1] is not None:
                payload["exception"] = _exception_payload(record.exc_info[1])
            return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        except Exception:
            return json.dumps(_fallback_record(record), ensure_ascii=False, separators=(",", ":"))


class FailClosedStreamHandler(logging.StreamHandler[TextIO]):
    """Suppress stdlib plaintext diagnostics if a formatter or stream fails."""

    _bookmarks_json_handler = False

    def emit(self, record: logging.LogRecord) -> None:
        """Write formatter output without allowing logging's plaintext error handler to run."""
        try:
            message = self.format(record)
            self.stream.write(message + self.terminator)
            self.flush()
        except Exception:
            try:
                self.stream.write(
                    json.dumps(_fallback_record(record), ensure_ascii=False, separators=(",", ":"))
                    + self.terminator
                )
                self.flush()
            except Exception:
                pass

    def handleError(self, record: logging.LogRecord) -> None:
        """Never allow logging's ``--- Logging error ---`` diagnostic to escape."""


def configure_logging(
    settings: LoggingSettings,
    *,
    stream: TextIO | None = None,
    application: str = "bookmarks-api",
    component: str = "application",
) -> logging.Logger:
    """Configure the application logger at the composition root and return it.

    Reconfiguration replaces only handlers previously installed by this module, so
    tests and process lifecycle code can safely inject a new destination.
    """
    logger = logging.getLogger(__name__.partition(".")[0])
    logger.setLevel(settings.log_level)
    logger.propagate = False
    for handler in tuple(logger.handlers):
        if getattr(handler, "_bookmarks_json_handler", False):
            logger.removeHandler(handler)
            handler.close()
    handler = FailClosedStreamHandler(stream or sys.stderr)
    handler._bookmarks_json_handler = True
    handler.setFormatter(JsonFormatter())
    handler.addFilter(_ApplicationFieldsFilter(settings.app_env, application, component))
    logger.addHandler(handler)
    return logger


class _ApplicationFieldsFilter(logging.Filter):
    """Populate schema fields for framework records that bypass structured helper calls."""

    def __init__(self, environment: str, application: str, component: str) -> None:
        super().__init__()
        self._environment = environment
        self._application = application
        self._component = component

    def filter(self, record: logging.LogRecord) -> bool:
        """Supply safe defaults while preserving explicit application-provided fields."""
        record.application = self._application
        record.service = self._application
        record.environment = self._environment
        record.component = getattr(record, "component", self._component)
        return True


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    *,
    outcome: str = "success",
    message: str = "",
    context: Mapping[str, Any] | None = None,
    correlation_id: str | None = None,
    trace_id: str | None = None,
    component: str | None = None,
    stacklevel: int = 1,
) -> None:
    """Emit one structured application event, attributing it to this helper's caller."""
    extra: dict[str, Any] = {
        "event": event,
        "outcome": outcome,
        "structured_context": context,
        "structured_source": _caller_source(stacklevel),
    }
    if correlation_id is not None:
        extra["correlation_id"] = correlation_id
    if trace_id is not None:
        extra["trace_id"] = trace_id
    if component is not None:
        extra["component"] = component
    logger.log(level, message, extra=extra, stacklevel=stacklevel + 1)


def log_exception(
    logger: logging.Logger,
    event: str,
    *,
    exception: BaseException | None = None,
    outcome: str = "failure",
    message: str = "unexpected application exception",
    context: Mapping[str, Any] | None = None,
    correlation_id: str | None = None,
    trace_id: str | None = None,
    component: str | None = None,
    stacklevel: int = 1,
) -> None:
    """Emit the one exception record owned by the current boundary."""
    active_exception = exception if exception is not None else sys.exception()
    if active_exception is None:
        msg = "log_exception requires an active or explicit exception"
        raise ValueError(msg)
    extra: dict[str, Any] = {
        "event": event,
        "outcome": outcome,
        "structured_context": context,
        "structured_source": _caller_source(stacklevel),
    }
    if correlation_id is not None:
        extra["correlation_id"] = correlation_id
    if trace_id is not None:
        extra["trace_id"] = trace_id
    if component is not None:
        extra["component"] = component
    logger.error(
        message,
        exc_info=(type(active_exception), active_exception, active_exception.__traceback__),
        extra=extra,
        stacklevel=stacklevel + 1,
    )


__all__ = [
    "FailClosedStreamHandler",
    "JsonFormatter",
    "LoggingSettings",
    "configure_logging",
    "log_event",
    "log_exception",
    "redact",
]
