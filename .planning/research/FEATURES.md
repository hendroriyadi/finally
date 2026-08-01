# Feature Research

**Domain:** AI-copiloted paper-trading / trading-terminal web app (capstone demo)
**Researched:** 2026-08-01
**Confidence:** MEDIUM (general web sources, cross-checked across multiple independent queries; no official vendor docs exist for this niche — see Sources)

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist in any paper-trading / trading-terminal product. Missing these makes the product feel broken or incomplete, regardless of how good the AI layer is.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Live-updating watchlist grid (ticker, price, % change) | Every paper-trading app (TradingView, Webull, StockBrokers-reviewed platforms) leads with this; it's the "is this thing alive" signal | LOW | Already partly built — price cache + SSE plumbing exists. This milestone wires `/api/stream/prices` + frontend `EventSource` consumer. |
| Price flash feedback (green up / red down, fades ~500ms) | Standard convention across every trading terminal reviewed (TradingView scripts, Bloomberg-style dashboards); without it, a live feed feels static even though numbers are changing | LOW | CSS transition on price cell; trivial once SSE delivers price+direction per tick. |
| Sparkline mini-chart per watchlist row | "Compact view typically includes symbol, last price, change... and a small sparkline" — near-universal in reviewed platforms | LOW-MEDIUM | PLAN.md specifies client-accumulated sparkline (builds from SSE stream since page load) rather than a server history endpoint — simpler, but means sparkline is empty/short right after page load. Acceptable for a demo. |
| Larger detail chart for selected ticker | Every dashboard reviewed places a chart alongside/above the watchlist; clicking a symbol to inspect it is assumed behavior | MEDIUM | Canvas-based library recommended (Lightweight Charts or Recharts per PLAN.md) for performance with frequent updates. |
| Positions table (qty, avg cost, current price, unrealized P&L, % change) | Portfolio tracking with P&L visibility is called out as a baseline expectation across every simulator reviewed | LOW-MEDIUM | Straightforward derived view from `positions` + live price cache; no new data model needed. |
| Buy/sell trade entry (ticker, quantity, side) | Core loop of any trading simulator — without it there's no product | LOW-MEDIUM | Market-order-only per PLAN.md; this dramatically simplifies validation (no order book, no partial fills). |
| Cash balance + total portfolio value, always visible | Every reviewed simulator dashboard keeps account value/balance in a persistent header or panel | LOW | Header per PLAN.md §10. |
| Connection/liveness indicator | Expected in any app with a persistent stream connection; users need to know if data is stale | LOW | Simple colored dot (green/yellow/red) per PLAN.md — cheap to build, meaningfully reduces "is this broken" confusion. |
| Watchlist add/remove | Table stakes across all platforms reviewed ("users can add markets to their watchlist... some platforms allow syncing") | LOW | Manual UI control; also exposed to the LLM chat (differentiator layer on top of a table-stakes primitive). |
| Trade history / audit log | Reviewed simulators consistently include "trading history" as baseline | LOW | `trades` table is append-only per PLAN.md — no dedicated history UI is mandated by PLAN.md, but the positions/portfolio views should be able to surface it if time allows. |

### Differentiators (Competitive Advantage)

