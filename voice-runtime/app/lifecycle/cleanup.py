"""Periodic and on-demand cleanup of stale sessions and temporary audio files."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.audio.storage import AudioStorageManager
from app.sessions.manager import SessionManager, session_manager

logger = logging.getLogger("voice_runtime.cleanup")


@dataclass
class CleanupReport:
    """Report summarizing cleanup run statistics."""

    purged_sessions: int
    purged_audio_files: int


class VoiceCleanupService:
    """Orchestrates garbage collection for voice runtime memory and disk state."""

    def __init__(
        self,
        manager: SessionManager | None = None,
        storage: AudioStorageManager | None = None,
    ):
        self.session_manager = manager or session_manager
        self.audio_storage = storage or AudioStorageManager()

    def run_cleanup(self, max_audio_age_seconds: float = 300.0) -> CleanupReport:
        """Purge expired in-memory sessions and disk scratch files."""
        purged_sessions = self.session_manager.purge_expired()
        purged_files = self.audio_storage.purge_stale_files(max_age_seconds=max_audio_age_seconds)

        report = CleanupReport(
            purged_sessions=purged_sessions,
            purged_audio_files=purged_files,
        )
        if purged_sessions > 0 or purged_files > 0:
            logger.info("Voice cleanup completed: %s", report)
        return report
