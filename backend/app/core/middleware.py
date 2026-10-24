"""Middleware for request ID injection, structured request logging, and CORS."""

from __future__ import annotations

import time
import uuid

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.logging import logger, request_id_ctx


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns or propagates X-Request-ID and logs incoming HTTP transactions."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_ctx.set(req_id)
        request.state.request_id = req_id

        start_time = time.perf_counter()
        logger.info("--> %s %s", request.method, request.url.path)

        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            response.headers["X-Request-ID"] = req_id
            logger.info("<-- %s %s [%d] (%sms)", request.method, request.url.path, response.status_code, duration_ms)
            return response
        except Exception:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.exception("XXX %s %s failed after %sms", request.method, request.url.path, duration_ms)
            raise
        finally:
            request_id_ctx.reset(token)


def setup_middleware(app: FastAPI) -> None:
    """Configure CORS and request context middleware."""
    # 1. Context and logging middleware
    app.add_middleware(RequestContextMiddleware)

    # 2. CORS configuration with explicit production origins
    if settings.app_env == "production":
        allowed_origins = [settings.frontend_url]
    else:
        allowed_origins = [
            settings.frontend_url,
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS", "HEAD"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Tenant-ID", "X-User-ID"],
    )
