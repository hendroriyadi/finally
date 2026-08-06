---
phase: 05-one-command-ship
plan: 04
subsystem: testing
tags: [playwright, e2e, docker-compose]

requires:
  - phase: 05-one-command-ship
    provides: "the production image from Plan 05-01, which this rig builds and drives"
provides:
  - "test/docker-compose.test.yml — the real production image plus a Playwright runner"
  - "test/playwright.config.ts, test/package.json + lockfile, test/e2e/helpers.ts"
  - "Six numerically-prefixed spec files covering TEST-04's six scenarios"
  - "The .dockerignore fix for a real shipping bug this rig caught"
affects: []

actuals:
  tokens: 16000
  tasks: 1
  commits: 1

tech-stack:
  added: ["@playwright/test@1.62.1"]
  patterns: []

key-files:
  created: [test/package.json, test/package-lock.json, test/playwright.config.ts, test/docker-compose.test.yml, test/e2e/helpers.ts, "test/e2e/0{1..6}-*.spec.ts"]
  modified: [.dockerignore]

key-decisions:
  - "The compose service is named finally-app, not app — Chromium's HSTS preload list contains the entire .app gTLD"
  - "No volume on the app service: spec 01 asserts the untouched $10,000 balance and needs a freshly seeded database each run"

requirements-completed: [TEST-04]

coverage:
  - id: D1
    description: "The E2E rig builds the real production image, gates on its healthcheck, and drives it with a real browser under LLM_MOCK=true"
    requirement: TEST-04
    verification:
      - kind: e2e
        ref: "docker compose -f test/docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from playwright"
        status: pass
    human_judgment: false
  - id: D2
    description: "All six TEST-04 scenarios pass end to end"
    requirement: TEST-04
    verification:
      - kind: e2e
        ref: "9/9 specs green in ~46s (docker compose -f test/docker-compose.test.yml up ...)"
        status: pass
    human_judgment: false

duration: ~50min
completed: 2026-08-04
status: complete
---

# Phase 5, Plan 04: Playwright E2E Rig Summary

**All six TEST-04 scenarios pass — and the suite immediately earned its keep by catching a real shipping bug and a real product bug that nothing else could see.**

## The bug it caught

This is the headline, and it is the entire argument for TEST-04 existing.

`.dockerignore` excluded `.env` and `.env.*` **only at the repository root**. `frontend/.env.local` therefore stayed in the build context, and Next.js reads `.env.local` at **build** time — baking `NEXT_PUBLIC_API_URL=http://localhost:8000` into the static bundle. The shipped image served a frontend that asked the **browser's** localhost for its API.

On a developer's machine that works by accident. Anywhere else — including inside the compose network — it fails with `ERR_CONNECTION_REFUSED`.

Confirmed directly rather than inferred:
```
$ docker run --rm finally:test sh -c "grep -rlo 'localhost:8000' /app/static/_next"
/app/static/_next/static/chunks/2d1po8_fqf7-q.js
```
Fixed with `**/.env` patterns; after rebuild the grep returns nothing.

**Every earlier check missed this.** `curl` against the container passed, because curl never executes the bundle. The persistence script passed for the same reason. Unit tests never build an image. Only a real browser driving the real image could see it.

## A second finding: the service could not be named `app`

The first run failed all ten specs with `net::ERR_SSL_PROTOCOL_ERROR` on a plain `http://` URL. Chromium's HSTS preload list contains the entire `.app` gTLD, and the single-label host `app` matches it, so `http://app:8000` is force-upgraded to HTTPS. Renamed the service to `finally-app` and documented it inline so nobody renames it back.

## What was built
- `test/docker-compose.test.yml` — builds the **real** production image (`context: ..`, root `Dockerfile`), gates the runner on the app's healthcheck, sets `LLM_MOCK=true`, never passes `OPENROUTER_API_KEY`, publishes no host port, mounts no volume
- `test/playwright.config.ts` — single worker (all specs share one SQLite database), `BASE_URL` from the environment with a localhost fallback, artifacts inside `test/`
- `test/package.json` + **committed lockfile** — the runner's `npm ci` fails outright without it
- `test/e2e/helpers.ts` — panel locators scoped by heading; separate trade-bar and add-ticker input helpers, because both share the placeholder `e.g. AAPL` and an unscoped query is a strict-mode violation
- Six numerically-prefixed specs — the prefix is load-bearing: Playwright collects alphabetically and `01-fresh-start` asserts the untouched $10,000 balance that every later spec spends

