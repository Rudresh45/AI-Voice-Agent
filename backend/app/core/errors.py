"""Standardized error hierarchy and FastAPI exception handlers."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.logging import logger, request_id_ctx
from app.db.tenant_scope import TenantAccessDeniedError


class AppException(Exception):
    """Base application exception with HTTP status and structured error code."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        error_code: str = "BAD_REQUEST",
        details: Any = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details


class EntityNotFoundError(AppException):
    def __init__(self, entity_name: str, entity_id: Any):
        super().__init__(
            message=f"{entity_name} with identifier '{entity_id}' not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="ENTITY_NOT_FOUND",
            details={"entity": entity_name, "id": str(entity_id)},
        )


class PermissionDeniedError(AppException):
    def __init__(self, message: str = "Access denied for this resource."):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="PERMISSION_DENIED",
        )


class ConflictError(AppException):
    def __init__(self, message: str, details: Any = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            error_code="CONFLICT",
            details=details,
        )


def make_error_envelope(code: str, message: str, details: Any = None) -> dict[str, Any]:
    """Format standardized JSON error envelope."""
    req_id = request_id_ctx.get() or "unknown"
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": req_id,
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    """Register uniform exception handlers across the application."""

    @app.exception_handler(AppException)
    async def app_exception_handler(_: Request, exc: AppException) -> JSONResponse:
        logger.warning("Application error [%s]: %s", exc.error_code, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content=make_error_envelope(exc.error_code, exc.message, exc.details),
        )

    @app.exception_handler(TenantAccessDeniedError)
    async def tenant_access_denied_handler(_: Request, exc: TenantAccessDeniedError) -> JSONResponse:
        logger.warning("Tenant isolation violation: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=make_error_envelope(
                code="TENANT_ACCESS_DENIED",
                message="Tenant is not authorized to access this resource.",
                details={"tenant_id": str(exc.tenant_id), "entity": exc.entity_name},
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        logger.info("Request validation failed: %s", exc.errors())
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=make_error_envelope(
                code="VALIDATION_ERROR",
                message="Request input validation failed.",
                details=exc.errors(),
            ),
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(_: Request, exc: IntegrityError) -> JSONResponse:
        logger.error("Database constraint integrity violation: %s", exc)
        # Never leak raw SQL query strings or internal DB schema details
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=make_error_envelope(
                code="INTEGRITY_VIOLATION",
                message="Database constraint or unique key violation occurred.",
            ),
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.error("Database internal execution error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=make_error_envelope(
                code="DATABASE_ERROR",
                message="An internal database error occurred. The operation could not be completed.",
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled server exception: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=make_error_envelope(
                code="INTERNAL_SERVER_ERROR",
                message="An unexpected server error occurred.",
            ),
        )
