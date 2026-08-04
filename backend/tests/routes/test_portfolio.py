"""End-to-end HTTP tests for the portfolio REST router.

Task 1 covers the buy path, the read side (`GET /api/portfolio`), and the
JSON-number wire boundary. Task 2 extends this file with the sell path,
rejection status codes, and the fresh-connection proof that a rejected
trade leaves state byte-identical.

Fill prices are read from the live response body (or, where a price is
needed before any trade has happened, from `client.app.state.price_cache`
directly) rather than hardcoded, since the simulator ticks prices on a
background schedule independent of the test.
"""

from __future__ import annotations

import json

import pytest

from app.db.connection import connect


def _live_price(client, ticker: str) -> float:
    price = client.app.state.price_cache.get_price(ticker)
    assert price is not None, f"expected a live price for {ticker}"
    return price


def test_buy_returns_200_and_debits_cash_exactly(client):
    response = client.post(
        "/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 10}
    )
    assert response.status_code == 200
    body = response.json()

    assert body["ticker"] == "AAPL"
    assert body["side"] == "buy"
    assert body["quantity"] == 10.0
    price = body["price"]
    assert body["cash_balance"] == pytest.approx(10000.0 - 10 * price)
    assert body["position"] == {"ticker": "AAPL", "quantity": 10.0, "avg_cost": price}


def test_second_buy_of_same_ticker_produces_weighted_average_cost(client):
    first = client.post(
        "/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 10}
    ).json()
    second = client.post(
        "/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 5}
    ).json()

    price1, price2 = first["price"], second["price"]
    expected_avg = (10 * price1 + 5 * price2) / 15

    assert second["position"]["quantity"] == 15.0
    assert second["position"]["avg_cost"] == pytest.approx(expected_avg)
    # Exactly one row for the ticker, not two.
    portfolio = client.get("/api/portfolio").json()
    matching = [p for p in portfolio["positions"] if p["ticker"] == "AAPL"]
    assert len(matching) == 1
    assert matching[0]["quantity"] == 15.0


def test_fractional_buy_debits_exactly_half(client):
    price = _live_price(client, "AAPL")
    response = client.post(
        "/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 0.5}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["quantity"] == 0.5
    assert body["cash_balance"] == pytest.approx(10000.0 - 0.5 * body["price"])
    assert price is not None  # sanity: cache had a price before the trade too


def test_get_portfolio_after_buy_reports_valued_position(client):
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 10})

    response = client.get("/api/portfolio")
    assert response.status_code == 200
    body = response.json()

    position = next(p for p in body["positions"] if p["ticker"] == "AAPL")
    assert position["quantity"] == 10.0
    assert position["current_price"] is not None
    assert position["unrealized_pnl"] is not None
    assert position["change_percent"] is not None

    priced_value = sum(
        p["quantity"] * p["current_price"]
        for p in body["positions"]
        if p["current_price"] is not None
    )
    cost_basis_value = sum(
        p["quantity"] * p["avg_cost"] for p in body["positions"] if p["current_price"] is None
    )
    expected_total = body["cash_balance"] + priced_value + cost_basis_value
    assert body["total_value"] == pytest.approx(expected_total)


def test_position_with_no_cached_price_reports_nulls_and_still_contributes_cost_basis(client):
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 10})
    client.app.state.price_cache.remove("AAPL")

    response = client.get("/api/portfolio")
    assert response.status_code == 200
    body = response.json()

    position = next(p for p in body["positions"] if p["ticker"] == "AAPL")
    assert position["current_price"] is None
    assert position["unrealized_pnl"] is None
    assert position["change_percent"] is None
    # total_value stays finite and includes the cost basis of the priceless position.
    assert body["total_value"] == pytest.approx(
        body["cash_balance"] + position["quantity"] * position["avg_cost"]
    )


def test_money_values_are_json_numbers_not_strings(client):
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 10})

    response = client.get("/api/portfolio")
    raw = json.loads(response.text)
    assert isinstance(raw["cash_balance"], float)
    assert isinstance(raw["total_value"], float)

    trade_response = client.post(
        "/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 1}
    )
    raw_trade = json.loads(trade_response.text)
    assert isinstance(raw_trade["cash_balance"], float)
    assert isinstance(raw_trade["price"], float)
    assert isinstance(raw_trade["quantity"], float)


# --- Task 2: sell, rejections, and the state-untouched proof ---------------


def _read_state(user_id: str = "default", ticker: str = "AAPL") -> dict:
    """Read cash, the position row, and the trades count from a fresh
    connection — not from the HTTP response or any in-process value — so
    rejection tests actually prove the transaction rolled back rather than
    merely proving the handler returned an error message."""
    conn = connect()
    try:
        cash_row = conn.execute(
            "SELECT cash_balance FROM users_profile WHERE id = ?", (user_id,)
        ).fetchone()
        position_row = conn.execute(
            "SELECT quantity, avg_cost FROM positions WHERE user_id = ? AND ticker = ?",
            (user_id, ticker),
        ).fetchone()
        trade_count = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        return {
            "cash_balance": cash_row["cash_balance"] if cash_row else None,
            "position": dict(position_row) if position_row else None,
            "trade_count": trade_count,
        }
    finally:
        conn.close()


