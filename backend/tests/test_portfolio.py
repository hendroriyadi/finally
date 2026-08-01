"""Trade execution and portfolio valuation logic."""

import pytest

import db
from app.portfolio import (
    TradeError,
    compute_portfolio,
    execute_trade,
    list_watchlist,
    record_snapshot,
    total_portfolio_value,
)


class TestComputePortfolio:
    def test_fresh_portfolio_is_all_cash(self):
        valuation = compute_portfolio()

        assert valuation.cash_balance == 10000.0
        assert valuation.positions == []
        assert valuation.positions_value == 0.0
        assert valuation.total_value == 10000.0
        assert valuation.unrealized_pnl == 0.0
        assert valuation.unrealized_pnl_percent == 0.0

    def test_position_marked_to_live_price(self, prices):
        db.upsert_position("AAPL", 10, 90.0)

        position = compute_portfolio().positions[0]

        assert position.ticker == "AAPL"
        assert position.current_price == 100.0
        assert position.cost_basis == 900.0
        assert position.market_value == 1000.0
        assert position.unrealized_pnl == 100.0
        assert position.unrealized_pnl_percent == pytest.approx(11.1111, abs=1e-4)

    def test_losing_position_reports_negative_pnl(self, prices):
        db.upsert_position("AAPL", 5, 120.0)

        valuation = compute_portfolio()

        assert valuation.positions[0].unrealized_pnl == -100.0
        assert valuation.unrealized_pnl == -100.0
        assert valuation.total_value == 10500.0

    def test_position_without_a_price_falls_back_to_avg_cost(self):
        db.upsert_position("ZZZZ", 4, 25.0)

        position = compute_portfolio().positions[0]

        assert position.current_price == 25.0
        assert position.unrealized_pnl == 0.0

    def test_weights_reflect_share_of_total_value(self, prices):
        db.set_cash_balance(0.0)
        db.upsert_position("AAPL", 10, 100.0)  # 1000
        db.upsert_position("GOOGL", 5, 200.0)  # 1000

        weights = {p.ticker: p.weight for p in compute_portfolio().positions}

        assert weights == {"AAPL": 0.5, "GOOGL": 0.5}

    def test_total_portfolio_value_matches_valuation(self, prices):
        db.upsert_position("AAPL", 10, 90.0)

        assert total_portfolio_value() == 11000.0


class TestBuy:
    def test_successful_buy(self, prices):
        result = execute_trade("AAPL", "buy", 10)

        assert result.success
        assert result.price == 100.0
        assert result.cost == 1000.0
        assert result.cash_balance == 9000.0
        assert result.position_quantity == 10
        assert result.position_avg_cost == 100.0
        assert db.get_profile().cash_balance == 9000.0

    def test_buy_records_a_trade_and_a_snapshot(self, prices):
        execute_trade("AAPL", "buy", 10)

        trades = db.list_trades()
        assert len(trades) == 1
        assert (trades[0].ticker, trades[0].side, trades[0].quantity) == ("AAPL", "buy", 10)
        assert db.latest_snapshot().total_value == 10000.0

    def test_second_buy_averages_the_cost(self, prices):
        execute_trade("AAPL", "buy", 10)
        prices.update("AAPL", 200.0)

        result = execute_trade("AAPL", "buy", 10)

        assert result.position_quantity == 20
        assert result.position_avg_cost == 150.0
        assert db.get_profile().cash_balance == 7000.0

    def test_fill_price_comes_from_the_cache_not_the_caller(self, prices):
        prices.update("AAPL", 137.25)

        result = execute_trade("aapl", "buy", 2)

        assert result.price == 137.25
        assert result.cost == 274.5

    def test_fractional_shares(self, prices):
        result = execute_trade("AAPL", "buy", 0.5)

        assert result.success
        assert result.position_quantity == 0.5
        assert result.cash_balance == 9950.0

    def test_ticker_is_normalized(self, prices):
        result = execute_trade("  aapl  ", "buy", 1)

        assert result.ticker == "AAPL"
        assert db.get_position("AAPL") is not None

    def test_insufficient_cash_is_rejected(self, prices):
        result = execute_trade("AAPL", "buy", 1000)

        assert not result.success
        assert result.error_code == TradeError.INSUFFICIENT_CASH
        assert "Insufficient cash" in result.reason

    def test_rejected_buy_writes_nothing(self, prices):
        execute_trade("AAPL", "buy", 1000)

        assert db.get_profile().cash_balance == 10000.0
        assert db.list_positions() == []
        assert db.count_trades() == 0

    def test_buy_can_spend_the_entire_balance(self, prices):
        result = execute_trade("AAPL", "buy", 100)

        assert result.success
        assert result.cash_balance == 0.0


