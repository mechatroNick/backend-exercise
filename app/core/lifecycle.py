"""Stable application lifecycle event names used by the composition root."""

from __future__ import annotations

from enum import StrEnum


class ApplicationLifecycleEvent(StrEnum):
    """Low-cardinality lifecycle transitions emitted by the application process."""

    STARTING = "application.starting"
    STARTUP_FAILED = "application.startup_failed"
    STARTED = "application.started"
    STOPPING = "application.stopping"
    STOPPED = "application.stopped"


__all__ = ["ApplicationLifecycleEvent"]
