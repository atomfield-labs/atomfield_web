# The web app: built here, served by the API at its own address.
FROM node:24-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# curl for health checks, PostgreSQL client for pg_dump backups before
# migrations
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl postgresql-client && \
    rm -rf /var/lib/apt/lists/*

# Install uv binary
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install project dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --no-install-project --python 3.11

# Copy application source
COPY . .
COPY --from=web /web/dist ./frontend/dist
