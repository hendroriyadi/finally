"""End-to-end HTTP tests for the chat router (Task 1, tracer).

Proves the entire new backend path in one pass: free text in, through the
mock LLM dispatcher, through `execute_trade()` (the exact function the
trade bar calls), through `record_portfolio_snapshot()`, and back out as a
`{message, actions}` confirmation — never a 5xx, regardless of what the
model (mocked here) proposed.

`monkeypatch.setenv("LLM_MOCK", "true")` is set inside each test function,
not a fixture, because a later test in this plan needs to flip it per-test
against the same shared `client` fixture (Pitfall 4 / D-01's per-request
resolution).

Fill prices are always read from the response body or
`client.app.state.price_cache`, never hardcoded — the simulator ticks
prices on its own schedule independent of the test. Snapshot-count
assertions are always a delta against a count captured immediately before
the request, read through a fresh `connect()`, since the 30-second recorder
is running during every `client` fixture test.
"""

from __future__ import annotations

import pytest

from app.db.connection import connect


def _live_price(client, ticker: str) -> float:
    price = client.app.state.price_cache.get_price(ticker)
    assert price is not None, f"expected a live price for {ticker}"
    return price


def _read_state(user_id: str = "default", ticker: str = "AAPL") -> dict:
    """Read cash, the position row, and the trades count from a fresh
    connection — mirrors tests/routes/test_portfolio.py's discipline so a
    rejection test proves the transaction actually left no trace."""
    conn = connect()
    try:
        cash_row = conn.execute(
            "SELECT cash_balance FROM users_profile WHERE id = ?", (user_id,)
        ).fetchone()
        position_row = conn.execute(
            "SELECT quantity, avg_cost FROM positions WHERE user_id = ? AND ticker = ?",
            (user_id, ticker),
        ).fetchone()
        trade_count = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        return {
            "cash_balance": cash_row["cash_balance"] if cash_row else None,
            "position": dict(position_row) if position_row else None,
            "trade_count": trade_count,
        }
    finally:
        conn.close()


def _snapshot_count(user_id: str = "default") -> int:
    """Count `portfolio_snapshots` rows through a brand-new `connect()` —
    the 30s recorder started by the client fixture's lifespan writes one
    snapshot at startup, so every assertion here must be a delta."""
    conn = connect()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM portfolio_snapshots WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
    finally:
        conn.close()


# --- Successful single-action buy -------------------------------------------


