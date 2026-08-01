"""Structured output parsing: valid schemas in, safe fallback on anything else."""

import json

from app.llm.client import FALLBACK_MESSAGE, parse_response
from app.llm.schema import ActionResult, ChatResponse


def test_parses_full_response():
    raw = json.dumps(
        {
            "message": "Buying the dip.",
            "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 10}],
            "watchlist_changes": [{"ticker": "PYPL", "action": "add"}],
        }
    )

    parsed = parse_response(raw)

    assert parsed.message == "Buying the dip."
    assert parsed.trades[0].ticker == "AAPL"
    assert parsed.trades[0].side == "buy"
    assert parsed.trades[0].quantity == 10
    assert parsed.watchlist_changes[0].action == "add"


def test_message_only_response_has_empty_action_lists():
    parsed = parse_response(json.dumps({"message": "Your portfolio is all cash."}))

    assert parsed.trades == []
    assert parsed.watchlist_changes == []


def test_explicit_nulls_are_not_accepted_as_actions():
    parsed = parse_response(json.dumps({"message": "hi", "trades": [], "watchlist_changes": []}))

    assert parsed.trades == []


def test_fractional_quantities_survive():
    raw = json.dumps(
        {"message": "ok", "trades": [{"ticker": "NVDA", "side": "sell", "quantity": 0.5}]}
    )

    assert parse_response(raw).trades[0].quantity == 0.5


def test_malformed_json_falls_back():
    parsed = parse_response("this is not json at all")

    assert parsed.message == FALLBACK_MESSAGE
    assert parsed.trades == []


def test_wrong_shape_falls_back():
    parsed = parse_response(json.dumps({"reply": "wrong key name"}))

    assert parsed.message == FALLBACK_MESSAGE


def test_invalid_trade_side_falls_back():
    raw = json.dumps(
        {"message": "ok", "trades": [{"ticker": "AAPL", "side": "short", "quantity": 1}]}
    )

    parsed = parse_response(raw)

    assert parsed.message == FALLBACK_MESSAGE
    assert parsed.trades == []


def test_empty_body_falls_back():
    assert parse_response("").message == FALLBACK_MESSAGE
    assert parse_response(None).message == FALLBACK_MESSAGE


def test_actions_payload_is_none_when_nothing_ran():
    assert ChatResponse(message="hello").actions_payload() is None


def test_actions_payload_captures_failures():
    response = ChatResponse(
        message="hello",
        trades=[
            ActionResult(
                kind="trade",
                ticker="AAPL",
                action="buy",
                quantity=1000,
                success=False,
                error="Insufficient cash.",
            )
        ],
    )

    payload = response.actions_payload()

    assert payload["trades"][0]["success"] is False
    assert payload["trades"][0]["error"] == "Insufficient cash."
    assert payload["watchlist_changes"] == []


def test_describe_reads_as_a_sentence_fragment():
    ok = ActionResult(kind="trade", ticker="AAPL", action="buy", quantity=5, success=True)
    bad = ActionResult(
        kind="watchlist", ticker="PYPL", action="add", success=False, error="bad ticker"
    )

    assert ok.describe() == "buy 5 AAPL"
    assert bad.describe() == "could not add PYPL to the watchlist — bad ticker"
