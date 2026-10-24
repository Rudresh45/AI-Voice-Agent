"""Configurable Google Gemini model adapter using the official google-genai SDK."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from google import genai
from google.genai import errors, types

from app.models.base import (
    ModelAdapter,
    ModelProviderError,
    ModelResponse,
    ModelTimeoutError,
    ToolCall,
    UsageTokens,
)

logger = logging.getLogger("agent_runtime.gemini")

# Redaction patterns for secrets in logs/errors
_API_KEY_REGEX = re.compile(r"AIza[0-9A-Za-z_-]{35}")
_QUERY_KEY_REGEX = re.compile(r"(key|api_key|token)=([^&\s'\"]+)", re.IGNORECASE)


def redact_sensitive(text: str) -> str:
    """Mask Google API keys and credential strings from logs and error messages."""
    if not text:
        return text
    masked = _API_KEY_REGEX.sub("AIza...[REDACTED]", text)
    masked = _QUERY_KEY_REGEX.sub(r"\1=[REDACTED]", masked)
    return masked


class GeminiAdapter(ModelAdapter):
    """Production model adapter interfacing with Google Gemini via official SDK."""

    def __init__(
        self,
        *,
        model_id: str | None = None,
        api_key: str | None = None,
        client: genai.Client | None = None,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_id = model_id or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

        if client is not None:
            self.client = client
        else:
            if not self.api_key:
                logger.warning(
                    "GEMINI_API_KEY is not configured in environment. "
                    "Live generation calls will fail unless a client is provided."
                )
            self.client = genai.Client(api_key=self.api_key or "DUMMY_KEY_FOR_LOCAL")

        logger.info("Initialized GeminiAdapter with model_id: %s", self.model_id)

    def generate(
        self,
        contents: list[Any],
        *,
        system_instruction: str | None = None,
        tools: list[Any] | None = None,
        config: dict[str, Any] | None = None,
    ) -> ModelResponse:
        """Execute a content generation request through the Gemini SDK."""
        req_config = config.copy() if config else {}
        temperature = req_config.get("temperature", 0.2)

        gen_config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction,
            tools=tools if tools else None,
        )

        try:
            raw_response = self.client.models.generate_content(
                model=self.model_id,
                contents=contents,
                config=gen_config,
            )
        except errors.APIError as exc:
            safe_msg = redact_sensitive(str(exc))
            logger.error("Gemini APIError encountered: %s", safe_msg)
            raise ModelProviderError(f"Gemini API error: {safe_msg}") from exc
        except TimeoutError as exc:
            safe_msg = redact_sensitive(str(exc))
            logger.error("Gemini timeout encountered: %s", safe_msg)
            raise ModelTimeoutError(f"Gemini request timed out: {safe_msg}") from exc
        except Exception as exc:
            safe_msg = redact_sensitive(str(exc))
            logger.error("Unexpected error in Gemini adapter: %s", safe_msg)
            raise ModelProviderError(f"Provider call failed: {safe_msg}") from exc

        return self._parse_response(raw_response)

    def _parse_response(self, raw: types.GenerateContentResponse) -> ModelResponse:
        """Parse text parts, tool calls, and usage metadata from SDK response."""
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        if raw.candidates:
            for candidate in raw.candidates:
                if candidate.content and candidate.content.parts:
                    for idx, part in enumerate(candidate.content.parts):
                        if part.text:
                            text_parts.append(part.text)
                        if part.function_call:
                            fc = part.function_call
                            call_id = f"call_{fc.name}_{idx}"
                            raw_args = dict(fc.args) if fc.args else {}
                            tool_calls.append(
                                ToolCall(id=call_id, name=fc.name, arguments=raw_args)
                            )

        content = "".join(text_parts).strip() if text_parts else None

        usage = UsageTokens()
        if raw.usage_metadata:
            meta = raw.usage_metadata
            usage = UsageTokens(
                prompt_tokens=meta.prompt_token_count or 0,
                response_tokens=meta.response_token_count or 0,
                total_tokens=meta.total_token_count or 0,
            )

        return ModelResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            raw_response=raw,
        )
