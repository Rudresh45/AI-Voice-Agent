"""Comprehensive integration and unit tests for the Voice Runtime subsystem.

Covers:
- Clear speech transcription and synthesis
- Silence detection and empty transcripts
- Speech recognition error handling
- Oversized audio uploads and duration limits
- TTS synthesis failure handling
- Real-time WebSocket streaming and user interruption (barge-in)
- Session lifecycle, timeouts, and unauthorized cross-tenant access
- Temporary audio storage isolation and cleanup policy
"""

from __future__ import annotations

import base64
import io
import math
import struct
import time
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.audio.storage import AudioStorageManager
from app.audio.validator import AudioValidationConfig, AudioValidationError, AudioValidator
from app.lifecycle.cleanup import VoiceCleanupService
from app.lifecycle.state_machine import VoiceLifecycleController
from app.server import app
from app.sessions.manager import (
    SessionExpiredError,
    SessionManager,
    SessionNotFoundError,
    SessionUnauthorizedError,
)
from app.sessions.models import VoiceSessionStatus
from app.stt.base import STTRecognitionError
from app.stt.whisper_adapter import WhisperSTTAdapter
from app.transport.http_transport import VoiceRuntimeService
from app.tts.base import TTSSynthesisError
from app.tts.piper_adapter import PiperTTSAdapter


def create_test_wav(
    duration_seconds: float = 1.0,
    sample_rate: int = 16000,
    frequency: float = 440.0,
    amplitude: float = 8000.0,
    simulated_transcript: str | None = None,
) -> bytes:
    """Helper to synthesize valid 16-bit mono RIFF/WAVE audio bytes."""
    buf = io.BytesIO()
    total_samples = int(sample_rate * duration_seconds)

    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)

        raw_frames = bytearray()
        for i in range(total_samples):
            val = int(amplitude * math.sin(2.0 * math.pi * frequency * (i / sample_rate)))
            raw_frames.extend(struct.pack("<h", val))

        # Optional simulation marker for deterministic test speech
        if simulated_transcript:
            raw_frames.extend(b"SIM_TRANSCRIPT:" + simulated_transcript.encode("utf-8") + b"\x00")

        wf.writeframes(bytes(raw_frames))

    return buf.getvalue()


