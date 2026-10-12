# Build from the repo root:  docker build -f services/mcp_volume/Dockerfile .
#
# Mirrors mcp_feedback: two stages, and the build stage installs exactly what uv.lock pins
# (--locked fails if the lock is stale; ADR-047). The final stage copies only the virtualenv
# and the committed artifact manifest. No training code: forecasts come from the
# forecast-runtime package (ADR-062, ADR-072).
#
# The manifest and the six volume_v2 parameter files are baked in (ADR-098); start-up verifies
# the files against the manifest and the server refuses to start on a mismatch (ADR-072).

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
RUN uv sync --locked --no-dev --no-editable --package mcp-volume

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
COPY --from=build /app/.venv /app/.venv
COPY ml/forecast/artifacts/volume_v2.manifest.json /app/artifacts/volume_v2.manifest.json
COPY models/forecast/volume_v2/ /models/forecast/volume_v2/

RUN useradd --system --uid 10001 app
USER app

EXPOSE 8103
CMD ["python", "-m", "mcp_volume"]
