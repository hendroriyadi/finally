#!/usr/bin/env bash
# Stop and remove the FinAlly container. Database files in db/ are left untouched.
set -euo pipefail

CONTAINER="finally"

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running — nothing to stop."
  exit 0
fi

if [ -z "$(docker ps -aq -f "name=^${CONTAINER}$")" ]; then
  echo "Container '$CONTAINER' is not running."
  exit 0
fi

docker rm -f "$CONTAINER" >/dev/null
echo "Stopped and removed container '$CONTAINER'. Your data in db/ is preserved."
