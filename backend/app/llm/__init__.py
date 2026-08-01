"""LLM chat assistant.

    from app.llm import chat_router
    app.include_router(chat_router)

The router owns the full path (POST /api/chat) — no prefix needed at include time.
Set LLM_MOCK=true to serve deterministic canned replies instead of calling
OpenRouter; see `mock.py` for the trigger rules.
"""

from .router import router as chat_router
from .schema import (
    ActionResult,
    AssistantResponse,
    ChatRequest,
    ChatResponse,
    TradeInstruction,
    WatchlistChange,
)
from .service import handle_chat

__all__ = [
    "chat_router",
    "handle_chat",
    "ActionResult",
    "AssistantResponse",
    "ChatRequest",
    "ChatResponse",
    "TradeInstruction",
    "WatchlistChange",
]
