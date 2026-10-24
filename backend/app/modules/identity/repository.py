"""Identity domain repository."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models import Membership, User, UserSession
from app.db.repositories.tenant import UserRepository


class IdentityRepository(UserRepository):
    """Repository handling user identity persistence, credentials, and sessions."""

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

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email.strip().lower())
        return self.db.scalars(stmt).first()

    def create_session(
        self,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> UserSession:
        session = UserSession(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(session)
        self.db.flush()
        return session

    def get_session_by_token_hash(self, token_hash: str) -> UserSession | None:
        stmt = (
            select(UserSession)
            .where(UserSession.token_hash == token_hash)
            .options(selectinload(UserSession.user))
        )
        return self.db.scalars(stmt).first()

    def revoke_session(self, session_id: uuid.UUID, user_id: uuid.UUID | None = None) -> bool:
        stmt = select(UserSession).where(UserSession.id == session_id)
        if user_id is not None:
            stmt = stmt.where(UserSession.user_id == user_id)
        session = self.db.scalars(stmt).first()
        if session is not None and not session.is_revoked:
            session.is_revoked = True
            self.db.flush()
            return True
        return False

    def list_active_sessions(self, user_id: uuid.UUID) -> Sequence[UserSession]:
        stmt = (
            select(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.is_revoked.is_(False),
                UserSession.expires_at > datetime.now(UTC),
            )
            .order_by(UserSession.created_at.desc())
        )
        return self.db.scalars(stmt).all()

    def touch_session(self, session: UserSession) -> None:
        session.last_seen_at = datetime.now(UTC)
        self.db.flush()
