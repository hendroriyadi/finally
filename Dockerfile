# Stage 1 — build the Next.js static export
FROM node:20-slim AS frontend-builder

WORKDIR /build

COPY frontend/package.json frontend/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY frontend/ ./
RUN npm run build


# Stage 2 — FastAPI runtime serving the API and the static frontend
FROM python:3.12-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/

# Application lives in /app/backend so that the data volume can mount at /app/db
# without shadowing the backend's `db` Python package.
WORKDIR /app/backend

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/backend/.venv \
    PATH="/app/backend/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    FINALLY_DB_PATH=/app/db/finally.db \
    FINALLY_STATIC_DIR=/app/backend/static

# Dependencies first so application edits don't invalidate the layer
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY backend/ ./
RUN uv sync --locked --no-dev

COPY --from=frontend-builder /build/out ./static

# Runtime volume mount point for the SQLite database
RUN mkdir -p /app/db

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health').read()"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
