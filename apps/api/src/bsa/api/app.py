"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from bsa import __version__
from bsa.api.schemas import HealthOut
from bsa.api.v1 import api_router
from bsa.core.config import Environment, Settings, get_settings
from bsa.core.errors import BsaError
from bsa.core.logging import configure_logging, get_logger
from bsa.db.session import get_engine

log = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, json_output=settings.env is not Environment.DEVELOPMENT)

    app = FastAPI(
        title="Baseball Analytics API",
        version=__version__,
        description=(
            "Internal player analytics for a baseball training facility. "
            "All athlete access is authorized server-side and scoped to one organization."
        ),
        docs_url="/docs" if settings.env is not Environment.PRODUCTION else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.env is not Environment.PRODUCTION else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def bind_request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Any]]
    ) -> Any:
        """Tag every log line in a request with its path and method."""
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(path=request.url.path, method=request.method)
        try:
            return await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()

    @app.exception_handler(BsaError)
    async def handle_bsa_error(_request: Request, exc: BsaError) -> JSONResponse:
        """Single translation point from domain errors to HTTP.

        Services and domain code raise plain exceptions and never import
        FastAPI, which keeps the business logic usable from CLI jobs too.
        """
        if exc.status_code >= 500:
            log.error("request.failed", code=exc.code, message=exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, **exc.details}},
        )

    @app.get("/health", response_model=HealthOut, tags=["health"])
    def health() -> HealthOut:
        """Liveness plus a real database round-trip.

        Cloud Run will route traffic to an instance that answers here, so a
        healthy reply that cannot reach Postgres would be worse than useless.
        """
        database = "ok"
        try:
            with get_engine().connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception as exc:
            database = f"error: {type(exc).__name__}"
        return HealthOut(
            status="ok" if database == "ok" else "degraded",
            version=__version__,
            environment=settings.env.value,
            database=database,
        )

    app.include_router(api_router)
    return app


app = create_app()
