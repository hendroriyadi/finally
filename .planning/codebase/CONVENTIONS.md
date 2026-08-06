# Coding Conventions

**Analysis Date:** 2026-08-01

## Naming Patterns

**Files:**
- Python modules use `snake_case.py` (e.g., `market_data_demo.py`, `price_cache.py`)
- Test files follow `test_*.py` pattern (e.g., `test_simulator.py`, `test_cache.py`)
- Directories use `snake_case` (e.g., `market/`, `routes/`)

**Functions:**
- Standard functions and methods use `snake_case` (e.g., `update()`, `get_price()`, `create_market_data_source()`)
- Private/internal methods/functions prefixed with single underscore (e.g., `_generate_events()`, `_poll_once()`)
- Async functions follow same naming convention (e.g., `async def start()`, `async def stop()`)

**Variables:**
- Instance variables use `snake_case` with leading underscore for private (e.g., `self._prices`, `self._tickers`)
- Public attributes use `snake_case` without underscore (e.g., `ticker`, `price`)
- Module-level constants use `UPPER_SNAKE_CASE` (e.g., `CORRELATION_GROUPS`, `DEFAULT_DT`, `TRADING_SECONDS_PER_YEAR`)

**Types:**
- Classes use `PascalCase` (e.g., `PriceUpdate`, `PriceCache`, `MarketDataSource`)
- Abstract base classes use `PascalCase` with naming indicating interface (e.g., `MarketDataSource`)
- Dataclass names use `PascalCase` (e.g., `PriceUpdate`)

## Code Style

**Formatting:**
- Line length: 100 characters (configured in `backend/pyproject.toml`)
- Python version: 3.12+ (`requires-python = ">=3.12"`)
- Use `from __future__ import annotations` at top of all modules for forward references

**Linting:**
- Tool: ruff
- Config: `backend/pyproject.toml` under `[tool.ruff]`
- Key rules selected: E (pycodestyle), F (pyflakes), I (isort), N (pep8-naming), W (warnings)
- Ignored: E501 (line too long — handled by formatter)
- Run: `uv run --extra dev ruff check app/ tests/`

**Type Hints:**
- All function signatures include type hints for parameters and return values
- Use `| None` for optional types (Python 3.10+ union syntax)
- Generic types are specific: `dict[str, float]`, `list[str]`, not `Dict` or `List`
- Use `collections.abc` types for function signatures (e.g., `AsyncGenerator[str, None]`)

## Import Organization

**Order:**
1. `from __future__ import annotations` (if needed)
2. Standard library imports (e.g., `asyncio`, `logging`, `time`, `os`)
3. Third-party imports (e.g., `fastapi`, `numpy`, `massive`)
4. Relative local imports (e.g., `from .cache import PriceCache`)
5. Type checking imports behind `if TYPE_CHECKING:` (if needed)

**Path Aliases:**
- No path aliases configured; relative imports from same package used (e.g., `from .cache import PriceCache`)
- Module exports are explicit via `__all__` in `__init__.py` files

**Barrel Files:**
- Used for package-level exports (e.g., `backend/app/market/__init__.py`)
- Lists public API with docstring documenting what's exported
- Example: `backend/app/market/__init__.py` exports `PriceUpdate`, `PriceCache`, `MarketDataSource`, `create_market_data_source`, `create_stream_router`

## Error Handling

**Patterns:**
- Exceptions are caught specifically, not bare `except:` (e.g., `except asyncio.CancelledError`)
- Errors in background tasks are logged with context (e.g., client IP for SSE disconnects)
- API errors in pollers are caught but not re-raised, allowing graceful degradation (e.g., `_poll_once()` catches network errors without crashing)
- Malformed data from APIs is skipped individually rather than failing the entire poll
- Thread-safe operations use `Lock` with context manager (`with self._lock:`)

**Logging Strategy:**
- Errors and important state changes are logged (e.g., "Massive poller started", "SSE client connected")
- Log levels used: `info()` for state changes, `warning()` for recoverable errors
- Log messages include context (e.g., ticker count, interval, client IP)

## Logging

**Framework:** Standard Python `logging` module

**Patterns:**
- Module-level logger created at top: `logger = logging.getLogger(__name__)`
- Info level for state changes and important events
- Structured logging with context (e.g., `logger.info("Massive poller started: %d tickers, %.1fs interval", len(tickers), self._interval)`)
- Example locations: `backend/app/market/factory.py`, `backend/app/market/massive_client.py`, `backend/app/market/stream.py`

## Comments

**When to Comment:**
- Complex mathematical logic is explained with detailed comments (e.g., GBM formula in `backend/app/market/simulator.py`)
- Non-obvious algorithm choices are documented (e.g., Cholesky decomposition for correlated random variables)
- Lifecycle expectations are documented (e.g., "Must be called exactly once" in interface docstrings)
- Performance-critical sections note why they're optimized (e.g., "This is the hot path — called every 500ms")

**Docstrings:**
- All public classes and functions have docstrings
- Docstrings use multi-line format with description, then detailed explanation of behavior
- Parameters and return values documented in prose (not Google/NumPy style)
- Examples of docstring patterns: `backend/app/market/interface.py`, `backend/app/market/models.py`, `backend/app/market/cache.py`

## Function Design

**Size:** Functions are kept focused. Market data functions typically 20-50 lines for implementation, 10-20 for helpers.

**Parameters:**
- Type hints required for all parameters
- Optional parameters have default values (e.g., `timestamp: float | None = None`)
- Factory functions accept dependencies as parameters (e.g., `cache: PriceCache`, `api_key: str`)
- Async context parameters passed explicitly (e.g., `request: Request` for SSE endpoint)

**Return Values:**
- Explicit return type hints (e.g., `-> PriceUpdate`, `-> dict[str, float] | None`, `-> AsyncGenerator[str, None]`)
- Convenience methods return simple types (e.g., `get_price()` returns `float | None`)
- Data-bearing methods return dataclass instances (e.g., `update()` returns `PriceUpdate`)

## Module Design

**Exports:**
- Public API exported via `__all__` in `__init__.py` files
- Module docstrings document the public API
- Example: `backend/app/market/__init__.py` lists all public exports

**Barrel Files:**
- Used in `backend/app/market/` to consolidate exports
- Pattern: `from .submodule import Class; __all__ = ["Class"]`

**Abstract Interfaces:**
- Used for pluggable implementations (e.g., `MarketDataSource` abstract base class in `backend/app/market/interface.py`)
- Abstract methods documented with lifecycle and contract information
- Factory pattern used to select concrete implementation at runtime (e.g., `create_market_data_source()`)

## Data Structures

**Dataclasses:**
- Used for immutable data (e.g., `PriceUpdate`)
- Configured with `@dataclass(frozen=True, slots=True)` for memory efficiency and immutability
- Properties used for computed values (e.g., `change`, `change_percent`, `direction` in `PriceUpdate`)

**Thread-Safe Collections:**
- `PriceCache` uses `threading.Lock` for thread-safe read/write
- Lock held via context manager: `with self._lock:`
- Dunder methods implemented: `__len__`, `__contains__` for container protocol

**Factory Pattern:**
- Used for dependency injection (e.g., `create_stream_router()`, `create_market_data_source()`)
- Returns configured object with all dependencies injected
- Allows testing without globals

---

*Convention analysis: 2026-08-01*
