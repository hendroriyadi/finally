"""App assembly: health check, static serving, and lifespan wiring."""

from fastapi.testclient import TestClient

import db
from app import state
from app.main import create_app, resolve_static_dir
from tests.api.conftest import FakeMarketDataSource


class TestHealth:
    def test_reports_ok(self, client):
        response = client.get("/api/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["database"] == "ok"
        assert body["market_data"] == "stopped"

    def test_initializes_the_database(self, client, temp_db):
        assert not temp_db.exists()

        client.get("/api/health")

        assert temp_db.exists()
        assert db.get_profile().cash_balance == 10000.0

    def test_reports_the_running_market_source(self, client, market_source, prices):
        market_source.tickers = ["AAPL", "GOOGL"]

        body = client.get("/api/health").json()

        assert body["market_data"] == "FakeMarketDataSource"
        assert body["tracked_tickers"] == 2
        assert body["cached_prices"] == 2

    def test_returns_503_when_the_database_is_unreachable(self, client, monkeypatch):
        monkeypatch.setattr(db, "get_profile", _raise)

        response = client.get("/api/health")

        assert response.status_code == 503
        assert "Database unreachable" in response.json()["detail"]


class TestRouting:
    def test_every_planned_endpoint_is_mounted(self):
        paths = {route.path for route in create_app().routes}

        assert {
            "/api/health",
            "/api/portfolio",
            "/api/portfolio/trade",
            "/api/portfolio/history",
            "/api/watchlist",
            "/api/watchlist/{ticker}",
            "/api/stream/prices",
            "/api/chat",
        } <= paths

    def test_stream_route_is_registered_once(self):
        paths = [route.path for route in create_app().routes]

        assert paths.count("/api/stream/prices") == 1


class TestStaticFiles:
    def test_honors_the_static_dir_env_var(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FINALLY_STATIC_DIR", str(tmp_path))

        assert resolve_static_dir() == tmp_path

    def test_missing_static_dir_is_not_fatal(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FINALLY_STATIC_DIR", str(tmp_path / "nope"))

        assert resolve_static_dir() is None
        assert TestClient(create_app()).get("/api/health").status_code == 200

    def test_serves_the_frontend_export(self, tmp_path, monkeypatch):
        (tmp_path / "index.html").write_text("<h1>FinAlly</h1>")
        monkeypatch.setenv("FINALLY_STATIC_DIR", str(tmp_path))

        response = TestClient(create_app()).get("/")

        assert response.status_code == 200
        assert "FinAlly" in response.text

    def test_static_mount_does_not_shadow_the_api(self, tmp_path, monkeypatch):
        (tmp_path / "index.html").write_text("<h1>FinAlly</h1>")
        monkeypatch.setenv("FINALLY_STATIC_DIR", str(tmp_path))

        assert TestClient(create_app()).get("/api/health").status_code == 200


class TestLifespan:
    def test_starts_and_stops_the_market_source(self, monkeypatch, temp_db):
        source = FakeMarketDataSource()
        monkeypatch.setattr("app.main.create_market_data_source", lambda cache: source)

        with TestClient(create_app()) as client:
            assert state.get_market_source() is source
            assert source.get_tickers() == list(db.DEFAULT_TICKERS)
            assert client.get("/api/health").json()["tracked_tickers"] == 10
            # The lifespan seeds the P&L series so the chart is never empty.
            assert len(client.get("/api/portfolio/history").json()) == 1

        assert state.get_market_source() is None
        assert source.get_tickers() == []


def _raise(*args, **kwargs):
    raise RuntimeError("boom")
