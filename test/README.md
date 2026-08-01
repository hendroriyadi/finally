# E2E tests

Playwright suite driving the real production image through a browser.

## Run

```bash
./test/run-e2e.sh
```

That builds `Dockerfile` at the repo root, starts it alongside a Playwright
container, runs the suite, and tears both down. Exit code is the suite's.
The HTML report lands in `test/artifacts/report/index.html`; failures also leave
a screenshot and a trace under `test/artifacts/results/` (open a trace with
`npx playwright show-trace <path>`).

Iterating on specs without rebuilding the app image:

```bash
docker compose -f test/docker-compose.test.yml up -d app
docker compose -f test/docker-compose.test.yml run --rm playwright \
  npx playwright test specs/03-trading.spec.ts
docker compose -f test/docker-compose.test.yml down
```

Specs are bind-mounted, so edits apply without a rebuild — but state
accumulates across runs against a long-lived `app`, so use `run-e2e.sh` for the
authoritative result.

The app is also published on host port `8100` while the stack is up, so
`E2E_BASE_URL=http://localhost:8100 npx playwright test` works from the host
once `npm install` has been run in this directory.

## Layout

| Path | Role |
|---|---|
| `docker-compose.test.yml` | App container (`LLM_MOCK=true`, tmpfs database) + Playwright runner |
| `Dockerfile.playwright` | Browser image; keeps browser deps out of the production image |
| `specs/helpers.ts` | Locators for the frontend's `data-testid`s, money parsing, trade/chat drivers |
| `specs/0*.spec.ts` | Scenarios, in execution order |

## How the suite is wired

- **One shared, stateful backend.** `workers: 1`, `fullyParallel: false`,
  `retries: 0` — a retried mutating test would replay against state its first
  attempt already changed. Specs are numbered because they run in filename
  order and later ones build on earlier positions.
- **Fresh database per run.** `/app/db` is a tmpfs, so the backend lazily
  re-seeds $10,000 and the ten default tickers on every run. Only
  `01-fresh-start` asserts the untouched balance; every other spec measures
  deltas.
- **`LLM_MOCK` is set in `environment:`, not from `.env`.** Importing `litellm`
  calls `load_dotenv()` as a side effect, so a mounted `.env` can re-leak real
  values over the test config.
- **Tickers are reserved per spec** (`NVDA`/`MSFT` trading, `META`
  visualization, `AAPL`/`TSLA` chat, `PYPL`/`SNOW` watchlist) so specs do not
  perturb each other's position math.
- **Browsing happens via the `finally-app` network alias.** Chrome's HSTS
  preload list covers the `app` gTLD and the bare compose service name `app`
  matches it, so `http://app:8000` gets forced to HTTPS and fails with
  `ERR_SSL_PROTOCOL_ERROR`.
