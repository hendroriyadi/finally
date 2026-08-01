"""Chat endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from .schema import ChatRequest, ChatResponse
from .service import handle_chat

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def post_chat(request: ChatRequest) -> ChatResponse:
    """Send a message to FinAlly. Any trades or watchlist changes it returns have
    already been executed by the time this responds."""
    return await handle_chat(request.message)
