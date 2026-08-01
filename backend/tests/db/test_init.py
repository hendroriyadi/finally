"""Tests for schema creation, seeding, and lazy initialization."""

import sqlite3

import pytest

import db
from db import (
    DEFAULT_CASH_BALANCE,
    DEFAULT_TICKERS,
    DEFAULT_USER_ID,
    TABLE_NAMES,
    connect,
    get_connection,
    get_db_path,
    init_db,
)
from db.schema import missing_tables


class TestSchemaCreation:
    def test_init_creates_file(self, db_path):
        assert not db_path.exists()
        init_db()
        assert db_path.exists()

    def test_init_creates_all_tables(self):
        init_db()
        conn = connect(get_db_path())
        try:
            assert missing_tables(conn) == []
        finally:
            conn.close()

    def test_all_expected_tables_present(self):
        init_db()
        with get_connection() as conn:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        names = {row["name"] for row in rows}
        for table in TABLE_NAMES:
            assert table in names

    def test_wal_mode_enabled(self):
        init_db()
        with get_connection() as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"

    def test_lazy_init_on_first_access(self, db_path):
        assert not db_path.exists()
        profile = db.get_profile()
        assert db_path.exists()
        assert profile is not None

    def test_side_check_constraint(self):
        init_db()
        with get_connection() as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at)"
                    " VALUES ('x', 'default', 'AAPL', 'hold', 1, 1, 'now')"
                )

    def test_role_check_constraint(self):
        init_db()
        with get_connection() as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at)"
                    " VALUES ('x', 'default', 'system', 'hi', NULL, 'now')"
                )


class TestSeeding:
    def test_seeds_profile(self):
        init_db()
        profile = db.get_profile()
        assert profile is not None
        assert profile.id == DEFAULT_USER_ID
        assert profile.cash_balance == DEFAULT_CASH_BALANCE

    def test_seeds_ten_tickers(self):
        init_db()
        tickers = db.list_watchlist_tickers()
        assert tickers == list(DEFAULT_TICKERS)

    def test_reinit_does_not_duplicate(self):
        init_db()
        init_db()
        init_db()
        assert len(db.list_watchlist()) == len(DEFAULT_TICKERS)

    def test_reinit_preserves_modified_cash(self):
        init_db()
        db.set_cash_balance(4321.0)
        init_db()
        assert db.get_profile().cash_balance == 4321.0

    def test_reinit_does_not_restore_removed_ticker(self):
        init_db()
        db.remove_watchlist_ticker("AAPL")
        init_db()
        assert "AAPL" not in db.list_watchlist_tickers()

    def test_reinit_preserves_user_rows(self):
        init_db()
        db.insert_trade("AAPL", "buy", 5, 100.0)
        db.upsert_position("AAPL", 5, 100.0)
        init_db()
        assert db.count_trades() == 1
        assert len(db.list_positions()) == 1

    def test_seed_defaults_returns_false_when_already_seeded(self):
        init_db()
        with get_connection() as conn:
            assert db.seed_defaults(conn) is False

    def test_is_seeded_false_on_empty_schema(self, tmp_path):
        conn = connect(tmp_path / "blank.db")
        try:
            conn.executescript(db.SCHEMA_SQL)
            assert db.is_seeded(conn) is False
        finally:
            conn.close()


class TestEnsureInitialized:
    def test_ensure_initialized_is_cached(self, db_path):
        db.ensure_initialized()
        db_path.unlink()
        # Cached: no re-creation attempted, so the file stays gone.
        db.ensure_initialized()
        assert not db_path.exists()

    def test_reset_cache_reinitializes(self, db_path):
        db.ensure_initialized()
        db_path.unlink()
        db.reset_initialization_cache()
        db.ensure_initialized()
        assert db_path.exists()


class TestTransaction:
    def test_transaction_commits(self):
        with db.transaction() as conn:
            db.insert_trade("AAPL", "buy", 1, 10.0, conn=conn)
        assert db.count_trades() == 1

    def test_transaction_rolls_back(self):
        with pytest.raises(RuntimeError):
            with db.transaction() as conn:
                db.insert_trade("AAPL", "buy", 1, 10.0, conn=conn)
                raise RuntimeError("boom")
        assert db.count_trades() == 0

    def test_multiple_writes_share_one_connection(self):
        with db.transaction() as conn:
            db.adjust_cash_balance(-500.0, conn=conn)
            db.upsert_position("AAPL", 5, 100.0, conn=conn)
            db.insert_trade("AAPL", "buy", 5, 100.0, conn=conn)
        assert db.get_profile().cash_balance == DEFAULT_CASH_BALANCE - 500.0
        assert db.get_position("AAPL").quantity == 5
        assert db.count_trades() == 1
