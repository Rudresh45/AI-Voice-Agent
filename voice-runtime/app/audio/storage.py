"""Secure temporary audio storage, isolated scratch paths, and deletion policy enforcement."""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger("voice_runtime.storage")


class AudioStorageManager:
    """Manages audio file lifecycles with strict deletion policies."""

    def __init__(
        self,
        base_dir: str | Path | None = None,
        *,
        retain_recordings: bool = False,
    ):
        self.retain_recordings = retain_recordings
        if base_dir:
            self.base_dir = Path(base_dir).resolve()
        else:
            self.base_dir = Path(tempfile.gettempdir()) / "ai_voice_runtime_scratch"

        # Ensure isolated directory exists with restricted access
        self.base_dir.mkdir(parents=True, exist_ok=True)
        try:
            # Set directory permissions on POSIX systems (no-op on Windows)
            os.chmod(self.base_dir, 0o700)
        except OSError:
            pass

    def save_temp_audio(
        self,
        session_id: str,
        audio_bytes: bytes,
        extension: str = "wav",
    ) -> Path:
        """Write incoming audio payload to isolated temporary scratch file."""
        file_id = uuid.uuid4().hex
        ext = extension.lstrip(".")
        filename = f"{session_id}_{file_id}.{ext}"
        filepath = self.base_dir / filename

        with open(filepath, "wb") as f:
            f.write(audio_bytes)

        logger.debug("Saved temporary audio file: %s (%d bytes)", filepath, len(audio_bytes))
        return filepath

    def delete_file(self, filepath: str | Path | None) -> bool:
        """Explicitly delete a temporary audio file."""
        if not filepath:
            return False
        path = Path(filepath)
        try:
            if path.exists() and path.is_file():
                path.unlink()
                logger.debug("Deleted temporary audio file: %s", path)
                return True
        except OSError as exc:
            logger.warning("Failed to delete audio file %s: %s", path, exc)
        return False

    @contextmanager
    def temp_audio_scope(
        self,
        session_id: str,
        audio_bytes: bytes,
        extension: str = "wav",
    ) -> Generator[Path, None, None]:
        """Scoped context manager guaranteeing file cleanup on exit."""
        path = self.save_temp_audio(session_id, audio_bytes, extension)
        try:
            yield path
        finally:
            if not self.retain_recordings:
                self.delete_file(path)

    def purge_stale_files(self, max_age_seconds: float = 300.0) -> int:
        """Purge temporary audio files exceeding the maximum retention window."""
        now = time.time()
        purged = 0
        if not self.base_dir.exists():
            return 0

        for item in self.base_dir.iterdir():
            if item.is_file():
                try:
                    mtime = item.stat().st_mtime
                    if (now - mtime) > max_age_seconds:
                        item.unlink()
                        purged += 1
                except OSError:
                    continue

        if purged > 0:
            logger.info("Purged %d stale audio files from %s", purged, self.base_dir)
        return purged

    def cleanup_all(self) -> None:
        """Remove entire scratch directory on system shutdown."""
        try:
            if self.base_dir.exists():
                shutil.rmtree(self.base_dir)
        except OSError as exc:
            logger.warning("Failed to clean scratch directory %s: %s", self.base_dir, exc)
