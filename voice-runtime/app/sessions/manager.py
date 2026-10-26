"""Thread-safe voice session registry with tenant boundary isolation and lifecycle controls."""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.sessions.models import VoiceSession, VoiceSessionStatus, generate_session_token

logger = logging.getLogger("voice_runtime.sessions")


class SessionNotFoundError(KeyError):
    """Raised when a voice session ID cannot be resolved."""


class SessionUnauthorizedError(PermissionError):
    """Raised on invalid token or tenant boundary crossing attempt."""


class SessionExpiredError(ValueError):
    """Raised when an operation targets an expired session."""


class SessionManager:
    """Manages active voice sessions across tenants with strict isolation."""

    def __init__(self, max_tenant_sessions: int = 50):
        self.max_tenant_sessions = max_tenant_sessions
        self._sessions: dict[str, VoiceSession] = {}
        self._lock = threading.RLock()

    def create_session(
        self,
        *,
        tenant_id: str,
        user_id: str,
        agent_id: str,
        conversation_id: str | None = None,
        duration_seconds: int = 300,
        max_inactivity_seconds: int = 120,
        metadata: dict[str, Any] | None = None,
    ) -> VoiceSession:
        """Create a new tenant-isolated voice session with an ephemeral token."""
        now = datetime.now(UTC)
        sid = str(uuid.uuid4())
        cid = conversation_id or str(uuid.uuid4())
        token = generate_session_token()

        with self._lock:
            # Check tenant concurrency limit
            active_for_tenant = sum(
                1 for s in self._sessions.values()
                if s.tenant_id == tenant_id and s.is_active
            )
            if active_for_tenant >= self.max_tenant_sessions:
                raise ValueError(
                    f"Tenant '{tenant_id}' reached maximum concurrent voice sessions ({self.max_tenant_sessions})."
                )

            session = VoiceSession(
                session_id=sid,
                tenant_id=tenant_id,
                user_id=user_id,
                agent_id=agent_id,
                conversation_id=cid,
                session_token=token,
                status=VoiceSessionStatus.CREATED,
                created_at=now,
                updated_at=now,
                expires_at=now + timedelta(seconds=min(duration_seconds, max_inactivity_seconds)),
                max_inactivity_seconds=max_inactivity_seconds,
                metadata=metadata or {},
            )
            self._sessions[sid] = session
            logger.info("Created voice session sid=%s for tenant=%s user=%s", sid, tenant_id, user_id)
            return session

    def get_session(self, session_id: str, tenant_id: str | None = None) -> VoiceSession:
        """Retrieve session and assert tenant boundary."""
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise SessionNotFoundError(f"Voice session '{session_id}' not found.")

            if tenant_id and session.tenant_id != tenant_id:
                logger.warning(
                    "Cross-tenant access rejected: caller tenant=%s session tenant=%s",
                    tenant_id,
                    session.tenant_id,
                )
                raise SessionUnauthorizedError("Access denied: session belongs to another tenant.")

            # Check expiration
            if not session.is_active:
                session.status = VoiceSessionStatus.EXPIRED
                raise SessionExpiredError(f"Voice session '{session_id}' has expired.")

            session.touch()
            return session

    def authenticate_session(
        self,
        session_id: str,
        token: str,
        tenant_id: str | None = None,
    ) -> VoiceSession:
        """Verify session token and tenant ownership."""
        session = self.get_session(session_id, tenant_id=tenant_id)
        if not session.verify_token(token):
            logger.warning("Invalid token attempt for session %s", session_id)
            raise SessionUnauthorizedError("Invalid voice session token.")

        if session.status == VoiceSessionStatus.CREATED:
            session.status = VoiceSessionStatus.ACTIVE
        return session

    def update_status(self, session_id: str, status: VoiceSessionStatus) -> None:
        """Update lifecycle state of session."""
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].status = status
                self._sessions[session_id].touch()

    def close_session(self, session_id: str) -> None:
        """Explicitly terminate and close a voice session."""
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].status = VoiceSessionStatus.CLOSED
                logger.info("Closed voice session sid=%s", session_id)

    def purge_expired(self) -> int:
        """Sweep expired or closed sessions from in-memory cache."""
        now = datetime.now(UTC)
        purged = 0
        with self._lock:
            to_remove = [
                sid for sid, s in self._sessions.items()
                if (not s.is_active) or (s.status == VoiceSessionStatus.CLOSED)
            ]
            for sid in to_remove:
                del self._sessions[sid]
                purged += 1

        if purged > 0:
            logger.debug("Purged %d expired/closed voice sessions", purged)
        return purged

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for s in self._sessions.values() if s.is_active)


# Global singleton session manager
session_manager = SessionManager()
