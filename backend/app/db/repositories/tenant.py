"""Tenant, User, and Membership repositories."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Membership, MembershipRole, Tenant, TenantStatus, User
from app.db.repositories.base import BaseRepository


class TenantRepository(BaseRepository[Tenant]):
    """Repository managing tenant organizations."""

    def __init__(self, db: Session):
        super().__init__(Tenant, db)

    def create(self, name: str, slug: str, status: str = TenantStatus.ACTIVE.value) -> Tenant:
        tenant = Tenant(name=name, slug=slug, status=status)
        return self.add(tenant)

    def get_by_slug(self, slug: str) -> Tenant | None:
        stmt = select(Tenant).where(Tenant.slug == slug)
        return self.db.scalars(stmt).first()

    def list_all(self, skip: int = 0, limit: int = 50) -> Sequence[Tenant]:
        stmt = select(Tenant).offset(skip).limit(limit)
        return self.db.scalars(stmt).all()


class UserRepository(BaseRepository[User]):
    """Repository managing global user identities."""

    def __init__(self, db: Session):
        super().__init__(User, db)

    def create(self, external_id: str, email: str, display_name: str | None = None) -> User:
        user = User(external_id=external_id, email=email, display_name=display_name)
        return self.add(user)

    def get_by_external_id(self, external_id: str) -> User | None:
        stmt = select(User).where(User.external_id == external_id)
        return self.db.scalars(stmt).first()

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        return self.db.scalars(stmt).first()


class MembershipRepository(BaseRepository[Membership]):
    """Repository managing tenant memberships and user roles."""

    def __init__(self, db: Session):
        super().__init__(Membership, db)

    def create(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str = MembershipRole.MEMBER.value,
    ) -> Membership:
        membership = Membership(tenant_id=tenant_id, user_id=user_id, role=role)
        return self.add(membership)

    def get_by_tenant_and_user(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> Membership | None:
        stmt = select(Membership).where(
            Membership.tenant_id == tenant_id, Membership.user_id == user_id
        )
        return self.db.scalars(stmt).first()

    def list_by_tenant(
        self, tenant_id: uuid.UUID, skip: int = 0, limit: int = 50
    ) -> Sequence[Membership]:
        stmt = select(Membership).where(Membership.tenant_id == tenant_id).offset(skip).limit(limit)
        return self.db.scalars(stmt).all()

    def list_by_user(
        self, user_id: uuid.UUID, skip: int = 0, limit: int = 50
    ) -> Sequence[Membership]:
        stmt = select(Membership).where(Membership.user_id == user_id).offset(skip).limit(limit)
        return self.db.scalars(stmt).all()
