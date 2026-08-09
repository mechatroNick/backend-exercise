"""Protected JSON HTTP transport for owner-scoped bookmark CRUD."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.api.errors import ErrorEnvelope, request_validation_issues
from app.auth.dependencies import get_rate_limited_subject
from app.auth.schemas import CurrentSubject
from app.bookmarks.dependencies import (
    get_bookmark_cursor_codec,
    get_bookmark_service,
    get_bookmark_stats_service,
)
from app.bookmarks.pagination import BookmarkCursorCodec
from app.bookmarks.schemas import (
    BookmarkCreate,
    BookmarkList,
    BookmarkPatch,
    BookmarkPublic,
    BookmarkQuery,
)
from app.bookmarks.service import BookmarkService
from app.bookmarks.stats.schemas import BookmarkStats
from app.bookmarks.stats.service import (
    CurrentStatsService,
    StatsSource,
    stats_generated_at_header,
)
from app.core.errors import ValidationApplicationError, ValidationIssue

_ERROR_EXAMPLES = {
    "authentication": {
        "summary": "Generic authentication failure",
        "value": {
            "error": {
                "code": "authentication_failed",
                "message": "Authentication failed.",
                "details": None,
            }
        },
    },
    "not_found": {
        "summary": "Concealed missing resource",
        "value": {
            "error": {
                "code": "not_found",
                "message": "Resource not found.",
                "details": None,
            }
        },
    },
    "validation": {
        "summary": "Safe validation failure",
        "value": {
            "error": {
                "code": "validation_error",
                "message": "Request validation failed.",
                "details": [
                    {"loc": ["body", "title"], "type": "value_error", "message": "Invalid value"}
                ],
            }
        },
    },
    "internal": {
        "summary": "Redacted unexpected failure",
        "value": {
            "error": {
                "code": "internal_error",
                "message": "Internal server error.",
                "details": None,
            }
        },
    },
    "rate_limited": {
        "summary": "Local bookmark rate limit",
        "value": {
            "error": {"code": "rate_limited", "message": "Too many requests.", "details": None}
        },
    },
}


def _error_response(example: str) -> dict[str, Any]:
    return {
        "model": ErrorEnvelope,
        "content": {"application/json": {"examples": {example: _ERROR_EXAMPLES[example]}}},
    }


def _rate_limit_response() -> dict[str, Any]:
    response = _error_response("rate_limited")
    response["headers"] = {
        "Retry-After": {
            "description": "Positive whole seconds until one request token is available.",
            "required": True,
            "schema": {"type": "integer", "minimum": 1},
        },
        "Cache-Control": {
            "description": "Prevents storage of a rate-limit response.",
            "required": True,
            "schema": {"type": "string", "example": "no-store"},
        },
    }
    return response


def _cursor_validation_response() -> dict[str, Any]:
    """Document the fixed opaque-token rejection alongside ordinary query validation."""
    return {
        "model": ErrorEnvelope,
        "content": {
            "application/json": {
                "examples": {
                    "validation": _ERROR_EXAMPLES["validation"],
                    "invalid_cursor": {
                        "summary": "Opaque cursor rejection",
                        "value": {
                            "error": {
                                "code": "invalid_cursor",
                                "message": "Cursor is invalid or expired.",
                                "details": None,
                            }
                        },
                    },
                }
            }
        },
    }


_CREATE_RESPONSES: dict[int | str, dict[str, Any]] = {
    429: _rate_limit_response(),
    401: _error_response("authentication"),
    422: _error_response("validation"),
    500: _error_response("internal"),
}
_LIST_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Owner-scoped bookmarks; cursor mode may include X-Next-Cursor.",
        "headers": {
            "X-Next-Cursor": {
                "description": (
                    "Opaque continuation cursor for pagination=cursor; absent when no further "
                    "page exists."
                ),
                "required": False,
                "schema": {"type": "string", "maxLength": 2048},
            }
        },
    },
    429: _rate_limit_response(),
    401: _error_response("authentication"),
    422: _cursor_validation_response(),
    500: _error_response("internal"),
}
_STATS_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Current owner-scoped statistics from a snapshot or live SQL.",
        "headers": {
            "X-Stats-Source": {
                "description": "The canonical body source.",
                "required": True,
                "schema": {"type": "string", "enum": ["snapshot", "live"]},
            },
            "X-Stats-Generated-At": {
                "description": "UTC snapshot generation time; absent for live SQL.",
                "required": False,
                "schema": {"type": "string"},
            },
        },
    },
    429: _rate_limit_response(),
    401: _error_response("authentication"),
    500: _error_response("internal"),
}
_DETAIL_RESPONSES: dict[int | str, dict[str, Any]] = {
    429: _rate_limit_response(),
    401: _error_response("authentication"),
    404: _error_response("not_found"),
    422: _error_response("validation"),
    500: _error_response("internal"),
}
_DELETE_RESPONSES: dict[int | str, dict[str, Any]] = {
    204: {"description": "Bookmark deleted successfully; the response has no body."},
    429: _rate_limit_response(),
    401: _error_response("authentication"),
    404: _error_response("not_found"),
    422: _error_response("validation"),
    500: _error_response("internal"),
}

router = APIRouter(prefix="/api/bookmarks", tags=["bookmarks"])


def get_bookmark_query(
    request: Request,
    tag: Annotated[str | None, Query(examples=["python"])] = None,
    q: Annotated[str | None, Query(max_length=200, examples=["fictional search"])] = None,
    created_from: Annotated[
        str | None,
        Query(
            alias="from",
            examples=["2025-01-01"],
            json_schema_extra={"anyOf": [{"type": "string", "format": "date"}, {"type": "null"}]},
        ),
    ] = None,
    created_to: Annotated[
        str | None,
        Query(
            alias="to",
            examples=["2025-12-31"],
            json_schema_extra={"anyOf": [{"type": "string", "format": "date"}, {"type": "null"}]},
        ),
    ] = None,
    updated_from: Annotated[
        str | None,
        Query(
            examples=["2025-01-01"],
            json_schema_extra={"anyOf": [{"type": "string", "format": "date"}, {"type": "null"}]},
        ),
    ] = None,
    updated_to: Annotated[
        str | None,
        Query(
            examples=["2025-12-31"],
            json_schema_extra={"anyOf": [{"type": "string", "format": "date"}, {"type": "null"}]},
        ),
    ] = None,
    page: Annotated[
        object,
        Query(
            json_schema_extra={"type": "integer", "minimum": 1, "examples": [1], "default": 1},
        ),
    ] = 1,
    page_size: Annotated[
        object,
        Query(
            json_schema_extra={
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
                "examples": [20],
                "default": 20,
            },
        ),
    ] = 20,
) -> BookmarkQuery:
    """Retain strict legacy raw-query parsing while adding independent cursor controls."""
    try:
        return BookmarkQuery.model_validate(_raw_bookmark_query_values(request))
    except ValidationError as error:
        details = request_validation_issues(RequestValidationError(_query_validation_errors(error)))
        raise ValidationApplicationError(details=details) from None


def _raw_bookmark_query_values(request: Request) -> dict[str, str | None]:
    """Pass every legacy query key to the strict DTO, excluding cursor-only controls."""
    date_filters = frozenset({"from", "to", "updated_from", "updated_to"})
    cursor_controls = frozenset({"pagination", "cursor"})
    return {
        key: _nullable_date_query(value) if key in date_filters else value
        for key, value in request.query_params.items()
        if key not in cursor_controls
    }


def _nullable_date_query(value: str | None) -> str | None:
    """Treat OpenAPI's serialized nullable query literal as an absent optional date."""
    return None if value == "null" else value


