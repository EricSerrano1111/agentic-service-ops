# Build from the repo root:  docker build -f services/mcp_incidents/Dockerfile .
#
# Two stages. The build stage resolves nothing: it installs exactly what uv.lock pins
# (--locked fails if the lock is stale), so CI, local and this image get identical
# versions (ADR-047).
# Installs only this service and its locked dependencies, db-models included.
# The final stage copies only the resulting virtualenv, not the workspace sources.

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# uv needs every workspace member's pyproject.toml to read the lock.
COPY pyproject.toml uv.lock ./
COPY packages packages
COPY services services
RUN uv sync --locked --no-dev --no-editable --package mcp-incidents

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
COPY --from=build /app/.venv /app/.venv

RUN useradd --system --uid 10001 app
USER app

EXPOSE 8101
CMD ["python", "-m", "mcp_incidents"]
