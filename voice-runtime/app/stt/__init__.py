"""Speech-to-Text module."""

from app.stt.base import STTAdapter, STTError, STTRecognitionError, STTResult
from app.stt.whisper_adapter import WhisperSTTAdapter

__all__ = [
    "STTAdapter",
    "STTError",
    "STTRecognitionError",
    "STTResult",
    "WhisperSTTAdapter",
]
