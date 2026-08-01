#!/usr/bin/env bash
# Build (if needed) and run the FinAlly container. Safe to re-run.
set -euo pipefail

IMAGE="finally"
CONTAINER="finally"
PORT="8000"
URL="http://localhost:${PORT}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FORCE_BUILD=false
OPEN_BROWSER=true
for arg in "$@"; do
  case "$arg" in
    --build) FORCE_BUILD=true ;;
    --no-browser) OPEN_BROWSER=false ;;
    -h|--help)
      echo "Usage: $0 [--build] [--no-browser]"
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running. Start Docker Desktop and try again." >&2
  exit 1
fi

if [ ! -f .env ]; then
  echo "No .env found — creating one from .env.example."
  cp .env.example .env
  echo "Add your OPENROUTER_API_KEY to .env to enable the AI chat."
fi

mkdir -p db

if [ "$FORCE_BUILD" = true ] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "Building image '$IMAGE'..."
  docker build -t "$IMAGE" .
fi

if [ -n "$(docker ps -q -f "name=^${CONTAINER}$")" ]; then
  echo "Container '$CONTAINER' is already running."
  if [ "$FORCE_BUILD" = true ]; then
    echo "Recreating it with the freshly built image..."
    docker rm -f "$CONTAINER" >/dev/null
  fi
fi

if [ -z "$(docker ps -q -f "name=^${CONTAINER}$")" ]; then
  # Remove any stopped container holding the name
  if [ -n "$(docker ps -aq -f "name=^${CONTAINER}$")" ]; then
    docker rm -f "$CONTAINER" >/dev/null
  fi
  docker run -d \
    --name "$CONTAINER" \
    -p "${PORT}:8000" \
    --env-file .env \
    -v "${ROOT}/db:/app/db" \
    "$IMAGE" >/dev/null
fi

echo -n "Waiting for FinAlly to come up"
for _ in $(seq 1 60); do
  if curl -fsS "${URL}/api/health" >/dev/null 2>&1; then
    echo " — ready."
    break
  fi
  echo -n "."
  sleep 1
done
echo ""

if ! curl -fsS "${URL}/api/health" >/dev/null 2>&1; then
  echo "FinAlly did not become healthy. Recent logs:" >&2
  docker logs --tail 50 "$CONTAINER" >&2
  exit 1
fi

echo "FinAlly is running at ${URL}"
echo "Stop it with: scripts/stop_mac.sh"

if [ "$OPEN_BROWSER" = true ] && command -v open >/dev/null 2>&1; then
  open "$URL"
fi
