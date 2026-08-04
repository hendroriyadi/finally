#!/usr/bin/env bash
#
# Stop FinAlly. Safe to run repeatedly — exits 0 whether or not anything was
# running, and never touches the data volume.

set -euo pipefail

CONTAINER_NAME="${FINALLY_CONTAINER:-finally}"
VOLUME_NAME="${FINALLY_VOLUME:-finally-data}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed. Install Docker Desktop: https://docs.docker.com/get-docker/" >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "Docker is installed but the daemon isn't running. Open Docker Desktop and try again." >&2
  exit 1
fi

# -a so a stopped-but-present container is still cleaned up. Anchored filter,
# same reason as the start script.
if [ -n "$(docker ps -aq --filter "name=^${CONTAINER_NAME}$")" ]; then
  docker rm -f "$CONTAINER_NAME" >/dev/null
  echo "FinAlly stopped and removed."
else
  echo "FinAlly is not running."
fi

echo "Your data volume ($VOLUME_NAME) was left in place — cash, positions, and history are safe."
