"""TEST-02 suite: structured-output parsing for `app.llm.client.chat_completion`.

Covers valid, defaulted, malformed, schema-violating, raising, and
empty-choices responses — the six failure/success modes `chat_completion()`
must handle without ever raising past its own boundary (D-08).

`completion` is monkeypatched on `app.llm.client` (the name the module
bound at import time), not on the `litellm` package, so these tests prove
the behaviour of the code under test rather than of the SDK.
"""

from __future__ import annotations

import json

import app.llm.client as client_module
from app.llm.schemas import ChatCompletionResult


class _Message:
    def __init__(self, content: str) -> None:
        self.content = content


class _Choice:
    def __init__(self, content: str) -> None:
        self.message = _Message(content)


class _Response:
    def __init__(self, content: str) -> None:
        self.choices = [_Choice(content)]


class _EmptyChoicesResponse:
    def __init__(self) -> None:
        self.choices = []


def test_valid_json_parses_into_chat_completion_result(monkeypatch):
    content = json.dumps(
        {
            "message": "Buying AAPL now.",
            "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 10}],
            "watchlist_changes": [{"ticker": "PYPL", "action": "add"}],
        }
    )
    monkeypatch.setattr(client_module, "completion", lambda **kwargs: _Response(content))

    result = client_module.chat_completion([{"role": "user", "content": "buy AAPL"}], ChatCompletionResult)

    assert isinstance(result, ChatCompletionResult)
    assert result.message == "Buying AAPL now."
    assert len(result.trades) == 1
    assert result.trades[0].ticker == "AAPL"
    assert len(result.watchlist_changes) == 1
    assert result.watchlist_changes[0].ticker == "PYPL"


def test_missing_optional_keys_default_to_empty_lists(monkeypatch):
    content = json.dumps({"message": "Nothing to do here."})
    monkeypatch.setattr(client_module, "completion", lambda **kwargs: _Response(content))

    result = client_module.chat_completion([{"role": "user", "content": "hi"}], ChatCompletionResult)

    assert isinstance(result, ChatCompletionResult)
    assert result.trades == []
    assert result.watchlist_changes == []


def test_non_json_content_returns_none(monkeypatch):
    monkeypatch.setattr(client_module, "completion", lambda **kwargs: _Response("not json at all"))

    result = client_module.chat_completion([{"role": "user", "content": "hi"}], ChatCompletionResult)

    assert result is None


def test_schema_violating_json_returns_none(monkeypatch):
    # message must be a string; Pydantic v2's lax mode does not coerce a
    # number into a string, so this is a clean schema-violation case.
    content = json.dumps({"message": 12345, "trades": [], "watchlist_changes": []})
    monkeypatch.setattr(client_module, "completion", lambda **kwargs: _Response(content))

    result = client_module.chat_completion([{"role": "user", "content": "hi"}], ChatCompletionResult)

    assert result is None


def test_sdk_call_raising_returns_none(monkeypatch):
    def _raise(**kwargs):
        raise RuntimeError("simulated network failure")

    monkeypatch.setattr(client_module, "completion", _raise)

    result = client_module.chat_completion([{"role": "user", "content": "hi"}], ChatCompletionResult)

    assert result is None


def test_empty_choices_list_returns_none_rather_than_raising(monkeypatch):
    monkeypatch.setattr(client_module, "completion", lambda **kwargs: _EmptyChoicesResponse())

    result = client_module.chat_completion([{"role": "user", "content": "hi"}], ChatCompletionResult)

    assert result is None


def test_outgoing_call_carries_model_format_effort_and_provider_ordering(monkeypatch):
    captured: dict = {}

    def _recorder(**kwargs):
        captured.update(kwargs)
        return _Response(json.dumps({"message": "ok"}))

    monkeypatch.setattr(client_module, "completion", _recorder)

    client_module.chat_completion([{"role": "user", "content": "hi"}], ChatCompletionResult)

    assert captured["model"] == client_module.MODEL
    assert captured["response_format"] is ChatCompletionResult
    assert captured["reasoning_effort"] == "low"
    assert captured["extra_body"] == client_module.EXTRA_BODY
    assert captured["extra_body"]["provider"]["order"] == ["cerebras"]
