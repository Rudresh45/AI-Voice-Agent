"""Standalone FastAPI application for Voice Runtime microservice."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.transport.http_transport import router as http_voice_router
from app.transport.websocket_transport import ws_router as ws_voice_router

app = FastAPI(
    title="AI Voice Runtime Service",
    description="Low-latency voice processing runtime with STT, TTS, agent bridging, and WebSockets.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(http_voice_router)
app.include_router(ws_voice_router)


@app.get("/health/live")
def liveness():
    return {"status": "ok", "service": "voice-runtime"}


@app.get("/health/ready")
def readiness():
    return {"status": "ready", "service": "voice-runtime"}
