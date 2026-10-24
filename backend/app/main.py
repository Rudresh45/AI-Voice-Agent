"""Main application entrypoint for the AI Voice Agent Platform API."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, FastAPI, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.api.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import setup_middleware

# Initialize structured logging
setup_logging(log_level=settings.log_level)
logger = logging.getLogger(__name__)

# Create FastAPI application instance with OpenAPI metadata
app = FastAPI(
    title=settings.app_name,
    description="Enterprise Multi-Tenant AI Voice Platform API with domain-driven design, tenant scoping, and real-time voice integration readiness.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Register middlewares (RequestContextMiddleware, CORS)
setup_middleware(app)

# Register centralized error handlers
register_exception_handlers(app)

# Mount consolidated v1 API router
app.include_router(api_router)


# Liveness Probe: Quick, unconditional check that process is responding
@app.get("/health/live", tags=["Health"], summary="Liveness check")
def liveness() -> dict[str, str]:
    """Kubernetes/container liveness probe confirming server event loop is alive."""
    return {"status": "alive"}


# Readiness Probe: Deep check of critical dependencies (Database connectivity)
@app.get("/health/ready", tags=["Health"], summary="Readiness check")
def readiness(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    """Readiness probe ensuring database connection is active and responsive."""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as exc:  # noqa: BLE001
        logger.error("Readiness check database failure: %s", exc)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unhealthy", "database": "disconnected"}
