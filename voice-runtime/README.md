# Voice Runtime — Integration Boundary

Real-time audio is not implemented in this scaffold.

Implementation order:
1. Backend creates a short-lived voice session after authentication.
2. Use WebRTC/LiveKit or authenticated WebSocket for audio.
3. Implement VAD, turn detection and interruption cancellation.
4. Integrate STT such as whisper.cpp.
5. Send transcripts and authenticated conversation IDs to the agent runtime.
6. Integrate TTS such as Piper and stream audio back.
7. Add session limits, lifecycle cleanup, telemetry and privacy controls.

Never send provider master keys to the browser. Review licenses for each engine
and voice model before commercial use.
