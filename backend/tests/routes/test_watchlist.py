"""Tests for the watchlist REST router."""

from __future__ import annotations

from app.market.seed_prices import SEED_PRICES


def test_get_watchlist_returns_seeded_tickers(client):
    response = client.get("/api/watchlist")
    assert response.status_code == 200
    body = response.json()
    tickers = [item["ticker"] for item in body["tickers"]]
    assert tickers == list(SEED_PRICES.keys())