`@playwright/test@1.62.1` was re-verified against the live registry before install (official `microsoft/playwright` repo, no install-time script) and pinned exactly, matching the runner image tag.

## A third finding: a real product bug

The suite also caught a defect the component tests could not: an AI-initiated
watchlist **remove** updated the database but not the grid. Proven with a probe
rather than inferred:

```
API_HAS_SHOP_AFTER_REMOVE:  false   <- server agrees it is gone
GRID_HAS_SHOP_AFTER_REMOVE: 1       <- the row is still on screen
```

That directly violates ROADMAP Phase 4 criterion 4 ("updates the watchlist
grid"). `WatchlistPanel` owns local state with no provider, and `ChatPanel`
lives in a different subtree, so `ChatPanel` now dispatches a window event the
panel listens for — a context for one signal would be more machinery than the
problem needs.

## Harness mistakes fixed along the way

Each diagnosed by probe rather than guessed, and each worth remembering:

- **`getByRole(name:)` is a substring match by default.** `name: "Positions"`
  also matched the heatmap's "No open positions" heading, resolving two
  sections and failing strict mode. Fixed with `exact: true`.
- **A plain `.click()` cannot work on this page.** It re-renders every ~500ms
  from the price stream, so Playwright's "stable" actionability check never
  passes: measured 12s timeout versus 29ms for `dispatchEvent`. Added
  `clickLive()`, which asserts `toBeEnabled()` first because `dispatchEvent`
  bypasses the disabled check and would otherwise "click" a dead control.
- **`dispatchEvent` does not perform default actions**, so it can never submit
  a `type="submit"` button. Chat sends use Enter — the real user gesture.
- **`sendChat` raced its own baseline**, counting assistant labels before the
  mount history fetch settled. Now waits for the skeleton to clear.
- **Watchlist row accessible names are `"AAPL190.13+0.02%"`** with no
  separator, so a `\b` word boundary could never match.

## The "flake" that was not a flake

The last failing test was recorded, in an earlier pass, as a known flake with an
open root cause. That was wrong, and the way it was wrong is the most useful
thing in this summary.

**It was deterministic.** The first chat test failed on attempt 1 in *every*
full-suite run and passed on retry — four for four. The configured retry turned
a 100%-reproducible assertion bug into something that looked probabilistic, and
"passes on retry" was accepted as good enough.

The actual cause, found by instrumenting the request rather than theorising:
the server was never involved. `POST /api/chat` returned `200 OK` with a
successful trade every time. The bug was in the test helper:

```ts
chatPanel(page).getByText("FINALLY")        // case-insensitive SUBSTRING
```

`getByText(string)` matches case-insensitively on substrings, so `"FINALLY"`
also matched the empty-state copy **"Start chatting with FinAlly"**. On an empty
conversation the baseline count was therefore 1, not 0. Sending a message
*replaced* the empty state with one assistant label — so the count stayed at 1
while the assertion waited for 2. On retry the conversation was no longer empty,
the empty state was gone, and the arithmetic happened to work out.

Fixed with `{ exact: true }`. The suite now passes **10/10 with retries
disabled**, twice, in 14–22s — and it is faster precisely because nothing is
burning 30s against a timeout any more.

This is the second time in this plan that Playwright's default substring
matching caused a failure that looked like something else (the first was
`getByRole(name:)` matching two panels). Both are now `exact: true`.

`playwright.config.ts` keeps one CI retry for genuine infrastructure noise, but
now carries a comment saying a retry-only pass is a bug report rather than a
pass — which is the check that would have caught this immediately.

## Next Phase Readiness
This is the final plan of the final phase. TEST-04 is complete: 9/9 specs green.

---
*Phase: 05-one-command-ship*
*Completed: 2026-08-04*
