"""Abstract base and data models for Text-to-Speech adapters."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


class TTSError(Exception):
    """Base error for speech synthesis failures."""


class TTSSynthesisError(TTSError):
    """Raised when text cannot be synthesized into speech."""


@dataclass
class TTSResult:
    """Standardized output of speech synthesis."""

    audio_bytes: bytes
    audio_format: str = "wav"
    duration_seconds: float = 1.0
    duration_ms: int = 0
    sample_rate: int = 16000
    channels: int = 1
    raw_details: dict[str, Any] = field(default_factory=dict)

    @property
    def byte_length(self) -> int:
        return len(self.audio_bytes)


class TTSAdapter(abc.ABC):
    """Abstract text-to-speech adapter."""

    @abc.abstractmethod
    def synthesize(
        self,
        text: str,
        voice_id: str | None = None,
    ) -> TTSResult:
        """Synthesize text into speech audio bytes."""
        pass
