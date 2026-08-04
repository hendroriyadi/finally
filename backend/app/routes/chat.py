"""Chat REST router.

This module contains no SQL and no valuation arithmetic of its own; every
side effect it causes happens inside a function an earlier phase already
wrote and tested (`execute_trade()`, `record_portfolio_snapshot()`,
`normalize_ticker()`). No failure of any kind leaves through it as a 5xx —
a chat turn that half-executed and then 500'd would tell the user nothing
about which half landed.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.db.chat import append_chat_message, list_recent_chat_messages
from app.db.portfolio import (
    InsufficientCashError,
    InsufficientSharesError,
    NoPriceAvailableError,
    TradeRejectedError,
    execute_trade,
    get_portfolio_state,
    value_portfolio,
)
from app.db.snapshots import record_portfolio_snapshot
from app.db.watchlist import list_watchlist
from app.llm.client import chat_completion
from app.llm.mock import mock_chat_completion
from app.llm.schemas import ChatCompletionResult, Trade
from app.routes.watchlist import normalize_ticker

logger = logging.getLogger(__name__)

# 04-UI-SPEC.md's copy contract names this as an ordinary assistant reply,
# not an error state, so it lives beside the other prose this route emits
# rather than being assembled at the call site.
LLM_FAILURE_MESSAGE = "I had trouble processing that — could you rephrase?"

# planning/PLAN.md §9's six required behaviours, plus one instruction of
# this project's own (never invent a figure). Constant across every turn —
# the volatile portfolio/watchlist snapshot lives in a separate message
# built fresh per request, never concatenated in here, so "is the context
# fresh?" is answerable by looking at one string. Deliberately does not
# restate the response schema in prose: the structured-output request
# carries the schema to the provider, and a prose restatement here would be
# a second, weaker copy of the same contract that can drift from the
# Pydantic models silently.
SYSTEM_PROMPT = (
    "You are FinAlly, an AI trading assistant. You analyze portfolio "
    "composition, concentration risk, and profit and loss. You suggest "
    "trades with reasoning, and you execute trades when the user asks or "
    "agrees. You manage the user's watchlist proactively. You are concise "
    "and data-driven in every response, always grounded in the figures "
    "given to you in the message that follows this one. You never invent a "
    "price, a holding, or a balance — if a figure is not in the context you "
    "were given, say plainly that you do not have it rather than guessing."
)

_NO_PRICE_MARKER = "unavailable"


def _render_context(portfolio: dict, watchlist: list[dict]) -> str:
    """Render the volatile portfolio + watchlist snapshot as compact,
    readable lines — not raw JSON. A `None` price-derived field renders the
    explicit `_NO_PRICE_MARKER` rather than a zero: a zero price would read
    to the model as a worthless holding and could reasonably provoke a
    sell."""
    lines = [
        f"Cash balance: ${portfolio['cash_balance']:.2f}",
        f"Total portfolio value: ${portfolio['total_value']:.2f}",
    ]

    positions = portfolio.get("positions") or []
    if positions:
        lines.append("Open holdings:")
        for pos in positions:
            price = (
                f"${pos['current_price']:.2f}" if pos["current_price"] is not None else _NO_PRICE_MARKER
            )
            pnl = (
                f"${pos['unrealized_pnl']:.2f}" if pos["unrealized_pnl"] is not None else _NO_PRICE_MARKER
            )
            lines.append(
                f"  - {pos['ticker']}: {pos['quantity']} shares, avg cost "
                f"${pos['avg_cost']:.2f}, current price {price}, unrealized P&L {pnl}"
            )
    else:
        lines.append("Open holdings: none")

    if watchlist:
        lines.append("Watchlist:")
        for item in watchlist:
            price = f"${item['price']:.2f}" if item["price"] is not None else _NO_PRICE_MARKER
            lines.append(f"  - {item['ticker']}: {price}")
    else:
        lines.append("Watchlist: empty")

    return "\n".join(lines)


def build_chat_messages(
    *, portfolio: dict, watchlist: list[dict], history: list[dict], user_message: str
) -> list[dict]:
    """Pure function — no `await`, no database read, no `request` access.
    Everything it needs arrives as an argument, which is what makes CHAT-02
    assertable in one call with no fixture and no network, and what keeps a
    hidden read from creeping into the prompt path later.

    Returns, in order: the persona message (SYSTEM_PROMPT, constant), the
    rendered context message (volatile — built fresh from `portfolio` and
    `watchlist` on every call), one message per `history` entry in its
    original role order, then the new user message exactly once.
    """
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": _render_context(portfolio, watchlist)},
    ]
    for entry in history:
        messages.append({"role": entry["role"], "content": entry["content"]})
    messages.append({"role": "user", "content": user_message})
    return messages


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


class ChatMessageOut(BaseModel):
    role: str
    content: str
    # Reusing ActionResult here rather than a looser dict type is what
    # guarantees a replayed transcript and a live reply are the same shape
    # to the frontend — one card component, one prop type, no branch on
    # where the data came from.
    actions: list[ActionResult] | None
    created_at: str


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessageOut]


def _is_mock_mode() -> bool:
    """Read fresh on every request, deliberately not resolved once at
    router-construction time. `create_market_data_source()`'s equivalent
    choice resolves once per process on purpose; copying that here would
    bake the choice into the app object before a test body could change it."""
    return os.environ.get("LLM_MOCK", "").strip().lower() == "true"


async def _get_llm_response(messages: list[dict]) -> ChatCompletionResult | None:
    if _is_mock_mode():
        return mock_chat_completion(messages)
    # The thread hop is not stylistic: this handler shares one event loop
    # with the long-lived price stream, and a blocking network call made
    # directly on it stops price ticks reaching every connected browser for
    # the whole model round trip (T-04-04). Mirrors run_db()'s existing
    # seam for blocking database calls.
    return await asyncio.to_thread(chat_completion, messages, ChatCompletionResult)


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
        # Read history *before* the new user row is written, so the message
        # currently being answered can never also appear in its own history
        # (D-04/D-12 ordering).
        history = await list_recent_chat_messages()
        logger.debug("chat turn starting with %d prior messages in context", len(history))

        # Written before the model call rather than after: a turn whose
        # model call fails still leaves a record of what was asked.
        await append_chat_message(role="user", content=body.message)

        # Loaded fresh on every request — never cached on app.state or
        # anywhere else. Prices move every half second and holdings move on
        # every trade; a context cached from an earlier turn would show the
        # model a balance the user has already spent (D-15). Reuses the
        # exact get_portfolio_state() + value_portfolio() pair the portfolio
        # route and the snapshot writer both call — no third valuation path.
        state = await get_portfolio_state()
        portfolio = value_portfolio(state, request.app.state.price_cache)
        watchlist_rows = await list_watchlist()
        watchlist = [
            {
                "ticker": row["ticker"],
                "price": request.app.state.price_cache.get_price(row["ticker"]),
            }
            for row in watchlist_rows
        ]

        # The history replayed here is user-supplied text and must be
        # treated as data, not instruction (T-04-11). No mitigation for that
        # lives in the prompt; every action the model proposes below still
        # passes the same ticker validation and the same atomic engine
        # guards a hand-typed request passes, so no phrasing can reach a
        # mutation the manual path would refuse.
        messages = build_chat_messages(
            portfolio=portfolio,
            watchlist=watchlist,
            history=history,
            user_message=body.message,
        )

        result = await _get_llm_response(messages)
        if result is None:
            await append_chat_message(role="assistant", content=LLM_FAILURE_MESSAGE, actions=[])
            return ChatResponse(message=LLM_FAILURE_MESSAGE, actions=[])

        actions: list[ActionResult] = []
        for trade in result.trades:
            actions.append(await _execute_trade_action(trade, request))
        # result.watchlist_changes is deliberately unhandled in this task —
        # Plan 04-03 owns it. An empty loop body would be a lie about
        # coverage; this is an explicit scope boundary instead.

        # Same reply text and the same action list the response is built
        # from, so the stored row and the returned body can never disagree.
        await append_chat_message(
            role="assistant",
            content=result.message,
            actions=[a.model_dump(exclude_none=True) for a in actions],
        )

        return ChatResponse(message=result.message, actions=actions)

    @router.get("/history", response_model=ChatHistoryResponse)
    async def get_chat_history() -> ChatHistoryResponse:
        rows = await list_recent_chat_messages()
        return ChatHistoryResponse(messages=[ChatMessageOut(**row) for row in rows])

    return router
