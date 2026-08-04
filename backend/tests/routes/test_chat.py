"""End-to-end HTTP tests for the chat router (Task 1, tracer).

Proves the entire new backend path in one pass: free text in, through the
mock LLM dispatcher, through `execute_trade()` (the exact function the
trade bar calls), through `record_portfolio_snapshot()`, and back out as a
`{message, actions}` confirmation — never a 5xx, regardless of what the
model (mocked here) proposed.

`monkeypatch.setenv("LLM_MOCK", "true")` is set inside each test function,
not a fixture, because a later test in this plan needs to flip it per-test
against the same shared `client` fixture (Pitfall 4 / D-01's per-request
resolution).

Fill prices are always read from the response body or
`client.app.state.price_cache`, never hardcoded — the simulator ticks
prices on its own schedule independent of the test. Snapshot-count
assertions are always a delta against a count captured immediately before
the request, read through a fresh `connect()`, since the 30-second recorder
is running during every `client` fixture test.
"""

from __future__ import annotations

import pytest

from app.db.connection import connect


def _live_price(client, ticker: str) -> float:
    price = client.app.state.price_cache.get_price(ticker)
    assert price is not None, f"expected a live price for {ticker}"
    return price


def _read_state(user_id: str = "default", ticker: str = "AAPL") -> dict:
    """Read cash, the position row, and the trades count from a fresh
    connection — mirrors tests/routes/test_portfolio.py's discipline so a
    rejection test proves the transaction actually left no trace."""
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


def _snapshot_count(user_id: str = "default") -> int:
    """Count `portfolio_snapshots` rows through a brand-new `connect()` —
    the 30s recorder started by the client fixture's lifespan writes one
    snapshot at startup, so every assertion here must be a delta."""
    conn = connect()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM portfolio_snapshots WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
    finally:
        conn.close()


# --- Successful single-action buy -------------------------------------------


def test_mock_triggered_buy_returns_200_with_one_success_action(client, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")

    response = client.post("/api/chat", json={"message": "buy 10 AAPL"})
    assert response.status_code == 200
    body = response.json()

    assert isinstance(body["message"], str) and body["message"]
    assert len(body["actions"]) == 1
    action = body["actions"][0]
    assert action["kind"] == "trade"
    assert action["status"] == "success"
    assert action["ticker"] == "AAPL"
    assert action["side"] == "buy"
    assert action["quantity"] == 10.0
    assert action["price"] is not None


def test_mock_triggered_buy_debits_cash_exactly_like_a_manual_trade(client, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    before = _read_state()

    response = client.post("/api/chat", json={"message": "buy 10 AAPL"})
    assert response.status_code == 200
    action = response.json()["actions"][0]

    after = _read_state()
    assert after["cash_balance"] == pytest.approx(
        before["cash_balance"] - action["quantity"] * action["price"]
    )
    assert after["position"]["quantity"] == 10.0
    assert after["position"]["avg_cost"] == pytest.approx(action["price"])


def test_manual_trade_of_same_size_produces_the_same_arithmetic(client):
    """The claim under test: an AI-initiated trade and a manual trade of the
    same size move cash and positions by the identical amount. Measured on
    both sides rather than assumed — no hardcoded expectation either way."""
    before = _read_state()

    response = client.post(
        "/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 10}
    )
    assert response.status_code == 200
    body = response.json()

    after = _read_state()
    assert after["cash_balance"] == pytest.approx(before["cash_balance"] - 10 * body["price"])
    assert after["position"]["quantity"] == 10.0
    assert after["position"]["avg_cost"] == pytest.approx(body["price"])


def test_mock_triggered_buy_increases_snapshot_count_by_exactly_one(client, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    before = _snapshot_count()

    response = client.post("/api/chat", json={"message": "buy 10 AAPL"})
    assert response.status_code == 200

    after = _snapshot_count()
    assert after == before + 1


# --- Rejected trade (insufficient cash) -------------------------------------


def test_mock_triggered_buy_far_beyond_cash_returns_200_with_error_action(client, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    before = _read_state()

    response = client.post("/api/chat", json={"message": "buy 100000 AAPL"})
    assert response.status_code == 200
    body = response.json()

    assert len(body["actions"]) == 1
    action = body["actions"][0]
    assert action["status"] == "error"
    assert "cash" in action["error"].lower()

    after = _read_state()
    assert after == before


# --- Partial success: one valid action, one referring to an unheld ticker --


def test_mock_triggered_buy_and_sell_returns_one_success_and_one_error(client, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")

    response = client.post(
        "/api/chat", json={"message": "buy 5 AAPL and sell 3 GOOGL"}
    )
    assert response.status_code == 200
    body = response.json()

    assert len(body["actions"]) == 2
    statuses = {action["ticker"]: action["status"] for action in body["actions"]}
    assert statuses["AAPL"] == "success"
    assert statuses["GOOGL"] == "error"


# --- Invalid ticker shape ----------------------------------------------------


def test_mock_triggered_trade_on_shape_invalid_ticker_returns_200_with_error(client, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    before_trade_count = _read_state()["trade_count"]

    # The mock's ticker capture group accepts a leading period
    # ([a-z.]{1,10}); TICKER_PATTERN requires a leading letter, so this is
    # exactly the "mock accepts it, normalize_ticker rejects it" case.
    response = client.post("/api/chat", json={"message": "buy 1 .AB"})
    assert response.status_code == 200
    body = response.json()

    assert len(body["actions"]) == 1
    assert body["actions"][0]["status"] == "error"

    after_trade_count = _read_state()["trade_count"]
    assert after_trade_count == before_trade_count


# --- No action at all ---------------------------------------------------------


def test_mock_no_action_message_returns_200_with_empty_actions(client, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")

    response = client.post("/api/chat", json={"message": "how is my portfolio doing?"})
    assert response.status_code == 200
    body = response.json()

    assert isinstance(body["message"], str) and body["message"]
    assert body["actions"] == []


def test_same_message_sent_twice_produces_the_same_message_string(client, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")

    first = client.post("/api/chat", json={"message": "how is my portfolio doing?"})
    second = client.post("/api/chat", json={"message": "how is my portfolio doing?"})

    assert first.json()["message"] == second.json()["message"]


# --- Request body validation --------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"message": ""},
        {"message": "x" * 2001},
    ],
)
def test_malformed_chat_body_returns_422_before_the_handler_runs(client, payload):
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 422