def test_partial_sell_reduces_quantity_and_leaves_avg_cost_unchanged(client):
    buy = client.post(
        "/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 10}
    ).json()
    avg_cost = buy["position"]["avg_cost"]

    response = client.post(
        "/api/portfolio/trade", json={"ticker": "AAPL", "side": "sell", "quantity": 4}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["position"]["quantity"] == 6.0
    assert body["position"]["avg_cost"] == pytest.approx(avg_cost)


def test_full_sell_removes_position_row_and_returns_null_position(client):
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 10})

    response = client.post(
        "/api/portfolio/trade", json={"ticker": "AAPL", "side": "sell", "quantity": 10}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["position"] is None

    portfolio = client.get("/api/portfolio").json()
    assert not any(p["ticker"] == "AAPL" for p in portfolio["positions"])

    state = _read_state()
    assert state["position"] is None


def test_fractional_sell_credits_exactly_the_proceeds(client):
    buy = client.post(
        "/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 10}
    ).json()
    cash_after_buy = buy["cash_balance"]

    response = client.post(
        "/api/portfolio/trade", json={"ticker": "AAPL", "side": "sell", "quantity": 0.5}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cash_balance"] == pytest.approx(cash_after_buy + 0.5 * body["price"])


def test_oversized_sell_returns_409_and_leaves_state_byte_identical(client):
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 10})
    before = _read_state()

    response = client.post(
        "/api/portfolio/trade", json={"ticker": "AAPL", "side": "sell", "quantity": 999}
    )
    assert response.status_code == 409

    after = _read_state()
    assert after == before


def test_sell_of_unheld_ticker_returns_409_and_writes_nothing(client):
    before = _read_state(ticker="GOOGL")

    response = client.post(
        "/api/portfolio/trade", json={"ticker": "GOOGL", "side": "sell", "quantity": 1}
    )
    assert response.status_code == 409

    after = _read_state(ticker="GOOGL")
    assert after == before


def test_buy_exceeding_cash_returns_409_and_appends_no_trade_row(client):
    before = _read_state()

    response = client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "side": "buy", "quantity": 1_000_000},
    )
    assert response.status_code == 409

    after = _read_state()
    assert after == before


def test_trade_with_no_cached_price_returns_400_and_writes_nothing(client):
    client.app.state.price_cache.remove("AAPL")
    before = _read_state()

    response = client.post(
        "/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 1}
    )
    assert response.status_code == 400

    after = _read_state()
    assert after == before


@pytest.mark.parametrize(
    "payload",
    [
        {"ticker": "AAPL", "side": "buy", "quantity": 0},
        {"ticker": "AAPL", "side": "buy", "quantity": -5},
        {"ticker": "AAPL", "side": "short", "quantity": 1},
    ],
)
def test_malformed_trade_body_returns_422_before_the_engine_runs(client, payload):
    response = client.post("/api/portfolio/trade", json=payload)
    assert response.status_code == 422


# --- Task 1 (tracer): post-trade snapshot recording + GET /history ---------


def _snapshot_count(user_id: str = "default") -> int:
    """Count `portfolio_snapshots` rows through a brand-new `connect()`, not
    through the HTTP response — the recorder started by Task 2's lifespan
    writes one snapshot at startup, so every assertion here must be a
    *delta* against a pre-request count, never an absolute count."""
    conn = connect()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM portfolio_snapshots WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
    finally:
        conn.close()


def test_successful_buy_increases_snapshot_count_by_exactly_one(client):
    before = _snapshot_count()

    response = client.post(
        "/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 1}
    )
    assert response.status_code == 200

    after = _snapshot_count()
    assert after == before + 1


def test_rejected_trade_adds_no_snapshot_row(client):
    before = _snapshot_count()

    response = client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "side": "buy", "quantity": 1_000_000},
    )
    assert response.status_code == 409

    after = _snapshot_count()
    assert after == before


def test_history_returns_a_list_shape_with_200(client):
    # Not literally `{"snapshots": []}`: the `client` fixture's lifespan runs
    # SnapshotRecorder.start(), which records one snapshot synchronously
    # before this fixture ever yields, so "fresh database" already has one
    # row by the time any test body runs. This test proves the response
    # shape (200, a `snapshots` list); the empty-list case is a frontend
    # concern (PnLChart's empty state), not reachable through this fixture.
    response = client.get("/api/portfolio/history")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["snapshots"], list)


def test_history_after_two_trades_returns_both_oldest_first(client):
    before = _snapshot_count()

    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 1})
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 1})

    response = client.get("/api/portfolio/history")
    assert response.status_code == 200
    snapshots = response.json()["snapshots"]

    assert len(snapshots) >= before + 2
    recorded_ats = [s["recorded_at"] for s in snapshots]
    assert recorded_ats == sorted(recorded_ats)


def test_history_total_value_is_a_json_number_not_a_string(client):
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 1})

    response = client.get("/api/portfolio/history")
    raw = json.loads(response.text)
    assert len(raw["snapshots"]) >= 1
    assert isinstance(raw["snapshots"][0]["total_value"], float)
