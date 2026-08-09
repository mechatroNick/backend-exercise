"""Request-scoped authentication composition for HTTP transport."""

from __future__ import annotations

import logging
from collections.abc import Generator
from typing import Annotated, cast

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.api.rate_limit import RateLimitDecision, RateLimiter
from app.auth.repository import UserRepository
from app.auth.schemas import CurrentSubject
from app.auth.security import AccessTokenCodec
from app.auth.service import AuthService
from app.core.errors import AuthenticationError, RateLimitError
from app.core.logging import log_event
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


def _rate_limiter(request: Request) -> RateLimiter:
    """Resolve the process-local limiter assembled by the application composition root."""
    limiter = request.app.state.rate_limiter
    if not isinstance(limiter, RateLimiter):
        raise RuntimeError("application rate limiter is unavailable")
    return limiter


def _raise_when_limited(
    request: Request,
    *,
    decision: RateLimitDecision,
    policy: str,
    route_family: str,
) -> None:
    """Emit a bounded opaque-key event before translating a safe limiter rejection."""
    if decision.allowed:
        return
    retry_after = decision.retry_after or 1
    if decision.emit_rejection_event:
        log_event(
            request.app.state.logger,
            logging.WARNING,
            "rate_limit.rejected",
            message="request rate limited",
            component="http",
            context={
                "policy": policy,
                "retry_after_seconds": retry_after,
                "route_family": route_family,
                "capacity_exhausted": decision.capacity_exhausted,
            },
            stacklevel=2,
        )
    raise RateLimitError(retry_after)


def enforce_auth_rate_limit(request: Request) -> None:
    """Apply the public auth policy to the socket peer, never forwarded headers."""
    peer_ip = request.client.host if request.client is not None else "unknown"
    decision = _rate_limiter(request).consume_auth(peer_ip)
    _raise_when_limited(
        request,
        decision=decision,
        policy="auth",
        route_family="authentication",
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


def get_rate_limited_subject(
    request: Request,
    subject: Annotated[CurrentSubject, Depends(get_current_subject)],
) -> CurrentSubject:
    """Apply the shared bookmark policy only after authentication has succeeded."""
    decision = _rate_limiter(request).consume_bookmark(subject.user_id)
    _raise_when_limited(
        request,
        decision=decision,
        policy="bookmark",
        route_family="bookmarks",
    )
    return subject


__all__ = [
    "bearer_scheme",
    "get_auth_service",
    "get_current_subject",
    "get_rate_limited_subject",
    "enforce_auth_rate_limit",
    "get_session",
]
