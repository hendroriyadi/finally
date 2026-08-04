"""CHAT-07 suite: `app.llm.mock.mock_chat_completion`'s determinism, pure
keyword-triggered parsing, and the never-reaches-the-SDK proof for the
route's mock dispatch branch.
"""

from __future__ import annotations

import app.routes.chat as chat_module
from app.llm.mock import mock_chat_completion
from app.llm.schemas import ChatCompletionResult
from app.routes.chat import LLM_FAILURE_MESSAGE


def _messages(text: str) -> list[dict]:
    return [{"role": "user", "content": text}]


def test_identical_input_produces_equal_results():
    first = mock_chat_completion(_messages("buy 10 AAPL"))
    second = mock_chat_completion(_messages("buy 10 AAPL"))

    assert first == second


def test_recognized_buy_produces_one_trade_with_uppercased_ticker_and_quantity():
    result = mock_chat_completion(_messages("buy 3.5 shares of tsla"))

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.ticker == "TSLA"
    assert trade.side == "buy"
    assert trade.quantity == 3.5


def test_recognized_watchlist_phrase_produces_one_watchlist_change():
    result = mock_chat_completion(_messages("add pypl to my watchlist"))

    assert len(result.watchlist_changes) == 1
    change = result.watchlist_changes[0]
    assert change.ticker == "PYPL"
    assert change.action == "add"


def test_unrecognized_message_produces_empty_lists_and_a_nonempty_message():
    result = mock_chat_completion(_messages("what do you think of the market today?"))

    assert result.trades == []
    assert result.watchlist_changes == []
    assert isinstance(result.message, str) and result.message


def test_returned_object_is_a_chat_completion_result_instance():
    result = mock_chat_completion(_messages("buy 1 AAPL"))

    assert isinstance(result, ChatCompletionResult)


def test_mock_mode_never_reaches_a_sabotaged_real_client(client, monkeypatch):
    """Proves the dispatcher took the mock branch: a sabotaged real client
    that raises immediately if called is monkeypatched in, mock mode is on,
    and the request still succeeds — the only way this passes is if the
    real client was never invoked."""

    def _sabotaged(*args, **kwargs):
        raise AssertionError("the real client must not be reached in mock mode")

    monkeypatch.setattr(chat_module, "chat_completion", _sabotaged)
    monkeypatch.setenv("LLM_MOCK", "true")

    response = client.post("/api/chat", json={"message": "how is my portfolio doing?"})

    assert response.status_code == 200


def test_mock_mode_off_with_real_client_returning_none_yields_graceful_fallback(client, monkeypatch):
    """D-08's contract measured from the wire: with mock mode off and the
    real client returning None (exactly what this sandbox's empty API key
    produces in production), the route still returns 200 with the fixed
    fallback message and an empty action list — never a 500."""
    monkeypatch.setattr(chat_module, "chat_completion", lambda *args, **kwargs: None)
    monkeypatch.setenv("LLM_MOCK", "false")

    response = client.post("/api/chat", json={"message": "buy 10 AAPL"})

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == LLM_FAILURE_MESSAGE
    assert body["actions"] == []
