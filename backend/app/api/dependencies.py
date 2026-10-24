"""Authentication, authorization, and tenant resolution dependencies.

Security Invariants:
- Never trust a client-supplied tenant_id without verifying membership.
- In production, user identity is extracted from a signed JWT / IdP token.
- For local development and automated testing, authentication resolves the user
  via Bearer token or development identity headers, and verifies that the user
  holds an active Membership in the target tenant before granting tenant access.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppException, PermissionDeniedError
from app.db.models import Membership, Tenant, TenantStatus, User
from app.db.session import get_db


@dataclass(frozen=True)
class RequestContext:
    """Authenticated principal and verified tenant context."""

    user: User
    tenant: Tenant
    role: str


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header(description="Bearer token or user identifier")] = None,
    x_user_id: Annotated[str | None, Header(alias="X-User-ID", description="Development user ID")] = None,
) -> User:
    """Resolve the current authenticated user identity.

    Checks Authorization: Bearer <token_or_id> or X-User-ID.
    """
    user_identifier: str | None = None

    if authorization and authorization.startswith("Bearer "):
        user_identifier = authorization.removeprefix("Bearer ").strip()
    elif x_user_id:
        user_identifier = x_user_id.strip()

    if not user_identifier:
        raise AppException(
            message="Authentication credentials were not provided. Provide 'Authorization: Bearer <id>' or 'X-User-ID'.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="UNAUTHORIZED",
        )

    # Lookup user by UUID id, external_id, or email
    user: User | None = None
    try:
        user_uuid = uuid.UUID(user_identifier)
        user = db.get(User, user_uuid)
    except ValueError:
        user = db.scalars(
            select(User).where((User.external_id == user_identifier) | (User.email == user_identifier))
        ).first()

    if user is None or not user.is_active:
        raise AppException(
            message="User identity not found or account is deactivated.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="USER_NOT_FOUND",
        )

    return user


def get_current_tenant(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID", description="Target tenant ID")] = None,
) -> Tenant:
    """Resolve and verify the tenant boundary.

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

    # Query memberships for this user
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
    user: Annotated[User, Depends(get_current_user)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
) -> RequestContext:
    """Provide combined authenticated user and verified tenant context."""
    stmt = select(Membership.role).where(
        Membership.user_id == user.id, Membership.tenant_id == tenant.id
    )
    role = db.scalars(stmt).first() or "member"
    return RequestContext(user=user, tenant=tenant, role=role)
