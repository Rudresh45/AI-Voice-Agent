"""Tenants domain service with RBAC enforcement and audit tracking."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, EntityNotFoundError, PermissionDeniedError
from app.core.security import SecurityRole
from app.db.models import Membership, MembershipRole, User
from app.modules.audit.service import AuditService
from app.modules.tenants.repository import TenantDomainRepository
from app.modules.tenants.schemas import MemberInvite, TenantCreate, TenantRead


class TenantService:
    """Business operations for tenants and access membership."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = TenantDomainRepository(db)
        self.audit_service = AuditService(db)

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

        self.audit_service.log_action(
            tenant_id=tenant.id,
            actor_id=str(current_user.id),
            action="tenant.create",
            entity_type="tenant",
            entity_id=str(tenant.id),
            outcome="success",
            details={"name": tenant.name, "slug": tenant.slug},
        )
        return TenantRead.model_validate(tenant)

    def get_tenant(self, tenant_id: uuid.UUID, current_user: User) -> TenantRead:
        role = self.repo.get_user_role(tenant_id, current_user.id)
        if role is None and not current_user.is_platform_admin:
            raise PermissionDeniedError("You are not a member of this tenant.")
        tenant = self.repo.tenants.get_by_id(tenant_id)
        if tenant is None:
            raise EntityNotFoundError("Tenant", tenant_id)
        return TenantRead.model_validate(tenant)

    def list_members(self, tenant_id: uuid.UUID, current_user: User) -> Sequence[Membership]:
        role = self.repo.get_user_role(tenant_id, current_user.id)
        if role is None and not current_user.is_platform_admin:
            raise PermissionDeniedError("You are not authorized to view members of this tenant.")
        return self.repo.list_members(tenant_id)

    def invite_member(
        self, tenant_id: uuid.UUID, current_user: User, invite: MemberInvite
    ) -> Membership:
        role = self.repo.get_user_role(tenant_id, current_user.id)
        if not (role and SecurityRole.is_admin_permitted(role)) and not current_user.is_platform_admin:
            raise PermissionDeniedError("Only owners and admins can invite members.")

        # Lookup user by email
        clean_email = invite.email.strip().lower()
        stmt = select(User).where(User.email == clean_email)
        invited_user = self.db.scalars(stmt).first()

        if invited_user is None:
            # Create synthetic reference user if invited user hasn't logged in yet
            invited_user = User(
                external_id=f"invited|{clean_email}",
                email=clean_email,
                display_name=clean_email.split("@")[0],
            )
            self.db.add(invited_user)
            self.db.flush()

        existing_membership = self.repo.memberships.get_by_tenant_and_user(
            tenant_id, invited_user.id
        )
        if existing_membership is not None:
            raise ConflictError(f"User '{clean_email}' is already a member of this tenant.")

        membership = self.repo.memberships.create(
            tenant_id=tenant_id,
            user_id=invited_user.id,
            role=invite.role,
        )
        self.db.commit()
        self.db.refresh(membership)

        self.audit_service.log_action(
            tenant_id=tenant_id,
            actor_id=str(current_user.id),
            action="tenant.member_invited",
            entity_type="membership",
            entity_id=str(membership.id),
            outcome="success",
            details={"invited_user_id": str(invited_user.id), "role": invite.role},
        )
        return membership
