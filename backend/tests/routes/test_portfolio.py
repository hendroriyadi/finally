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
