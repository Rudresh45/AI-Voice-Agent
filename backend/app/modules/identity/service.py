"""Identity domain service."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.errors import EntityNotFoundError
from app.modules.identity.models import User
from app.modules.identity.repository import IdentityRepository
from app.modules.identity.schemas import UserProfileResponse, UserRead, UserUpdate


class IdentityService:
    """Business logic for user identities."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = IdentityRepository(db)

    def get_profile(self, user: User) -> UserProfileResponse:
        user_with_memberships = self.repo.get_with_memberships(user.id)
        if user_with_memberships is None:
            raise EntityNotFoundError("User", user.id)
        return UserProfileResponse(
            user=UserRead.model_validate(user_with_memberships),
            memberships=list(user_with_memberships.memberships),
        )

    def update_profile(self, user_id: uuid.UUID, data: UserUpdate) -> UserRead:
        user = self.repo.get_by_id(user_id)
        if user is None:
            raise EntityNotFoundError("User", user_id)
        if data.display_name is not None:
            user.display_name = data.display_name
        self.db.commit()
        self.db.refresh(user)
        return UserRead.model_validate(user)
