"""Pure, deterministic, keyword-triggered stand-in for a model reply.

This module imports nothing from the LLM SDK and issues no I/O of any
kind — Phase 5's browser suite and this phase's own tests both run against
it, so a single network call here would make the whole downstream test
surface flaky and key-dependent. `mock_chat_completion()` reads only the
latest user turn's text and returns a schema-valid `ChatCompletionResult`
every time, never touching the network.

Watchlist changes are parsed here even though nothing consumes them until
Plan 04-03. That is deliberate: this module is the fixed reference
implementation of the schema, and a mock that could only produce half the
schema would let a shape mismatch hide until the plan that needs the other
half.
"""

from __future__ import annotations

import re

from app.llm.schemas import ChatCompletionResult, Trade, WatchlistChange

# Deliberately simple keyword patterns — this is a test/demo fixture, not a
# real NLU layer. Every match still round-trips through the exact same
# ChatCompletionResult Pydantic shape the real client produces (CHAT-07).
_BUY_RE = re.compile(r"\bbuy\s+(\d+(?:\.\d+)?)\s+(?:shares?\s+of\s+)?([a-z.]{1,10})\b", re.I)
_SELL_RE = re.compile(r"\bsell\s+(\d+(?:\.\d+)?)\s+(?:shares?\s+of\s+)?([a-z.]{1,10})\b", re.I)
_ADD_RE = re.compile(r"\badd\s+([a-z.]{1,10})\s+to\s+(?:my\s+)?watchlist\b", re.I)
_REMOVE_RE = re.compile(r"\bremove\s+([a-z.]{1,10})\s+from\s+(?:my\s+)?watchlist\b", re.I)

_MOCK_ACTION_MESSAGE = "Done — I've made the changes you asked for."
_MOCK_NO_ACTION_MESSAGE = (
    "This is a mock response (LLM_MOCK=true) — ask me to buy/sell a ticker or "
    "update your watchlist."
)


def mock_chat_completion(messages: list[dict]) -> ChatCompletionResult:
    """Pure function — no network, no litellm import. Parses the latest
    user turn for buy/sell/add/remove keywords and returns a deterministic,
    schema-valid ChatCompletionResult every time."""
    user_text = messages[-1]["content"]

    trades: list[Trade] = []
    if m := _BUY_RE.search(user_text):
        trades.append(Trade(ticker=m.group(2).upper(), side="buy", quantity=float(m.group(1))))
    if m := _SELL_RE.search(user_text):
        trades.append(Trade(ticker=m.group(2).upper(), side="sell", quantity=float(m.group(1))))

    watchlist_changes: list[WatchlistChange] = []
    if m := _ADD_RE.search(user_text):
        watchlist_changes.append(WatchlistChange(ticker=m.group(1).upper(), action="add"))
    if m := _REMOVE_RE.search(user_text):
        watchlist_changes.append(WatchlistChange(ticker=m.group(1).upper(), action="remove"))

    message = _MOCK_ACTION_MESSAGE if (trades or watchlist_changes) else _MOCK_NO_ACTION_MESSAGE

    return ChatCompletionResult(message=message, trades=trades, watchlist_changes=watchlist_changes)
