"""Voice session state transitions, timeout checks, and user interruption handling."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.sessions.models import VoiceSession, VoiceSessionStatus

logger = logging.getLogger("voice_runtime.lifecycle")


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal voice session state transition is attempted."""


class VoiceLifecycleController:
    """Controls session state transitions, cancellations, and interruption events."""

    # Permitted state transitions
    _VALID_TRANSITIONS: dict[VoiceSessionStatus, set[VoiceSessionStatus]] = {
        VoiceSessionStatus.CREATED: {VoiceSessionStatus.ACTIVE, VoiceSessionStatus.CLOSED},
        VoiceSessionStatus.ACTIVE: {
            VoiceSessionStatus.LISTENING,
            VoiceSessionStatus.PROCESSING,
            VoiceSessionStatus.CLOSED,
            VoiceSessionStatus.EXPIRED,
        },
        VoiceSessionStatus.LISTENING: {
            VoiceSessionStatus.PROCESSING,
            VoiceSessionStatus.INTERRUPTED,
            VoiceSessionStatus.CLOSED,
            VoiceSessionStatus.EXPIRED,
        },
        VoiceSessionStatus.PROCESSING: {
            VoiceSessionStatus.SPEAKING,
            VoiceSessionStatus.INTERRUPTED,
            VoiceSessionStatus.ACTIVE,
            VoiceSessionStatus.CLOSED,
            VoiceSessionStatus.EXPIRED,
        },
        VoiceSessionStatus.SPEAKING: {
            VoiceSessionStatus.LISTENING,
            VoiceSessionStatus.ACTIVE,
            VoiceSessionStatus.INTERRUPTED,
            VoiceSessionStatus.CLOSED,
            VoiceSessionStatus.EXPIRED,
        },
        VoiceSessionStatus.INTERRUPTED: {
            VoiceSessionStatus.LISTENING,
            VoiceSessionStatus.ACTIVE,
            VoiceSessionStatus.CLOSED,
        },
        VoiceSessionStatus.CLOSED: set(),
        VoiceSessionStatus.EXPIRED: set(),
    }

    @classmethod
    def transition(cls, session: VoiceSession, target_status: VoiceSessionStatus) -> None:
        """Validate and apply state transition."""
        current = session.status
        allowed = cls._VALID_TRANSITIONS.get(current, set())
        if target_status not in allowed and target_status != current:
            raise InvalidStateTransitionError(
                f"Cannot transition voice session {session.session_id} from '{current.value}' to '{target_status.value}'."
            )

        session.status = target_status
        session.touch()
        logger.debug("Session %s transitioned from %s to %s", session.session_id, current.value, target_status.value)

    @classmethod
    def handle_user_interruption(cls, session: VoiceSession, reason: str = "user_barge_in") -> bool:
        """Process a user barge-in / interruption signal while speaking or processing."""
        if session.status in (VoiceSessionStatus.SPEAKING, VoiceSessionStatus.PROCESSING):
            session.status = VoiceSessionStatus.INTERRUPTED
            session.metadata["last_interruption"] = {
                "timestamp": datetime.now(UTC).isoformat(),
                "reason": reason,
                "interrupted_turn": session.turn_count,
            }
            session.metadata["interruption_count"] = session.metadata.get("interruption_count", 0) + 1
            session.touch()
            logger.info("Session %s interrupted by user barge-in (turn=%d)", session.session_id, session.turn_count)
            return True
        return False

    @classmethod
    def check_and_expire(cls, session: VoiceSession) -> bool:
        """Evaluate session expiration and transition to EXPIRED if overdue."""
        if not session.is_active:
            if session.status != VoiceSessionStatus.CLOSED:
                session.status = VoiceSessionStatus.EXPIRED
            return True
        return False
