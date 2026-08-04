# FinAlly — one image, one process, one port.
#
# Stage 1 builds the Next.js static export; stage 2 installs the Python
# backend and copies that export in, so a single uvicorn process serves both
# the API and the frontend on port 8000 (DEPLOY-01).

# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1 — frontend static export
# ---------------------------------------------------------------------------
# node:24 rather than PLAN.md's indicative "Node 20": 24 is Active LTS, is this
# project's own local dev version, and clears Next.js 16's >=20.9 floor.
FROM node:24-slim AS frontend-builder

WORKDIR /app/frontend

# Manifest pair first, source second: this is what makes the dependency
# install a cached layer that an ordinary source edit does not invalidate.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# next.config.ts already sets output: 'export', so this writes ./out.
# NEXT_PUBLIC_API_URL is deliberately never set anywhere in this file — its
# empty default is exactly what makes the frontend talk to its own origin.
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 — Python runtime serving API + static
# ---------------------------------------------------------------------------
# `-trixie`, NOT `-bookworm`: Astral moved the combined uv+Python images to
# Debian 13. The bookworm tag family is a stale-training-data trap.
FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim AS runtime

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

# Astral's documented two-sync split. Not cosmetic: syncing dependencies
# before the project source is copied means a source edit reuses the
# dependency layer instead of reinstalling everything.
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY backend/ ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# This destination and app/main.py's STATIC_DIR are a matched pair. Change
# either alone and the container starts fine, logs "API-only", and serves the
# frontend nowhere.
COPY --from=frontend-builder /app/frontend/out ./static

ENV PATH="/app/.venv/bin:$PATH" \
    FINALLY_DB_PATH=/app/db/finally.db

# Set explicitly rather than trusting get_db_path()'s default: that default is
# computed from this REPO's directory depth (parents[3]), and the image's
# layout is a different shape — so the default would resolve somewhere in the
# container's ephemeral filesystem and lose every write on restart, silently.

# Unprivileged runtime user (T-05-04). The mkdir before the chown is
# load-bearing: a named volume inherits its initial ownership from the image's
# directory at the mount point, so if /app/db does not exist in the image the
# fresh volume arrives owned by root and this process cannot create the
# SQLite file or its WAL sidecars.
RUN groupadd --system appuser \
    && useradd --system --gid appuser --home-dir /app appuser \
    && mkdir -p /app/db \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Python rather than curl so the image does not carry a package added purely
# to have a healthcheck.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
