# Testing Patterns

**Analysis Date:** 2026-08-01

## Test Framework

**Runner:**
- Framework: pytest 8.3.0+
- Async support: pytest-asyncio 0.24.0+
- Coverage: pytest-cov 5.0.0+
- Config: `backend/pyproject.toml` under `[tool.pytest.ini_options]`

**Pytest Configuration:**
```
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
```

**Run Commands:**
```bash
uv run --extra dev pytest -v              # Run all tests with verbose output
uv run --extra dev pytest --cov=app       # Run with coverage report
uv run --extra dev pytest tests/market/   # Run specific test directory
uv run --extra dev ruff check app/ tests/ # Lint before testing
```

## Test File Organization

**Location:**
- Backend unit tests co-located with source: `backend/tests/market/test_*.py` mirrors `backend/app/market/`
- Test directory structure mirrors source tree for easy navigation
- E2E tests in `test/` directory (Playwright-based, infrastructure in `test/artifacts/`)

**Naming:**
- Test files: `test_*.py` (e.g., `test_simulator.py`, `test_cache.py`)
- Test classes: `Test*` (e.g., `TestGBMSimulator`, `TestPriceCache`)
- Test methods: `test_*` (e.g., `test_step_returns_all_tickers()`)

**Structure:**
```
backend/
├── app/
│   └── market/
│       ├── simulator.py
│       ├── cache.py
│       └── ...
└── tests/
    ├── market/
    │   ├── test_simulator.py      # Tests for simulator.py
    │   ├── test_cache.py          # Tests for cache.py
    │   └── ...
    ├── api/                        # (Empty, ready for implementation)
    ├── db/                         # (Empty, ready for implementation)
    ├── llm/                        # (Empty, ready for implementation)
    └── conftest.py                 # Shared pytest fixtures
```

## Test Structure

**Suite Organization:**
```python
@pytest.mark.asyncio
class TestSimulatorDataSource:
    """Integration tests for the SimulatorDataSource."""

    async def test_start_populates_cache(self):
        """Test that start() immediately populates the cache."""
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=0.1)
        await source.start(["AAPL", "GOOGL"])

        assert cache.get("AAPL") is not None
        assert cache.get("GOOGL") is not None

        await source.stop()
```

**Patterns:**
- Class-based organization with `@pytest.mark.asyncio` at class level for async tests
- Each test method is independent with its own setup
- Minimal setup — no setUp/tearDown methods, just inline instantiation
- Teardown via explicit cleanup (e.g., `await source.stop()`)
- One assertion per test concept (multiple related asserts OK for single concept)

**Synchronous Test Pattern:**
```python
class TestGBMSimulator:
    """Unit tests for the GBM price simulator."""

    def test_step_returns_all_tickers(self):
        """Test that step() returns prices for all tickers."""
        sim = GBMSimulator(tickers=["AAPL", "GOOGL"])
        result = sim.step()
        assert set(result.keys()) == {"AAPL", "GOOGL"}
```

**Asynchronous Test Pattern:**
```python
@pytest.mark.asyncio
class TestSimulatorDataSource:
    async def test_prices_update_over_time(self):
        """Test that prices are updated periodically."""
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=0.05)
        await source.start(["AAPL"])

        initial_version = cache.version
        await asyncio.sleep(0.3)  # Several update cycles

        assert cache.version > initial_version
        await source.stop()
```

## Mocking

**Framework:** `unittest.mock` (standard library)

**Common Mock Patterns:**

**Environment Variable Mocking:**
```python
from unittest.mock import patch

def test_creates_simulator_when_no_api_key(self):
    cache = PriceCache()
    with patch.dict(os.environ, {}, clear=True):
        source = create_market_data_source(cache)
    assert isinstance(source, SimulatorDataSource)
```

**Method Mocking:**
```python
with patch.object(source, "_fetch_snapshots", return_value=mock_snapshots):
    await source._poll_once()
```

**Exception Mocking:**
```python
with patch.object(source, "_fetch_snapshots", side_effect=Exception("network error")):
    await source._poll_once()  # Should not raise
```

**MagicMock for Objects:**
```python
snap = MagicMock()
snap.ticker = "AAPL"
snap.last_trade = MagicMock()
snap.last_trade.price = 190.50
snap.last_trade.timestamp = 1707580800000
```

**What to Mock:**
- External API calls (Massive REST API via `_fetch_snapshots()`)
- Environment variables (via `patch.dict`)
- File I/O (not yet in codebase)
- Time-dependent operations (via `asyncio.sleep()` for timing, not time mocking)

**What NOT to Mock:**
- Core business logic (simulator, cache operations)
- Database operations (when implemented)
- Internal method calls in unit tests of that class

## Fixtures and Factories

**Test Data:**
No centralized fixtures yet. Tests create their own instances:
```python
def test_update_and_get(self):
    cache = PriceCache()
    update = cache.update("AAPL", 190.50)
    assert update.price == 190.50
```

