# FinAlly — AI Trading Workstation

A visually stunning AI-powered trading workstation that streams live market data, simulates portfolio trading, and integrates an LLM chat assistant that can analyze positions and execute trades via natural language.

Built entirely by coding agents as a capstone project for an agentic AI coding course. See [planning/PLAN.md](planning/PLAN.md) for the full spec.

## Quick Start

You need [Docker](https://docs.docker.com/get-docker/) running. Nothing else.

```bash
./scripts/start_mac.sh      # macOS / Linux
.\scripts\start_windows.ps1 # Windows PowerShell
```

Then open **http://localhost:8000**.

The first run builds the image (a few minutes); later runs reuse it. Pass
`--build` to force a rebuild after pulling new code, and `--open` to launch a
browser. Running the script twice is harmless.

```bash
./scripts/stop_mac.sh       # macOS / Linux
.\scripts\stop_windows.ps1  # Windows PowerShell
```

Stopping never deletes your data — cash, positions, trade history, watchlist,
and chat history live in a Docker volume (`finally-data`) and survive
restarts.

On first run the start script creates `.env` from `.env.example`. The app
works without any API key; add `OPENROUTER_API_KEY` to enable the AI copilot.

## Status

**All five phases are built.** Live streaming watchlist, manual trading,
portfolio visualizations, the AI copilot, and single-container packaging are
all implemented and tested.

- ✅ **Live Market Terminal** — SSE price streaming, editable watchlist, flash animations, sparklines
- ✅ **Manual Trading** — atomic buy/sell with race-safe cash and share guards, live positions table
- ✅ **Portfolio Visualization** — position heatmap, P&L-over-time chart, per-ticker detail chart
- ✅ **AI Copilot** — portfolio-grounded chat that executes trades and watchlist changes through the same validated code paths the UI uses
- ✅ **One-Command Ship** — single Docker container on port 8000, persistent volume, start/stop scripts, component and E2E test suites

See [planning/PLAN.md](planning/PLAN.md) for the full spec and
[planning/MARKET_DATA_SUMMARY.md](planning/MARKET_DATA_SUMMARY.md) for the
market data subsystem.

## Planned Features

- **Live price streaming** via SSE with green/red flash animations
- **Simulated portfolio** — $10k virtual cash, market orders, instant fills
- **Portfolio visualizations** — heatmap (treemap), P&L chart, positions table
- **AI chat assistant** — analyzes holdings, suggests and auto-executes trades
- **Watchlist management** — track tickers manually or via AI
- **Dark terminal aesthetic** — Bloomberg-inspired, data-dense layout

## Planned Architecture

Single Docker container serving everything on port 8000:

- **Frontend**: Next.js (static export) with TypeScript and Tailwind CSS
- **Backend**: FastAPI (Python/uv) with SSE streaming
- **Database**: SQLite with lazy initialization
- **AI**: LiteLLM → OpenRouter (Cerebras inference) with structured outputs
- **Market data**: Built-in GBM simulator (default) or Massive API (optional) — ✅ implemented

## Try the Market Data Demo

The only runnable piece right now is a terminal demo of the market data simulator:

```bash
cd backend
uv sync
uv run market_data_demo.py
```

Displays a live-updating dashboard with all 10 tickers, sparklines, and an event log. Runs 60 seconds or until Ctrl+C.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes (once chat is built) | OpenRouter API key for AI chat |
| `MASSIVE_API_KEY` | No | Massive (Polygon.io) key for real market data; omit to use simulator |
| `LLM_MOCK` | No | Set `true` for deterministic mock LLM responses (testing) |

## Project Structure

```
finally/
├── backend/     # FastAPI uv project (market data subsystem built; API/DB/chat pending)
├── planning/    # Project documentation and agent contracts
└── (planned)    frontend/, test/, db/, scripts/
```

## License

See [LICENSE](LICENSE).
