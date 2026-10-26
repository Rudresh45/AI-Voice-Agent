"""HTTP audio upload and voice session REST endpoints."""

from __future__ import annotations

import base64
import logging
import time
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Header, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field

from app.agent_bridge.bridge import VoiceAgentBridge
from app.audio.storage import AudioStorageManager
from app.audio.validator import AudioValidationError, AudioValidator
from app.lifecycle.state_machine import VoiceLifecycleController
from app.sessions.manager import (
    SessionExpiredError,
    SessionManager,
    SessionNotFoundError,
    SessionUnauthorizedError,
    session_manager,
)
from app.sessions.models import VoiceSessionStatus
from app.stt.base import STTRecognitionError
from app.stt.whisper_adapter import WhisperSTTAdapter
from app.telemetry.metrics import TelemetryCollector, VoiceTurnMetrics, telemetry_collector
from app.tts.base import TTSSynthesisError
from app.tts.piper_adapter import PiperTTSAdapter

logger = logging.getLogger("voice_runtime.transport.http")

router = APIRouter(prefix="/voice", tags=["Voice Runtime"])


# Request / Response Schemas
class CreateVoiceSessionRequest(BaseModel):
    agent_id: str
    conversation_id: str | None = None
    duration_seconds: int = Field(default=300, ge=30, le=1800)
    max_inactivity_seconds: int = Field(default=120, ge=10, le=600)
    audio_format: str = Field(default="wav", pattern="^(wav|mp3|ogg|webm)$")
    sample_rate: int = Field(default=16000, ge=8000, le=48000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VoiceSessionResponse(BaseModel):
    session_id: str
    tenant_id: str
    user_id: str
    agent_id: str
    conversation_id: str
    session_token: str
    status: str
    expires_at: str
    max_inactivity_seconds: int


class VoiceTurnResponse(BaseModel):
    session_id: str
    turn_id: str
    user_transcript: str
    agent_response_text: str
    audio_response_base64: str
    audio_format: str = "wav"
    audio_duration_seconds: float
    telemetry: dict[str, Any]
    status: str = "success"


class VoiceRuntimeService:
    """Orchestrates audio turn execution for the HTTP and WebSocket endpoints."""

    def __init__(
        self,
        manager: SessionManager | None = None,
        validator: AudioValidator | None = None,
        storage: AudioStorageManager | None = None,
        stt: WhisperSTTAdapter | None = None,
        tts: PiperTTSAdapter | None = None,
        agent_bridge: VoiceAgentBridge | None = None,
        telemetry: TelemetryCollector | None = None,
    ):
        self.manager = manager or session_manager
        self.validator = validator or AudioValidator()
        self.storage = storage or AudioStorageManager()
        self.stt = stt or WhisperSTTAdapter(validator=self.validator)
        self.tts = tts or PiperTTSAdapter()
        self.agent_bridge = agent_bridge or VoiceAgentBridge()
        self.telemetry = telemetry or telemetry_collector

    def process_audio_turn(
        self,
        session_id: str,
        token: str,
        audio_bytes: bytes,
        audio_format: str = "wav",
        tenant_id: str | None = None,
    ) -> VoiceTurnResponse:
        """Execute full speech turn: validate -> STT -> Agent Bridge -> TTS."""
        turn_start = time.perf_counter()
        turn_id = f"turn_{int(time.time() * 1000)}"

        # 1. Authenticate and resolve session
        try:
            session = self.manager.authenticate_session(session_id, token, tenant_id=tenant_id)
        except (SessionNotFoundError, SessionUnauthorizedError, SessionExpiredError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED if isinstance(exc, SessionUnauthorizedError) else status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc

        session.turn_count += 1
        VoiceLifecycleController.transition(session, VoiceSessionStatus.PROCESSING)

        metrics = VoiceTurnMetrics(
            session_id=session.session_id,
            tenant_id=session.tenant_id,
            turn_id=turn_id,
            audio_input_bytes=len(audio_bytes),
        )

        try:
            # 2. Validate audio payload
            normalized_format = self.validator.validate(audio_bytes, declared_format=audio_format)
            metrics.audio_input_duration_s = (
                self.validator.get_wav_duration(audio_bytes) if normalized_format == "wav" else 0.0
            )

            # 3. Speech-to-Text
            stt_res = self.stt.transcribe(audio_bytes, audio_format=normalized_format)
            metrics.stt_latency_ms = stt_res.duration_ms
            metrics.transcript_chars = len(stt_res.text)

            if stt_res.is_silent or not stt_res.text.strip():
                # User sent silence
                metrics.status = "silence"
                metrics.total_latency_ms = int((time.perf_counter() - turn_start) * 1000)
                self.telemetry.record_turn(metrics)
                VoiceLifecycleController.transition(session, VoiceSessionStatus.ACTIVE)
                return VoiceTurnResponse(
                    session_id=session.session_id,
                    turn_id=turn_id,
                    user_transcript="",
                    agent_response_text="",
                    audio_response_base64="",
                    audio_format=normalized_format,
                    audio_duration_seconds=0.0,
                    telemetry=metrics.to_dict(),
                    status="silence",
                )

            # 4. Agent Bridge Execution
            agent_res = self.agent_bridge.process_turn(session, stt_res.text)
            metrics.agent_latency_ms = agent_res.agent_latency_ms
            metrics.response_chars = len(agent_res.output_text)

            # 5. Text-to-Speech Synthesis
            VoiceLifecycleController.transition(session, VoiceSessionStatus.SPEAKING)
            tts_res = self.tts.synthesize(agent_res.output_text)
            metrics.tts_latency_ms = tts_res.duration_ms
            metrics.audio_output_bytes = len(tts_res.audio_bytes)
            metrics.audio_output_duration_s = tts_res.duration_seconds
            metrics.status = "success"

            VoiceLifecycleController.transition(session, VoiceSessionStatus.ACTIVE)

            total_ms = int((time.perf_counter() - turn_start) * 1000)
            metrics.total_latency_ms = total_ms
            self.telemetry.record_turn(metrics)

            audio_b64 = base64.b64encode(tts_res.audio_bytes).decode("ascii")

            return VoiceTurnResponse(
                session_id=session.session_id,
                turn_id=turn_id,
                user_transcript=stt_res.text,
                agent_response_text=agent_res.output_text,
                audio_response_base64=audio_b64,
                audio_format=tts_res.audio_format,
                audio_duration_seconds=tts_res.duration_seconds,
                telemetry=metrics.to_dict(),
                status="success",
            )

        except AudioValidationError as val_exc:
            metrics.status = "failed"
            metrics.error_message = str(val_exc)
            metrics.total_latency_ms = int((time.perf_counter() - turn_start) * 1000)
            self.telemetry.record_turn(metrics)
            VoiceLifecycleController.transition(session, VoiceSessionStatus.ACTIVE)
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
                if "exceeds maximum limit" in str(val_exc)
                else status.HTTP_400_BAD_REQUEST,
                detail=str(val_exc),
            ) from val_exc

        except (STTRecognitionError, TTSSynthesisError) as engine_exc:
            metrics.status = "failed"
            metrics.error_message = str(engine_exc)
            metrics.total_latency_ms = int((time.perf_counter() - turn_start) * 1000)
            self.telemetry.record_turn(metrics)
            VoiceLifecycleController.transition(session, VoiceSessionStatus.ACTIVE)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Speech engine error: {engine_exc}",
            ) from engine_exc

        except Exception as exc:
            metrics.status = "failed"
            metrics.error_message = str(exc)
            metrics.total_latency_ms = int((time.perf_counter() - turn_start) * 1000)
            self.telemetry.record_turn(metrics)
            VoiceLifecycleController.transition(session, VoiceSessionStatus.ACTIVE)
            raise


