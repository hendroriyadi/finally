"""Row dataclasses returned by the repository layer."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

DEFAULT_USER_ID = "default"


def utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string (sorts lexicographically)."""
    return datetime.now(UTC).isoformat()


def new_id() -> str:
    """Fresh UUID4 primary key."""
    return str(uuid.uuid4())


@dataclass(frozen=True)
class UserProfile:
    id: str
    cash_balance: float
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> UserProfile:
        return cls(id=row["id"], cash_balance=row["cash_balance"], created_at=row["created_at"])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WatchlistEntry:
    id: str
    user_id: str
    ticker: str
    added_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> WatchlistEntry:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            ticker=row["ticker"],
            added_at=row["added_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Position:
    id: str
    user_id: str
    ticker: str
    quantity: float
    avg_cost: float
    updated_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Position:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            ticker=row["ticker"],
            quantity=row["quantity"],
            avg_cost=row["avg_cost"],
            updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Trade:
    id: str
    user_id: str
    ticker: str
    side: str
    quantity: float
    price: float
    executed_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Trade:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            ticker=row["ticker"],
            side=row["side"],
            quantity=row["quantity"],
            price=row["price"],
            executed_at=row["executed_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PortfolioSnapshot:
    id: str
    user_id: str
    total_value: float
    recorded_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> PortfolioSnapshot:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            total_value=row["total_value"],
            recorded_at=row["recorded_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ChatMessage:
    id: str
    user_id: str
    role: str
    content: str
    actions: Any | None
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> ChatMessage:
        raw = row["actions"]
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            role=row["role"],
            content=row["content"],
            actions=json.loads(raw) if raw else None,
            created_at=row["created_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
