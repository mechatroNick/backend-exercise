"""Thin JSON HTTP transport for Track 02 authentication operations."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI

from app.api.errors import ErrorEnvelope
from app.auth.dependencies import get_auth_service, get_current_subject
from app.auth.schemas import AuthResponse, CurrentSubject, LoginRequest, RegisterRequest
from app.auth.service import AuthService
from app.core.config import Settings

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
    "conflict": {
        "summary": "Canonical identity conflict",
        "value": {
            "error": {
                "code": "identity_conflict",
                "message": "Username or email is already registered.",
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
                    {"loc": ["body", "email"], "type": "value_error", "message": "Invalid value"}
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


_REGISTER_RESPONSES: dict[int | str, dict[str, Any]] = {
    409: _error_response("conflict"),
    422: _error_response("validation"),
    500: _error_response("internal"),
}
_LOGIN_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: _error_response("authentication"),
    422: _error_response("validation"),
    500: _error_response("internal"),
}

router = APIRouter(prefix="/api/auth", tags=["authentication"])


@router.post(
    "/register",
    status_code=201,
    response_model=AuthResponse,
    responses=_REGISTER_RESPONSES,
    summary="Register a user",
)
def register(
    payload: RegisterRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthResponse:
    """Register one canonical identity and return its public access response."""
    return service.register(
        username=payload.username,
        email=payload.email,
        password=payload.password.get_secret_value(),
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    responses=_LOGIN_RESPONSES,
    summary="Log in",
)
def login(
    payload: LoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthResponse:
    """Authenticate without disclosing whether the submitted email exists."""
    return service.login(email=payload.email, password=payload.password.get_secret_value())


def install_test_protected_route(app: FastAPI, app_settings: Settings) -> None:
    """Register the non-public process-harness seam only in the test environment."""
    if app_settings.app_env != "test":
        return

    @app.get("/__track02/protected", include_in_schema=False)
    def track02_protected(
        subject: Annotated[CurrentSubject, Depends(get_current_subject)],
    ) -> dict[str, int]:
        return {"user_id": subject.user_id}


__all__ = ["install_test_protected_route", "router"]