**Custom Fixture Helper Functions:**
```python
def _make_snapshot(ticker: str, price: float, timestamp_ms: int) -> MagicMock:
    """Create a mock Massive snapshot object."""
    snap = MagicMock()
    snap.ticker = ticker
    snap.last_trade = MagicMock()
    snap.last_trade.price = price
    snap.last_trade.timestamp = timestamp_ms
    return snap
```
Location: `backend/tests/market/test_massive.py`

**Pytest Fixtures:**
`backend/tests/conftest.py` provides event loop configuration:
```python
@pytest.fixture
def event_loop_policy():
    """Use the default event loop policy for all async tests."""
    import asyncio
    return asyncio.DefaultEventLoopPolicy()
```

## Coverage

**Configuration:**
```
[tool.coverage.run]
source = ["app"]
omit = ["tests/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
]
```

**Target:** No enforced minimum (to be determined)

**View Coverage:**
```bash
uv run --extra dev pytest --cov=app --cov-report=html
# Opens htmlcov/index.html in browser
```

## Test Types

**Unit Tests:**
- Scope: Single class or function in isolation
- Examples: `TestGBMSimulator`, `TestPriceCache`, `TestFactory`
- Pattern: Create instance, call method, assert result
- Mocking: External dependencies mocked (APIs, environment)
- Location: `backend/tests/market/test_*.py`

**Integration Tests:**
- Scope: Multiple components interacting (e.g., source + cache)
- Examples: `TestSimulatorDataSource`, `TestMassiveDataSource`
- Pattern: Create data source, await start(), perform operations, await stop()
- Mocking: Minimal; use real cache and simulator, mock only external APIs (e.g., Massive)
- Location: `backend/tests/market/test_simulator_source.py`, `backend/tests/market/test_massive.py`

**E2E Tests:**
- Not yet implemented
- Will use Playwright in `test/` directory
- Infrastructure: `test/docker-compose.test.yml` (separate from production)
- Environment: `LLM_MOCK=true` by default for determinism

## Common Patterns

**Async Testing:**
```python
async def test_stop_is_clean(self):
    """Test that stop() is clean and idempotent."""
    cache = PriceCache()
    source = SimulatorDataSource(price_cache=cache, update_interval=0.1)
    await source.start(["AAPL"])
    await source.stop()
    await source.stop()  # Double stop should not raise
```

**Edge Case Testing:**
```python
def test_add_duplicate_is_noop(self):
    """Test that adding a duplicate ticker is a no-op."""
    sim = GBMSimulator(tickers=["AAPL"])
    sim.add_ticker("AAPL")
    assert len(sim._tickers) == 1

def test_remove_nonexistent_is_noop(self):
    """Test that removing a non-existent ticker is a no-op."""
    sim = GBMSimulator(tickers=["AAPL"])
    sim.remove_ticker("NOPE")  # Should not raise
```

**Error/Exception Testing:**
```python
async def test_malformed_snapshot_skipped(self):
    """Test that malformed snapshots are skipped gracefully."""
    cache = PriceCache()
    source = MassiveDataSource(api_key="test-key", price_cache=cache, poll_interval=60.0)
    source._tickers = ["AAPL", "BAD"]
    source._client = MagicMock()

    good_snap = _make_snapshot("AAPL", 190.50, 1707580800000)
    bad_snap = MagicMock()
    bad_snap.ticker = "BAD"
    bad_snap.last_trade = None  # Will cause AttributeError

    with patch.object(source, "_fetch_snapshots", return_value=[good_snap, bad_snap]):
        await source._poll_once()

    assert cache.get_price("AAPL") == 190.50
    assert cache.get_price("BAD") is None
```

**Timing/State Change Testing:**
```python
async def test_prices_update_over_time(self):
    """Test that prices are updated periodically."""
    cache = PriceCache()
    source = SimulatorDataSource(price_cache=cache, update_interval=0.05)
    await source.start(["AAPL"])

    initial_version = cache.version
    await asyncio.sleep(0.3)  # Several update cycles

    assert cache.version > initial_version
    await source.stop()
```

**Property/State Testing:**
```python
def test_version_increments(self):
    """Test that version counter increments."""
    cache = PriceCache()
    v0 = cache.version
    cache.update("AAPL", 190.00)
    assert cache.version == v0 + 1
    cache.update("AAPL", 191.00)
    assert cache.version == v0 + 2
```

## Test Descriptions

All tests include docstrings explaining the test's purpose:
```python
def test_prices_are_positive(self):
    """GBM prices can never go negative (exp() is always positive)."""
    sim = GBMSimulator(tickers=["AAPL"])
    for _ in range(10_000):
        prices = sim.step()
        assert prices["AAPL"] > 0
```

---

*Testing analysis: 2026-08-01*
