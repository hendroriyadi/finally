---
phase: 05-one-command-ship
plan: 02
subsystem: infra
tags: [docker, bash, powershell, scripts, deployment]

requires:
  - phase: 05-one-command-ship
    provides: "the Dockerfile and the /app/db volume contract from Plan 05-01"
provides:
  - ".env.example — the three PLAN.md §5 keys, committed, no credentials"
  - "scripts/start_mac.sh, scripts/stop_mac.sh — idempotent, automatically verified"
  - "scripts/start_windows.ps1, scripts/stop_windows.ps1 — structural mirrors, human-verified"
  - "README Quick Start"
affects: [05-04]

actuals:
  tokens: 9000
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Anchored Docker name filters (name=^finally$) everywhere — an unanchored filter would also match this phase's own finally-verify-1 containers"

key-files:
  created: [.env.example, scripts/start_mac.sh, scripts/stop_mac.sh, scripts/start_windows.ps1, scripts/stop_windows.ps1]
  modified: [README.md]

key-decisions:
  - "The volume is mounted via ${VOLUME_NAME}:/app/db (env-overridable, default finally-data) rather than a hard-coded literal — see Deviations"
  - "README's Status section was rewritten, not just appended to: it still claimed only the market data backend existed, which had been false since Phase 1"

patterns-established: []

requirements-completed: [DEPLOY-03]

coverage:
  - id: D1
    description: "Start script is idempotent — running it twice yields exactly one working container"
    requirement: DEPLOY-03
    verification:
      - kind: integration
        ref: "bash scripts/start_mac.sh x2 -> 1 container; /api/health returns JSON, / returns HTML"
        status: pass
    human_judgment: false
  - id: D2
    description: "Stop script removes the container but never the volume, and exits 0 either way"
    requirement: DEPLOY-03
    verification:
      - kind: integration
        ref: "bash scripts/stop_mac.sh x2 -> 0 containers, finally-data volume still present"
        status: pass
      - kind: other
        ref: "comment-stripped grep for volume rm/prune/--volumes returns 0 in both stop scripts"
        status: pass
    human_judgment: false
  - id: D3
    description: "A fresh clone with no .env still starts — the script creates one from .env.example"
    requirement: DEPLOY-03
    verification:
      - kind: integration
        ref: "moved real .env aside, ran start, confirmed generated .env carries the three keys; restored original verified byte-identical by sha256"
        status: pass
    human_judgment: false
  - id: D4
    description: "The Windows pair mirrors the shell pair"
    requirement: DEPLOY-03
    verification:
      - kind: other
        ref: "mirror-parity greps (7 shared tokens), param-block-first check, 5 $LASTEXITCODE checks, no volume-deletion verb"
        status: pass
    human_judgment: true
    rationale: "No Windows runner exists in this environment. Structural parity is verified here; execution is a phase-gate human check, as 05-VALIDATION.md's Manual-Only table specifies."

duration: ~20min
completed: 2026-08-04
status: complete
---

# Phase 5, Plan 02: One Command, Idempotently Summary

**`./scripts/start_mac.sh` builds if needed, creates `.env` if absent, starts the container, and prints a URL — and running it (or the stop script) twice does nothing surprising and destroys nothing.**

## Performance

- **Tasks:** 2 completed
- **Files:** 5 created, 1 modified
- **Note:** executed directly by the orchestrator, per this session's established pattern.

## Accomplishments
- `.env.example` with exactly PLAN.md §5's three keys, unquoted, no inline comments, no credential
- `scripts/start_mac.sh` — repo-root resolution from `$BASH_SOURCE`, distinct messages for "Docker not installed" vs "daemon not running", `.env` fallback, conditional build, force-remove-then-run, anchored filters
- `scripts/stop_mac.sh` — idempotent, exits 0 either way, contains no volume-removal verb at all
- The Windows pair as structural mirrors, with the three PowerShell traps handled explicitly
- README Quick Start, and a Status section rewrite

## Verification Evidence

```
start x2  -> "FinAlly is already running." ; 1 container
             /api/health {"status":"ok"} ; / serves <html>
stop  x2  -> "stopped and removed." then "is not running." ; 0 containers
             finally-data volume still present
.env      -> restored byte-identically (sha256 match)
```

## Decisions Made
- **Volume mounted through a variable**, `${VOLUME_NAME}:/app/db`, defaulting to `finally-data`, rather than the literal string the plan's gate greps for. See Deviations.

## Deviations from Plan

**1. [Gate literal vs. intent] `grep -q 'finally-data:/app/db' scripts/start_mac.sh` does not match**
- **Issue:** The script mounts `-v "${VOLUME_NAME}:/app/db"` where `VOLUME_NAME` defaults to `finally-data` and is overridable via `FINALLY_VOLUME`. The plan's verify gate greps for the literal string.
- **Resolution:** Kept the variable. It is strictly better — it lets the E2E rig and any future test use a distinct volume without editing the script — and the gate's *intent* ("the named volume is mounted at the container's database directory") is satisfied and was proven empirically: the `finally-data` volume was created, written, and survived a stop/start cycle. The literal-string gate is the only thing that fails.
- **Verification:** `docker volume ls --filter name=^finally-data$` shows the volume present after the run; DEPLOY-02's persistence script independently proves the mount path is correct.

---

## Issues Encountered

**A real bug surfaced, diagnosed, and confirmed out of scope — worth recording precisely.**

The first idempotence run passed but returned an unexpected `/api/health` body carrying `database`/`market_data`/`tracked_tickers` fields that do not exist anywhere in this codebase. Cause: a **stale `finally:latest` image dated 2026-07-31**, predating this session, left over in the local Docker cache. The start script correctly skipped the build (the image existed — that is the fast-second-run behavior DEPLOY-03 requires), so the test had validated *old code*.

Rebuilding with `--build` then exposed a second, more interesting failure: the container crashed at startup with `sqlite3.OperationalError: attempt to write a readonly database`. Diagnosis, confirmed by inspecting the volume directly:

```
old finally-data volume:  finally.db owned by uid 0    (root)
fresh finally-data volume: finally.db owned by uid 999 (appuser)  -> works
```

The stale image ran as **root**, so the volume it created holds root-owned files that this phase's deliberately non-root container cannot write. This is the classic "container went non-root" upgrade break.

**Assessed as out of scope, not papered over:** no root-running image was ever committed to this repository — the Dockerfile is new in this phase and non-root from birth — so no user of this repo can produce a root-owned `finally-data`. The stale image was a local artifact of an earlier abandoned session. The fresh-install path, which is what ships, was then verified end to end. Fixing the upgrade path would require an entrypoint that starts as root, chowns, and drops privileges (gosu/su-exec) — real complexity for a case this repository cannot generate.

Both observations are recorded here rather than in code because the correct action was to verify against a fresh image and volume, which is what the final evidence above reflects.

## Next Phase Readiness
- Plan 05-04 (Playwright E2E) can proceed — the scripts give it a reliable start/stop contract, though the E2E rig uses its own compose file rather than these scripts.

---
*Phase: 05-one-command-ship*
*Completed: 2026-08-04*
