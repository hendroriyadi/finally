"""LLM_MOCK trigger rules and determinism."""

import pytest

from app.llm.mock import mock_response
from app.portfolio import PortfolioValuation


@pytest.fixture
def portfolio():
    return PortfolioValuation(
        cash_balance=10000.0,
        positions=[],
        positions_value=0.0,
        total_value=10000.0,
        cost_basis=0.0,
        unrealized_pnl=0.0,
        unrealized_pnl_percent=0.0,
    )


def test_plain_question_returns_a_summary_with_no_actions(portfolio):
    response = mock_response("How is my portfolio doing?", portfolio)

    assert response.trades == []
    assert response.watchlist_changes == []
    assert "$10,000.00" in response.message


def test_buy_with_quantity_and_ticker(portfolio):
    response = mock_response("Buy 5 shares of AAPL", portfolio)

    assert len(response.trades) == 1
    trade = response.trades[0]
    assert (trade.ticker, trade.side, trade.quantity) == ("AAPL", "buy", 5.0)


def test_sell_with_quantity_and_ticker(portfolio):
    response = mock_response("sell 2 TSLA please", portfolio)

    trade = response.trades[0]
    assert (trade.ticker, trade.side, trade.quantity) == ("TSLA", "sell", 2.0)


def test_bare_buy_uses_defaults(portfolio):
    trade = mock_response("I want to buy something", portfolio).trades[0]

    assert (trade.ticker, trade.side, trade.quantity) == ("AAPL", "buy", 1.0)


def test_fractional_quantity(portfolio):
    trade = mock_response("buy 2.5 NVDA", portfolio).trades[0]

    assert trade.quantity == 2.5


def test_watchlist_add(portfolio):
    response = mock_response("Add PYPL to my watchlist", portfolio)

    assert response.trades == []
    change = response.watchlist_changes[0]
    assert (change.ticker, change.action) == ("PYPL", "add")


def test_watchlist_remove(portfolio):
    change = mock_response("remove NFLX from the watchlist", portfolio).watchlist_changes[0]

    assert (change.ticker, change.action) == ("NFLX", "remove")


def test_watchlist_wins_over_buy(portfolio):
    """"Add X to the watchlist so I can buy it" must not fire a trade."""
    response = mock_response("Add NVDA to the watchlist so I can buy it later", portfolio)

    assert response.trades == []
    assert response.watchlist_changes[0].ticker == "NVDA"


def test_bare_watchlist_uses_default_ticker(portfolio):
    change = mock_response("do something with my watchlist", portfolio).watchlist_changes[0]

    assert (change.ticker, change.action) == ("PYPL", "add")


def test_pronoun_is_not_mistaken_for_a_ticker(portfolio):
    trade = mock_response("I would like to buy 3 GOOGL", portfolio).trades[0]

    assert trade.ticker == "GOOGL"


def test_same_input_gives_identical_output(portfolio):
    first = mock_response("Buy 5 shares of AAPL", portfolio)
    second = mock_response("Buy 5 shares of AAPL", portfolio)

    assert first.model_dump() == second.model_dump()
