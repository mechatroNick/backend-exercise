"""Request-scoped authentication composition for HTTP transport."""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated, cast

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.auth.repository import UserRepository
from app.auth.schemas import CurrentSubject
from app.auth.security import AccessTokenCodec
from app.auth.service import AuthService
from app.core.errors import AuthenticationError
from app.db.engine import SessionFactory, session_scope

bearer_scheme = HTTPBearer(auto_error=False, scheme_name="BearerAuth", bearerFormat="JWT")


def _session_factory(request: Request) -> SessionFactory:
    """Resolve the live application's session factory, never an import-time singleton."""
    factory = request.app.state.session_factory
    if not callable(factory):
        raise RuntimeError("application session factory is unavailable")
    return cast(SessionFactory, factory)


def get_session(request: Request) -> Generator[Session, None, None]:
    """Yield a short-lived session with rollback and close owned by ``session_scope``."""
    with session_scope(_session_factory(request)) as session:
        yield session


def get_auth_service(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> AuthService:
    """Compose the transport-independent auth service from live application state."""
    return AuthService(
        session=session,
        repository=UserRepository(session),
        password_hasher=request.app.state.password_hasher,
        token_codec=request.app.state.token_codec,
        clock=request.app.state.clock,
    )


def _canonical_subject_id(value: str) -> int:
    """Accept only the canonical ASCII-decimal encoding emitted for durable user ids."""
    if not value or not value.isascii() or not value.isdecimal() or value[0] == "0":
        raise AuthenticationError() from None
    try:
        identifier = int(value)
    except ValueError:
        raise AuthenticationError() from None
    return identifier


def get_current_subject(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> CurrentSubject:
    """Resolve a verified bearer credential to an extant durable subject."""
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise AuthenticationError() from None
    codec: AccessTokenCodec = request.app.state.token_codec
    user_id = _canonical_subject_id(codec.verify(credentials.credentials))
    if UserRepository(session).find_by_id(user_id) is None:
        raise AuthenticationError() from None
    return CurrentSubject(user_id=user_id)


__all__ = [
    "bearer_scheme",
    "get_auth_service",
    "get_current_subject",
    "get_session",
]
