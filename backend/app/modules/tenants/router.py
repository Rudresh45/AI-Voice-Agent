"""Tenants domain API router."""

import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.db.models import User
from app.modules.tenants.schemas import (
    MemberInvite,
    MembershipRead,
    TenantCreate,
    TenantRead,
)
from app.modules.tenants.service import TenantService

router = APIRouter(prefix="/tenants", tags=["Tenants"])


@router.post("/", response_model=TenantRead, status_code=status.HTTP_201_CREATED, summary="Create tenant")
def create_tenant(
    data: TenantCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> TenantRead:
    service = TenantService(db)
    return service.create_tenant(current_user, data)


@router.get("/{tenant_id}", response_model=TenantRead, summary="Get tenant details")
def get_tenant(
    tenant_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> TenantRead:
    service = TenantService(db)
    return service.get_tenant(tenant_id, current_user)


@router.get("/{tenant_id}/members", response_model=list[MembershipRead], summary="List tenant members")
def list_tenant_members(
    tenant_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Sequence[MembershipRead]:
    service = TenantService(db)
    memberships = service.list_members(tenant_id, current_user)
    return [MembershipRead.model_validate(m) for m in memberships]


@router.post("/{tenant_id}/members", response_model=MembershipRead, status_code=status.HTTP_201_CREATED, summary="Invite member")
def invite_member(
    tenant_id: uuid.UUID,
    invite: MemberInvite,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MembershipRead:
    service = TenantService(db)
    membership = service.invite_member(tenant_id, current_user, invite)
    return MembershipRead.model_validate(membership)
