"""FastAPI application factory: middleware, CORS, error handlers, lifespan."""

from __future__ import annotations

import datetime as dt
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import AppError, ErrorCode, code_for_status
from app.core.logging_config import configure_logging, get_logger
from app.core.redis_client import get_cache, reset_cache
from app.db.session import dispose_engine
from app.schemas.common import ErrorDetail
from app.services import media_service
from app.worker.scheduler import shutdown_scheduler, start_scheduler

configure_logging()
logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


def error_payload(
    *,
    status_code: int,
    code: ErrorCode,
    message: str,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """The one and only error shape emitted by the API."""
    return {
        "status_code": status_code,
        "code": code.value if isinstance(code, ErrorCode) else str(code),
        "message": message,
        "details": details,
        "request_id": request_id,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a request id, time the handler, and emit one structured access log."""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.exception(
                "request_failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                },
            )
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "user_id": getattr(getattr(request.state, "current_user", None), "id", None),
            },
        )
        return response


def register_exception_handlers(app: FastAPI) -> None:
    """Map every failure mode onto the shared error envelope."""

    def _request_id(request: Request) -> str | None:
        return getattr(request.state, "request_id", None)

    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        level = logger.warning if exc.status_code < 500 else logger.error
        level(
            "app_error",
            extra={
                "request_id": _request_id(request),
                "code": exc.code.value,
                "status_code": exc.status_code,
                "path": request.url.path,
            },
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(
                status_code=exc.status_code,
                code=exc.code,
                message=exc.message,
                details=exc.details,
                request_id=_request_id(request),
            ),
            headers=exc.headers or None,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {
                "location": ".".join(str(part) for part in error.get("loc", ())),
                "message": error.get("msg", "invalid value"),
                "type": error.get("type", "value_error"),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_payload(
                status_code=422,
                code=ErrorCode.VALIDATION_ERROR,
                message="Request validation failed",
                details={"fields": fields},
                request_id=_request_id(request),
            ),
        )

    @app.exception_handler(ResponseValidationError)
    async def _response_validation_error(
        request: Request, exc: ResponseValidationError
    ) -> JSONResponse:
        logger.error(
            "response_validation_error",
            extra={"request_id": _request_id(request), "path": request.url.path, "errors": str(exc)},
        )
        return JSONResponse(
            status_code=500,
            content=error_payload(
                status_code=500,
                code=ErrorCode.INTERNAL_ERROR,
                message="The server produced an invalid response",
                request_id=_request_id(request),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = code_for_status(exc.status_code)
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(
                status_code=exc.status_code,
                code=code,
                message=message,
                request_id=_request_id(request),
            ),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(IntegrityError)
    async def _integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning(
            "integrity_error",
            extra={
                "request_id": _request_id(request),
                "path": request.url.path,
                "error": str(getattr(exc, "orig", exc)),
            },
        )
        return JSONResponse(
            status_code=409,
            content=error_payload(
                status_code=409,
                code=ErrorCode.CONFLICT,
                message="The request conflicts with existing data",
                request_id=_request_id(request),
            ),
        )

    @app.exception_handler(SQLAlchemyError)
    async def _db_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.error(
            "database_error",
            extra={"request_id": _request_id(request), "path": request.url.path, "error": str(exc)},
        )
        return JSONResponse(
            status_code=503,
            content=error_payload(
                status_code=503,
                code=ErrorCode.DATABASE_ERROR,
                message="The database is temporarily unavailable",
                request_id=_request_id(request),
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled_exception",
            extra={"request_id": _request_id(request), "path": request.url.path},
        )
        return JSONResponse(
            status_code=500,
            content=error_payload(
                status_code=500,
                code=ErrorCode.INTERNAL_ERROR,
                message="Internal server error",
                request_id=_request_id(request),
            ),
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    cache = await get_cache()
    logger.info(
        "startup",
        extra={
            "env": settings.app_env,
            "cache_backend": cache.kind,
            "chatbot_enabled": settings.chatbot_enabled,
            "cors_origins": settings.cors_origin_list,
        },
    )
    media_service.media_root().mkdir(parents=True, exist_ok=True)
    start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()
        await reset_cache()
        await dispose_engine()
        logger.info("shutdown", extra={})


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Fan Hub Plus backend - a fandom content platform for Anime, Gaming, Movies, "
            "TV Shows, K-Pop, Comics, Manga and Cosplay.\n\n"
            "**Access tiers**: `Visitor` (public GETs), `Registered` (JWT), `Admin` "
            "(JWT + role=admin). Errors always use the envelope "
            "`{status_code, code, message, details, request_id, timestamp}`."
        ),
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    app.mount(
        "/media",
        StaticFiles(directory=str(media_service.media_root()), check_dir=False),
        name="media",
    )

    @app.get("/", tags=["system"], summary="API root")
    async def root() -> dict[str, Any]:
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs" if settings.docs_enabled else None,
            "api": settings.api_v1_prefix,
        }

    _install_error_contract(app)
    return app


#: Status codes that always return the shared error envelope, so Swagger shows
#: one predictable shape for every failure instead of FastAPI's default 422 body.
_ERROR_STATUSES = (400, 401, 403, 404, 409, 422, 429, 500, 503)


def _install_error_contract(app: FastAPI) -> None:
    """Document the global error envelope on every operation."""
    from fastapi.openapi.utils import get_openapi

    original_openapi = app.openapi

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        components.setdefault(
            "ErrorDetail",
            ErrorDetail.model_json_schema(ref_template="#/components/schemas/{model}"),
        )

        error_ref = {
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorDetail"}}}
        }
        for operation in schema.get("paths", {}).values():
            for method in ("get", "post", "put", "patch", "delete"):
                op = operation.get(method)
                if not isinstance(op, dict):
                    continue
                responses = op.setdefault("responses", {})
                for code in _ERROR_STATUSES:
                    if code not in responses:
                        responses[str(code)] = dict(error_ref)
                for code, existing in list(responses.items()):
                    if code.startswith(("4", "5")) and not existing.get("content"):
                        responses[code] = dict(error_ref)

        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
    assert original_openapi is not None


app = create_app()
