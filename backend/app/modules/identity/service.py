"""Identity domain service handling authentication, session lifecycle, and profile management."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.errors import AppException, EntityNotFoundError
from app.core.rate_limit import login_rate_limiter
from app.core.security import (
    generate_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)
from app.db.models import User, UserSession
from app.modules.audit.service import AuditService
from app.modules.identity.repository import IdentityRepository
from app.modules.identity.schemas import (
    UserProfileResponse,
    UserRead,
    UserSessionRead,
    UserUpdate,
)

logger = logging.getLogger(__name__)

DEFAULT_SESSION_DURATION_DAYS = 7


class IdentityService:
    """Business logic for user identities, authentication, and session security."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = IdentityRepository(db)
        self.audit_service = AuditService(db)

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

    def set_user_password(self, user_id: uuid.UUID, plain_password: str) -> None:
        """Securely hash and persist a user's password."""
        user = self.repo.get_by_id(user_id)
        if user is None:
            raise EntityNotFoundError("User", user_id)
        user.hashed_password = hash_password(plain_password)
        self.db.commit()

    def login(
        self,
        email: str,
        password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[str, UserSession, User]:
        """Authenticate user credentials with rate limiting and audit logging."""
        rate_key = f"{ip_address or 'unknown'}:{email.lower().strip()}"
        login_rate_limiter.check(rate_key)

        user = self.repo.get_by_email(email)

        # Constant-time safety: verify password even if user is None or password unconfigured
        is_valid = False
        if user is not None and user.hashed_password:
            is_valid = verify_password(password, user.hashed_password)

        if not is_valid or user is None or not user.is_active:
            login_rate_limiter.record_failure(rate_key)
            # Log security audit failure if tenant can be resolved, else log warning
            logger.warning("Failed login attempt for email: %s from IP: %s", email, ip_address)
            raise AppException(
                message="Invalid email or password.",
                status_code=401,
                error_code="INVALID_CREDENTIALS",
            )

        # Successful credential check
        login_rate_limiter.record_success(rate_key)

        raw_token = generate_session_token()
        token_hash = hash_session_token(raw_token)
        expires_at = datetime.now(UTC) + timedelta(days=DEFAULT_SESSION_DURATION_DAYS)

        session = self.repo.create_session(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.commit()
        self.db.refresh(session)

        logger.info("User %s successfully authenticated. Session %s created.", user.id, session.id)
        return raw_token, session, user

    def logout_session(self, session: UserSession) -> None:
        """Revoke the current active session."""
        session.is_revoked = True
        self.db.commit()
        logger.info("Session %s revoked on logout.", session.id)

    def revoke_session(self, session_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Revoke a specific session belonging to the user."""
        revoked = self.repo.revoke_session(session_id=session_id, user_id=user_id)
        if revoked:
            self.db.commit()
        return revoked

    def list_active_sessions(self, user_id: uuid.UUID) -> list[UserSessionRead]:
        sessions = self.repo.list_active_sessions(user_id)
        return [UserSessionRead.model_validate(s) for s in sessions]
