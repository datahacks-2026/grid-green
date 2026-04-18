"""FastAPI entry point."""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import get_settings
from app.routes import context, grid, health, stubs
from app.services.limits import limiter


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # httpx logs the full request URL which leaks ?api_key=… in query params.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    app = FastAPI(
        title="GridGreen Backend",
        description="Carbon-aware copilot for ML engineers — Person A slice.",
        version="0.1.0",
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
    app.add_middleware(SlowAPIMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _request_timeout(request: Request, call_next):  # noqa: ANN001
        try:
            return await asyncio.wait_for(
                call_next(request), timeout=settings.request_timeout_s
            )
        except asyncio.TimeoutError:
            return JSONResponse(
                {"detail": f"Request exceeded {settings.request_timeout_s}s timeout."},
                status_code=504,
            )

    @app.middleware("http")
    async def _server_timing(request: Request, call_next):  # noqa: ANN001
        start = time.perf_counter()
        response = await call_next(request)
        dur_ms = (time.perf_counter() - start) * 1000
        response.headers["Server-Timing"] = f"app;dur={dur_ms:.1f}"
        return response

    app.include_router(health.router)
    app.include_router(grid.router)
    app.include_router(stubs.router)
    app.include_router(context.router)
    return app


def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:  # noqa: ARG001
    return JSONResponse(
        {"detail": f"Rate limit exceeded: {exc.detail}"}, status_code=429
    )


app = create_app()
"""FastAPI entrypoint.

Person B's routes live here today. Person A merges their estimate/grid
routers via `app.include_router(...)` — no other change required.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import scorecard, suggest

load_dotenv()

app = FastAPI(title="GridGreen API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o.strip()
        for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
        if o.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/ping")
def ping() -> dict[str, bool]:
    return {"ok": True}


app.include_router(suggest.router, prefix="/api")
app.include_router(scorecard.router, prefix="/api")

# When Person A is ready, they uncomment one line each:
# from app.routes import estimate, grid
# app.include_router(estimate.router, prefix="/api")
# app.include_router(grid.router, prefix="/api")
