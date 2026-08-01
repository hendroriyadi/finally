"""Chat orchestration: context -> LLM -> auto-execution -> persistence."""

from __future__ import annotations

import asyncio
import logging

import db
from app.portfolio import compute_portfolio, execute_trade, list_watchlist
from app.watchlist_service import add_ticker, remove_ticker

from .client import complete, mock_mode_enabled
from .mock import mock_response
from .prompt import build_messages, format_context
from .schema import ActionResult, AssistantResponse, ChatResponse

logger = logging.getLogger(__name__)

# How many past turns are replayed to the model. Enough for a coherent
# conversation without paying for the whole history on every call.
HISTORY_LIMIT = 20


async def handle_chat(user_message: str, user_id: str = db.DEFAULT_USER_ID) -> ChatResponse:
    """Answer a chat message, running any actions the assistant asks for."""
    portfolio = compute_portfolio(user_id)
    watchlist = list_watchlist(user_id)
    history = db.list_chat_messages(user_id, limit=HISTORY_LIMIT)

    if mock_mode_enabled():
        assistant = mock_response(user_message, portfolio)
    else:
        messages = build_messages(user_message, format_context(portfolio, watchlist), history)
        assistant = await asyncio.to_thread(complete, messages)

    response = await _apply_actions(assistant, user_id)

    db.insert_chat_message("user", user_message, None, user_id)
    db.insert_chat_message("assistant", response.message, response.actions_payload(), user_id)
    return response


async def _apply_actions(assistant: AssistantResponse, user_id: str) -> ChatResponse:
    """Execute the assistant's actions and fold any failures into the reply.

    Watchlist changes run first: a ticker only has a live price once the market
    data source is tracking it, so "add NVDA and buy 5" has to happen in that order.
    """
    watchlist_results = [
        await _apply_watchlist_change(change.ticker, change.action, user_id)
        for change in assistant.watchlist_changes
    ]
    trade_results = [
        _apply_trade(trade.ticker, trade.side, trade.quantity, user_id)
        for trade in assistant.trades
    ]

    message = assistant.message
    failures = [r.describe() for r in watchlist_results + trade_results if not r.success]
    if failures:
        message = f"{message}\n\nNote: " + "; ".join(failures) + "."

    return ChatResponse(
        message=message,
        trades=trade_results,
        watchlist_changes=watchlist_results,
    )


def _apply_trade(ticker: str, side: str, quantity: float, user_id: str) -> ActionResult:
    result = execute_trade(ticker, side, quantity, user_id)
    if not result.success:
        logger.info("LLM trade rejected: %s %s %s — %s", side, quantity, ticker, result.reason)
    return ActionResult(
        kind="trade",
        ticker=result.ticker,
        action=result.side,
        quantity=result.quantity,
        price=result.price,
        success=result.success,
        error=result.reason,
    )


async def _apply_watchlist_change(ticker: str, action: str, user_id: str) -> ActionResult:
    symbol = db.normalize_ticker(ticker)
    try:
        if action == "add":
            await add_ticker(symbol, user_id)
            success, error = True, None
        else:
            removed = await remove_ticker(symbol, user_id)
            success = removed
            error = None if removed else f"{symbol} was not on the watchlist."
    except ValueError as exc:
        success, error = False, str(exc)

    if not success:
        logger.info("LLM watchlist change rejected: %s %s — %s", action, symbol, error)
    return ActionResult(
        kind="watchlist",
        ticker=symbol,
        action=action,
        success=success,
        error=error,
    )
