#!/usr/bin/env bash
# Build the production image, stand up an isolated app + Playwright pair, run the
# E2E suite, and tear everything down. Idempotent; safe to re-run.
set -euo pipefail

cd "$(dirname "$0")"

COMPOSE=(docker compose -f docker-compose.test.yml)

cleanup() {
  "${COMPOSE[@]}" down --remove-orphans --volumes >/dev/null 2>&1 || true
}
trap cleanup EXIT

cleanup
mkdir -p artifacts

set +e
"${COMPOSE[@]}" up --build --abort-on-container-exit --exit-code-from playwright "$@"
status=$?
set -e

if [ "$status" -ne 0 ]; then
  echo
  echo "E2E suite failed. App logs:"
  "${COMPOSE[@]}" logs --no-color app | tail -60
fi

echo
echo "HTML report: test/artifacts/report/index.html"
exit "$status"
