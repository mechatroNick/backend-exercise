"""Protected JSON HTTP transport for owner-scoped bookmark CRUD."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.api.errors import ErrorEnvelope
from app.auth.dependencies import get_current_subject
from app.auth.schemas import CurrentSubject
from app.bookmarks.dependencies import get_bookmark_service, get_bookmark_stats_reader
from app.bookmarks.schemas import (
    BookmarkCreate,
    BookmarkList,
    BookmarkPatch,
    BookmarkPublic,
    BookmarkQuery,
)
from app.bookmarks.service import BookmarkService
from app.bookmarks.stats.raw_sql import BookmarkStatsReader
from app.bookmarks.stats.schemas import BookmarkStats

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
}


def _error_response(example: str) -> dict[str, Any]:
    return {
        "model": ErrorEnvelope,
        "content": {"application/json": {"examples": {example: _ERROR_EXAMPLES[example]}}},
    }


_CREATE_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: _error_response("authentication"),
    422: _error_response("validation"),
    500: _error_response("internal"),
}
_LIST_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: _error_response("authentication"),
    422: _error_response("validation"),
    500: _error_response("internal"),
}
_STATS_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: _error_response("authentication"),
    500: _error_response("internal"),
}
_DETAIL_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: _error_response("authentication"),
    404: _error_response("not_found"),
    422: _error_response("validation"),
    500: _error_response("internal"),
}
_DELETE_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: _error_response("authentication"),
    404: _error_response("not_found"),
    422: _error_response("validation"),
    500: _error_response("internal"),
}

router = APIRouter(prefix="/api/bookmarks", tags=["bookmarks"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=BookmarkPublic,
    responses=_CREATE_RESPONSES,
    summary="Create a bookmark",
)
def create_bookmark(
    payload: BookmarkCreate,
    subject: Annotated[CurrentSubject, Depends(get_current_subject)],
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
    subject: Annotated[CurrentSubject, Depends(get_current_subject)],
    query: Annotated[BookmarkQuery, Query()],
    service: Annotated[BookmarkService, Depends(get_bookmark_service)],
) -> BookmarkList:
    """Return the authenticated subject's filtered, stable collection page."""
    return service.list(subject.user_id, query)


@router.get(
    "/stats",
    response_model=BookmarkStats,
    responses=_STATS_RESPONSES,
    summary="Read current bookmark statistics",
)
def get_bookmark_stats(
    subject: Annotated[CurrentSubject, Depends(get_current_subject)],
    reader: Annotated[BookmarkStatsReader, Depends(get_bookmark_stats_reader)],
) -> BookmarkStats:
    """Return the current owner-scoped aggregates from one live read snapshot."""
    return reader.read(subject.user_id)


# Keep dynamic detail routes after collection routes so Track 04 can insert /stats first.
@router.get(
    "/{bookmark_id}",
    response_model=BookmarkPublic,
    responses=_DETAIL_RESPONSES,
    summary="Get an owned bookmark",
)
def get_bookmark(
    bookmark_id: Annotated[int, Path(gt=0)],
    subject: Annotated[CurrentSubject, Depends(get_current_subject)],
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
    bookmark_id: Annotated[int, Path(gt=0)],
    payload: BookmarkPatch,
    subject: Annotated[CurrentSubject, Depends(get_current_subject)],
    service: Annotated[BookmarkService, Depends(get_bookmark_service)],
) -> BookmarkPublic:
    """Apply a material partial update to an owned bookmark."""
    return service.patch(subject.user_id, bookmark_id, payload)


@router.delete(
    "/{bookmark_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_DELETE_RESPONSES,
    summary="Delete an owned bookmark",
)
def delete_bookmark(
    bookmark_id: Annotated[int, Path(gt=0)],
    subject: Annotated[CurrentSubject, Depends(get_current_subject)],
    service: Annotated[BookmarkService, Depends(get_bookmark_service)],
) -> Response:
    """Delete an owned bookmark and return an explicitly bodyless response."""
    service.delete(subject.user_id, bookmark_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
