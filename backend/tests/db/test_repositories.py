"""CRUD tests for every repository module."""

import sqlite3

import pytest

import db
from db import DEFAULT_CASH_BALANCE, DEFAULT_TICKERS, get_connection


class TestProfileRepo:
    def test_get_profile_returns_seeded_row(self):
        profile = db.get_profile()
        assert profile.id == "default"
        assert profile.cash_balance == DEFAULT_CASH_BALANCE
        assert profile.created_at

    def test_get_profile_unknown_user(self):
        assert db.get_profile("nobody") is None

    def test_create_profile(self):
        profile = db.create_profile("alice", 500.0)
        assert profile.id == "alice"
        assert profile.cash_balance == 500.0

    def test_create_profile_is_idempotent(self):
        db.create_profile("alice", 500.0)
        again = db.create_profile("alice", 999.0)
        assert again.cash_balance == 500.0

    def test_set_cash_balance(self):
        updated = db.set_cash_balance(1234.56)
        assert updated.cash_balance == 1234.56
        assert db.get_profile().cash_balance == 1234.56

    def test_set_cash_balance_unknown_user(self):
        assert db.set_cash_balance(10.0, "nobody") is None

    def test_adjust_cash_balance_up_and_down(self):
        db.adjust_cash_balance(-1000.0)
        assert db.get_profile().cash_balance == DEFAULT_CASH_BALANCE - 1000.0
        db.adjust_cash_balance(250.0)
        assert db.get_profile().cash_balance == DEFAULT_CASH_BALANCE - 750.0

    def test_adjust_allows_negative_balance(self):
        """No validation at this layer — overdraft is the API layer's concern."""
        db.adjust_cash_balance(-999999.0)
        assert db.get_profile().cash_balance < 0

    def test_to_dict(self):
        assert set(db.get_profile().to_dict()) == {"id", "cash_balance", "created_at"}


class TestWatchlistRepo:
    def test_seeded_watchlist(self):
        assert db.list_watchlist_tickers() == list(DEFAULT_TICKERS)

    def test_entries_have_fields(self):
        entry = db.list_watchlist()[0]
        assert entry.user_id == "default"
        assert entry.ticker == "AAPL"
        assert entry.id and entry.added_at

    def test_add_ticker(self):
        entry = db.add_watchlist_ticker("PYPL")
        assert entry.ticker == "PYPL"
        assert "PYPL" in db.list_watchlist_tickers()

    def test_add_normalizes_case_and_whitespace(self):
        entry = db.add_watchlist_ticker("  pypl \n")
        assert entry.ticker == "PYPL"

    def test_add_duplicate_is_idempotent(self):
        first = db.add_watchlist_ticker("PYPL")
        second = db.add_watchlist_ticker("pypl")
        assert first.id == second.id
        assert db.list_watchlist_tickers().count("PYPL") == 1

    def test_unique_constraint_enforced_at_sql_level(self):
        with get_connection() as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO watchlist (id, user_id, ticker, added_at)"
                    " VALUES ('dup', 'default', 'AAPL', 'now')"
                )

    def test_is_watching(self):
        assert db.is_watching("AAPL") is True
        assert db.is_watching("aapl") is True
        assert db.is_watching("PYPL") is False

    def test_remove_ticker(self):
        assert db.remove_watchlist_ticker("AAPL") is True
        assert "AAPL" not in db.list_watchlist_tickers()

    def test_remove_missing_ticker(self):
        assert db.remove_watchlist_ticker("ZZZZ") is False

    def test_watchlists_are_per_user(self):
        db.add_watchlist_ticker("PYPL", "alice")
        assert db.list_watchlist_tickers("alice") == ["PYPL"]
        assert "PYPL" not in db.list_watchlist_tickers()


class TestPositionsRepo:
    def test_no_positions_initially(self):
        assert db.list_positions() == []

    def test_upsert_creates(self):
        position = db.upsert_position("AAPL", 10, 190.0)
        assert position.ticker == "AAPL"
        assert position.quantity == 10
        assert position.avg_cost == 190.0
        assert len(db.list_positions()) == 1

    def test_upsert_updates_existing_row(self):
        first = db.upsert_position("AAPL", 10, 190.0)
        second = db.upsert_position("AAPL", 15, 195.0)
        assert first.id == second.id
        assert second.quantity == 15
        assert second.avg_cost == 195.0
        assert len(db.list_positions()) == 1

    def test_fractional_quantity(self):
        position = db.upsert_position("AAPL", 0.5, 190.0)
        assert position.quantity == 0.5

    def test_get_position(self):
        db.upsert_position("AAPL", 10, 190.0)
        assert db.get_position("aapl").quantity == 10
        assert db.get_position("TSLA") is None

    def test_list_positions_sorted_by_ticker(self):
        db.upsert_position("TSLA", 1, 250.0)
        db.upsert_position("AAPL", 1, 190.0)
        db.upsert_position("MSFT", 1, 420.0)
        assert [p.ticker for p in db.list_positions()] == ["AAPL", "MSFT", "TSLA"]

    def test_delete_position(self):
        db.upsert_position("AAPL", 10, 190.0)
        assert db.delete_position("AAPL") is True
        assert db.get_position("AAPL") is None

    def test_delete_missing_position(self):
        assert db.delete_position("AAPL") is False

    def test_positions_are_per_user(self):
        db.upsert_position("AAPL", 10, 190.0)
        db.upsert_position("AAPL", 3, 100.0, "alice")
        assert db.get_position("AAPL").quantity == 10
        assert db.get_position("AAPL", "alice").quantity == 3


