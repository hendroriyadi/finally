"""FinAlly SQLite persistence layer.

Pure CRUD — no business rules. Nothing here checks for sufficient cash or shares;
validation belongs to the API layer.

    from db import get_profile, list_positions, insert_trade, transaction

Every repository function takes an optional keyword-only ``conn``. Pass None (the
default) and it opens and commits its own short-lived connection. Pass a connection
from ``transaction()`` to make several writes atomic:

    with transaction() as conn:
        adjust_cash_balance(-cost, conn=conn)
        upsert_position("AAPL", qty, avg_cost, conn=conn)
        insert_trade("AAPL", "buy", qty, price, conn=conn)

The database file is created and seeded lazily on first access.
"""

from .chat_repo import clear_chat_messages, insert_chat_message, list_chat_messages
from .connection import DB_PATH_ENV_VAR, DEFAULT_DB_PATH, connect, get_db_path
from .database import (
    ensure_initialized,
    get_connection,
    init_db,
    reset_initialization_cache,
    transaction,
    use_connection,
)
from .models import (
    DEFAULT_USER_ID,
    ChatMessage,
    PortfolioSnapshot,
    Position,
    Trade,
    UserProfile,
    WatchlistEntry,
    new_id,
    utc_now_iso,
)
from .positions_repo import delete_position, get_position, list_positions, upsert_position
from .profile_repo import adjust_cash_balance, create_profile, get_profile, set_cash_balance
from .schema import SCHEMA_SQL, TABLE_NAMES
from .seed import DEFAULT_CASH_BALANCE, DEFAULT_TICKERS, is_seeded, seed_defaults
from .snapshots_repo import insert_snapshot, latest_snapshot, list_snapshots
from .trades_repo import count_trades, insert_trade, list_trades
from .watchlist_repo import (
    add_watchlist_ticker,
    is_watching,
    list_watchlist,
    list_watchlist_tickers,
    normalize_ticker,
    remove_watchlist_ticker,
)

__all__ = [
    # connection / lifecycle
    "DB_PATH_ENV_VAR",
    "DEFAULT_DB_PATH",
    "connect",
    "get_db_path",
    "init_db",
    "ensure_initialized",
    "reset_initialization_cache",
    "get_connection",
    "transaction",
    "use_connection",
    # schema / seed
    "SCHEMA_SQL",
    "TABLE_NAMES",
    "DEFAULT_CASH_BALANCE",
    "DEFAULT_TICKERS",
    "is_seeded",
    "seed_defaults",
    # models
    "DEFAULT_USER_ID",
    "UserProfile",
    "WatchlistEntry",
    "Position",
    "Trade",
    "PortfolioSnapshot",
    "ChatMessage",
    "new_id",
    "utc_now_iso",
    "normalize_ticker",
    # profile
    "get_profile",
    "create_profile",
    "set_cash_balance",
    "adjust_cash_balance",
    # watchlist
    "list_watchlist",
    "list_watchlist_tickers",
    "is_watching",
    "add_watchlist_ticker",
    "remove_watchlist_ticker",
    # positions
    "list_positions",
    "get_position",
    "upsert_position",
    "delete_position",
    # trades
    "insert_trade",
    "list_trades",
    "count_trades",
    # snapshots
    "insert_snapshot",
    "list_snapshots",
    "latest_snapshot",
    # chat
    "insert_chat_message",
    "list_chat_messages",
    "clear_chat_messages",
]
