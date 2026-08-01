"""POST /api/chat wiring."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import db
from app.llm import chat_router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(chat_router)
    return TestClient(app)


def test_chat_returns_message_and_action_lists(client, mock_mode, prices):
    response = client.post("/api/chat", json={"message": "How is my portfolio doing?"})

    assert response.status_code == 200
    body = response.json()
    assert body["message"]
    assert body["trades"] == []
    assert body["watchlist_changes"] == []


def test_chat_executes_a_trade_and_echoes_the_fill(client, mock_mode, prices):
    body = client.post("/api/chat", json={"message": "Buy 5 shares of AAPL"}).json()

    assert body["trades"][0] == {
        "kind": "trade",
        "ticker": "AAPL",
        "action": "buy",
        "quantity": 5.0,
        "price": 190.0,
        "success": True,
        "error": None,
    }
    assert db.get_position("AAPL").quantity == 5


def test_chat_executes_a_watchlist_change(client, mock_mode, prices):
    body = client.post("/api/chat", json={"message": "Add PYPL to my watchlist"}).json()

    assert body["watchlist_changes"][0]["success"] is True
    assert db.is_watching("PYPL")


def test_missing_message_is_a_422(client, mock_mode):
    assert client.post("/api/chat", json={}).status_code == 422