Features that set FinAlly apart from a generic paper-trading app. This is where PLAN.md's "AI copilot" framing pays off, and where course-demo impact is concentrated.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| AI chat assistant with portfolio-aware analysis | Most retail paper-trading apps have zero AI; conversational portfolio analysis (concentration risk, P&L narrative) is the headline feature of this project | MEDIUM-HIGH | Requires assembling portfolio context (cash, positions w/ P&L, watchlist w/ live prices) into the prompt each turn — get this context-construction right, it's the difference between generic and genuinely useful chat. |
| AI auto-executes trades from natural language, no confirmation | This is the single most distinctive, demo-impressive feature — "describe a strategy, agent acts on it" is explicitly called out in market research as an emerging 2026 fintech frontier (e.g. Public.com's "Agentic Brokerage," launched March 2026) | MEDIUM | See Pitfalls below — this is high-impact but carries real trust-design tension that PLAN.md consciously accepts because stakes are zero (fake money). Frame it in the UI as a deliberate feature, not an accident (see "AI action transparency" below). |
| AI manages the watchlist proactively | Extends the "agent takes real actions" theme beyond trading into a second domain (watchlist curation), reinforcing the agentic narrative | LOW-MEDIUM | Same structured-output mechanism as trades; low incremental cost once trade auto-exec exists. |
| Portfolio heatmap/treemap (size = weight, color = P&L) | Treemaps are the recognized best-practice visualization for "at a glance" portfolio composition + performance (Finviz market map is the canonical reference); most retail paper-trading apps do NOT include this — it reads as "pro-grade" | MEDIUM | Standard nested-rectangle treemap; note the documented treemap limitation (near-zero-value positions become illegible slivers) — with only ~10 tickers and $10k starting capital this is unlikely to bite, but don't over-engineer around it. |
| P&L-over-time line chart (from `portfolio_snapshots`) | Turns "current state" into "story" — most basic simulators show current P&L only, not portfolio value trajectory | LOW-MEDIUM | Snapshot-based (every 30s + post-trade), so resolution is coarse but sufficient for a demo session. |
| Bloomberg-terminal dark, dense aesthetic | Reviewed sources confirm this is a recognizable, differentiated visual language (vs. the friendlier, whitespace-heavy look of Robinhood-style consumer apps) — signals "professional tool" even though it's a teaching demo | MEDIUM | Design system already specified in PLAN.md (colors, dark bg). Consistency and density execution matter more than novel visual invention here. |
| AI action transparency inline in chat (trade/watchlist confirmations shown as chat cards) | Agentic-UX research is unanimous that even when actions execute without a gate, users need *visible* record of what the agent did and why — this is the mitigation for the "no confirmation" choice, not a nice-to-have | LOW-MEDIUM | PLAN.md already specifies "trade executions and watchlist changes shown inline as confirmations" — treat this as load-bearing for trust, not decorative. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good for a trading app but would be scope traps or actively wrong for this project's constraints (single-user, zero real stakes, capstone timeline).

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|------------------|-------------|
| Trade confirmation dialog before AI-executed trades | Standard "safe" pattern; real fintech AI copilots (e.g. PipSync connecting Claude/ChatGPT to live broker accounts) require exactly this two-step preview-then-approve flow | Directly contradicts PLAN.md's explicit, deliberate design choice — the whole point of the demo is a frictionless "describe a strategy, watch it happen" agentic moment; with fake money the safety rationale for confirmation doesn't apply | Keep zero-confirmation execution, but make agent actions maximally *visible after the fact* (inline chat cards, trade already reflected in positions table/heatmap within the same response) so trust comes from transparency, not gating |
| Limit orders / stop-loss / take-profit / options chains | Reviewed "advanced" paper-trading platforms all offer these; feels like a natural v2 ask | PLAN.md explicitly scopes to market-orders-only specifically to avoid order-book/partial-fill/pending-order complexity — adding any of this reopens a large state-machine (open orders, order lifecycle, triggers) that the rest of the architecture (simple positions table, instant-fill trades) isn't built for | Out of scope for this milestone; if ever revisited, treat as its own milestone with its own schema (`orders` table, order-matching logic against the live price stream) |
| Multi-user accounts / login | Feels like an obvious "real product" requirement | No auth = no multi-user is a deliberate PLAN.md simplification; adding it means auth, session management, per-user DB scoping — none of which serves the capstone's teaching goal (demonstrating agentic AI orchestration) | `user_id="default"` hardcoded, schema already carries the column for painless future migration if ever needed |
| Server-persisted sparkline/price history endpoint | Feels more "correct" than client-accumulated sparklines (which are empty on fresh page load) | Adds a new table/endpoint/query surface for a cosmetic improvement; PLAN.md deliberately keeps this client-side and stream-derived to avoid extra backend surface area | Accept the "sparkline fills in progressively" UX as intentional and demo-appropriate; document it as a known limitation, not a bug |
| Real brokerage integration / real money execution | "Wouldn't it be cool if trades were real" is a common escalation once the AI-trades-for-you demo lands well | Total scope, compliance, and regulatory explosion; also destroys the entire "zero-stakes, no-confirmation" design rationale that makes the auto-execute UX defensible | Simulated portfolio only; if real market data realism is desired, that's already covered by the optional Massive/Polygon.io read-only price feed — never wire write/execution paths to a real broker |
| Push/toast notifications, price alerts | Reviewed platforms include "alert systems" as a value-add | Adds a notification subsystem (thresholds, delivery, dismissal state) orthogonal to the core agentic-AI demo value; not mentioned anywhere in PLAN.md | Skip entirely for this milestone; the AI chat can proactively surface anything alert-worthy if asked ("how's my portfolio doing") |

## Feature Dependencies

```
SSE price stream (existing)
    └──requires──> Watchlist grid with live prices
                       └──enables──> Price flash animation
                       └──enables──> Sparkline (client-accumulated)
                       └──enables──> Main detail chart (selected ticker)

Positions table + Portfolio API
    └──requires──> Trade execution (buy/sell)
                       └──requires──> Watchlist/price cache (for current price at fill time)
    └──enables──> Portfolio heatmap/treemap
    └──enables──> Header total-value + cash display

portfolio_snapshots (30s cadence + post-trade)
    └──requires──> Trade execution (to trigger post-trade snapshot)
    └──enables──> P&L line chart

AI chat assistant
    └──requires──> Portfolio API (context: cash, positions, P&L)
    └──requires──> Watchlist API (context: live prices)
    └──requires──> Trade execution (to auto-execute LLM-proposed trades)
    └──requires──> Watchlist add/remove (to auto-execute LLM-proposed watchlist changes)
    └──enables──> AI action transparency (inline chat confirmation cards)

AI action transparency ──enhances──> AI auto-execute trust (mitigates "no confirmation" pitfall)

LLM_MOCK mode ──enhances──> E2E test determinism (does not block any user-facing feature)

Limit orders / stop-loss ──conflicts──> Market-orders-only architecture (anti-feature, out of scope)
Multi-user auth ──conflicts──> Single hardcoded user_id="default" (anti-feature, out of scope)
```

### Dependency Notes

- **Positions table requires Trade execution:** there is nothing to display until at least one buy has happened; trade execution must land before positions/heatmap/P&L views can be meaningfully verified end-to-end.
- **Portfolio heatmap requires Positions table (data), not vice versa:** build/verify the tabular positions view first (simpler, easier to eyeball-verify math), then layer the treemap visualization on the same underlying data.
- **AI chat assistant requires Portfolio API + Watchlist API + Trade execution to all exist first:** the chat's value is entirely derivative of the underlying REST surface — it reads portfolio context and writes through the same trade/watchlist mutation paths as the manual UI. Building chat before those primitives exist means faking/duplicating logic that will need to be thrown away.
- **AI action transparency enhances AI auto-execute trust:** this is the most important dependency for the roadmap — the no-confirmation design choice (PLAN.md §9, explicitly retained per research above) is only defensible UX if paired with strong post-hoc visibility (inline trade/watchlist-change cards in the chat transcript, immediate reflection in positions/heatmap). Do not schedule "auto-execute" and "inline confirmation cards" in separate phases without the latter landing in the same phase or immediately after.
- **Limit orders / multi-user auth conflict with current architecture:** both are anti-features for this milestone; flagging the conflict explicitly so a future roadmap doesn't accidentally schedule them as "quick additions" — each requires schema and logic changes that ripple through trade execution and portfolio valuation.

## MVP Definition

Given this is a subsequent milestone building on an already-completed market-data layer, "MVP" here means the minimum needed to demonstrate the full agentic-AI value proposition end-to-end — not a trimmed-down version of PLAN.md (scope is locked, per PROJECT.md).

### Launch With (v1 — this milestone, matches PLAN.md scope exactly)

- [ ] SQLite schema + lazy init/seed (users_profile, watchlist, positions, trades, portfolio_snapshots, chat_messages) — everything else depends on this existing first
- [ ] `/api/stream/prices` SSE endpoint wired to existing price cache — watchlist/chart/flash all depend on this
- [ ] Watchlist grid with price flash + sparkline + add/remove — table stakes, first visible payoff
- [ ] Portfolio API (get, trade, history) + trade bar (buy/sell) — core loop
- [ ] Positions table — cheapest way to verify trade/P&L math is correct before layering visualization
- [ ] Portfolio heatmap/treemap + P&L chart — differentiators that make the dashboard feel "pro"
- [ ] AI chat with portfolio-aware analysis + auto-execute trades/watchlist changes + inline action confirmation cards — the centerpiece; ship the transparency UX alongside auto-execution, not after
- [ ] `LLM_MOCK=true` mode — required for deterministic E2E tests, not user-facing but blocks the testing strategy
- [ ] Dark terminal visual design (PLAN.md color scheme) — differentiator, but low technical risk; can be layered incrementally across phases rather than gating other work

### Add After Validation (v1.x — not currently in scope, only if milestone has slack)

- [ ] Trade history detail view (beyond the append-only log existing in the DB) — trigger: if positions table alone feels insufficient during UAT
- [ ] Richer AI proactivity (e.g., AI flags concentration risk unprompted on load) — trigger: if base chat Q&A feels too passive during UAT

### Future Consideration (v2+ — explicitly out of scope per PROJECT.md)

- [ ] Limit orders, stop-loss/take-profit, options — defer: reopens order-lifecycle complexity the current architecture isn't built for
- [ ] Multi-user auth — defer: no product reason to support multiple users in a single-session teaching demo
- [ ] Real brokerage execution — defer: destroys the zero-stakes rationale that makes no-confirmation auto-execute defensible; regulatory/compliance scope explosion
- [ ] Price alerts/notifications — defer: orthogonal subsystem, not mentioned in PLAN.md, no course-value justification

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| SSE price stream wiring + watchlist grid + flash | HIGH | LOW | P1 |
| Sparkline (client-accumulated) | MEDIUM | LOW | P1 |
| Main detail chart | MEDIUM | MEDIUM | P1 |
| Trade execution (buy/sell) + positions table | HIGH | MEDIUM | P1 |
| Cash/total-value header + connection indicator | HIGH | LOW | P1 |
| Portfolio heatmap/treemap | HIGH | MEDIUM | P1 |
| P&L line chart | MEDIUM | LOW-MEDIUM | P1 |
| AI chat: portfolio analysis (read-only Q&A) | HIGH | MEDIUM | P1 |
| AI chat: auto-execute trades + watchlist changes | HIGH | MEDIUM | P1 |
| AI action transparency (inline confirmation cards) | HIGH | LOW-MEDIUM | P1 (bundle with auto-execute, not deferred) |
| Dark terminal visual polish | MEDIUM | MEDIUM | P1 (spread across phases, not a gate) |
| `LLM_MOCK` deterministic mode | LOW (invisible to end user) | LOW | P1 (blocks E2E test strategy) |
| Docker/deploy scripts | LOW (invisible to end user) | LOW-MEDIUM | P1 (required for "single command" experience in Core Value) |
| Trade history detail UI | LOW-MEDIUM | LOW | P2 |
| Proactive AI risk flags | MEDIUM | MEDIUM | P2 |
| Limit orders / stop-loss | MEDIUM (for a "real" trading app) | HIGH | P3 (out of scope) |
| Multi-user auth | LOW (for this project's goals) | HIGH | P3 (out of scope) |
| Price alerts | LOW-MEDIUM | MEDIUM | P3 (out of scope) |

**Priority key:**
- P1: Must have for this milestone (matches PLAN.md scope — scope is locked, not a negotiable MVP trim)
- P2: Should have if time permits, not currently scoped
- P3: Explicitly out of scope for this project

## Competitor Feature Analysis

| Feature | TradingView / Webull-style paper trading | Real-money AI-copilot fintech (e.g. PipSync via Claude/ChatGPT + MCP) | FinAlly's Approach |
|---------|-------------------------------------------|--------------------------------------------------------------------------|---------------------|
| Trade execution model | Manual only, sometimes with limit/stop orders | AI proposes, user must approve (two-step confirmation) — real money is at stake | Market orders only, manual OR AI-initiated, both auto-fill with **zero confirmation** — defensible because it's simulated money and the design goal is demonstrating agentic capability |
| Watchlist visualization | Ticker + price + sparkline, standard grid | N/A (not the focus) | Same grid pattern, plus price-flash animation for stream "aliveness" |
| Portfolio visualization | P&L numbers, sometimes a pie/allocation chart; treemap is a "pro" feature (Finviz-style), not default in most retail paper-trading apps | N/A (chat-only interface) | Treemap/heatmap as a default, differentiating feature |
| AI role | None, or bolted-on chatbot for market news/education | Full execution agent, but gated behind explicit approval and scoped account permissions | Full execution agent, ungated, but mitigated via inline action-transparency cards in the chat transcript |
| Trust/audit mechanism | N/A | Two-step confirm + presumably order history in the broker's own UI | `chat_messages.actions` JSON column logs every executed action tied to the conversation turn that caused it — audit trail exists even without a confirmation gate |

## Sources

- [6 Best Paper Trading Apps & Platforms for 2026 - StockBrokers.com](https://www.stockbrokers.com/guides/paper-trading)
- [Paper Trading on TradingView: a full review](https://www.newtrading.io/tradingview-paper-trading/)
- [Best Paper Trading Apps in 2026: Top Simulators Reviewed](https://www.gainify.io/blog/best-paper-trading-apps)
- [Best Stock Market Simulator & Paper Trading Platforms in 2026 | ChartingLens](https://chartinglens.com/blog/best-stock-market-simulator-paper-trading)
- [Adapting Treemaps To Stock Portfolio Visualization (ResearchGate/UMD)](https://www.researchgate.net/publication/2370624_Adapting_Treemaps_To_Stock_Portfolio_Visualization)
- [Portfolio Heatmap Tracker - Stock & Crypto Portfolio Visualization](https://portfolioheatmaps.com/)
- [Data visualization applied to Finance: how to use Treemap (Medium)](https://medium.com/@matteo.bernard/data-visualization-applied-to-finance-how-to-use-treemap-b2f0c58ca2a6)
- [fin/SPEC.md — ed-donner/fin (sibling reference implementation of this same course project)](https://github.com/ed-donner/fin/blob/main/SPEC.md)
- [Agentic AI UX: Design for Autonomous Agents - YUJ Designs](https://www.yujdesigns.com/blog/agentic-ai-ux-design/)
- [AI Agent UX: Designing for Autonomy and Oversight - ParallelHQ](https://www.parallelhq.com/blog/ai-agent-ux-design)
- [Fintechs Put AI in the Driver's Seat with Agentic Trading (Corporate Insight)](https://corporateinsight.com/fintechs-put-ai-in-the-drivers-seat-with-agentic-trading/)
- [AI Agents That Refuse Commands: The Fatal Design Flaws](https://www.ruh.ai/blogs/ai-agents-that-refuse-commands-the-fatal-design-flaws)
- [10 Agent UX Mistakes Users Never Forgive (Medium)](https://medium.com/@npavfan2facts/10-agent-ux-mistakes-users-never-forgive-ad9a28db1cdc)
- [PipSync.io Launches AI Copilot Letting Users Manage Accounts Through Claude (Morningstar/AccessWire)](https://www.morningstar.com/news/accesswire/1196658msn/pipsyncio-launches-ai-copilot-letting-users-manage-accounts-through-claude)
- [Why do Bloomberg terminals have such non-standard interfaces? (Quora)](https://www.quora.com/Why-do-Bloomberg-terminals-have-such-non-standard-interfaces)
- [UI Density — Matt Ström-Awn](https://mattstromawn.com/writing/ui-density/)
- Internal: `/Users/hendro/Documents/Projects/finally/planning/PLAN.md` (project spec, source of truth for exact scope/contracts)
- Internal: `/Users/hendro/Documents/Projects/finally/.planning/PROJECT.md` (locked requirements, out-of-scope list)

---
*Feature research for: AI-copiloted paper-trading / trading-terminal capstone app*
*Researched: 2026-08-01*
