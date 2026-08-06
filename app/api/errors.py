"""One safe HTTP translation boundary for the application's error contract."""

from __future__ import annotations

import re
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import (
    ApplicationError,
    InternalServerError,
    NotFoundError,
    ValidationApplicationError,
    ValidationIssue,
)

_MAX_VALIDATION_ISSUES = 20
_MAX_LOCATION_SEGMENTS = 10
_MAX_LOCATION_TEXT_LENGTH = 64
_SAFE_ERROR_TYPE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


class ValidationDetail(BaseModel):
    """Public validation detail with no echoed input, context, or request body."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    loc: tuple[str | int, ...]
    type: str
    message: Literal["Invalid value"] = "Invalid value"


class ErrorBody(BaseModel):
    """The stable inner error shape shared by every HTTP failure response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    message: str
    details: list[ValidationDetail] | None = None


class ErrorEnvelope(BaseModel):
    """The public API error envelope fixed by ADR-002."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    error: ErrorBody


def _safe_location(value: object) -> tuple[str | int, ...]:
    """Bound a Pydantic error path without reflecting arbitrary objects."""
    if not isinstance(value, tuple | list):
        return ()

    safe_parts: list[str | int] = []
    for part in value[:_MAX_LOCATION_SEGMENTS]:
        if isinstance(part, bool):
            safe_parts.append("invalid")
        elif isinstance(part, int):
            safe_parts.append(part)
        elif isinstance(part, str):
            safe_parts.append(part[:_MAX_LOCATION_TEXT_LENGTH])
        else:
            safe_parts.append("invalid")
    return tuple(safe_parts)


def _safe_error_type(value: object) -> str:
    """Keep a machine-readable validation kind only when it has a safe shape."""
    if isinstance(value, str) and _SAFE_ERROR_TYPE.fullmatch(value):
        return value
    return "invalid"


def request_validation_issues(error: RequestValidationError) -> tuple[ValidationIssue, ...]:
    """Extract only bounded location and type metadata from framework errors."""
    return tuple(
        ValidationIssue(
            loc=_safe_location(item.get("loc")),
            type=_safe_error_type(item.get("type")),
            message="Invalid value",
        )
        for item in error.errors()[:_MAX_VALIDATION_ISSUES]
    )


def error_response(error: ApplicationError) -> JSONResponse:
    """Serialize a typed expected failure without exposing an exception object."""
    details = (
        [
            ValidationDetail(loc=issue.loc, type=issue.type)
            for issue in error.details[:_MAX_VALIDATION_ISSUES]
        ]
        if error.details is not None
        else None
    )
    envelope = ErrorEnvelope(
        error=ErrorBody(code=error.code, message=error.message, details=details)
    )
    return JSONResponse(
        status_code=error.status_code,
        content=envelope.model_dump(mode="json"),
        headers=error.headers,
    )


def unexpected_error_response() -> JSONResponse:
    """Return the deliberately uninformative public response for an owned fault."""
    return error_response(InternalServerError())


async def application_error_handler(_request: Request, error: ApplicationError) -> JSONResponse:
    """Translate all expected application failures at one registered boundary."""
    return error_response(error)


async def request_validation_error_handler(
    _request: Request, error: RequestValidationError
) -> JSONResponse:
    """Replace FastAPI's input-echoing default validation response."""
    return error_response(ValidationApplicationError(details=request_validation_issues(error)))


async def http_exception_handler(_request: Request, error: StarletteHTTPException) -> JSONResponse:
    """Keep missing routes within the documented envelope without reflecting detail."""
    if error.status_code == 404:
        return error_response(NotFoundError())
    envelope = ErrorEnvelope(error=ErrorBody(code="http_error", message="Request failed."))
    return JSONResponse(status_code=error.status_code, content=envelope.model_dump(mode="json"))


def register_exception_handlers(app: FastAPI) -> None:
    """Install the sole registration point for expected and framework failures."""
    app.add_exception_handler(ApplicationError, application_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]


__all__ = [
    "ErrorBody",
    "ErrorEnvelope",
    "ValidationDetail",
    "error_response",
    "register_exception_handlers",
    "request_validation_issues",
    "unexpected_error_response",
]
