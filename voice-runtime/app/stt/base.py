"""Abstract base and data models for Speech-to-Text adapters."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


class STTError(Exception):
    """Base error for speech recognition failures."""


class STTRecognitionError(STTError):
    """Raised when audio cannot be decoded or recognized."""


@dataclass
class STTResult:
    """Standardized output of speech recognition."""

    text: str
    confidence: float = 1.0
    duration_ms: int = 0
    language: str = "en"
    is_silent: bool = False
    raw_details: dict[str, Any] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not bool(self.text.strip())


class STTAdapter(abc.ABC):
    """Abstract speech-to-text adapter."""

    @abc.abstractmethod
    def transcribe(
        self,
        audio_bytes: bytes,
        audio_format: str = "wav",
        language: str | None = None,
    ) -> STTResult:
        """Transcribe audio bytes to text transcript."""
        pass
