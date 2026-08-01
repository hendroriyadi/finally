"""LiteLLM -> OpenRouter -> Cerebras call, with parsing that never raises."""

from __future__ import annotations

import logging
import os

from pydantic import ValidationError

from .schema import AssistantResponse

logger = logging.getLogger(__name__)

MODEL = "openrouter/openai/gpt-oss-120b"
EXTRA_BODY = {"provider": {"order": ["cerebras"]}}
REASONING_EFFORT = "low"

FALLBACK_MESSAGE = (
    "I had trouble generating a response just now. Nothing was traded. "
    "Please try asking again."
)

NO_API_KEY_MESSAGE = (
    "The AI assistant is not configured: set OPENROUTER_API_KEY in your .env file "
    "and restart, or set LLM_MOCK=true to use canned responses."
)


def mock_mode_enabled() -> bool:
    """True when LLM_MOCK is set to a truthy value."""
    return os.getenv("LLM_MOCK", "").strip().lower() in {"1", "true", "yes", "on"}


def parse_response(raw: str | None) -> AssistantResponse:
    """Validate the model's JSON. Malformed output degrades to a safe reply."""
    if not raw:
        logger.warning("LLM returned an empty response body")
        return AssistantResponse(message=FALLBACK_MESSAGE)
    try:
        return AssistantResponse.model_validate_json(raw)
    except ValidationError:
        logger.warning("LLM response did not match the schema: %s", raw[:500])
        return AssistantResponse(message=FALLBACK_MESSAGE)


def complete(messages: list[dict[str, str]]) -> AssistantResponse:
    """Call the model and return a validated response, never raising."""
    from litellm import completion

    if not os.getenv("OPENROUTER_API_KEY", "").strip():
        logger.warning("OPENROUTER_API_KEY is not set — chat is unavailable")
        return AssistantResponse(message=NO_API_KEY_MESSAGE)

    try:
        response = completion(
            model=MODEL,
            messages=messages,
            response_format=AssistantResponse,
            reasoning_effort=REASONING_EFFORT,
            extra_body=EXTRA_BODY,
        )
    except Exception:
        logger.exception("LLM request failed")
        return AssistantResponse(message=FALLBACK_MESSAGE)

    return parse_response(response.choices[0].message.content)