def create_silent_wav(duration_seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    """Helper to generate perfectly silent WAV audio."""
    return create_test_wav(duration_seconds=duration_seconds, sample_rate=sample_rate, amplitude=0.0)


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Session Creation, Ownership, and Tenant Scoping
# ---------------------------------------------------------------------------

def test_session_creation_and_ownership(client: TestClient):
    """Test voice session creation, token issuance, and tenant isolation."""
    # 1. Create valid session
    headers = {
        "X-Tenant-ID": "tenant-alpha",
        "X-User-ID": "user-alice",
    }
    payload = {
        "agent_id": "agent-support-1",
        "conversation_id": "conv-100",
        "duration_seconds": 300,
        "max_inactivity_seconds": 120,
    }
    resp = client.post("/voice/sessions", headers=headers, json=payload)
    assert resp.status_code == 201
    data = resp.json()

    session_id = data["session_id"]
    token = data["session_token"]
    assert data["tenant_id"] == "tenant-alpha"
    assert data["user_id"] == "user-alice"
    assert data["status"] == "created"
    assert token.startswith("vst_")

    # 2. Query session with correct tenant
    query_resp = client.get(f"/voice/sessions/{session_id}", headers={"X-Tenant-ID": "tenant-alpha"})
    assert query_resp.status_code == 200
    assert query_resp.json()["session_id"] == session_id

    # 3. Cross-tenant access must be rejected (403 Forbidden)
    cross_resp = client.get(f"/voice/sessions/{session_id}", headers={"X-Tenant-ID": "tenant-bravo"})
    assert cross_resp.status_code == 403

    # 4. Non-existent session
    not_found = client.get("/voice/sessions/00000000-0000-0000-0000-000000000000")
    assert not_found.status_code == 404


def test_session_unauthorized_token_rejection(client: TestClient):
    """Test that requests with an invalid session token are rejected."""
    headers = {
        "X-Tenant-ID": "tenant-alpha",
        "X-User-ID": "user-alice",
    }
    resp = client.post("/voice/sessions", headers=headers, json={"agent_id": "agent-1"})
    session_id = resp.json()["session_id"]

    audio_bytes = create_test_wav(0.5)
    files = {"audio": ("turn.wav", audio_bytes, "audio/wav")}

    # Send forged token
    upload_resp = client.post(
        f"/voice/sessions/{session_id}/audio",
        headers={"X-Session-Token": "vst_FORGED_TOKEN", "X-Tenant-ID": "tenant-alpha"},
        files=files,
    )
    assert upload_resp.status_code == 401


# ---------------------------------------------------------------------------
# 2. Clear Speech & Audio Turn Execution
# ---------------------------------------------------------------------------

def test_clear_speech_audio_turn(client: TestClient):
    """Test full voice interaction turn: Audio in -> STT -> Agent -> TTS -> Audio out."""
    headers = {
        "X-Tenant-ID": "tenant-alpha",
        "X-User-ID": "user-alice",
    }
    resp = client.post("/voice/sessions", headers=headers, json={"agent_id": "agent-1"})
    session_id = resp.json()["session_id"]
    token = resp.json()["session_token"]

    speech_wav = create_test_wav(
        duration_seconds=1.0,
        simulated_transcript="Check my account balance please",
    )
    files = {"audio": ("speech.wav", speech_wav, "audio/wav")}

    turn_resp = client.post(
        f"/voice/sessions/{session_id}/audio",
        headers={"X-Session-Token": token, "X-Tenant-ID": "tenant-alpha"},
        files=files,
    )
    assert turn_resp.status_code == 200
    turn_data = turn_resp.json()

    assert turn_data["status"] == "success"
    assert turn_data["user_transcript"] == "Check my account balance please"
    assert len(turn_data["agent_response_text"]) > 0
    assert len(turn_data["audio_response_base64"]) > 0
    assert turn_data["audio_duration_seconds"] > 0

    # Telemetry verification
    tel = turn_data["telemetry"]
    assert tel["stt_latency_ms"] >= 0
    assert tel["agent_latency_ms"] >= 0
    assert tel["tts_latency_ms"] >= 0
    assert tel["total_latency_ms"] >= 0


# ---------------------------------------------------------------------------
# 3. Silence Detection & Empty Transcripts
# ---------------------------------------------------------------------------

def test_silence_detection(client: TestClient):
    """Test that pure silence is recognized without triggering model execution."""
    headers = {"X-Tenant-ID": "tenant-alpha", "X-User-ID": "user-alice"}
    resp = client.post("/voice/sessions", headers=headers, json={"agent_id": "agent-1"})
    session_id = resp.json()["session_id"]
    token = resp.json()["session_token"]

    silent_wav = create_silent_wav(duration_seconds=1.0)
    files = {"audio": ("silent.wav", silent_wav, "audio/wav")}

    turn_resp = client.post(
        f"/voice/sessions/{session_id}/audio",
        headers={"X-Session-Token": token, "X-Tenant-ID": "tenant-alpha"},
        files=files,
    )
    assert turn_resp.status_code == 200
    data = turn_resp.json()

    assert data["status"] == "silence"
    assert data["user_transcript"] == ""
    assert data["agent_response_text"] == ""
    assert data["audio_response_base64"] == ""


# ---------------------------------------------------------------------------
# 4. Recognition Errors & Corrupt Audio
# ---------------------------------------------------------------------------

def test_recognition_errors_handling(client: TestClient):
    """Test recognition error handling when unparseable audio is supplied."""
    headers = {"X-Tenant-ID": "tenant-alpha", "X-User-ID": "user-alice"}
    resp = client.post("/voice/sessions", headers=headers, json={"agent_id": "agent-1"})
    session_id = resp.json()["session_id"]
    token = resp.json()["session_token"]

    corrupt_audio = create_test_wav(0.5) + b"__CORRUPT_AUDIO__"
    files = {"audio": ("corrupt.wav", corrupt_audio, "audio/wav")}

    turn_resp = client.post(
        f"/voice/sessions/{session_id}/audio",
        headers={"X-Session-Token": token, "X-Tenant-ID": "tenant-alpha"},
        files=files,
    )
    assert turn_resp.status_code == 502
    assert "Speech engine error" in turn_resp.json()["detail"]


# ---------------------------------------------------------------------------
# 5. Audio Input Validation & File Size Limits
# ---------------------------------------------------------------------------

def test_audio_validator_limits():
    """Test unit validation for file sizes and durations."""
    cfg = AudioValidationConfig(max_bytes=200000, max_duration_seconds=2.0)
    validator = AudioValidator(cfg)

    # 1. Valid short audio
    short_wav = create_test_wav(0.5)
    assert validator.validate(short_wav, "wav") == "wav"

    # 2. Oversized payload rejection
    oversized = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 250000
    with pytest.raises(AudioValidationError, match="exceeds maximum limit"):
        validator.validate(oversized, "wav")

    # 3. Too small payload
    with pytest.raises(AudioValidationError, match="too small"):
        validator.validate(b"RIFF123", "wav")

    # 4. Invalid header / magic bytes
    with pytest.raises(AudioValidationError, match="Invalid WAV audio header"):
        validator.validate(b"INVALID_HEADER_PADDING_BYTES_AT_LEAST_44_CHARS_LONG", "wav")

    # 5. Long audio duration rejection
    long_wav = create_test_wav(duration_seconds=3.0)
    with pytest.raises(AudioValidationError, match="exceeds maximum allowed limit"):
        validator.validate(long_wav, "wav")


def test_oversized_audio_upload_rejection_api(client: TestClient):
    """Test HTTP API rejects oversized audio upload with 413 Payload Too Large."""
    headers = {"X-Tenant-ID": "tenant-alpha", "X-User-ID": "user-alice"}
    resp = client.post("/voice/sessions", headers=headers, json={"agent_id": "agent-1"})
    session_id = resp.json()["session_id"]
    token = resp.json()["session_token"]

    # Create dummy audio payload exceeding 10MB
    large_payload = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * (11 * 1024 * 1024)
    files = {"audio": ("huge.wav", large_payload, "audio/wav")}

    upload_resp = client.post(
        f"/voice/sessions/{session_id}/audio",
        headers={"X-Session-Token": token, "X-Tenant-ID": "tenant-alpha"},
        files=files,
    )
    assert upload_resp.status_code == 413


# ---------------------------------------------------------------------------
# 6. TTS Failures Handling
# ---------------------------------------------------------------------------

def test_tts_failure_handling(client: TestClient):
    """Test that speech synthesizer errors are caught and surfaced safely."""
    tts = PiperTTSAdapter()

    # Empty text
    with pytest.raises(TTSSynthesisError, match="Cannot synthesize empty"):
        tts.synthesize("   ")

    # Simulated engine error
    with pytest.raises(TTSSynthesisError, match="Simulated speech synthesizer engine failure"):
        tts.synthesize("Hello __FAIL_TTS__ world")


# ---------------------------------------------------------------------------
# 7. Session Lifecycle, Timeouts, and User Interruption
# ---------------------------------------------------------------------------

def test_user_interruption_state_machine():
    """Test that a user barge-in signal correctly halts speaking state."""
    manager = SessionManager()
    session = manager.create_session(
        tenant_id="tenant-t",
        user_id="user-u",
        agent_id="agent-a",
    )

    VoiceLifecycleController.transition(session, VoiceSessionStatus.ACTIVE)
    VoiceLifecycleController.transition(session, VoiceSessionStatus.LISTENING)
    VoiceLifecycleController.transition(session, VoiceSessionStatus.PROCESSING)
    VoiceLifecycleController.transition(session, VoiceSessionStatus.SPEAKING)

    # Trigger user barge-in interruption
    interrupted = VoiceLifecycleController.handle_user_interruption(session, reason="vad_speech_start")
    assert interrupted is True
    assert session.status == VoiceSessionStatus.INTERRUPTED
    assert session.metadata["interruption_count"] == 1

    # Transition back to listening
    VoiceLifecycleController.transition(session, VoiceSessionStatus.LISTENING)
    assert session.status == VoiceSessionStatus.LISTENING


def test_session_inactivity_timeout():
    """Test that overdue sessions expire and are purged."""
    manager = SessionManager()
    session = manager.create_session(
        tenant_id="tenant-t",
        user_id="user-u",
        agent_id="agent-a",
        duration_seconds=1,
        max_inactivity_seconds=1,
    )

    # Force expiration
    session.expires_at = session.created_at

    with pytest.raises(SessionExpiredError):
        manager.get_session(session.session_id)

    purged = manager.purge_expired()
    assert purged == 1


# ---------------------------------------------------------------------------
# 8. Temporary Audio Storage Isolation & Deletion Policy
# ---------------------------------------------------------------------------

def test_audio_storage_temporary_cleanup(tmp_path: Path):
    """Test that temporary audio files are deleted immediately after scoped use."""
    storage = AudioStorageManager(base_dir=tmp_path, retain_recordings=False)

    wav_bytes = create_test_wav(0.5)
    file_path = None

    with storage.temp_audio_scope("sess-1", wav_bytes, "wav") as path:
        file_path = path
        assert file_path.exists()
        assert file_path.stat().st_size > 0

    # Once scope exits, file must be automatically unlinked (deleted)
    assert not file_path.exists()


# ---------------------------------------------------------------------------
# 9. Real-Time Streaming WebSocket & Interruption
# ---------------------------------------------------------------------------

def test_websocket_streaming_and_interruption(client: TestClient):
    """Test WebSocket real-time audio chunk streaming, end-of-turn, and interruption."""
    # 1. Create session
    headers = {"X-Tenant-ID": "tenant-alpha", "X-User-ID": "user-alice"}
    resp = client.post("/voice/sessions", headers=headers, json={"agent_id": "agent-1"})
    session_id = resp.json()["session_id"]
    token = resp.json()["session_token"]

    # 2. Connect via WebSocket
    with client.websocket_connect(f"/voice/sessions/{session_id}/stream?token={token}") as ws:
        ready_msg = ws.receive_json()
        assert ready_msg["type"] == "ready"
        assert ready_msg["session_id"] == session_id

        # 3. Send audio chunks
        speech_wav = create_test_wav(1.0, simulated_transcript="Help with billing")
        # Split into two chunks
        mid = len(speech_wav) // 2
        chunk1 = base64.b64encode(speech_wav[:mid]).decode("ascii")
        chunk2 = base64.b64encode(speech_wav[mid:]).decode("ascii")

        ws.send_json({"type": "audio_chunk", "data": chunk1})
        ws.send_json({"type": "audio_chunk", "data": chunk2})

        # 4. Signal turn end
        ws.send_json({"type": "end_turn", "format": "wav"})

        # Receive turn progress events
        events = []
        for _ in range(4):
            ev = ws.receive_json()
            events.append(ev)
            if ev.get("type") == "turn_complete":
                break

        event_types = [e["type"] for e in events]
        assert "transcript" in event_types
        assert "agent_text" in event_types
        assert "audio_response" in event_types
        assert "turn_complete" in event_types

        # 5. Send interruption signal
        ws.send_json({"type": "interrupt"})
        interrupt_msg = ws.receive_json()
        assert interrupt_msg["type"] == "interrupted"
