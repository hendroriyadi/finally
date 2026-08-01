"""System prompt and prompt assembly for the chat assistant."""

from __future__ import annotations

from app.portfolio import PortfolioValuation, WatchlistItem
from db import ChatMessage

SYSTEM_PROMPT = """\
You are FinAlly, an AI trading assistant embedded in a simulated trading terminal.
The user trades a virtual $10,000 portfolio — no real money is at stake.

Your job:
- Analyze portfolio composition, risk concentration, and P&L. Name specific numbers.
- Suggest trades and always give the reasoning behind them.
- Execute trades when the user asks for them or agrees to a suggestion. Do not ask
  for confirmation twice — put the trade in the `trades` array and it runs.
- Manage the watchlist proactively: add tickers you are discussing, remove ones the
  user has lost interest in.
- Be concise and data-driven. A few sentences, not essays. No markdown headings.

Rules:
- Market orders only, filled instantly at the live price in the context below.
- A ticker must be on the watchlist to have a live price. To trade something new,
  add it to the watchlist in the same response.
- Never invent prices, positions, or history — use only the context provided.
- Leave `trades` and `watchlist_changes` empty unless you intend those actions to
  happen right now. They execute automatically the moment you return them.
- Always respond with valid JSON matching the required schema."""


def format_context(portfolio: PortfolioValuation, watchlist: list[WatchlistItem]) -> str:
    """Render the live portfolio and watchlist as a compact text block."""
    lines = [
        "=== PORTFOLIO ===",
        f"Cash: ${portfolio.cash_balance:,.2f}",
        f"Positions value: ${portfolio.positions_value:,.2f}",
        f"Total value: ${portfolio.total_value:,.2f}",
        f"Unrealized P&L: ${portfolio.unrealized_pnl:,.2f} "
        f"({portfolio.unrealized_pnl_percent:+.2f}%)",
        "",
    ]

    if portfolio.positions:
        lines.append("Holdings:")
        lines.extend(
            f"  {p.ticker}: {p.quantity:g} @ ${p.avg_cost:,.2f} avg, now ${p.current_price:,.2f}, "
            f"value ${p.market_value:,.2f}, P&L ${p.unrealized_pnl:,.2f} "
            f"({p.unrealized_pnl_percent:+.2f}%), {p.weight * 100:.1f}% of portfolio"
            for p in portfolio.positions
        )
    else:
        lines.append("Holdings: none — the portfolio is all cash.")

    lines.append("")
    lines.append("=== WATCHLIST ===")
    if watchlist:
        lines.extend(
            f"  {item.ticker}: "
            + (f"${item.price:,.2f}" if item.price is not None else "no price yet")
            + (
                f" ({item.change_percent:+.2f}% today)"
                if item.change_percent is not None
                else ""
            )
            for item in watchlist
        )
    else:
        lines.append("  (empty)")

    return "\n".join(lines)


def build_messages(
    user_message: str,
    context_block: str,
    history: list[ChatMessage],
) -> list[dict[str, str]]:
    """Assemble the message list: system + live context + history + new message."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"Live account state:\n{context_block}"},
    ]
    messages.extend({"role": m.role, "content": m.content} for m in history)
    messages.append({"role": "user", "content": user_message})
    return messages
