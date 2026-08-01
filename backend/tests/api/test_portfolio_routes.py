"""HTTP contract for /api/portfolio."""

import db


class TestGetPortfolio:
    def test_fresh_portfolio(self, client):
        response = client.get("/api/portfolio")

        assert response.status_code == 200
        body = response.json()
        assert body["cash_balance"] == 10000.0
        assert body["positions"] == []
        assert body["total_value"] == 10000.0

    def test_position_shape(self, client, prices):
        db.upsert_position("AAPL", 10, 90.0)

        position = client.get("/api/portfolio").json()["positions"][0]

        assert set(position) == {
            "ticker",
            "quantity",
            "avg_cost",
            "current_price",
            "cost_basis",
            "market_value",
            "unrealized_pnl",
            "unrealized_pnl_percent",
            "weight",
        }
        assert position["unrealized_pnl"] == 100.0


class TestPostTrade:
    def test_buy(self, client, prices):
        response = client.post(
            "/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 10, "side": "buy"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["price"] == 100.0
        assert body["cash_balance"] == 9000.0
        assert body["trade_id"]

    def test_sell(self, client, prices):
        client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 10, "side": "buy"})

        response = client.post(
            "/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 4, "side": "sell"}
        )

        assert response.status_code == 200
        assert response.json()["position_quantity"] == 6

    def test_insufficient_cash_returns_400_with_reason(self, client, prices):
        response = client.post(
            "/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1000, "side": "buy"}
        )

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["error_code"] == "insufficient_cash"
        assert "Insufficient cash" in detail["reason"]

    def test_insufficient_shares_returns_400(self, client, prices):
        response = client.post(
            "/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "sell"}
        )

        assert response.status_code == 400
        assert response.json()["detail"]["error_code"] == "insufficient_shares"

    def test_untracked_ticker_returns_400(self, client):
        response = client.post(
            "/api/portfolio/trade", json={"ticker": "ZZZZ", "quantity": 1, "side": "buy"}
        )

        assert response.status_code == 400
        assert response.json()["detail"]["error_code"] == "no_price"

    def test_bad_side_is_rejected_by_validation(self, client, prices):
        response = client.post(
            "/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "short"}
        )

        assert response.status_code == 422

    def test_non_positive_quantity_is_rejected_by_validation(self, client, prices):
        response = client.post(
            "/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 0, "side": "buy"}
        )

        assert response.status_code == 422


class TestGetHistory:
    def test_empty_history(self, client):
        response = client.get("/api/portfolio/history")

        assert response.status_code == 200
        assert response.json() == []

    def test_history_is_chronological(self, client, prices):
        db.insert_snapshot(10000.0, recorded_at="2026-01-01T00:00:00+00:00")
        db.insert_snapshot(10500.0, recorded_at="2026-01-02T00:00:00+00:00")

        body = client.get("/api/portfolio/history").json()

        assert [point["total_value"] for point in body] == [10000.0, 10500.0]
        assert set(body[0]) == {"total_value", "recorded_at"}

    def test_trade_appends_a_snapshot(self, client, prices):
        client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "buy"})

        assert len(client.get("/api/portfolio/history").json()) == 1

    def test_limit_keeps_the_most_recent_points(self, client):
        for day in range(1, 4):
            db.insert_snapshot(float(day), recorded_at=f"2026-01-0{day}T00:00:00+00:00")

        body = client.get("/api/portfolio/history", params={"limit": 2}).json()

        assert [point["total_value"] for point in body] == [2.0, 3.0]