class TestTradesRepo:
    def test_insert_trade(self):
        trade = db.insert_trade("AAPL", "buy", 10, 190.0)
        assert trade.ticker == "AAPL"
        assert trade.side == "buy"
        assert trade.quantity == 10
        assert trade.price == 190.0
        assert trade.executed_at

    def test_insert_normalizes_ticker_and_side(self):
        trade = db.insert_trade(" aapl ", "SELL", 1, 190.0)
        assert trade.ticker == "AAPL"
        assert trade.side == "sell"

    def test_trade_log_is_append_only(self):
        db.insert_trade("AAPL", "buy", 10, 190.0)
        db.insert_trade("AAPL", "sell", 4, 195.0)
        assert db.count_trades() == 2

    def test_list_trades_most_recent_first(self):
        db.insert_trade("AAPL", "buy", 1, 1.0, executed_at="2026-01-01T00:00:00+00:00")
        db.insert_trade("TSLA", "buy", 1, 2.0, executed_at="2026-02-01T00:00:00+00:00")
        assert [t.ticker for t in db.list_trades()] == ["TSLA", "AAPL"]

    def test_list_trades_filtered_by_ticker(self):
        db.insert_trade("AAPL", "buy", 1, 1.0)
        db.insert_trade("TSLA", "buy", 1, 2.0)
        assert [t.ticker for t in db.list_trades(ticker="tsla")] == ["TSLA"]

    def test_list_trades_limit(self):
        for _ in range(5):
            db.insert_trade("AAPL", "buy", 1, 1.0)
        assert len(db.list_trades(limit=2)) == 2

    def test_explicit_executed_at_preserved(self):
        stamp = "2026-03-04T12:00:00+00:00"
        assert db.insert_trade("AAPL", "buy", 1, 1.0, executed_at=stamp).executed_at == stamp

    def test_count_trades_empty(self):
        assert db.count_trades() == 0

    def test_trades_are_per_user(self):
        db.insert_trade("AAPL", "buy", 1, 1.0)
        db.insert_trade("AAPL", "buy", 1, 1.0, "alice")
        assert db.count_trades() == 1
        assert db.count_trades("alice") == 1


class TestSnapshotsRepo:
    def test_insert_snapshot(self):
        snapshot = db.insert_snapshot(10000.0)
        assert snapshot.total_value == 10000.0
        assert snapshot.recorded_at

    def test_list_snapshots_chronological(self):
        db.insert_snapshot(3.0, recorded_at="2026-03-01T00:00:00+00:00")
        db.insert_snapshot(1.0, recorded_at="2026-01-01T00:00:00+00:00")
        db.insert_snapshot(2.0, recorded_at="2026-02-01T00:00:00+00:00")
        assert [s.total_value for s in db.list_snapshots()] == [1.0, 2.0, 3.0]

    def test_list_snapshots_limit_returns_recent_but_chronological(self):
        for i in range(1, 6):
            db.insert_snapshot(float(i), recorded_at=f"2026-01-0{i}T00:00:00+00:00")
        assert [s.total_value for s in db.list_snapshots(limit=2)] == [4.0, 5.0]

    def test_list_snapshots_since(self):
        db.insert_snapshot(1.0, recorded_at="2026-01-01T00:00:00+00:00")
        db.insert_snapshot(2.0, recorded_at="2026-02-01T00:00:00+00:00")
        result = db.list_snapshots(since="2026-01-15T00:00:00+00:00")
        assert [s.total_value for s in result] == [2.0]

    def test_latest_snapshot(self):
        db.insert_snapshot(1.0, recorded_at="2026-01-01T00:00:00+00:00")
        db.insert_snapshot(2.0, recorded_at="2026-02-01T00:00:00+00:00")
        assert db.latest_snapshot().total_value == 2.0

    def test_latest_snapshot_empty(self):
        assert db.latest_snapshot() is None

    def test_empty_list(self):
        assert db.list_snapshots() == []


class TestChatRepo:
    def test_insert_user_message(self):
        message = db.insert_chat_message("user", "How is my portfolio?")
        assert message.role == "user"
        assert message.content == "How is my portfolio?"
        assert message.actions is None

    def test_actions_round_trip_as_python_object(self):
        actions = {"trades": [{"ticker": "AAPL", "side": "buy", "quantity": 10}]}
        db.insert_chat_message("assistant", "Bought 10 AAPL.", actions)
        stored = db.list_chat_messages()[0]
        assert stored.actions == actions

    def test_role_normalized(self):
        assert db.insert_chat_message("ASSISTANT", "hi").role == "assistant"

    def test_history_is_chronological(self):
        db.insert_chat_message("user", "one", created_at="2026-01-01T00:00:00+00:00")
        db.insert_chat_message("assistant", "two", created_at="2026-01-02T00:00:00+00:00")
        assert [m.content for m in db.list_chat_messages()] == ["one", "two"]

    def test_limit_keeps_most_recent_in_order(self):
        for i in range(1, 6):
            db.insert_chat_message("user", str(i), created_at=f"2026-01-0{i}T00:00:00+00:00")
        assert [m.content for m in db.list_chat_messages(limit=3)] == ["3", "4", "5"]

    def test_same_timestamp_keeps_insertion_order(self):
        stamp = "2026-01-01T00:00:00+00:00"
        db.insert_chat_message("user", "first", created_at=stamp)
        db.insert_chat_message("assistant", "second", created_at=stamp)
        assert [m.content for m in db.list_chat_messages()] == ["first", "second"]

    def test_clear_chat_messages(self):
        db.insert_chat_message("user", "hi")
        db.insert_chat_message("assistant", "hello")
        assert db.clear_chat_messages() == 2
        assert db.list_chat_messages() == []

    def test_empty_history(self):
        assert db.list_chat_messages() == []
