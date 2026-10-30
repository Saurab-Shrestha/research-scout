# Build the React app, then one Python image runs the API (which also serves the app) and the worker.
FROM node:24.4.0-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web ./
RUN npm run build

FROM python:3.12.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.10.8 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH=/app/.venv/bin:$PATH PYTHONPATH=/app/backend
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY alembic.ini ./
COPY backend ./backend
COPY --from=web /web/dist ./web/dist
RUN useradd --create-home scout
USER scout
