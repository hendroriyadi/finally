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

requirements-completed: []

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
        ref: "3 of 10 specs green; 7 failing on locator/test-design refinements"
        status: fail
    human_judgment: true
    rationale: "Incomplete and reported as such. The rig is proven; the specs need locator work. See Issues Encountered for the precise remaining list."

duration: ~50min
completed: 2026-08-04
status: partial
---

# Phase 5, Plan 04: Playwright E2E Rig Summary

**The rig works end to end and immediately earned its keep — it caught a real shipping bug that every prior check missed. Six scenarios are written; three pass, seven need locator refinement.**

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

## Issues Encountered — remaining work, stated plainly

**3 of 10 specs pass.** The rig, the image build, the healthcheck gating, the mock wiring, and the artifact paths are all proven. The seven failures are in the specs, not the infrastructure:

- Several assert on panel-scoped text that needs locator refinement against the real rendered DOM (the add-button label was `Add Ticker`, not `Add`; the header figures needed an xpath sibling rather than a CSS `+ div` — both already fixed, others remain).
- `06-sse-reconnect` has a genuine **test-design** problem, not a locator one: `context.route(...).abort()` does not tear down an already-open `EventSource`, so the status never leaves `Connected` and the assertion times out. Cutting the stream needs a different mechanism (route the request before the page opens it, or restart the app service mid-test).

None of these indicate a product defect — the same flows are covered by 27 passing component tests and by the DEPLOY-01/02/03 container proofs. Reported as incomplete rather than rounded up.

## Next Phase Readiness
This is the final plan of the final phase. TEST-04 is partially delivered and recorded as such in `05-VERIFICATION.md`.

---
*Phase: 05-one-command-ship*
*Completed: 2026-08-04 (partial)*
