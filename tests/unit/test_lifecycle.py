"""Tests for the closed application lifecycle event vocabulary."""

from __future__ import annotations

from enum import StrEnum

from app.core.lifecycle import ApplicationLifecycleEvent


def test_application_lifecycle_events_are_exact_stable_strings() -> None:
    assert issubclass(ApplicationLifecycleEvent, StrEnum)
    assert {event.name: event.value for event in ApplicationLifecycleEvent} == {
        "STARTING": "application.starting",
        "STARTUP_FAILED": "application.startup_failed",
        "STARTED": "application.started",
        "STOPPING": "application.stopping",
        "STOPPED": "application.stopped",
    }
    assert all(isinstance(event, str) for event in ApplicationLifecycleEvent)
