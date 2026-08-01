"""Structured output schema for the chat assistant (PLAN.md section 9)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TradeInstruction(BaseModel):
    """A trade the assistant wants executed on the user's behalf."""

    ticker: str
    side: Literal["buy", "sell"]
    quantity: float


class WatchlistChange(BaseModel):
    """A watchlist modification the assistant wants applied."""

    ticker: str
    action: Literal["add", "remove"]


class AssistantResponse(BaseModel):
    """What the LLM returns. Only `message` is guaranteed to be populated."""

    message: str
    trades: list[TradeInstruction] = Field(default_factory=list)
    watchlist_changes: list[WatchlistChange] = Field(default_factory=list)


class ActionResult(BaseModel):
    """Outcome of one auto-executed action, echoed back to the frontend.

    Failures are reported here rather than raised: a rejected trade still
    produces a chat response so the user learns why (PLAN.md section 9).
    """

    kind: Literal["trade", "watchlist"]
    ticker: str
    action: str
    quantity: float | None = None
    price: float | None = None
    success: bool
    error: str | None = None

    def describe(self) -> str:
        """One-line human summary, used to append failure notes to the reply."""
        if self.kind == "trade":
            what = f"{self.action} {self.quantity:g} {self.ticker}"
        else:
            what = f"{self.action} {self.ticker} {'to' if self.action == 'add' else 'from'} the watchlist"
        return what if self.success else f"could not {what} — {self.error}"


class ChatRequest(BaseModel):
    """Body of POST /api/chat."""

    message: str


class ChatResponse(BaseModel):
    """Body returned by POST /api/chat."""

    message: str
    trades: list[ActionResult] = Field(default_factory=list)
    watchlist_changes: list[ActionResult] = Field(default_factory=list)

    def actions_payload(self) -> dict | None:
        """JSON-serializable `actions` column value, or None if nothing ran."""
        if not self.trades and not self.watchlist_changes:
            return None
        return {
            "trades": [t.model_dump() for t in self.trades],
            "watchlist_changes": [w.model_dump() for w in self.watchlist_changes],
        }
