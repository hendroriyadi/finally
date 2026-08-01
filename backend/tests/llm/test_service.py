"""The chat flow: auto-execution, failure surfacing, persistence."""

import json
from types import SimpleNamespace

import pytest

import db
from app.llm.client import FALLBACK_MESSAGE
from app.llm.service import handle_chat


def _llm_returning(payload: dict):
    """Fake litellm.completion that answers with `payload` as its JSON content."""

    def fake_completion(**kwargs):
        content = json.dumps(payload)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    return fake_completion


@pytest.fixture
def llm(monkeypatch):
    """Stub the LLM so tests drive the exact structured output they need."""

    def _install(payload: dict):
        monkeypatch.setattr("litellm.completion", _llm_returning(payload))

    return _install


async def test_informational_reply_persists_both_turns(prices, llm):
    llm({"message": "You are all cash right now."})

    response = await handle_chat("How am I doing?")

    assert response.message == "You are all cash right now."
    assert response.trades == []

    history = db.list_chat_messages()
    assert [m.role for m in history] == ["user", "assistant"]
    assert history[0].content == "How am I doing?"
    assert history[1].actions is None


async def test_successful_trade_moves_cash_and_creates_a_position(prices, llm):
    llm(
        {
            "message": "Buying 10 AAPL.",
            "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 10}],
        }
    )

    response = await handle_chat("Buy me some Apple")

    assert response.trades[0].success is True
    assert response.trades[0].price == 190.0
    assert "Note:" not in response.message

    position = db.get_position("AAPL")
    assert position.quantity == 10
    assert db.get_profile().cash_balance == pytest.approx(10000.0 - 1900.0)


async def test_rejected_trade_is_reported_not_raised(prices, llm):
    llm(
        {
            "message": "Buying 1000 AAPL.",
            "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 1000}],
        }
    )

    response = await handle_chat("Buy 1000 Apple")

    result = response.trades[0]
    assert result.success is False
    assert "Insufficient cash" in result.error
    assert "Note: could not buy 1000 AAPL" in response.message
    assert db.get_position("AAPL") is None
    assert db.get_profile().cash_balance == 10000.0


async def test_rejection_reason_is_persisted_for_the_next_turn(prices, llm):
    llm(
        {
            "message": "Selling 5 TSLA.",
            "trades": [{"ticker": "TSLA", "side": "sell", "quantity": 5}],
        }
    )

    await handle_chat("Sell my Tesla")

    assistant_turn = db.list_chat_messages()[-1]
    assert assistant_turn.actions["trades"][0]["success"] is False
    assert "Insufficient shares" in assistant_turn.actions["trades"][0]["error"]
    assert "Insufficient shares" in assistant_turn.content


async def test_trade_without_a_price_is_rejected_cleanly(prices, llm):
    llm(
        {
            "message": "Buying SNOW.",
            "trades": [{"ticker": "SNOW", "side": "buy", "quantity": 1}],
        }
    )

    response = await handle_chat("Buy Snowflake")

    assert response.trades[0].success is False
    assert "No live price" in response.trades[0].error


async def test_watchlist_add_is_applied(prices, llm):
    llm({"message": "Watching PYPL.", "watchlist_changes": [{"ticker": "pypl", "action": "add"}]})

    response = await handle_chat("Watch PayPal")

    assert response.watchlist_changes[0].success is True
    assert response.watchlist_changes[0].ticker == "PYPL"
    assert db.is_watching("PYPL")


async def test_watchlist_remove_is_applied(prices, llm):
    llm({"message": "Dropping NFLX.", "watchlist_changes": [{"ticker": "NFLX", "action": "remove"}]})

    await handle_chat("Stop watching Netflix")

    assert not db.is_watching("NFLX")


async def test_removing_an_unwatched_ticker_surfaces_a_note(prices, llm):
    llm({"message": "Dropping PYPL.", "watchlist_changes": [{"ticker": "PYPL", "action": "remove"}]})

    response = await handle_chat("Stop watching PayPal")

    assert response.watchlist_changes[0].success is False
    assert "not on the watchlist" in response.message


async def test_invalid_ticker_does_not_crash_the_request(prices, llm):
    llm({"message": "Adding it.", "watchlist_changes": [{"ticker": "!!!", "action": "add"}]})

    response = await handle_chat("Watch that thing")

    assert response.watchlist_changes[0].success is False
    assert "Note:" in response.message


async def test_watchlist_add_runs_before_the_trade(llm):
    """A brand-new ticker must be watched (and priced) before the buy is attempted."""
    from app.state import get_price_cache

    llm(
        {
            "message": "Adding and buying SNOW.",
            "trades": [{"ticker": "SNOW", "side": "buy", "quantity": 1}],
            "watchlist_changes": [{"ticker": "SNOW", "action": "add"}],
        }
    )

    # No market source runs in tests, so stand in for it: price the ticker the
    # moment it is watched, exactly as the simulator would.
    get_price_cache().update("SNOW", 150.0)

    response = await handle_chat("Add SNOW and buy one")

    assert response.watchlist_changes[0].success is True
    assert response.trades[0].success is True


async def test_malformed_llm_output_yields_the_fallback_reply(prices, monkeypatch):
    def broken_completion(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="<html>oops</html>"))]
        )

    monkeypatch.setattr("litellm.completion", broken_completion)

    response = await handle_chat("Buy everything")

    assert response.message == FALLBACK_MESSAGE
    assert response.trades == []
    assert db.list_chat_messages()[-1].actions is None


async def test_llm_transport_error_yields_the_fallback_reply(prices, monkeypatch):
    def exploding_completion(**kwargs):
        raise RuntimeError("openrouter is down")

    monkeypatch.setattr("litellm.completion", exploding_completion)

    response = await handle_chat("Hello?")

    assert response.message == FALLBACK_MESSAGE


async def test_missing_api_key_explains_itself(prices, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(
        "litellm.completion", lambda **kwargs: pytest.fail("must not call the API without a key")
    )

    response = await handle_chat("Hello?")

    assert "OPENROUTER_API_KEY" in response.message
    assert response.trades == []


async def test_history_is_replayed_to_the_model(prices, monkeypatch):
    captured = {}

    def capturing_completion(**kwargs):
        captured["messages"] = kwargs["messages"]
        return SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content=json.dumps({"message": "ok"})))
            ]
        )

    monkeypatch.setattr("litellm.completion", capturing_completion)
    db.insert_chat_message("user", "earlier question")
    db.insert_chat_message("assistant", "earlier answer")

    await handle_chat("follow up")

    contents = [m["content"] for m in captured["messages"]]
    assert contents[-3:] == ["earlier question", "earlier answer", "follow up"]
    assert "FinAlly" in contents[0]
    assert "=== PORTFOLIO ===" in contents[1]


async def test_mock_mode_needs_no_api_call(mock_mode, prices, monkeypatch):
    def forbidden(**kwargs):
        raise AssertionError("LLM_MOCK=true must not reach the API")

    monkeypatch.setattr("litellm.completion", forbidden)

    response = await handle_chat("Buy 5 shares of AAPL")

    assert response.trades[0].success is True
    assert db.get_position("AAPL").quantity == 5


async def test_mock_mode_is_deterministic(mock_mode, prices):
    first = await handle_chat("How is my portfolio doing?")
    second = await handle_chat("How is my portfolio doing?")

    assert first.model_dump() == second.model_dump()
