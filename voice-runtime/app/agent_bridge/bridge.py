"""Bridge connecting voice sessions to the Agent Runtime harness."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.harness.runner import AgentConfig, AgentExecutionResult, AgentRunner
from app.models.gemini import redact_sensitive
from app.policies.authorization import PrincipalContext
from app.sessions.models import VoiceSession

logger = logging.getLogger("voice_runtime.agent_bridge")


@dataclass
class AgentBridgeResult:
    """Output from agent reasoning turn triggered by voice transcript."""

    output_text: str
    agent_latency_ms: int
    steps_taken: int
    tool_executions: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    error_message: str | None = None

    @property
    def is_success(self) -> bool:
        return self.error_message is None


class VoiceAgentBridge:
    """Bridges authenticated voice turns to the enterprise Agent Runtime."""

    def __init__(
        self,
        runner: AgentRunner | None = None,
        default_agent_config: AgentConfig | None = None,
    ):
        self.runner = runner or AgentRunner(agent_config=default_agent_config)

    def process_turn(
        self,
        session: VoiceSession,
        transcript: str,
    ) -> AgentBridgeResult:
        """Execute a speech transcript through the agent harness within tenant bounds."""
        start_time = time.perf_counter()

        # Build strict principal context from session authentication
        role = session.metadata.get("role", "agent_operator")
        allowed_tools = set(session.metadata.get("allowed_tools", self.runner.config.allowed_tools))

        context = PrincipalContext(
            tenant_id=session.tenant_id,
            user_id=session.user_id,
            role=role,
            allowed_tools=allowed_tools,
        )

        logger.info(
            "AgentBridge executing turn for tenant=%s user=%s session=%s conv=%s transcript_len=%d",
            session.tenant_id,
            session.user_id,
            session.session_id,
            session.conversation_id,
            len(transcript),
        )

        try:
            exec_res: AgentExecutionResult = self.runner.execute(
                user_input=transcript,
                context=context,
                conversation_id=session.conversation_id,
            )
            latency_ms = int((time.perf_counter() - start_time) * 1000)

            return AgentBridgeResult(
                output_text=exec_res.output_text,
                agent_latency_ms=max(1, latency_ms),
                steps_taken=exec_res.steps_taken,
                tool_executions=exec_res.tool_executions,
                usage=exec_res.usage,
                error_message=exec_res.error_message,
            )
        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            clean_err = redact_sensitive(str(exc))
            logger.error("Agent execution failed for session %s: %s", session.session_id, clean_err)
            return AgentBridgeResult(
                output_text="I apologize, but I encountered an error processing your request. Please try again.",
                agent_latency_ms=latency_ms,
                steps_taken=0,
                error_message=clean_err,
            )
