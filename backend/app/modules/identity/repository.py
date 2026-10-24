"""Identity domain repository."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models import Membership, User
from app.db.repositories.tenant import UserRepository


class IdentityRepository(UserRepository):
    """Repository handling user identity persistence and membership lookups."""

    def get_with_memberships(self, user_id: uuid.UUID) -> User | None:
        stmt = (
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.memberships))
        )
        return self.db.scalars(stmt).first()

    def get_user_memberships(self, user_id: uuid.UUID) -> Sequence[Membership]:
        stmt = select(Membership).where(Membership.user_id == user_id)
        return self.db.scalars(stmt).all()
