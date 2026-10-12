# Build from the repo root:
#   docker build -f services/mcp_feedback/Dockerfile .                    # `full` (the default)
#   docker build -f services/mcp_feedback/Dockerfile --target stored .    # what Cloud Run runs
#
# Two final targets (ADR-100). Both resolve from uv.lock only (--locked fails if the lock is
# stale), CPU-only torch from the PyTorch CPU index included (ADR-065, ADR-047).
#
# - `stored`: no torch, no transformers, no weights. Scoring mode `stored_only`: it answers
#   from stored predictions and fails closed on a gap. Cloud Build builds this target.
# - `full`: the `model` extra (torch and the rest). Scoring mode `lazy`. Model weights are
#   NOT baked in locally: compose mounts models/ read-only at /models (ADR-062), and start-up
#   verifies the mounted files against the manifest. It is the LAST stage, so it is what a
#   plain `docker build` produces and what compose builds.
#
# `stored` and its build stage come first on purpose: a builder that does not skip unused
# stages stops at `--target stored` before reaching the torch stage.
# The manifest is baked into both, because its SHA-256 is the stored predictions'
# model_version (ADR-067).

# ---- stored -------------------------------------------------------------------------------
FROM python:3.12-slim AS build-stored
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

FROM python:3.12-slim AS stored
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    MCP_FEEDBACK_SCORING=stored_only
COPY --from=build-stored /app/.venv /app/.venv
COPY ml/sentiment/artifacts/bert_v1.manifest.json /app/artifacts/bert_v1.manifest.json

RUN useradd --system --uid 10001 app
USER app

EXPOSE 8102
CMD ["python", "-m", "mcp_feedback"]

# ---- full (default) -----------------------------------------------------------------------
FROM python:3.12-slim AS build-full
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages packages
COPY services services
RUN uv sync --locked --no-dev --no-editable --package mcp-feedback --extra model

FROM python:3.12-slim AS full
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1
COPY --from=build-full /app/.venv /app/.venv
COPY ml/sentiment/artifacts/bert_v1.manifest.json /app/artifacts/bert_v1.manifest.json

RUN useradd --system --uid 10001 app
USER app

EXPOSE 8102
CMD ["python", "-m", "mcp_feedback"]
