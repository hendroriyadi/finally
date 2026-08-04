#!/usr/bin/env bash
#
# Start FinAlly. Safe to run repeatedly — a second run does not rebuild, does
# not restart a healthy container, and does not error.
#
# Despite the name this works on Linux too; the pairing is PLAN.md's.

set -euo pipefail

IMAGE_TAG="${FINALLY_IMAGE:-finally:latest}"
CONTAINER_NAME="${FINALLY_CONTAINER:-finally}"
VOLUME_NAME="${FINALLY_VOLUME:-finally-data}"
HOST_PORT="${FINALLY_PORT:-8000}"

# Resolve from the script's own location, not the caller's cwd, so the
# relative `docker build .` and `--env-file .env` below mean the same thing
# no matter where this was invoked from.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

REBUILD=0
OPEN_BROWSER=0
for arg in "$@"; do
  case "$arg" in
    --build) REBUILD=1 ;;
    --open) OPEN_BROWSER=1 ;;
    *)
      echo "usage: $(basename "$0") [--build] [--open]" >&2
      exit 2
      ;;
  esac
done

# Two preconditions, reported differently because they have different fixes:
# "Docker isn't installed" and "Docker is installed but not running" send a
# user to completely different places.
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed. Install Docker Desktop: https://docs.docker.com/get-docker/" >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "Docker is installed but the daemon isn't running. Open Docker Desktop and try again." >&2
  exit 1
fi

# The most important branch in this file: `--env-file` exits with a hard
# Docker error when the file is absent, and `.env` is gitignored so no fresh
# clone has one. That first-run error is exactly what this phase exists to
# eliminate.
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example."
  echo "  Add your OPENROUTER_API_KEY to it to enable the AI copilot (everything else works without it)."
fi

if [ "$REBUILD" -eq 1 ] || ! docker image inspect "$IMAGE_TAG" >/dev/null 2>&1; then
  echo "Building $IMAGE_TAG ..."
  docker build -t "$IMAGE_TAG" .
fi

# Anchored filter: an unanchored `name=finally` would also match
# `finally-verify-1` and friends.
if [ -n "$(docker ps -q --filter "name=^${CONTAINER_NAME}$")" ]; then
  echo "FinAlly is already running."
else
  # Force-remove first so a previously exited or crashed container of the
  # same name doesn't turn the next run into a name-conflict error — which is
  # precisely the non-idempotent behavior this script must not have.
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  docker run -d \
    --name "$CONTAINER_NAME" \
    -p "${HOST_PORT}:8000" \
    -v "${VOLUME_NAME}:/app/db" \
    --env-file .env \
    "$IMAGE_TAG" >/dev/null
  echo "FinAlly started."
fi

URL="http://localhost:${HOST_PORT}"
echo "  $URL"

if [ "$OPEN_BROWSER" -eq 1 ]; then
  if command -v open >/dev/null 2>&1; then
    open "$URL" || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" || true
  fi
fi
