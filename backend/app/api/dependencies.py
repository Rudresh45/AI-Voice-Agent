"""Authentication, authorization, session validation, and tenant resolution dependencies.

Security Invariants:
- A client-supplied tenant_id is NEVER trusted without database membership verification.
- Anonymous requests to protected resources are strictly rejected with 401 Unauthorized.
- Revoked and expired sessions are verified server-side and immediately rejected.
- RBAC rules prevent read-only roles from executing mutations (POST, PATCH, DELETE).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.errors import AppException, PermissionDeniedError
from app.core.security import SecurityRole, hash_session_token
from app.db.models import Membership, Tenant, TenantStatus, User, UserSession
from app.db.session import get_db


@dataclass(frozen=True)
class RequestContext:
    """Authenticated principal and verified tenant context."""

    user: User
    tenant: Tenant
    role: str
    session: UserSession | None = None


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def get_current_session_and_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header(description="Bearer token")] = None,
    x_user_id: Annotated[str | None, Header(alias="X-User-ID", description="Development user ID")] = None,
) -> tuple[User, UserSession | None]:
    """Resolve authenticated user and validate session status."""
    token: str | None = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()

    # 1. Bearer Token Session Validation
    if token:
        token_hash = hash_session_token(token)
        session_stmt = (
            select(UserSession)
            .where(UserSession.token_hash == token_hash)
            .options(selectinload(UserSession.user))
        )
        user_session = db.scalars(session_stmt).first()

        if user_session is not None:
            # Check revocation
            if user_session.is_revoked:
                raise AppException(
                    message="Session has been revoked. Please log in again.",
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    error_code="SESSION_REVOKED",
                )
            # Check expiry
            if _ensure_utc(user_session.expires_at) <= datetime.now(UTC):
                raise AppException(
                    message="Session has expired. Please log in again.",
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    error_code="SESSION_EXPIRED",
                )
            # Check user active status
            if not user_session.user.is_active:
                raise AppException(
                    message="User account is deactivated.",
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    error_code="USER_DEACTIVATED",
                )
            # Update last seen timestamp
            user_session.last_seen_at = datetime.now(UTC)
            db.flush()
            return user_session.user, user_session

        # In development mode only: allow direct UUID or identity lookup via bearer token
        if settings.app_env == "development":
            dev_user = _lookup_user_by_identifier(db, token)
            if dev_user is not None and dev_user.is_active:
                return dev_user, None

        raise AppException(
            message="Invalid or expired session token.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="UNAUTHORIZED",
        )

    # 2. Development-only X-User-ID fallback
    if x_user_id:
        if settings.app_env != "development":
            raise AppException(
                message="Header-based authentication is disabled in production.",
                status_code=status.HTTP_401_UNAUTHORIZED,
                error_code="UNAUTHORIZED",
            )
        dev_user = _lookup_user_by_identifier(db, x_user_id.strip())
        if dev_user is None or not dev_user.is_active:
            raise AppException(
                message="User identity not found or account is deactivated.",
                status_code=status.HTTP_401_UNAUTHORIZED,
                error_code="USER_NOT_FOUND",
            )
        return dev_user, None

    # 3. Anonymous request rejected
    raise AppException(
        message="Authentication credentials were not provided. Provide 'Authorization: Bearer <token>'.",
        status_code=status.HTTP_401_UNAUTHORIZED,
        error_code="UNAUTHORIZED",
    )


def _lookup_user_by_identifier(db: Session, identifier: str) -> User | None:
    """Helper to lookup user by UUID, external_id, or email."""
    try:
        user_uuid = uuid.UUID(identifier)
        return db.get(User, user_uuid)
    except ValueError:
        return db.scalars(
            select(User).where((User.external_id == identifier) | (User.email == identifier))
        ).first()


def get_current_user(
    principal: Annotated[tuple[User, UserSession | None], Depends(get_current_session_and_user)],
) -> User:
    """Dependency returning the authenticated User instance."""
    return principal[0]


def get_current_user_session(
    principal: Annotated[tuple[User, UserSession | None], Depends(get_current_session_and_user)],
) -> UserSession | None:
    """Dependency returning the active UserSession if session-authenticated."""
    return principal[1]


def get_current_tenant(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID", description="Target tenant ID")] = None,
) -> Tenant:
    """Resolve and verify the tenant boundary server-side.

    CRITICAL SECURITY CHECK:
    A tenant ID supplied by the client is NEVER trusted blindly. We assert that
    the authenticated user holds an active membership in the target tenant.
    """
    target_tenant_id: uuid.UUID | None = None
    if x_tenant_id:
        try:
            target_tenant_id = uuid.UUID(x_tenant_id.strip())
        except ValueError:
            raise AppException(
                message="Provided X-Tenant-ID is not a valid UUID.",
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="INVALID_TENANT_ID",
            )

    stmt = (
        select(Membership)
        .where(Membership.user_id == current_user.id, Membership.status == "active")
        .join(Tenant, Tenant.id == Membership.tenant_id)
        .where(Tenant.status == TenantStatus.ACTIVE.value)
    )

    if target_tenant_id is not None:
        stmt = stmt.where(Membership.tenant_id == target_tenant_id)

    membership = db.scalars(stmt).first()

    if membership is None:
        if target_tenant_id is not None:
            raise PermissionDeniedError("You do not hold an active membership in the specified tenant.")
        raise PermissionDeniedError("No active tenant membership found for current user.")

    tenant = db.get(Tenant, membership.tenant_id)
    if tenant is None:
        raise PermissionDeniedError("Tenant not found or has been removed.")

    return tenant


def get_request_context(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[tuple[User, UserSession | None], Depends(get_current_session_and_user)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
) -> RequestContext:
    """Provide combined authenticated user, verified tenant context, role, and active session."""
    user, session = principal
    stmt = select(Membership.role).where(
        Membership.user_id == user.id, Membership.tenant_id == tenant.id, Membership.status == "active"
    )
    role = db.scalars(stmt).first() or "member"
    return RequestContext(user=user, tenant=tenant, role=role, session=session)


# --- RBAC Authorization Dependencies ---

def require_write_access(
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> RequestContext:
    """Ensure principal possesses write authority (rejects read-only/viewer roles)."""
    if not SecurityRole.is_write_permitted(context.role):
        raise PermissionDeniedError(
            f"Role '{context.role}' (read-only) is not authorized to perform write operations."
        )
    return context


def require_admin_access(
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> RequestContext:
    """Ensure principal possesses tenant administrative authority."""
    if not (SecurityRole.is_admin_permitted(context.role) or context.user.is_platform_admin):
        raise PermissionDeniedError("Tenant administrator privileges required for this action.")
    return context


def require_platform_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Ensure principal possesses platform-level administrator authority."""
    if not current_user.is_platform_admin:
        raise PermissionDeniedError("Platform administrator privileges required.")
    return current_user