def test_mock_triggered_buy_returns_200_with_one_success_action(client, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")

    response = client.post("/api/chat", json={"message": "buy 10 AAPL"})
    assert response.status_code == 200
    body = response.json()

    assert isinstance(body["message"], str) and body["message"]
    assert len(body["actions"]) == 1
    action = body["actions"][0]
    assert action["kind"] == "trade"
    assert action["status"] == "success"
    assert action["ticker"] == "AAPL"
    assert action["side"] == "buy"
    assert action["quantity"] == 10.0
    assert action["price"] is not None


def test_mock_triggered_buy_debits_cash_exactly_like_a_manual_trade(client, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    before = _read_state()

    response = client.post("/api/chat", json={"message": "buy 10 AAPL"})
    assert response.status_code == 200
    action = response.json()["actions"][0]

    after = _read_state()
    assert after["cash_balance"] == pytest.approx(
        before["cash_balance"] - action["quantity"] * action["price"]
    )
    assert after["position"]["quantity"] == 10.0
    assert after["position"]["avg_cost"] == pytest.approx(action["price"])


def test_manual_trade_of_same_size_produces_the_same_arithmetic(client):
    """The claim under test: an AI-initiated trade and a manual trade of the
    same size move cash and positions by the identical amount. Measured on
    both sides rather than assumed — no hardcoded expectation either way."""
    before = _read_state()

    response = client.post(
        "/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 10}
    )
    assert response.status_code == 200
    body = response.json()

    after = _read_state()
    assert after["cash_balance"] == pytest.approx(before["cash_balance"] - 10 * body["price"])
    assert after["position"]["quantity"] == 10.0
    assert after["position"]["avg_cost"] == pytest.approx(body["price"])


def test_mock_triggered_buy_increases_snapshot_count_by_exactly_one(client, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    before = _snapshot_count()

    response = client.post("/api/chat", json={"message": "buy 10 AAPL"})
    assert response.status_code == 200

    after = _snapshot_count()
    assert after == before + 1


# --- Rejected trade (insufficient cash) -------------------------------------


def test_mock_triggered_buy_far_beyond_cash_returns_200_with_error_action(client, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    before = _read_state()

    response = client.post("/api/chat", json={"message": "buy 100000 AAPL"})
    assert response.status_code == 200
    body = response.json()

    assert len(body["actions"]) == 1
    action = body["actions"][0]
    assert action["status"] == "error"
    assert "cash" in action["error"].lower()

    after = _read_state()
    assert after == before


# --- Partial success: one valid action, one referring to an unheld ticker --


def test_mock_triggered_buy_and_sell_returns_one_success_and_one_error(client, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")

    response = client.post(
        "/api/chat", json={"message": "buy 5 AAPL and sell 3 GOOGL"}
    )
    assert response.status_code == 200
    body = response.json()

    assert len(body["actions"]) == 2
    statuses = {action["ticker"]: action["status"] for action in body["actions"]}
    assert statuses["AAPL"] == "success"
    assert statuses["GOOGL"] == "error"


# --- Invalid ticker shape ----------------------------------------------------


def test_mock_triggered_trade_on_shape_invalid_ticker_returns_200_with_error(client, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    before_trade_count = _read_state()["trade_count"]

    # The mock's ticker capture group accepts a leading period
    # ([a-z.]{1,10}); TICKER_PATTERN requires a leading letter, so this is
    # exactly the "mock accepts it, normalize_ticker rejects it" case.
    response = client.post("/api/chat", json={"message": "buy 1 .AB"})
    assert response.status_code == 200
    body = response.json()

    assert len(body["actions"]) == 1
    assert body["actions"][0]["status"] == "error"

    after_trade_count = _read_state()["trade_count"]
    assert after_trade_count == before_trade_count


# --- No action at all ---------------------------------------------------------


def test_mock_no_action_message_returns_200_with_empty_actions(client, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")

    response = client.post("/api/chat", json={"message": "how is my portfolio doing?"})
    assert response.status_code == 200
    body = response.json()

    assert isinstance(body["message"], str) and body["message"]
    assert body["actions"] == []


def test_same_message_sent_twice_produces_the_same_message_string(client, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")

    first = client.post("/api/chat", json={"message": "how is my portfolio doing?"})
    second = client.post("/api/chat", json={"message": "how is my portfolio doing?"})

    assert first.json()["message"] == second.json()["message"]


# --- Request body validation --------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"message": ""},
        {"message": "x" * 2001},
    ],
)
def test_malformed_chat_body_returns_422_before_the_handler_runs(client, payload):
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 422


# --- Persistence (Task 1 / CHAT-01) ------------------------------------------


def _chat_message_count(user_id: str = "default") -> int:
    conn = connect()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM chat_messages WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
    finally:
        conn.close()


def _chat_rows(user_id: str = "default") -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT role, content, actions, created_at FROM chat_messages "
            "WHERE user_id = ? ORDER BY created_at",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def test_a_completed_turn_leaves_exactly_two_new_rows(client, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    before = _chat_message_count()

    response = client.post("/api/chat", json={"message": "buy 10 AAPL"})
    assert response.status_code == 200

    after = _chat_message_count()
    assert after == before + 2


def test_assistant_row_stored_actions_equal_response_body_actions(client, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")

    response = client.post("/api/chat", json={"message": "buy 10 AAPL"})
    body = response.json()

    rows = _chat_rows()
    assistant_row = rows[-1]
    assert assistant_row["role"] == "assistant"

    import json as _json

    from app.routes.chat import ActionResult

    stored_actions = _json.loads(assistant_row["actions"])
    # The route stores actions via model_dump(exclude_none=True), so
    # round-trip the response body's actions through the same model + dump
    # to compare like with like, entry for entry.
    expected = [ActionResult(**a).model_dump(exclude_none=True) for a in body["actions"]]
    assert stored_actions == expected


def test_a_failed_model_call_still_leaves_both_rows_with_fallback_and_empty_actions(
    client, monkeypatch
):
    monkeypatch.setenv("LLM_MOCK", "false")

    async def _failing(*args, **kwargs):
        return None

    import app.routes.chat as chat_module

    monkeypatch.setattr(chat_module, "_get_llm_response", _failing)

    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 200
    body = response.json()
    assert body["message"] == chat_module.LLM_FAILURE_MESSAGE
    assert body["actions"] == []

    rows = _chat_rows()
    assert rows[-2]["role"] == "user"
    assert rows[-2]["content"] == "hello"
    assert rows[-1]["role"] == "assistant"
    assert rows[-1]["content"] == chat_module.LLM_FAILURE_MESSAGE
    import json as _json

    assert _json.loads(rows[-1]["actions"]) == []


# --- GET /api/chat/history (Task 1 / CHAT-01, D-12) --------------------------


def test_history_on_fresh_database_returns_200_with_empty_list(client):
    response = client.get("/api/chat/history")
    assert response.status_code == 200
    assert response.json() == {"messages": []}


def test_history_after_a_turn_returns_both_rows_oldest_first_with_actions_as_json_array(
    client, monkeypatch
):
    monkeypatch.setenv("LLM_MOCK", "true")

    post_response = client.post("/api/chat", json={"message": "buy 10 AAPL"})
    assert post_response.status_code == 200

    response = client.get("/api/chat/history")
    assert response.status_code == 200
    body = response.json()

    assert len(body["messages"]) == 2
    assert body["messages"][0]["role"] == "user"
    assert body["messages"][0]["content"] == "buy 10 AAPL"
    assert body["messages"][0]["actions"] is None
    assert body["messages"][1]["role"] == "assistant"
    # Actions arrive as a JSON array the test can index, not a quoted string.
    assert isinstance(body["messages"][1]["actions"], list)
    assert body["messages"][1]["actions"] == post_response.json()["actions"]


# --- build_chat_messages() — pure function (Task 2 / CHAT-02) ---------------


def _fabricated_portfolio(cash: float = 8000.0) -> dict:
    return {
        "cash_balance": cash,
        "total_value": cash + 1500.0,
        "positions": [
            {
                "ticker": "AAPL",
                "quantity": 10.0,
                "avg_cost": 150.0,
                "current_price": 150.0,
                "unrealized_pnl": 0.0,
                "change_percent": 0.0,
            }
        ],
    }


def _fabricated_watchlist() -> list[dict]:
    return [{"ticker": "GOOGL", "price": 175.25}]


def test_build_chat_messages_includes_cash_holding_and_watchlist_price():
    from app.routes.chat import build_chat_messages

    messages = build_chat_messages(
        portfolio=_fabricated_portfolio(cash=8000.0),
        watchlist=_fabricated_watchlist(),
        history=[],
        user_message="how am I doing?",
    )

    rendered = "\n".join(m["content"] for m in messages)
    assert "8000" in rendered
    assert "AAPL" in rendered
    assert "GOOGL" in rendered
    assert "175.25" in rendered


def test_build_chat_messages_persona_is_byte_identical_across_different_portfolios():
    from app.routes.chat import build_chat_messages

    first = build_chat_messages(
        portfolio=_fabricated_portfolio(cash=8000.0),
        watchlist=[],
        history=[],
        user_message="hello",
    )
    second = build_chat_messages(
        portfolio=_fabricated_portfolio(cash=1234.0),
        watchlist=[],
        history=[],
        user_message="hello",
    )

    assert first[0]["role"] == "system"
    assert first[0]["content"] == second[0]["content"]
    # The context message (second system message) is the volatile one.
    assert first[1]["content"] != second[1]["content"]


def test_build_chat_messages_holding_with_no_price_renders_unavailable_not_zero():
    from app.routes.chat import build_chat_messages

    portfolio = _fabricated_portfolio()
    portfolio["positions"][0]["current_price"] = None
    portfolio["positions"][0]["unrealized_pnl"] = None
    portfolio["positions"][0]["change_percent"] = None

    messages = build_chat_messages(
        portfolio=portfolio, watchlist=[], history=[], user_message="hi"
    )

    context_content = messages[1]["content"]
    assert "unavailable" in context_content.lower()
    # A bare zero must never stand in for the missing price.
    assert "$0.00" not in context_content
    assert "$0" not in context_content


def test_build_chat_messages_orders_history_between_context_and_new_message():
    from app.routes.chat import build_chat_messages

    history = [
        {"role": "user", "content": "earlier question", "actions": None, "created_at": "t1"},
        {"role": "assistant", "content": "earlier answer", "actions": [], "created_at": "t2"},
    ]

    messages = build_chat_messages(
        portfolio=_fabricated_portfolio(),
        watchlist=[],
        history=history,
        user_message="follow-up question",
    )

    # persona, context, then history in order, then exactly one new message.
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "system"
    assert messages[2] == {"role": "user", "content": "earlier question"}
    assert messages[3] == {"role": "assistant", "content": "earlier answer"}
    assert messages[4] == {"role": "user", "content": "follow-up question"}
    assert len(messages) == 5
    # The new message appears exactly once in the whole list.
    assert sum(1 for m in messages if m["content"] == "follow-up question") == 1


def test_build_chat_messages_bounds_history_by_shared_constant():
    from app.db.chat import MAX_CONTEXT_MESSAGES
    from app.routes.chat import build_chat_messages

    # build_chat_messages itself does not truncate (the caller already
    # bounded `history` via list_recent_chat_messages()); this asserts the
    # constant it relies on for that bound is the shared one, not a second
    # magic number.
    assert MAX_CONTEXT_MESSAGES == 20


def test_build_chat_messages_on_empty_state_still_includes_cash_balance():
    from app.routes.chat import build_chat_messages

    empty_portfolio = {"cash_balance": 10000.0, "total_value": 10000.0, "positions": []}

    messages = build_chat_messages(
        portfolio=empty_portfolio, watchlist=[], history=[], user_message="hi"
    )

    assert "10000" in messages[1]["content"]


# --- Freshness proof — context re-read every turn (Task 2 / CHAT-02, D-15) --


class _RecordingLLM:
    """Stand-in for mock_chat_completion that records the message list it
    was handed and returns a schema-valid no-action result — recording the
    *input* to the model is what makes this a test of the context, not of
    the mock (per 04-02-PLAN.md's discretion table)."""

    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    def __call__(self, messages: list[dict]):
        from app.llm.schemas import ChatCompletionResult

        self.calls.append(messages)
        return ChatCompletionResult(message="ok", trades=[], watchlist_changes=[])


def test_a_trade_between_two_turns_is_visible_in_the_second_recorded_context(
    client, monkeypatch
):
    monkeypatch.setenv("LLM_MOCK", "true")
    import app.routes.chat as chat_module

    recorder = _RecordingLLM()
    monkeypatch.setattr(chat_module, "mock_chat_completion", recorder)

    client.post("/api/chat", json={"message": "how am I doing?"})
    assert len(recorder.calls) == 1
    first_rendered = "\n".join(m["content"] for m in recorder.calls[0])

    trade_response = client.post(
        "/api/portfolio/trade", json={"ticker": "NFLX", "side": "buy", "quantity": 2}
    )
    assert trade_response.status_code == 200

    client.post("/api/chat", json={"message": "how am I doing now?"})
    assert len(recorder.calls) == 2
    second_rendered = "\n".join(m["content"] for m in recorder.calls[1])

    assert "NFLX" not in first_rendered
    assert "NFLX" in second_rendered

    # The cash figure must have moved between the two recorded contexts.
    first_cash_line = next(
        line for line in first_rendered.splitlines() if "cash" in line.lower()
    )
    second_cash_line = next(
        line for line in second_rendered.splitlines() if "cash" in line.lower()
    )
    assert first_cash_line != second_cash_line


def test_a_watchlist_ticker_added_between_two_turns_is_visible_in_the_second_context(
    client, monkeypatch
):
    monkeypatch.setenv("LLM_MOCK", "true")
    import app.routes.chat as chat_module

    recorder = _RecordingLLM()
    monkeypatch.setattr(chat_module, "mock_chat_completion", recorder)

    client.post("/api/chat", json={"message": "what's on my watchlist?"})
    first_rendered = "\n".join(m["content"] for m in recorder.calls[0])

    add_response = client.post("/api/watchlist", json={"ticker": "PYPL"})
    assert add_response.status_code == 201

    client.post("/api/chat", json={"message": "what's on my watchlist now?"})
    second_rendered = "\n".join(m["content"] for m in recorder.calls[1])

    assert "PYPL" not in first_rendered
    assert "PYPL" in second_rendered


def test_fresh_database_chat_request_still_records_starting_cash_balance(client, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    import app.routes.chat as chat_module

    recorder = _RecordingLLM()
    monkeypatch.setattr(chat_module, "mock_chat_completion", recorder)

    response = client.post("/api/chat", json={"message": "hi"})
    assert response.status_code == 200

    rendered = "\n".join(m["content"] for m in recorder.calls[0])
    assert "10000" in rendered


def test_history_never_includes_the_message_currently_being_answered(client, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    import app.routes.chat as chat_module

    recorder = _RecordingLLM()
    monkeypatch.setattr(chat_module, "mock_chat_completion", recorder)

    client.post("/api/chat", json={"message": "first turn"})
    client.post("/api/chat", json={"message": "second turn"})

    second_call_messages = recorder.calls[1]
    occurrences = sum(1 for m in second_call_messages if m["content"] == "second turn")
    assert occurrences == 1

    # And the first turn's user text is present exactly once as history.
    occurrences_first = sum(1 for m in second_call_messages if m["content"] == "first turn")
    assert occurrences_first == 1


def test_no_context_is_cached_on_application_state():
    import inspect
    import re

    import app.routes.chat as chat_module

    source = inspect.getsource(chat_module)
    pattern = re.compile(r"app\.state\.(chat|context|prompt)")
    assert not pattern.search(source)