# Service instance
voice_service = VoiceRuntimeService()


@router.post("/sessions", response_model=VoiceSessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(
    data: CreateVoiceSessionRequest,
    x_tenant_id: Annotated[str, Header(alias="X-Tenant-ID", description="Tenant ID")],
    x_user_id: Annotated[str, Header(alias="X-User-ID", description="User ID")],
) -> VoiceSessionResponse:
    """Create authenticated voice session for tenant and user."""
    session = voice_service.manager.create_session(
        tenant_id=x_tenant_id,
        user_id=x_user_id,
        agent_id=data.agent_id,
        conversation_id=data.conversation_id,
        duration_seconds=data.duration_seconds,
        max_inactivity_seconds=data.max_inactivity_seconds,
        metadata=data.metadata,
    )
    return VoiceSessionResponse(
        session_id=session.session_id,
        tenant_id=session.tenant_id,
        user_id=session.user_id,
        agent_id=session.agent_id,
        conversation_id=session.conversation_id,
        session_token=session.session_token,
        status=session.status.value,
        expires_at=session.expires_at.isoformat(),
        max_inactivity_seconds=session.max_inactivity_seconds,
    )


@router.get("/sessions/{session_id}", response_model=VoiceSessionResponse)
def get_session(
    session_id: str,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
) -> VoiceSessionResponse:
    """Query voice session state with tenant validation."""
    try:
        session = voice_service.manager.get_session(session_id, tenant_id=x_tenant_id)
        return VoiceSessionResponse(
            session_id=session.session_id,
            tenant_id=session.tenant_id,
            user_id=session.user_id,
            agent_id=session.agent_id,
            conversation_id=session.conversation_id,
            session_token=session.session_token,
            status=session.status.value,
            expires_at=session.expires_at.isoformat(),
            max_inactivity_seconds=session.max_inactivity_seconds,
        )
    except (SessionNotFoundError, SessionExpiredError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SessionUnauthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/audio", response_model=VoiceTurnResponse)
async def upload_audio_turn(
    session_id: str,
    audio: Annotated[UploadFile, File(description="Audio recording file")],
    x_session_token: Annotated[str, Header(alias="X-Session-Token", description="Voice session token")],
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
) -> VoiceTurnResponse:
    """Upload recorded audio turn, perform STT, Agent reasoning, and TTS response."""
    audio_bytes = await audio.read()
    fmt = audio.filename.split(".")[-1] if audio.filename and "." in audio.filename else "wav"

    return voice_service.process_audio_turn(
        session_id=session_id,
        token=x_session_token,
        audio_bytes=audio_bytes,
        audio_format=fmt,
        tenant_id=x_tenant_id,
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def close_session(
    session_id: str,
    x_session_token: Annotated[str, Header(alias="X-Session-Token")],
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
) -> Response:
    """Terminate and close voice session."""
    try:
        session = voice_service.manager.authenticate_session(session_id, x_session_token, tenant_id=x_tenant_id)
        voice_service.manager.close_session(session.session_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except (SessionNotFoundError, SessionExpiredError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SessionUnauthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
