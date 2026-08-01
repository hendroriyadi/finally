"""Deterministic stand-in for the LLM, used when LLM_MOCK=true.

Trigger rules (keyword-based, case-insensitive, first match wins):

1. The word "watchlist" appears -> a watchlist change. "remove"/"drop" means
   remove, anything else means add.
2. The word "buy" or "sell" appears -> a trade on that side.
3. Otherwise -> a plain informational portfolio summary, no actions.

The ticker is the first ALL-CAPS 1-5 letter token in the original message
(pronouns and a few common abbreviations are ignored); it falls back to PYPL for
watchlist changes and AAPL for trades. The quantity is the first number in the
message, defaulting to 1.
"""

from __future__ import annotations

import re

from app.portfolio import PortfolioValuation

from .schema import AssistantResponse, TradeInstruction, WatchlistChange

TICKER_RE = re.compile(r"\b[A-Z]{1,5}\b")
QUANTITY_RE = re.compile(r"\b(\d+(?:\.\d+)?)\b")
NOT_TICKERS = frozenset({"I", "A", "AI", "OK", "USD", "P", "L", "US", "PM", "AM"})

DEFAULT_TRADE_TICKER = "AAPL"
DEFAULT_WATCHLIST_TICKER = "PYPL"


def _extract_ticker(message: str, fallback: str) -> str:
    for candidate in TICKER_RE.findall(message):
        if candidate not in NOT_TICKERS:
            return candidate
    return fallback


def _extract_quantity(message: str) -> float:
    match = QUANTITY_RE.search(message)
    return float(match.group(1)) if match else 1.0


def mock_response(user_message: str, portfolio: PortfolioValuation) -> AssistantResponse:
    """Produce a canned response for `user_message`. Same input -> same output."""
    lowered = user_message.lower()

    if "watchlist" in lowered:
        ticker = _extract_ticker(user_message, DEFAULT_WATCHLIST_TICKER)
        removing = "remove" in lowered or "drop" in lowered
        action = "remove" if removing else "add"
        verb = "Removed" if removing else "Added"
        preposition = "from" if removing else "to"
        return AssistantResponse(
            message=f"{verb} {ticker} {preposition} your watchlist.",
            watchlist_changes=[WatchlistChange(ticker=ticker, action=action)],
        )

    if "buy" in lowered or "sell" in lowered:
        side = "sell" if "sell" in lowered else "buy"
        ticker = _extract_ticker(user_message, DEFAULT_TRADE_TICKER)
        quantity = _extract_quantity(user_message)
        preposition = "of" if side == "sell" else "share(s) of"
        return AssistantResponse(
            message=f"Placing a market order to {side} {quantity:g} {preposition} {ticker}.",
            trades=[TradeInstruction(ticker=ticker, side=side, quantity=quantity)],
        )

    return AssistantResponse(
        message=(
            f"You are holding {len(portfolio.positions)} position(s) worth "
            f"${portfolio.positions_value:,.2f}, with "
            f"${portfolio.cash_balance:,.2f} in cash for a total of "
            f"${portfolio.total_value:,.2f}. "
            "Ask me to buy or sell anything, or to change your watchlist."
        )
    )