def _query_validation_errors(error: ValidationError) -> list[dict[str, object]]:
    """Prefix Pydantic issues for the existing safe framework-error translation boundary."""
    errors: list[dict[str, object]] = []
    for item in error.errors()[:20]:
        location = item.get("loc")
        suffix = tuple(location) if isinstance(location, tuple | list) else ("invalid",)
        errors.append({"loc": ("query", *suffix), "type": item.get("type")})
    return errors or [{"loc": ("query", "invalid"), "type": "invalid"}]


def _mode_validation_error(field: str) -> ValidationApplicationError:
    """Use the established safe validation envelope for mutually exclusive controls."""
    return ValidationApplicationError(
        details=(
            ValidationIssue(loc=("query", field), type="value_error", message="Invalid value"),
        )
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=BookmarkPublic,
    responses=_CREATE_RESPONSES,
    summary="Create a bookmark",
)
def create_bookmark(
    payload: BookmarkCreate,
    subject: Annotated[CurrentSubject, Depends(get_rate_limited_subject)],
    service: Annotated[BookmarkService, Depends(get_bookmark_service)],
) -> BookmarkPublic:
    """Create a bookmark for the authenticated subject only."""
    return service.create(subject.user_id, payload)


@router.get(
    "",
    response_model=BookmarkList,
    responses=_LIST_RESPONSES,
    summary="List the authenticated subject's bookmarks",
)
def list_bookmarks(
    request: Request,
    response: Response,
    subject: Annotated[CurrentSubject, Depends(get_rate_limited_subject)],
    query: Annotated[BookmarkQuery, Depends(get_bookmark_query)],
    codec: Annotated[BookmarkCursorCodec, Depends(get_bookmark_cursor_codec)],
    service: Annotated[BookmarkService, Depends(get_bookmark_service)],
    pagination: Annotated[
        Literal["page", "cursor"],
        Query(
            description=(
                "Pagination strategy. Page mode is the default and forbids cursor; cursor mode "
                "forbids an explicitly supplied page."
            ),
            examples=["page", "cursor"],
        ),
    ] = "page",
    cursor: Annotated[
        str | None,
        Query(
            description=(
                "Opaque owner- and filter-bound continuation token, accepted only when "
                "pagination=cursor."
            ),
            examples=["eyJjYSI6IjIwMjYtMDEtMDFUMDA6MDA6MDAuMDAwMDAwWiJ9.signature"],
            json_schema_extra={"maxLength": 2048},
        ),
    ] = None,
) -> BookmarkList:
    """Return a legacy offset page or a stable authenticated keyset page."""
    if pagination == "page":
        if cursor is not None:
            raise _mode_validation_error("cursor")
        return service.list(subject.user_id, query)
    if "page" in request.query_params:
        raise _mode_validation_error("page")
    result = service.list_cursor(subject.user_id, query, cursor=cursor, codec=codec)
    if result.next_cursor is not None:
        response.headers["X-Next-Cursor"] = result.next_cursor
    return result.body


