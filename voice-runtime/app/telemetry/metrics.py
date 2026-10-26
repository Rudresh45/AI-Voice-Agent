"""Voice runtime telemetry, latency measurement, and metrics collection."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("voice_runtime.telemetry")


@dataclass
class VoiceTurnMetrics:
    """Latency and volume telemetry for a single voice interaction turn."""

    session_id: str
    tenant_id: str
    turn_id: str
    stt_latency_ms: int = 0
    agent_latency_ms: int = 0
    tts_latency_ms: int = 0
    total_latency_ms: int = 0
    audio_input_bytes: int = 0
    audio_input_duration_s: float = 0.0
    audio_output_bytes: int = 0
    audio_output_duration_s: float = 0.0
    transcript_chars: int = 0
    response_chars: int = 0
    status: str = "success"  # "success", "interrupted", "failed", "silence", "timeout"
    error_message: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return data


class TelemetryCollector:
    """In-memory telemetry collector and audit logger for voice metrics."""

    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self._metrics_history: list[VoiceTurnMetrics] = []

    def record_turn(self, metrics: VoiceTurnMetrics) -> None:
        """Record turn telemetry and log structured operational event."""
        self._metrics_history.append(metrics)
        if len(self._metrics_history) > self.max_history:
            self._metrics_history.pop(0)

        logger.info(
            "VoiceTurn telemetry: tenant=%s session=%s turn=%s status=%s "
            "stt_ms=%d agent_ms=%d tts_ms=%d total_ms=%d",
            metrics.tenant_id,
            metrics.session_id,
            metrics.turn_id,
            metrics.status,
            metrics.stt_latency_ms,
            metrics.agent_latency_ms,
            metrics.tts_latency_ms,
            metrics.total_latency_ms,
        )

    def get_metrics_summary(self, tenant_id: str | None = None) -> dict[str, Any]:
        """Aggregate metrics summary (averages, counts, error rates)."""
        filtered = [
            m for m in self._metrics_history
            if tenant_id is None or m.tenant_id == tenant_id
        ]
        if not filtered:
            return {
                "total_turns": 0,
                "avg_stt_ms": 0,
                "avg_agent_ms": 0,
                "avg_tts_ms": 0,
                "avg_total_ms": 0,
                "error_rate": 0.0,
            }

        total = len(filtered)
        errors = sum(1 for m in filtered if m.status in ("failed", "timeout"))
        avg_stt = sum(m.stt_latency_ms for m in filtered) // total
        avg_agent = sum(m.agent_latency_ms for m in filtered) // total
        avg_tts = sum(m.tts_latency_ms for m in filtered) // total
        avg_total = sum(m.total_latency_ms for m in filtered) // total

        return {
            "total_turns": total,
            "avg_stt_ms": avg_stt,
            "avg_agent_ms": avg_agent,
            "avg_tts_ms": avg_tts,
            "avg_total_ms": avg_total,
            "error_rate": round(errors / total, 4),
        }

    def clear(self) -> None:
        self._metrics_history.clear()


# Global default collector
telemetry_collector = TelemetryCollector()
