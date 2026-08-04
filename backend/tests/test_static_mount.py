"""DEPLOY-01 at unit level: the catch-all static mount must not shadow /api/*.

This is the fast half of DEPLOY-01's proof. The slow half builds an image and
curls a real container; this file proves the same claim in milliseconds, so a
mount-ordering regression fails in the test suite rather than in a multi-minute
Docker build (or, worse, in production).

`STATIC_DIR` is monkeypatched as a MODULE attribute rather than as a local:
`create_app()` reads the module global at call time, so the patch has to land
before the factory runs.

No test here requests /api/stream/prices. That endpoint is an infinite SSE
stream and a TestClient request against it never returns — its presence is
asserted against the route table instead.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import create_app

INDEX_MARKER = "finally-index-marker-8fc21e"
NOT_FOUND_MARKER = "finally-404-marker-3ab77d"


@pytest.fixture
def static_dir(tmp_path, monkeypatch):
    """Build a throwaway export directory and point STATIC_DIR at it."""
    directory = tmp_path / "static"
    directory.mkdir()
    (directory / "index.html").write_text(f"<html><body>{INDEX_MARKER}</body></html>")
    (directory / "404.html").write_text(f"<html><body>{NOT_FOUND_MARKER}</body></html>")
    monkeypatch.setattr(main_module, "STATIC_DIR", directory)
    return directory


@pytest.fixture
def static_client(static_dir, temp_db):
    """A TestClient over an app built WITH a static directory present."""
    with TestClient(create_app()) as client:
        yield client


def test_inline_api_route_is_not_shadowed_by_the_static_mount(static_client):
    # The single most important assertion in this file: if the mount were
    # registered before the routers, this would return the SPA's HTML.
    response = static_client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "text/html" not in response.headers.get("content-type", "")


def test_router_supplied_api_route_is_not_shadowed(static_client):
    # /api/health is declared inline on the app; this proves a route that
    # arrived via include_router survives too.
    response = static_client.get("/api/watchlist")

    assert response.status_code == 200
    assert isinstance(response.json()["tickers"], list)


def test_static_index_is_served_at_root(static_client):
    response = static_client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert INDEX_MARKER in response.text


def test_unknown_non_api_path_serves_the_404_page(static_client):
    # Proves html=True is actually engaged rather than the mount behaving as
    # a plain directory server (which would return a bare Starlette 404).
    response = static_client.get("/some/route/that/does/not/exist")

    assert response.status_code == 404
    assert NOT_FOUND_MARKER in response.text


def test_static_mount_is_the_last_route_registered(static_dir, temp_db):
    # The ordering claim, asserted structurally rather than by request — a
    # future edit that appends a route after the mount fails here with an
    # obvious message instead of as a mysterious 404 at runtime.
    app = create_app()

    assert getattr(app.routes[-1], "name", None) == "static"


def test_sse_route_is_present_in_the_route_table(static_dir, temp_db):
    # Asserted against the route table, never by issuing the request: that
    # endpoint is an infinite stream.
    app = create_app()
    paths = {getattr(route, "path", None) for route in app.routes}

    assert "/api/stream/prices" in paths


def test_app_starts_without_a_static_directory(tmp_path, monkeypatch, temp_db):
    """The dev path (D-04): a checkout with no built frontend must still run.

    StaticFiles' check_dir default would raise at construction time here, so
    this is the test that proves the guard exists.
    """
    monkeypatch.setattr(main_module, "STATIC_DIR", tmp_path / "definitely-absent")

    with TestClient(create_app()) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        assert client.get("/").status_code == 404
