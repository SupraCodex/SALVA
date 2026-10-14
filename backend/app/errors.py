"""Errors as application/problem+json (RFC 7807), always carrying the request id."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("salva")
TITLES = {
    400: "Bad request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not found",
    409: "Conflict",
    413: "Payload too large",
    422: "Validation failed",
    429: "Too many requests",
    500: "Internal error",
    503: "Service unavailable",
}


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        detail: str,
        errors: list[dict] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status, self.code, self.detail = status, code, detail
        self.errors, self.headers = errors or [], headers or {}


def not_found(entity: str) -> ApiError:
    """Also used for resources of another organization: never reveal that they exist."""
    return ApiError(404, "not-found", f"{entity} not found.")


def field_error(field: str, code: str, message: str) -> ApiError:
    return ApiError(
        422,
        "validation-error",
        "One or more fields are invalid.",
        [{"field": field, "code": code, "message": message}],
    )


def problem(
    request: Request,
    status: int,
    code: str,
    detail: str,
    errors: list[dict] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = {
        "type": f"https://salva.example/problems/{code}",
        "title": TITLES.get(status, "Error"),
        "status": status,
        "code": code,
        "detail": detail,
        "errors": errors or [],
        "request_id": getattr(request.state, "request_id", None),
    }
    return JSONResponse(body, status_code=status, media_type="application/problem+json", headers=headers)


def _field_name(loc: tuple) -> str | None:
    parts = [str(p) for p in loc if p not in ("body", "query", "path")]
    return ".".join(parts) or None


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api(request: Request, exc: ApiError):
        return problem(request, exc.status, exc.code, exc.detail, exc.errors, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        errors = []
        for e in exc.errors():
            message = str(e.get("msg", "invalid value"))
            errors.append(
                {
                    "field": _field_name(tuple(e.get("loc", ()))),
                    "code": e.get("type"),
                    "message": message.removeprefix("Value error, "),
                }
            )
        return problem(request, 422, "validation-error", "One or more fields are invalid.", errors)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        return problem(request, exc.status_code, "http-error", str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception(
            "unhandled_error",
            extra={"request_id": getattr(request.state, "request_id", None)},
        )
        return problem(request, 500, "internal-error", "Internal error.")
