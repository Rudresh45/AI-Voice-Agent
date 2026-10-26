"""Voice session models, token security, and lifecycle statuses."""

from __future__ import annotations

import enum
import hmac
import os
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any


class VoiceSessionStatus(str, enum.Enum):
    """Voice session lifecycle states."""

    CREATED = "created"
    ACTIVE = "active"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    CLOSED = "closed"
    EXPIRED = "expired"


def generate_session_token() -> str:
    """Generate cryptographically secure 32-byte URL-safe session token."""
    return f"vst_{secrets.token_urlsafe(32)}"


@dataclass
class VoiceSession:
    """Authenticated and tenant-scoped voice session."""

    session_id: str
    tenant_id: str
    user_id: str
    agent_id: str
    conversation_id: str
    session_token: str
    status: VoiceSessionStatus = VoiceSessionStatus.CREATED
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(minutes=5))
    max_inactivity_seconds: int = 120
    turn_count: int = 0
    audio_format: str = "wav"
    sample_rate: int = 16000
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        """Return True if session is open and not timed out."""
        if self.status in (VoiceSessionStatus.CLOSED, VoiceSessionStatus.EXPIRED):
            return False
        return datetime.now(UTC) < self.expires_at

    def touch(self) -> None:
        """Update last active timestamp and slide the inactivity expiration window."""
        now = datetime.now(UTC)
        self.updated_at = now
        self.expires_at = now + timedelta(seconds=self.max_inactivity_seconds)

    def verify_token(self, token: str) -> bool:
        """Constant-time token comparison to avoid timing attacks."""
        return hmac.compare_digest(self.session_token, token)
