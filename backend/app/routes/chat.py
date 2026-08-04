"""Chat REST router.

This module contains no SQL and no valuation arithmetic of its own; every
side effect it causes happens inside a function an earlier phase already
wrote and tested (`execute_trade()`, `record_portfolio_snapshot()`,
`normalize_ticker()`). No failure of any kind leaves through it as a 5xx —
a chat turn that half-executed and then 500'd would tell the user nothing
about which half landed.
"""

from __future__ import annotations

import logging
import os
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.db.portfolio import (
    InsufficientCashError,
    InsufficientSharesError,
    NoPriceAvailableError,
    TradeRejectedError,
    execute_trade,
)
from app.db.snapshots import record_portfolio_snapshot
from app.llm.mock import mock_chat_completion
from app.llm.schemas import ChatCompletionResult, Trade
from app.routes.watchlist import normalize_ticker

logger = logging.getLogger(__name__)

# 04-UI-SPEC.md's copy contract names this as an ordinary assistant reply,
# not an error state, so it lives beside the other prose this route emits
# rather than being assembled at the call site.
LLM_FAILURE_MESSAGE = "I had trouble processing that — could you rephrase?"


class ChatRequest(BaseModel):
    # A chat body is the one free-text field in this application that
    # becomes billable model input; an unbounded one is a cost and latency
    # amplifier reachable by anyone who can reach the port (T-04-02).
    message: str = Field(min_length=1, max_length=2000)


class ActionResult(BaseModel):
    kind: Literal["trade", "watchlist"]
    status: Literal["success", "error"]
    ticker: str
    side: Literal["buy", "sell"] | None = None
    action: Literal["add", "remove"] | None = None
    # Annotated float, never Decimal — app/routes/portfolio.py's reasoning
    # applies verbatim here: a quoted number reaching the chat transcript
    # would render as a broken confirmation rather than raise.
    quantity: float | None = None
    price: float | None = None
    error: str | None = None


class ChatResponse(BaseModel):
    message: str
    actions: list[ActionResult]


def _is_mock_mode() -> bool:
    """Read fresh on every request, deliberately not resolved once at
    router-construction time. `create_market_data_source()`'s equivalent
    choice resolves once per process on purpose; copying that here would
    bake the choice into the app object before a test body could change it."""
    return os.environ.get("LLM_MOCK", "").strip().lower() == "true"


async def _get_llm_response(messages: list[dict]) -> ChatCompletionResult | None:
    if _is_mock_mode():
        return mock_chat_completion(messages)
    # Task 2 replaces this line with the threaded real-client call. `None`
    # is already the route's graceful-failure value, so this branch is
    # functionally complete-but-empty rather than a placeholder that
    # changes shape later.
    return None


async def _execute_trade_action(trade: Trade, request: Request) -> ActionResult:
    # normalize_ticker() raises HTTPException directly by design — the
    # single most likely way this endpoint breaks is letting that escape a
    # loop over several actions, converting one hallucinated symbol into a
    # 400 for the entire turn and discarding the valid actions beside it
    # (T-04-03).
    try:
        ticker = normalize_ticker(trade.ticker)
    except HTTPException:
        return ActionResult(
            kind="trade",
            status="error",
            ticker=trade.ticker,
            side=trade.side,
            error=f"Couldn't {trade.side} {trade.ticker} — invalid ticker symbol.",
        )

    try:
        result = await execute_trade(
            ticker, trade.side, trade.quantity, price_cache=request.app.state.price_cache
        )
    except NoPriceAvailableError:
        return ActionResult(
            kind="trade",
            status="error",
            ticker=ticker,
            side=trade.side,
            error=f"Couldn't {trade.side} {ticker} — no live price available.",
        )
    except InsufficientCashError:
        return ActionResult(
            kind="trade",
            status="error",
            ticker=ticker,
            side=trade.side,
            error=f"Couldn't buy {ticker} — insufficient cash.",
        )
    except InsufficientSharesError:
        return ActionResult(
            kind="trade",
            status="error",
            ticker=ticker,
            side=trade.side,
            error=f"Couldn't sell {ticker} — you don't own that many shares.",
        )
    except TradeRejectedError as exc:
        return ActionResult(
            kind="trade", status="error", ticker=ticker, side=trade.side, error=str(exc)
        )

    # D-17: the manual trade route makes this call after every fill; an AI
    # trade that skipped it would leave the value chart flat until the next
    # 30-second tick even though cash and positions had already moved. The
    # guard is load-bearing for the same reason it is in the manual route —
    # the trade has already committed, so a raise here would report a
    # filled order as a failure.
    try:
        await record_portfolio_snapshot(price_cache=request.app.state.price_cache)
    except Exception:
        logger.exception(
            "record_portfolio_snapshot failed after AI-initiated trade on %s", ticker
        )

    # quantity/price come from the engine's own return dict — never from
    # `trade`, whose quantity is what the model asked for rather than what
    # actually filled.
    return ActionResult(
        kind="trade",
        status="success",
        ticker=ticker,
        side=trade.side,
        quantity=result["quantity"],
        price=result["price"],
    )


def create_chat_router() -> APIRouter:
    """Create the chat router, prefix='/api/chat'."""
    router = APIRouter(prefix="/api/chat", tags=["chat"])

    @router.post("", response_model=ChatResponse)
    async def post_chat(body: ChatRequest, request: Request) -> ChatResponse:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are FinAlly, an AI trading assistant. Be concise and "
                    "data-driven. Always respond with valid structured JSON."
                ),
            },
            {"role": "user", "content": body.message},
        ]

        result = await _get_llm_response(messages)
        if result is None:
            return ChatResponse(message=LLM_FAILURE_MESSAGE, actions=[])

        actions: list[ActionResult] = []
        for trade in result.trades:
            actions.append(await _execute_trade_action(trade, request))
        # result.watchlist_changes is deliberately unhandled in this task —
        # Plan 04-03 owns it. An empty loop body would be a lie about
        # coverage; this is an explicit scope boundary instead.

        return ChatResponse(message=result.message, actions=actions)

    return router
