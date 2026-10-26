"""Audio format validation, magic byte checking, duration estimation, and silence detection."""

from __future__ import annotations

import io
import math
import struct
import wave
from dataclasses import dataclass
from typing import ClassVar


class AudioValidationError(ValueError):
    """Raised when an audio payload fails security or format validation."""


@dataclass(frozen=True)
class AudioValidationConfig:
    """Security and processing constraints for voice audio payloads."""

    max_bytes: int = 10 * 1024 * 1024  # 10 MB limit
    max_duration_seconds: float = 60.0  # 60s per turn limit
    min_bytes: int = 44  # Minimum valid WAV header size
    silence_threshold_rms: float = 50.0  # Energy threshold for silence
    allowed_formats: tuple[str, ...] = ("wav", "mp3", "ogg", "webm", "pcm")


class AudioValidator:
    """Validates audio files against size, duration, format, and magic bytes."""

    # Magic signatures for binary verification
    _MAGIC_SIGS: ClassVar[dict[str, list[bytes]]] = {
        "wav": [b"RIFF"],
        "ogg": [b"OggS"],
        "webm": [b"\x1a\x45\xdf\xa3"],
        "mp3": [b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"],
    }

    def __init__(self, config: AudioValidationConfig | None = None):
        self.config = config or AudioValidationConfig()

    def validate(self, audio_bytes: bytes, declared_format: str = "wav") -> str:
        """Validate audio bytes, ensuring payload is within bounds and authentic.

        Returns normalized format string (e.g., 'wav').
        Raises AudioValidationError on violation.
        """
        fmt = declared_format.lower().replace("audio/", "").replace("x-", "")
        if fmt not in self.config.allowed_formats:
            raise AudioValidationError(
                f"Unsupported audio format '{declared_format}'. "
                f"Allowed formats: {list(self.config.allowed_formats)}"
            )

        byte_len = len(audio_bytes)
        if byte_len < self.config.min_bytes:
            raise AudioValidationError(
                f"Audio payload too small ({byte_len} bytes); minimum is {self.config.min_bytes} bytes."
            )

        if byte_len > self.config.max_bytes:
            raise AudioValidationError(
                f"Audio payload exceeds maximum limit of {self.config.max_bytes} bytes (received {byte_len} bytes)."
            )

        # Magic byte verification
        if fmt in self._MAGIC_SIGS:
            signatures = self._MAGIC_SIGS[fmt]
            if not any(audio_bytes.startswith(sig) for sig in signatures):
                # Extra check for WAV: RIFF at 0 and WAVE at 8
                if fmt == "wav":
                    if not (audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE"):
                        raise AudioValidationError("Invalid WAV audio header: missing RIFF/WAVE marker.")
                else:
                    raise AudioValidationError(f"Invalid {fmt.upper()} audio header: binary signature mismatch.")

        # Duration verification for WAV
        if fmt == "wav":
            duration = self.get_wav_duration(audio_bytes)
            if duration > self.config.max_duration_seconds:
                raise AudioValidationError(
                    f"Audio duration ({duration:.1f}s) exceeds maximum allowed limit of {self.config.max_duration_seconds:.1f}s."
                )

        return fmt

    @staticmethod
    def get_wav_duration(audio_bytes: bytes) -> float:
        """Calculate exact playback duration of WAV bytes."""
        try:
            with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
                framerate = wf.getframerate()
                nframes = wf.getnframes()
                if framerate <= 0:
                    return 0.0
                return float(nframes) / float(framerate)
        except Exception as exc:  # noqa: BLE001
            raise AudioValidationError(f"Malformed WAV structure: {exc}") from exc

    def is_silent(self, pcm_bytes: bytes) -> bool:
        """Determine whether 16-bit PCM audio contains only silence/background noise."""
        if not pcm_bytes:
            return True

        # Ensure 2-byte alignment for 16-bit samples
        aligned_len = len(pcm_bytes) - (len(pcm_bytes) % 2)
        if aligned_len == 0:
            return True

        sample_count = aligned_len // 2
        try:
            samples = struct.unpack(f"<{sample_count}h", pcm_bytes[:aligned_len])
            sum_squares = sum(s * s for s in samples)
            rms = math.sqrt(sum_squares / sample_count)
            return rms < self.config.silence_threshold_rms
        except Exception:
            return True
