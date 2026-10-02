# Build from the repo root:  docker build -f services/mcp_feedback/Dockerfile .
#
# Mirrors mcp_incidents: two stages, and the build stage resolves nothing. It installs
# exactly what uv.lock pins (--locked fails if the lock is stale), CPU-only torch from
# the PyTorch CPU index included (ADR-065, ADR-047). The final stage copies only the
# virtualenv and the committed artifact manifest.
#
# Model weights are NOT baked in locally: compose mounts models/ read-only at /models
# (ADR-062). The manifest is baked in, because its SHA-256 is the stored predictions'
# model_version (ADR-067), and start-up verifies the mounted files against it.

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
RUN uv sync --locked --no-dev --no-editable --package mcp-feedback

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1
COPY --from=build /app/.venv /app/.venv
COPY ml/sentiment/artifacts/bert_v1.manifest.json /app/artifacts/bert_v1.manifest.json

RUN useradd --system --uid 10001 app
USER app

EXPOSE 8102
CMD ["python", "-m", "mcp_feedback"]
