#!/usr/bin/env bash
#
# DEPLOY-02: state written through a running container is still there after
# that container is destroyed and replaced by a new one on the same volume.
#
# What this script deliberately does NOT do:
#   - It never reads or writes the SQLite file directly. Every write goes
#     through the real HTTP API and every read comes back through it.
#   - It never inspects the text of a `docker run` command. A check that
#     asserted a `-v` flag is present would pass against an image that
#     persists nothing, which is the entire failure mode this exists to catch.
#   - It never reuses the first container. It REMOVES it — a merely stopped
#     container still owns its writable layer, so restarting it would prove
#     nothing about the volume.

set -euo pipefail

IMAGE_TAG="finally:verify"
# Distinct from the start scripts' `finally-data` on purpose: this script
# destroys its volume at the end and must never be able to delete real data.
VOLUME_NAME="finally-verify-data"
CONTAINER_ONE="finally-persist-1"
CONTAINER_TWO="finally-persist-2"
HOST_PORT="${HOST_PORT:-8010}"
BASE="http://localhost:${HOST_PORT}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cleanup() {
  docker rm -f "$CONTAINER_ONE" >/dev/null 2>&1 || true
  docker rm -f "$CONTAINER_TWO" >/dev/null 2>&1 || true
}
trap cleanup EXIT

wait_ready() {
  local name="$1"
  for _ in $(seq 1 60); do
    if curl -sf "${BASE}/api/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "FAIL: ${name} never became ready at ${BASE}/api/health" >&2
  docker logs "$name" >&2 || true
  return 1
}

start_container() {
  local name="$1"
  docker run -d \
    --name "$name" \
    -p "${HOST_PORT}:8000" \
    -v "${VOLUME_NAME}:/app/db" \
    -e LLM_MOCK=true \
    "$IMAGE_TAG" >/dev/null
  wait_ready "$name"
}

# Stable comparable values only. Full response bodies carry live prices and
# timestamps that legitimately differ between reads, and comparing those would
# fail for the wrong reason.
read_cash() {
  curl -sf "${BASE}/api/portfolio" | python3 -c 'import json,sys; print("%.4f" % json.load(sys.stdin)["cash_balance"])'
}
read_positions() {
  curl -sf "${BASE}/api/portfolio" | python3 -c 'import json,sys; print(sorted((p["ticker"], round(p["quantity"],6)) for p in json.load(sys.stdin)["positions"]))'
}
read_watchlist() {
  curl -sf "${BASE}/api/watchlist" | python3 -c 'import json,sys; print(sorted(t["ticker"] for t in json.load(sys.stdin)["tickers"]))'
}
read_chat_count() {
  curl -sf "${BASE}/api/chat/history" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["messages"]))'
}

echo "==> Cleaning up any previous run"
cleanup
docker volume rm "$VOLUME_NAME" >/dev/null 2>&1 || true

echo "==> Building ${IMAGE_TAG}"
docker build -t "$IMAGE_TAG" "$REPO_ROOT" >/dev/null

echo "==> Lifecycle 1: starting ${CONTAINER_ONE}"
start_container "$CONTAINER_ONE"

echo "==> Writing state through the real HTTP API"
# A buy writes cash, a position, and a trade row in one call.
curl -sf -X POST "${BASE}/api/portfolio/trade" \
  -H 'Content-Type: application/json' \
  -d '{"ticker":"AAPL","side":"buy","quantity":3}' >/dev/null
# A ticker outside the seeded ten.
curl -sf -X POST "${BASE}/api/watchlist" \
  -H 'Content-Type: application/json' \
  -d '{"ticker":"PYPL"}' >/dev/null
# Writes two chat rows and executes a second trade (mock trigger phrase).
curl -sf -X POST "${BASE}/api/chat" \
  -H 'Content-Type: application/json' \
  -d '{"message":"buy 2 MSFT"}' >/dev/null

BEFORE_CASH="$(read_cash)"
BEFORE_POSITIONS="$(read_positions)"
BEFORE_WATCHLIST="$(read_watchlist)"
BEFORE_CHAT="$(read_chat_count)"

echo "    cash=${BEFORE_CASH} positions=${BEFORE_POSITIONS} chat_messages=${BEFORE_CHAT}"

echo "==> Destroying ${CONTAINER_ONE} (remove, not just stop)"
docker rm -f "$CONTAINER_ONE" >/dev/null

echo "==> Lifecycle 2: starting ${CONTAINER_TWO} on the same volume"
start_container "$CONTAINER_TWO"

AFTER_CASH="$(read_cash)"
AFTER_POSITIONS="$(read_positions)"
AFTER_WATCHLIST="$(read_watchlist)"
AFTER_CHAT="$(read_chat_count)"

echo "==> Comparing"
FAILED=0

if [ "$BEFORE_CASH" = "$AFTER_CASH" ]; then
  echo "    PASS cash            ${AFTER_CASH}"
else
  echo "    FAIL cash            before=${BEFORE_CASH} after=${AFTER_CASH}" >&2
  FAILED=1
fi

if [ "$BEFORE_POSITIONS" = "$AFTER_POSITIONS" ]; then
  echo "    PASS positions       ${AFTER_POSITIONS}"
else
  echo "    FAIL positions       before=${BEFORE_POSITIONS} after=${AFTER_POSITIONS}" >&2
  FAILED=1
fi

if [ "$BEFORE_WATCHLIST" = "$AFTER_WATCHLIST" ]; then
  echo "    PASS watchlist       ${AFTER_WATCHLIST}"
else
  echo "    FAIL watchlist       before=${BEFORE_WATCHLIST} after=${AFTER_WATCHLIST}" >&2
  FAILED=1
fi

if [ "$BEFORE_CHAT" = "$AFTER_CHAT" ]; then
  echo "    PASS chat history    ${AFTER_CHAT} messages"
else
  echo "    FAIL chat history    before=${BEFORE_CHAT} after=${AFTER_CHAT}" >&2
  FAILED=1
fi

echo "==> Cleaning up"
docker rm -f "$CONTAINER_TWO" >/dev/null 2>&1 || true
docker volume rm "$VOLUME_NAME" >/dev/null 2>&1 || true

if [ "$FAILED" -ne 0 ]; then
  echo "DEPLOY-02 FAILED: state did not survive the container lifecycle" >&2
  exit 1
fi

echo "DEPLOY-02 verified: cash, positions, watchlist, and chat history all survived"
