"""Enterprise agent harness managing configuration, execution lifecycle, and audit hooks."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from dotenv import load_dotenv

from app.memory.conversation import ConversationMemory
from app.models.base import ModelAdapter
from app.models.gemini import GeminiAdapter, redact_sensitive
from app.orchestration.loop import (
    OrchestrationConfig,
    OrchestrationLoop,
    OrchestrationResult,
)
from app.policies.authorization import PolicyEngine, PrincipalContext
from app.tools.registry import ToolRegistry, get_default_tool_registry

logger = logging.getLogger("agent_runtime.harness")


@dataclass
class AgentConfig:
    """Authorized runtime configuration for an agent."""

    agent_id: str = "agent-default"
    name: str = "Enterprise Voice/Text Assistant"
    instructions: str = (
        "You are an authorized enterprise assistant. "
        "Be concise, professional, and accurate. "
        "Never claim an action succeeded unless verified by a trusted tool result. "
        "Never ask for or reveal secrets."
    )
    model_id: str = "gemini-2.5-flash"
    temperature: float = 0.2
    allowed_tools: set[str] = field(
        default_factory=lambda: {
            "lookup_customer",
            "search_knowledge_base",
            "schedule_callback",
            "cancel_reservation",
        }
    )
    max_steps: int = 5
    max_tool_calls_total: int = 10
    timeout_seconds: float = 30.0


@dataclass
class AgentExecutionResult:
    """Standardized response from the agent harness."""

    conversation_id: str
    output_text: str
    status: str
    steps_taken: int
    tool_executions: list[dict[str, Any]]
    usage: dict[str, int]
    pending_confirmation: dict[str, Any] | None = None
    error_message: str | None = None

    @property
    def is_success(self) -> bool:
        return self.status == "completed"


class AgentRunner:
    """Harness managing the full execution lifecycle of an authorized agent."""

    def __init__(
        self,
        *,
        agent_config: AgentConfig | None = None,
        model: ModelAdapter | None = None,
        registry: ToolRegistry | None = None,
        policy_engine: PolicyEngine | None = None,
        on_usage_hook: Callable[[str, int, str, dict[str, Any]], None] | None = None,
        on_audit_hook: Callable[[str, str, str, str, dict[str, Any]], None] | None = None,
    ):
        load_dotenv()
        self.config = agent_config or AgentConfig()
        self.registry = registry or get_default_tool_registry()
        self.policy_engine = policy_engine or PolicyEngine()
        self.model = model or GeminiAdapter(model_id=self.config.model_id)

        self.on_usage_hook = on_usage_hook
        self.on_audit_hook = on_audit_hook

        self.memory = ConversationMemory(
            system_instruction=self.config.instructions,
            max_turns=20,
        )

        orch_config = OrchestrationConfig(
            max_steps=self.config.max_steps,
            max_tool_calls_total=self.config.max_tool_calls_total,
            timeout_seconds=self.config.timeout_seconds,
        )
        self.orchestration = OrchestrationLoop(
            model=self.model,
            registry=self.registry,
            policy_engine=self.policy_engine,
            config=orch_config,
        )

    def execute(
        self,
        user_input: str,
        context: PrincipalContext,
        conversation_id: str | None = None,
    ) -> AgentExecutionResult:
        """Execute a user request within a strict tenant boundary and authorization context."""
        cid = conversation_id or str(uuid.uuid4())
        logger.info(
            "Executing request for tenant=%s, user=%s, conv=%s",
            context.tenant_id,
            context.user_id,
            cid,
        )

        # 1. Append user input to bounded conversation memory
        self.memory.add_user_message(user_input)

        # 2. Run bounded orchestration loop
        res: OrchestrationResult = self.orchestration.run(
            memory=self.memory,
            context=context,
        )

        # 3. Format tool execution summaries safely (redact sensitive values)
        tool_summaries: list[dict[str, Any]] = []
        for te in res.tool_executions:
            tool_summaries.append({
                "tool_name": te.tool_name,
                "call_id": te.call_id,
                "status": te.status,
                "arguments": te.arguments,
                "result": te.result,
                "error_message": redact_sensitive(te.error_message or ""),
                "duration_ms": te.duration_ms,
            })

        # 4. Trigger Usage Hooks
        usage_dict = {
            "prompt_tokens": res.total_usage.prompt_tokens,
            "response_tokens": res.total_usage.response_tokens,
            "total_tokens": res.total_usage.total_tokens,
        }
        if self.on_usage_hook:
            try:
                self.on_usage_hook(
                    "llm_tokens",
                    res.total_usage.total_tokens,
                    "tokens",
                    {
                        "tenant_id": context.tenant_id,
                        "conversation_id": cid,
                        "agent_id": self.config.agent_id,
                        "model_id": self.config.model_id,
                        "details": usage_dict,
                    },
                )
            except Exception as hook_exc:  # noqa: BLE001 - hooks must never crash core execution
                logger.warning("Usage event hook failed: %s", hook_exc)

        # 5. Trigger Audit Event Hooks
        if self.on_audit_hook:
            try:
                self.on_audit_hook(
                    "agent_orchestration_run",
                    "conversation",
                    cid,
                    "SUCCESS" if res.is_success else "FAILURE",
                    {
                        "tenant_id": context.tenant_id,
                        "user_id": context.user_id,
                        "status": res.status,
                        "steps": res.steps_taken,
                        "tools_invoked": [t["tool_name"] for t in tool_summaries],
                    },
                )
            except Exception as hook_exc:  # noqa: BLE001 - hooks must never crash core execution
                logger.warning("Audit event hook failed: %s", hook_exc)

        return AgentExecutionResult(
            conversation_id=cid,
            output_text=res.final_response or "",
            status=res.status,
            steps_taken=res.steps_taken,
            tool_executions=tool_summaries,
            usage=usage_dict,
            pending_confirmation=res.pending_confirmation,
            error_message=res.error_message,
        )

    def run(self, user_text: str) -> str:
        """Convenience method for simple single-tenant testing/CLI."""
        # Default local tenant context
        context = PrincipalContext(
            tenant_id="tenant-local-dev",
            user_id="local-user",
            role="agent_operator",
            allowed_tools=self.config.allowed_tools,
        )
        result = self.execute(user_text, context)
        return result.output_text
