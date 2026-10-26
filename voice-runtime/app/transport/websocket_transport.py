"""Real-time streaming WebSocket transport with turn detection and user interruption."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.lifecycle.state_machine import VoiceLifecycleController
from app.sessions.manager import SessionExpiredError, SessionNotFoundError, SessionUnauthorizedError
from app.sessions.models import VoiceSessionStatus
from app.transport.http_transport import voice_service

logger = logging.getLogger("voice_runtime.transport.ws")

ws_router = APIRouter(prefix="/voice", tags=["Voice Streaming"])


@ws_router.websocket("/sessions/{session_id}/stream")
async def websocket_voice_stream(
    websocket: WebSocket,
    session_id: str,
    token: str | None = Query(default=None),
) -> None:
    """Real-time bi-directional voice streaming WebSocket.

    Supports incremental audio chunk delivery, user barge-in interruptions,
    immediate STT/Agent/TTS processing, and disconnect handling.
    """
    await websocket.accept()
    session = None
    accumulated_audio = bytearray()
    turn_active = False

    # 1. Authentication Handshake
    try:
        auth_token = token
        if not auth_token:
            # Wait for initial auth message
            auth_msg_raw = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
            auth_data = json.loads(auth_msg_raw)
            if auth_data.get("type") != "auth" or not auth_data.get("token"):
                await websocket.send_json({"type": "error", "code": "AUTH_REQUIRED", "message": "Auth token required."})
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
            auth_token = auth_data["token"]

        session = voice_service.manager.authenticate_session(session_id, auth_token)
        VoiceLifecycleController.transition(session, VoiceSessionStatus.LISTENING)
        await websocket.send_json({
            "type": "ready",
            "session_id": session.session_id,
            "status": session.status.value,
        })
    except (TimeoutError, SessionNotFoundError, SessionUnauthorizedError, SessionExpiredError) as exc:
        logger.warning("WebSocket auth failed for session %s: %s", session_id, exc)
        try:
            await websocket.send_json({"type": "error", "code": "AUTH_FAILED", "message": str(exc)})
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        except Exception:
            pass
        return

    # 2. Main Streaming Loop
    try:
        while True:
            # Receive either text control frame or binary audio
            message = await websocket.receive()
            if "text" in message:
                try:
                    payload = json.loads(message["text"])
                except Exception:
                    continue

                msg_type = payload.get("type")

                # Heartbeat keep-alive
                if msg_type == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": int(time.time())})
                    session.touch()
                    continue

                # User barge-in / Interruption
                if msg_type == "interrupt":
                    logger.info("Received client interruption signal for session %s", session_id)
                    VoiceLifecycleController.handle_user_interruption(session, reason="client_interrupt_message")
                    accumulated_audio.clear()
                    turn_active = False
                    VoiceLifecycleController.transition(session, VoiceSessionStatus.LISTENING)
                    await websocket.send_json({"type": "interrupted", "session_id": session_id})
                    continue

                # Streamed audio chunk in JSON
                if msg_type == "audio_chunk":
                    chunk_b64 = payload.get("data", "")
                    if chunk_b64:
                        chunk_bytes = base64.b64decode(chunk_b64)
                        accumulated_audio.extend(chunk_bytes)
                        turn_active = True
                    continue

                # Turn End: Trigger processing of accumulated audio buffer
                if msg_type == "end_turn":
                    if not accumulated_audio:
                        await websocket.send_json({
                            "type": "turn_empty",
                            "message": "No audio received before end_turn.",
                        })
                        continue

                    # Process turn
                    audio_turn_bytes = bytes(accumulated_audio)
                    accumulated_audio.clear()
                    turn_active = False

                    fmt = payload.get("format", session.audio_format)
                    try:
                        turn_res = voice_service.process_audio_turn(
                            session_id=session.session_id,
                            token=session.session_token,
                            audio_bytes=audio_turn_bytes,
                            audio_format=fmt,
                            tenant_id=session.tenant_id,
                        )

                        # Emit progressive feedback
                        if turn_res.user_transcript:
                            await websocket.send_json({
                                "type": "transcript",
                                "text": turn_res.user_transcript,
                            })

                        if turn_res.agent_response_text:
                            await websocket.send_json({
                                "type": "agent_text",
                                "text": turn_res.agent_response_text,
                            })

                        if turn_res.audio_response_base64:
                            await websocket.send_json({
                                "type": "audio_response",
                                "data": turn_res.audio_response_base64,
                                "format": turn_res.audio_format,
                                "duration_seconds": turn_res.audio_duration_seconds,
                            })

                        await websocket.send_json({
                            "type": "turn_complete",
                            "turn_id": turn_res.turn_id,
                            "telemetry": turn_res.telemetry,
                            "status": turn_res.status,
                        })

                        VoiceLifecycleController.transition(session, VoiceSessionStatus.LISTENING)

                    except Exception as turn_exc:
                        logger.error("Error processing stream turn: %s", turn_exc)
                        await websocket.send_json({
                            "type": "error",
                            "code": "TURN_PROCESSING_ERROR",
                            "message": str(turn_exc),
                        })
                        VoiceLifecycleController.transition(session, VoiceSessionStatus.LISTENING)
                    continue

            elif "bytes" in message:
                # Raw binary PCM/WAV chunk
                raw_chunk = message["bytes"]
                accumulated_audio.extend(raw_chunk)
                turn_active = True

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for session %s", session_id)
        if session:
            VoiceLifecycleController.transition(session, VoiceSessionStatus.CLOSED)
    except Exception as exc:
        logger.error("WebSocket stream error for session %s: %s", session_id, exc)
        if session:
            VoiceLifecycleController.transition(session, VoiceSessionStatus.CLOSED)
