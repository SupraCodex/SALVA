"""FastAPI application: API under /api/v1, the built web interface served at /."""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

from app import errors
from app import logging as app_logging
from app.api.v1 import router as v1
from app.config import get_settings

log = logging.getLogger("salva")

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


def create_app() -> FastAPI:
    settings = get_settings()
    app_logging.setup()
    app = FastAPI(
        title="SALVA API",
        version="1.0.0",
        description=(
            "Spoilage-Aware Logistics & Value Allocation: decision support for perishable produce.\n\n"
            "Every figure is a **model estimate, not validated on field data** "
            "(`disclaimer_code: MODEL_ESTIMATE_NOT_FIELD_VALIDATED`)."
        ),
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/docs",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Requested-With",
            "X-Request-ID",
        ],
        expose_headers=["X-Request-ID", "Retry-After"],
    )
    # Slow mobile networks (NFR-02): compress the interface bundle and JSON responses.
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    errors.install(app)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id", "")[:64] or f"req_{uuid.uuid4().hex[:12]}"
        request.state.request_id = rid
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > settings.max_body_bytes:
            response = errors.problem(request, 413, "payload-too-large", "Request body too large.")
        else:
            started = time.perf_counter()
            response = await call_next(request)
            log.info(
                "request",
                extra={
                    "request_id": rid,
                    "path": f"{request.method} {request.url.path}",
                    "status": response.status_code,
                    "ms": round((time.perf_counter() - started) * 1000, 1),
                    "user_id": getattr(request.state, "user_id", None),
                },
            )
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if settings.env == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/docs"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    app.include_router(v1)
    _mount_frontend(app, settings.frontend_dist)
    return app


class _ImmutableStatic(StaticFiles):
    """Bundles carry a content hash in their name, so browsers may keep them for a year."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the single-page interface built by `npm run build` (frontend/dist)."""
    index = dist / "index.html"
    if not index.exists():
        log.warning("frontend_not_built", extra={"path": str(dist)})
        return
    assets = dist / "assets"
    if assets.exists():
        app.mount("/assets", _ImmutableStatic(directory=assets), name="assets")
    root = dist.resolve()

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def spa(full_path: str, request: Request) -> Response:
        if full_path.startswith("api/"):
            return errors.problem(request, 404, "not-found", "Not found.")
        candidate = (root / full_path).resolve()
        if full_path and candidate.is_file() and root in candidate.parents:
            return FileResponse(candidate)
        response = FileResponse(index, media_type="text/html")
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Content-Security-Policy"] = CSP
        return response


app = create_app()
