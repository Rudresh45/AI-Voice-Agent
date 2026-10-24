"""Bounded conversation context builder and memory manager."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from google.genai import types

from app.models.base import ToolCall

logger = logging.getLogger("agent_runtime.memory")


@dataclass
class ConversationTurn:
    """Individual dialogue or tool execution turn."""

    role: str  # "user", "model", "tool"
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_response_name: str | None = None
    tool_response_data: dict[str, Any] | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class ConversationMemory:
    """Bounded, tenant-isolated in-memory conversation context manager.

    Maintains bounded context history to prevent token window exhaustion and
    formats messages into native Gemini SDK Content structures.
    """

    def __init__(
        self,
        *,
        system_instruction: str = "You are an authorized enterprise AI assistant.",
        max_turns: int = 20,
    ):
        self.system_instruction = system_instruction
        self.max_turns = max(4, max_turns)
        self.turns: list[ConversationTurn] = []

    def add_user_message(self, text: str) -> None:
        """Record user input turn."""
        self.turns.append(ConversationTurn(role="user", content=text))

    def add_model_message(
        self,
        content: str | None = None,
        tool_calls: list[ToolCall] | None = None,
    ) -> None:
        """Record model response turn, including any tool invocation requests."""
        self.turns.append(
            ConversationTurn(
                role="model",
                content=content,
                tool_calls=list(tool_calls) if tool_calls else [],
            )
        )

    def add_tool_response(self, tool_name: str, response_data: dict[str, Any]) -> None:
        """Record output from an executed backend tool."""
        self.turns.append(
            ConversationTurn(
                role="tool",
                tool_response_name=tool_name,
                tool_response_data=response_data,
            )
        )

    def get_bounded_turns(self) -> list[ConversationTurn]:
        """Return a bounded slice of turns: preserves first user turn + recent turns."""
        if len(self.turns) <= self.max_turns:
            return list(self.turns)

        # Always preserve the initial query for task coherence, plus the tail
        first_turn = self.turns[0]
        tail_count = self.max_turns - 1
        return [first_turn] + self.turns[-tail_count:]

    def to_gemini_contents(self) -> list[types.Content]:
        """Compile bounded conversation history into official Gemini types.Content objects."""
        bounded_turns = self.get_bounded_turns()
        contents: list[types.Content] = []

        for turn in bounded_turns:
            if turn.role == "user":
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=turn.content or "")],
                    )
                )
            elif turn.role == "model":
                parts: list[types.Part] = []
                if turn.content:
                    parts.append(types.Part.from_text(text=turn.content))
                for tc in turn.tool_calls:
                    parts.append(
                        types.Part.from_function_call(name=tc.name, args=tc.arguments)
                    )
                if parts:
                    contents.append(types.Content(role="model", parts=parts))
            elif turn.role == "tool":
                # In Gemini SDK, tool responses are submitted as role="user" with function_response part
                contents.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_function_response(
                                name=turn.tool_response_name or "unknown_tool",
                                response=turn.tool_response_data or {},
                            )
                        ],
                    )
                )

        return contents

    def clear(self) -> None:
        """Reset conversation memory."""
        self.turns.clear()
