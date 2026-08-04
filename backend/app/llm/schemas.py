"""The structured-output wire contract, reproduced exactly from
`planning/PLAN.md` §9 — this file is the authority for what the LLM is asked
to generate, not an internal convenience. A rename of any field here is a
change to what the provider is instructed to produce, not a refactor.

`Trade` and `WatchlistChange` deliberately declare `side`/`action` as
two-value `Literal`s rather than a bare `str`: that narrowness is what turns
a hallucinated third value into a parse failure handled once, at the
`chat_completion()` boundary, instead of a string that reaches
`execute_trade()` and has to be rejected again downstream.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Trade(BaseModel):
    ticker: str
    side: Literal["buy", "sell"]
    quantity: float


class WatchlistChange(BaseModel):
    ticker: str
    action: Literal["add", "remove"]


class ChatCompletionResult(BaseModel):
    message: str
    # default_factory=list (not `= []`) so a provider that omits the key
    # entirely and one that emits an explicit empty array both parse to the
    # same value — Pydantic v2 fills the default when the key is missing.
    trades: list[Trade] = Field(default_factory=list)
    watchlist_changes: list[WatchlistChange] = Field(default_factory=list)
