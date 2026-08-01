"""HTTP contract for /api/watchlist."""

import db


class TestGetWatchlist:
    def test_returns_the_seeded_tickers(self, client):
        response = client.get("/api/watchlist")

        assert response.status_code == 200
        body = response.json()
        assert [item["ticker"] for item in body] == list(db.DEFAULT_TICKERS)

    def test_joins_live_prices(self, client, prices):
        body = client.get("/api/watchlist").json()

        by_ticker = {item["ticker"]: item for item in body}
        assert by_ticker["AAPL"]["price"] == 100.0
        assert by_ticker["NVDA"]["price"] is None
        assert set(by_ticker["AAPL"]) == {
            "ticker",
            "added_at",
            "price",
            "previous_price",
            "change",
            "change_percent",
            "direction",
            "timestamp",
        }


class TestPostWatchlist:
    def test_adds_a_ticker(self, client):
        response = client.post("/api/watchlist", json={"ticker": "PYPL"})

        assert response.status_code == 201
        assert response.json()["ticker"] == "PYPL"
        assert db.is_watching("PYPL")

    def test_normalizes_the_symbol(self, client):
        response = client.post("/api/watchlist", json={"ticker": " pypl "})

        assert response.json()["ticker"] == "PYPL"

    def test_duplicate_is_idempotent(self, client):
        response = client.post("/api/watchlist", json={"ticker": "AAPL"})

        assert response.status_code == 200
        assert len(db.list_watchlist_tickers()) == 10

    def test_registers_the_ticker_with_the_market_source(self, client, market_source):
        client.post("/api/watchlist", json={"ticker": "PYPL"})

        assert market_source.added == ["PYPL"]
        assert "PYPL" in market_source.get_tickers()

    def test_malformed_ticker_returns_400(self, client):
        response = client.post("/api/watchlist", json={"ticker": "1$"})

        assert response.status_code == 400
        assert "Invalid ticker" in response.json()["detail"]

    def test_empty_ticker_is_rejected_by_validation(self, client):
        assert client.post("/api/watchlist", json={"ticker": ""}).status_code == 422


class TestDeleteWatchlist:
    def test_removes_a_ticker(self, client):
        response = client.delete("/api/watchlist/AAPL")

        assert response.status_code == 200
        assert response.json() == {"ticker": "AAPL", "removed": True}
        assert not db.is_watching("AAPL")

    def test_is_case_insensitive(self, client):
        assert client.delete("/api/watchlist/aapl").status_code == 200

    def test_unwatched_ticker_returns_404(self, client):
        response = client.delete("/api/watchlist/PYPL")

        assert response.status_code == 404
        assert "not watched" in response.json()["detail"]

    def test_deregisters_the_ticker_from_the_market_source(self, client, market_source):
        client.delete("/api/watchlist/AAPL")

        assert market_source.removed == ["AAPL"]

    def test_malformed_ticker_returns_400(self, client):
        assert client.delete("/api/watchlist/1$").status_code == 400
