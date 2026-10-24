"""Tenants domain service."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, EntityNotFoundError, PermissionDeniedError
from app.db.models import Membership, MembershipRole, User
from app.modules.tenants.repository import TenantDomainRepository
from app.modules.tenants.schemas import MemberInvite, TenantCreate, TenantRead


class TenantService:
    """Business operations for tenants and access membership."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = TenantDomainRepository(db)

    def create_tenant(self, current_user: User, data: TenantCreate) -> TenantRead:
        # Check slug collision
        existing = self.repo.tenants.get_by_slug(data.slug)
        if existing is not None:
            raise ConflictError(f"Tenant slug '{data.slug}' is already taken.")

        # Create tenant and assign creator as OWNER in one transaction
        tenant = self.repo.tenants.create(name=data.name, slug=data.slug)
        self.repo.memberships.create(
            tenant_id=tenant.id,
            user_id=current_user.id,
            role=MembershipRole.OWNER.value,
        )
        self.db.commit()
        self.db.refresh(tenant)
        return TenantRead.model_validate(tenant)

    def get_tenant(self, tenant_id: uuid.UUID, current_user: User) -> TenantRead:
        role = self.repo.get_user_role(tenant_id, current_user.id)
        if role is None:
            raise PermissionDeniedError("You are not a member of this tenant.")
        tenant = self.repo.tenants.get_by_id(tenant_id)
        if tenant is None:
            raise EntityNotFoundError("Tenant", tenant_id)
        return TenantRead.model_validate(tenant)

    def list_members(self, tenant_id: uuid.UUID, current_user: User) -> Sequence[Membership]:
        role = self.repo.get_user_role(tenant_id, current_user.id)
        if role is None:
            raise PermissionDeniedError("You are not authorized to view members of this tenant.")
        return self.repo.list_members(tenant_id)

    def invite_member(
        self, tenant_id: uuid.UUID, current_user: User, invite: MemberInvite
    ) -> Membership:
        role = self.repo.get_user_role(tenant_id, current_user.id)
        if role not in (MembershipRole.OWNER.value, MembershipRole.ADMIN.value):
            raise PermissionDeniedError("Only owners and admins can invite members.")

        # Lookup user by email
        invited_user = self.repo.tenants.db.query(User).filter(User.email == invite.email).first()
        if invited_user is None:
            # Create synthetic reference user if invited user hasn't logged in yet
            invited_user = User(
                external_id=f"invited|{invite.email}",
                email=invite.email,
                display_name=invite.email.split("@")[0],
            )
            self.db.add(invited_user)
            self.db.flush()

        existing_membership = self.repo.memberships.get_by_tenant_and_user(
            tenant_id, invited_user.id
        )
        if existing_membership is not None:
            raise ConflictError(f"User '{invite.email}' is already a member of this tenant.")

        membership = self.repo.memberships.create(
            tenant_id=tenant_id,
            user_id=invited_user.id,
            role=invite.role,
        )
        self.db.commit()
        self.db.refresh(membership)
        return membership
