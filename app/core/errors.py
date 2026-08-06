"""Transport-independent expected application failures.

Only the HTTP boundary decides how these errors become responses.  The exception
objects intentionally carry stable, non-sensitive presentation data rather than
driver messages, submitted input, credentials, or persistence details.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """A bounded, safe description of a rejected request field."""

    loc: tuple[str | int, ...]
    type: str
    message: str


class ApplicationError(Exception):
    """Expected application failure with a stable public error contract."""

    code = "application_error"
    message = "Request could not be completed."
    status_code = 400
    headers: dict[str, str] | None = None

    def __init__(self, *, details: Sequence[ValidationIssue] | None = None) -> None:
        super().__init__(self.message)
        self.details = tuple(details) if details is not None else None


class ValidationApplicationError(ApplicationError):
    """A safe validation failure that maps to HTTP 422."""

    code = "validation_error"
    message = "Request validation failed."
    status_code = 422


class AuthenticationError(ApplicationError):
    """Generic credential failure that does not reveal its source."""

    code = "authentication_failed"
    message = "Authentication failed."
    status_code = 401
    headers = {"WWW-Authenticate": "Bearer"}


class ConflictError(ApplicationError):
    """Expected, safe resource conflict."""

    code = "conflict"
    message = "Resource conflict."
    status_code = 409


class IdentityConflictError(ConflictError):
    """A deliberately generic conflict for an existing username or email."""

    code = "identity_conflict"
    message = "Username or email is already registered."


class NotFoundError(ApplicationError):
    """Expected, concealment-safe missing resource failure."""

    code = "not_found"
    message = "Resource not found."
    status_code = 404


class InternalServerError(ApplicationError):
    """Redacted presentation value used only by the owning unexpected boundary."""

    code = "internal_error"
    message = "Internal server error."
    status_code = 500


__all__ = [
    "ApplicationError",
    "AuthenticationError",
    "ConflictError",
    "IdentityConflictError",
    "InternalServerError",
    "NotFoundError",
    "ValidationApplicationError",
    "ValidationIssue",
]
