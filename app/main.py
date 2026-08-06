"""FastAPI composition root for the foundation application."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.openapi.utils import get_openapi
from sqlalchemy import Engine

from app.api.errors import register_exception_handlers, unexpected_error_response
from app.auth.passwords import PasswordHasher
from app.auth.router import install_test_protected_route
from app.auth.router import router as auth_router
from app.auth.security import AccessTokenCodec
from app.bookmarks.router import router as bookmarks_router
from app.core.clock import SystemClock
from app.core.config import Settings
from app.core.logging import configure_logging, log_event, log_exception
from app.db.engine import create_database_engine, create_session_factory

_APPLICATION_NAME = "Bookmarks API"
_APPLICATION_VERSION = "0.1.0"
_RequestHandler = Callable[[Request], Awaitable[Response]]


def _install_openapi_security_scheme(app: FastAPI) -> None:
    """Publish the reusable bearer component without inventing a public protected route."""

    def openapi() -> dict[str, object]:
        if app.openapi_schema is None:
            schema = get_openapi(
                title=app.title,
                version=app.version,
                description=app.description,
                routes=app.routes,
            )
            components = schema.setdefault("components", {})
            security_schemes = components.setdefault("securitySchemes", {})
            security_schemes["BearerAuth"] = {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
            }
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Assemble and dispose runtime-owned infrastructure without mutating schema."""
    settings: Settings = app.state.settings
    logger = configure_logging(settings, component="lifecycle")
    app.state.logger = logger
    log_event(
        logger,
        logging.INFO,
        "application.starting",
        message="application starting",
        component="lifecycle",
    )
    engine: Engine | None = None
    try:
        engine = create_database_engine(settings)
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        app.state.clock = SystemClock()
        app.state.password_hasher = PasswordHasher()
        app.state.password_hasher.dummy_hash()
        app.state.token_codec = AccessTokenCodec(
            secret=settings.jwt_secret,
            ttl=timedelta(minutes=settings.access_token_ttl_minutes),
            clock=app.state.clock,
        )
    except Exception as error:
        log_exception(
            logger,
            "application.startup_failed",
            exception=error,
            message="application startup failed",
            component="lifecycle",
        )
        if engine is not None:
            engine.dispose()
        raise
    try:
        log_event(
            logger,
            logging.INFO,
            "application.started",
            message="application started",
            component="lifecycle",
        )
        yield
    finally:
        log_event(
            logger,
            logging.INFO,
            "application.stopping",
            message="application stopping",
            component="lifecycle",
        )
        engine.dispose()
        log_event(
            logger,
            logging.INFO,
            "application.stopped",
            message="application stopped",
            component="lifecycle",
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an inert FastAPI application with explicit, injectable settings."""
    resolved_settings = settings if settings is not None else Settings()
    app = FastAPI(
        title=_APPLICATION_NAME,
        version=_APPLICATION_VERSION,
        description="Foundation runtime for the Bookmarks API.",
        lifespan=_lifespan,
    )
    app.state.settings = resolved_settings
    app.include_router(auth_router)
    app.include_router(bookmarks_router)
    install_test_protected_route(app, resolved_settings)
    _install_openapi_security_scheme(app)

    @app.middleware("http")
    async def unexpected_request_boundary(request: Request, call_next: _RequestHandler) -> Response:
        try:
            if (
                app.state.settings.app_env == "test"
                and request.headers.get("X-Track01-Harness-Fault") == "1"
            ):
                raise RuntimeError(
                    "track01-secret-sentinel-do-not-emit "
                    "track01-submitted-bookmark-sentinel-do-not-emit"
                )
            return await call_next(request)
        except Exception as error:
            log_exception(
                app.state.logger,
                "http.request.unexpected_exception",
                exception=error,
                message="unexpected HTTP request exception",
                context={"method": request.method},
                correlation_id=str(uuid4()),
                component="http",
            )
            return unexpected_error_response()

    register_exception_handlers(app)

    return app


__all__ = ["create_app"]