@router.get(
    "/stats",
    response_model=BookmarkStats,
    responses=_STATS_RESPONSES,
    summary="Read current bookmark statistics",
)
def get_bookmark_stats(
    response: Response,
    subject: Annotated[CurrentSubject, Depends(get_rate_limited_subject)],
    service: Annotated[CurrentStatsService, Depends(get_bookmark_stats_service)],
) -> BookmarkStats:
    """Return exact current aggregates with transport-only source metadata."""
    result = service.read(subject.user_id)
    response.headers["X-Stats-Source"] = result.source.value
    if result.source is StatsSource.SNAPSHOT:
        response.headers["X-Stats-Generated-At"] = stats_generated_at_header(
            cast(datetime, result.generated_at)
        )
    return result.stats


# Keep dynamic detail routes after collection routes so Track 04 can insert /stats first.
@router.get(
    "/{bookmark_id}",
    response_model=BookmarkPublic,
    responses=_DETAIL_RESPONSES,
    summary="Get an owned bookmark",
)
def get_bookmark(
    bookmark_id: Annotated[int, Path(gt=0, examples=[1])],
    subject: Annotated[CurrentSubject, Depends(get_rate_limited_subject)],
    service: Annotated[BookmarkService, Depends(get_bookmark_service)],
) -> BookmarkPublic:
    """Return an owned bookmark or the shared concealed not-found response."""
    return service.get(subject.user_id, bookmark_id)


@router.patch(
    "/{bookmark_id}",
    response_model=BookmarkPublic,
    responses=_DETAIL_RESPONSES,
    summary="Patch an owned bookmark",
)
def patch_bookmark(
    bookmark_id: Annotated[int, Path(gt=0, examples=[1])],
    payload: BookmarkPatch,
    subject: Annotated[CurrentSubject, Depends(get_rate_limited_subject)],
    service: Annotated[BookmarkService, Depends(get_bookmark_service)],
) -> BookmarkPublic:
    """Apply a material partial update to an owned bookmark."""
    return service.patch(subject.user_id, bookmark_id, payload)


@router.delete(
    "/{bookmark_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_DELETE_RESPONSES,
    summary="Delete an owned bookmark",
    description="Delete an owned bookmark and return HTTP 204 with no response body.",
)
def delete_bookmark(
    bookmark_id: Annotated[int, Path(gt=0, examples=[1])],
    subject: Annotated[CurrentSubject, Depends(get_rate_limited_subject)],
    service: Annotated[BookmarkService, Depends(get_bookmark_service)],
) -> Response:
    """Delete an owned bookmark and return an explicitly bodyless response."""
    service.delete(subject.user_id, bookmark_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
