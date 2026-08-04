"""The real LiteLLM/OpenRouter/Cerebras structured-output call.

`MODEL` and `EXTRA_BODY` are copied verbatim from
`.claude/skills/cerebras/SKILL.md` — the contract this project validated
end-to-end (short of authentication) this session. Do not substitute a
different model name or drop the provider ordering; the "fast enough for a
single loading state" design assumption rests on the Cerebras path
specifically.
"""

from __future__ import annotations

import logging

from litellm import completion
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

MODEL = "openrouter/openai/gpt-oss-120b"
EXTRA_BODY = {"provider": {"order": ["cerebras"]}}


def chat_completion(messages: list[dict], response_format: type[BaseModel]) -> BaseModel | None:
    """Blocking call — the caller must run this via `asyncio.to_thread()`.

    Returns a validated `response_format` instance, or `None` on *every*
    failure mode — network failure, authentication failure, rate limiting,
    output that is not JSON, output that is JSON but does not validate, and
    a response whose `choices` list is empty — because the caller's correct
    response to every one of them is identical (D-08, Assumption A1).
    """
    try:
        response = completion(
            model=MODEL,
            messages=messages,
            response_format=response_format,
            reasoning_effort="low",
            extra_body=EXTRA_BODY,
        )
    except Exception:
        logger.exception("LLM completion call failed")
        return None

    try:
        raw = response.choices[0].message.content
        return response_format.model_validate_json(raw)
    except (ValidationError, IndexError, AttributeError, TypeError, ValueError):
        logger.exception("LLM response failed extraction or schema validation")
        return None
