"""Text-to-Speech module."""

from app.tts.base import TTSAdapter, TTSError, TTSSynthesisError, TTSResult
from app.tts.piper_adapter import PiperTTSAdapter

__all__ = [
    "PiperTTSAdapter",
    "TTSAdapter",
    "TTSError",
    "TTSSynthesisError",
    "TTSResult",
]
