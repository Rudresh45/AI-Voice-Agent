"""Bounded agent orchestration loop enforcing limits, authorization, and error handling."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.memory.conversation import ConversationMemory
from app.models.base import (
    ModelAdapter,
    ModelProviderError,
    ModelTimeoutError,
    UsageTokens,
)
from app.policies.authorization import (
    AuthorizationStatus,
    PolicyEngine,
    PrincipalContext,
)
from app.tools.registry import MalformedArgumentsError, ToolRegistry
from app.tools.schemas import ToolExecutionRecord

logger = logging.getLogger("agent_runtime.orchestration")


@dataclass(frozen=True)
class OrchestrationConfig:
    """Configurable boundaries for agent orchestration loop."""

    max_steps: int = 5
    max_tool_calls_total: int = 10
    timeout_seconds: float = 30.0


@dataclass
class OrchestrationResult:
    """Structured result of bounded agent execution."""

    status: str  # "completed", "max_steps_exceeded", "tool_limit_exceeded", "confirmation_required", "provider_error"
    final_response: str | None = None
    steps_taken: int = 0
    tool_executions: list[ToolExecutionRecord] = field(default_factory=list)
    total_usage: UsageTokens = field(default_factory=UsageTokens)
    pending_confirmation: dict[str, Any] | None = None
    error_message: str | None = None

    @property
    def is_success(self) -> bool:
        return self.status == "completed"


class OrchestrationLoop:
    """Executes the bounded orchestration loop between Gemini and authorized tools."""

    def __init__(
        self,
        *,
        model: ModelAdapter,
        registry: ToolRegistry,
        policy_engine: PolicyEngine | None = None,
        config: OrchestrationConfig | None = None,
    ):
        self.model = model
        self.registry = registry
        self.policy_engine = policy_engine or PolicyEngine()
        self.config = config or OrchestrationConfig()
        # Session-level idempotency cache for side-effecting operations
        self._idempotency_cache: dict[str, dict[str, Any]] = {}

    def run(
        self,
        *,
        memory: ConversationMemory,
        context: PrincipalContext,
    ) -> OrchestrationResult:
        """Run the bounded loop until final answer, limits exceeded, or confirmation required."""
        step = 0
        total_tool_calls = 0
        execution_records: list[ToolExecutionRecord] = []
        total_prompt_tokens = 0
        total_response_tokens = 0

        # Compile Gemini tool declarations according to principal's allowed tools
        gemini_tools = self.registry.to_gemini_tools(context.allowed_tools)

        while True:
            # Check maximum model-call/step boundaries to prevent infinite loops
            if step >= self.config.max_steps:
                logger.warning(
                    "Orchestration loop reached max_steps (%d). Halting to prevent infinite loop.",
                    self.config.max_steps,
                )
                return OrchestrationResult(
                    status="max_steps_exceeded",
                    final_response=(
                        "I was unable to complete the request within the permitted execution steps. "
                        "Please verify your instructions or contact support."
                    ),
                    steps_taken=step,
                    tool_executions=execution_records,
                    total_usage=UsageTokens(
                        prompt_tokens=total_prompt_tokens,
                        response_tokens=total_response_tokens,
                        total_tokens=total_prompt_tokens + total_response_tokens,
                    ),
                    error_message="Maximum execution steps exceeded.",
                )

            step += 1
            contents = memory.to_gemini_contents()

            # Call model adapter with error isolation (never crash the API process)
            try:
                response = self.model.generate(
                    contents=contents,
                    system_instruction=memory.system_instruction,
                    tools=gemini_tools if gemini_tools else None,
                )
            except (ModelProviderError, ModelTimeoutError) as exc:
                logger.error("Model provider error on step %d: %s", step, exc)
                return OrchestrationResult(
                    status="provider_error",
                    final_response=(
                        "The language model provider encountered an error or timed out. "
                        "The platform remained stable and your request can be safely retried."
                    ),
                    steps_taken=step,
                    tool_executions=execution_records,
                    total_usage=UsageTokens(
                        prompt_tokens=total_prompt_tokens,
                        response_tokens=total_response_tokens,
                        total_tokens=total_prompt_tokens + total_response_tokens,
                    ),
                    error_message=str(exc),
                )

            # Accumulate token usage
            total_prompt_tokens += response.usage.prompt_tokens
            total_response_tokens += response.usage.response_tokens

            # Case A: Model returned text response and no tool calls
            if not response.has_tool_calls:
                answer = response.content or ""
                memory.add_model_message(content=answer)
                return OrchestrationResult(
                    status="completed",
                    final_response=answer,
                    steps_taken=step,
                    tool_executions=execution_records,
                    total_usage=UsageTokens(
                        prompt_tokens=total_prompt_tokens,
                        response_tokens=total_response_tokens,
                        total_tokens=total_prompt_tokens + total_response_tokens,
                    ),
                )

            # Case B: Model requested tool calls
            memory.add_model_message(
                content=response.content, tool_calls=response.tool_calls
            )

            for call in response.tool_calls:
                total_tool_calls += 1
                if total_tool_calls > self.config.max_tool_calls_total:
                    logger.warning(
                        "Exceeded max total tool calls (%d). Halting.",
                        self.config.max_tool_calls_total,
                    )
                    return OrchestrationResult(
                        status="tool_limit_exceeded",
                        final_response="Maximum tool execution limit exceeded for this request.",
                        steps_taken=step,
                        tool_executions=execution_records,
                        total_usage=UsageTokens(
                            prompt_tokens=total_prompt_tokens,
                            response_tokens=total_response_tokens,
                            total_tokens=total_prompt_tokens + total_response_tokens,
                        ),
                        error_message="Tool call quota exceeded.",
                    )

                # 1. Verify tool registration
                if not self.registry.has_tool(call.name):
                    logger.warning("Rejecting unregistered tool: %s", call.name)
                    rec = ToolExecutionRecord(
                        tool_name=call.name,
                        call_id=call.id,
                        arguments=call.arguments,
                        status="rejected",
                        error_message=f"Tool '{call.name}' is unregistered or not allowlisted.",
                    )
                    execution_records.append(rec)
                    memory.add_tool_response(
                        tool_name=call.name,
                        response_data={"error": f"Tool '{call.name}' is unregistered."},
                    )
                    continue

                tool = self.registry.get(call.name)

                # 2. Validate tool arguments with Pydantic
                try:
                    validated_input = tool.validate_input(call.arguments)
                except MalformedArgumentsError as exc:
                    logger.warning("Malformed arguments for %s: %s", call.name, exc)
                    rec = ToolExecutionRecord(
                        tool_name=call.name,
                        call_id=call.id,
                        arguments=call.arguments,
                        status="failed",
                        error_message=str(exc),
                    )
                    execution_records.append(rec)
                    memory.add_tool_response(
                        tool_name=call.name,
                        response_data={"error": f"Invalid arguments for '{call.name}': {exc}"},
                    )
                    continue

                # 3. Independent Authorization via Policy Engine
                auth_result = self.policy_engine.authorize_tool(
                    tool_name=tool.name,
                    is_side_effecting=tool.is_side_effecting,
                    requires_confirmation=tool.requires_confirmation,
                    context=context,
                    arguments=call.arguments,
                )

                if auth_result.status == AuthorizationStatus.DENIED:
                    logger.warning("Authorization denied for %s: %s", call.name, auth_result.reason)
                    rec = ToolExecutionRecord(
                        tool_name=call.name,
                        call_id=call.id,
                        arguments=call.arguments,
                        status="rejected",
                        error_message=auth_result.reason,
                    )
                    execution_records.append(rec)
                    memory.add_tool_response(
                        tool_name=call.name,
                        response_data={"error": f"Authorization denied: {auth_result.reason}"},
                    )
                    continue

                if auth_result.status == AuthorizationStatus.REQUIRES_CONFIRMATION:
                    logger.info("Tool %s paused for explicit user confirmation", call.name)
                    rec = ToolExecutionRecord(
                        tool_name=call.name,
                        call_id=call.id,
                        arguments=call.arguments,
                        status="confirmation_required",
                        error_message="Action requires explicit user confirmation.",
                    )
                    execution_records.append(rec)
                    return OrchestrationResult(
                        status="confirmation_required",
                        final_response=(
                            f"Action '{call.name}' requires explicit confirmation before proceeding."
                        ),
                        steps_taken=step,
                        tool_executions=execution_records,
                        total_usage=UsageTokens(
                            prompt_tokens=total_prompt_tokens,
                            response_tokens=total_response_tokens,
                            total_tokens=total_prompt_tokens + total_response_tokens,
                        ),
                        pending_confirmation=auth_result.confirmation_payload,
                    )

                # 4. Check idempotency for side-effecting operations
                idempotency_key = call.arguments.get("idempotency_key")
                cache_key = f"{context.tenant_id}:{call.name}:{idempotency_key}" if idempotency_key else None
                if cache_key and cache_key in self._idempotency_cache:
                    logger.info("Idempotent hit for %s (key=%s)", call.name, idempotency_key)
                    cached_output = self._idempotency_cache[cache_key]
                    rec = ToolExecutionRecord(
                        tool_name=call.name,
                        call_id=call.id,
                        arguments=call.arguments,
                        result=cached_output,
                        status="completed",
                        duration_ms=0,
                    )
                    execution_records.append(rec)
                    memory.add_tool_response(tool.name, cached_output)
                    continue

                # 5. Execute Approved Backend Service
                start_time = time.perf_counter()
                try:
                    result = tool.handler(context, validated_input)
                    duration_ms = int((time.perf_counter() - start_time) * 1000)

                    # Serialize result
                    result_dict = (
                        result.model_dump()
                        if hasattr(result, "model_dump")
                        else dict(result)
                    )

                    # Validate output schema
                    tool.output_schema.model_validate(result_dict)

                    if cache_key:
                        self._idempotency_cache[cache_key] = result_dict

                    rec = ToolExecutionRecord(
                        tool_name=call.name,
                        call_id=call.id,
                        arguments=call.arguments,
                        result=result_dict,
                        status="completed",
                        duration_ms=duration_ms,
                    )
                    execution_records.append(rec)
                    memory.add_tool_response(tool.name, result_dict)

                except Exception as exc:  # noqa: BLE001 - tool handler failure must not crash engine
                    duration_ms = int((time.perf_counter() - start_time) * 1000)
                    logger.error("Tool %s handler failed: %s", call.name, exc)
                    rec = ToolExecutionRecord(
                        tool_name=call.name,
                        call_id=call.id,
                        arguments=call.arguments,
                        status="failed",
                        error_message=str(exc),
                        duration_ms=duration_ms,
                    )
                    execution_records.append(rec)
                    memory.add_tool_response(
                        tool.name, {"error": f"Tool execution failed: {exc}"}
                    )
