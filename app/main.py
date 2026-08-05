"""FastAPI composition root for the foundation application."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from sqlalchemy import Engine

from app.core.config import Settings
from app.core.logging import configure_logging, log_event, log_exception
from app.db.engine import create_database_engine, create_session_factory

_APPLICATION_NAME = "Bookmarks API"
_APPLICATION_VERSION = "0.1.0"
_RequestHandler = Callable[[Request], Awaitable[Response]]


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
                component="http",
            )
            raise

    return app


__all__ = ["create_app"]