class TestSell:
    def test_successful_sell_leaves_avg_cost_untouched(self, prices):
        execute_trade("AAPL", "buy", 10)
        prices.update("AAPL", 150.0)

        result = execute_trade("AAPL", "sell", 4)

        assert result.success
        assert result.price == 150.0
        assert result.position_quantity == 6
        assert result.position_avg_cost == 100.0
        assert result.cash_balance == 9600.0

    def test_selling_the_whole_position_deletes_it(self, prices):
        execute_trade("AAPL", "buy", 10)

        result = execute_trade("AAPL", "sell", 10)

        assert result.success
        assert result.position_quantity == 0
        assert db.get_position("AAPL") is None
        assert db.list_positions() == []

    def test_selling_at_a_loss(self, prices):
        execute_trade("AAPL", "buy", 10)
        prices.update("AAPL", 50.0)

        result = execute_trade("AAPL", "sell", 10)

        assert result.cash_balance == 9500.0
        assert result.total_value == 9500.0

    def test_selling_more_than_owned_is_rejected(self, prices):
        execute_trade("AAPL", "buy", 5)

        result = execute_trade("AAPL", "sell", 6)

        assert not result.success
        assert result.error_code == TradeError.INSUFFICIENT_SHARES
        assert "only 5" in result.reason
        assert db.get_position("AAPL").quantity == 5

    def test_selling_an_unheld_ticker_is_rejected(self, prices):
        result = execute_trade("AAPL", "sell", 1)

        assert not result.success
        assert result.error_code == TradeError.INSUFFICIENT_SHARES


class TestTradeValidation:
    def test_untracked_ticker_has_no_price(self):
        result = execute_trade("ZZZZ", "buy", 1)

        assert not result.success
        assert result.error_code == TradeError.NO_PRICE
        assert "watchlist" in result.reason

    def test_unknown_side_is_rejected(self, prices):
        result = execute_trade("AAPL", "short", 1)

        assert not result.success
        assert result.error_code == TradeError.INVALID_SIDE

    @pytest.mark.parametrize("quantity", [0, -5])
    def test_non_positive_quantity_is_rejected(self, prices, quantity):
        result = execute_trade("AAPL", "buy", quantity)

        assert not result.success
        assert result.error_code == TradeError.INVALID_QUANTITY

    def test_empty_ticker_is_rejected(self, prices):
        result = execute_trade("   ", "buy", 1)

        assert not result.success
        assert result.error_code == TradeError.INVALID_TICKER

    def test_failure_result_serializes(self, prices):
        payload = execute_trade("AAPL", "buy", 1000).to_dict()

        assert payload["success"] is False
        assert payload["error_code"] == TradeError.INSUFFICIENT_CASH
        assert payload["trade_id"] is None


class TestSnapshots:
    def test_record_snapshot_captures_total_value(self, prices):
        db.upsert_position("AAPL", 10, 90.0)

        snapshot = record_snapshot()

        assert snapshot.total_value == 11000.0
        assert db.latest_snapshot().id == snapshot.id


class TestWatchlistValuation:
    def test_seeded_watchlist_joins_prices(self, prices):
        items = {item.ticker: item for item in list_watchlist()}

        assert len(items) == 10
        assert items["AAPL"].price == 100.0
        assert items["NVDA"].price is None
        assert items["NVDA"].direction == "flat"

    def test_direction_reflects_the_latest_tick(self, prices):
        prices.update("AAPL", 105.0)

        item = next(i for i in list_watchlist() if i.ticker == "AAPL")

        assert item.direction == "up"
        assert item.change == 5.0
