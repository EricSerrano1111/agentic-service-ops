# Build from the repo root:  docker build -f services/api_gateway/Dockerfile .
#
# Three stages. `ui` builds the Next.js static export (ADR-080): it fails if the installed
# `next` is below the patched minimum (scripts/check-next-version.mjs) or `npm audit` reports a
# high or critical finding in a runtime dependency. `build` installs exactly what uv.lock pins
# (ADR-047). The final image holds the virtualenv and the export, with the export's inline
# script hashes written next to it (ADR-097); there is no Node runtime in it.
# No db-models, no database driver, no model SDK: the gateway holds only its own session key
# and the invite store (ADR-079's least privilege).

FROM node:24-slim AS ui
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build && npm audit --omit=dev --audit-level=high

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages packages
COPY services services
RUN uv sync --locked --no-dev --no-editable --package api-gateway
COPY --from=ui /web/out /app/static
RUN /app/.venv/bin/python -m api_gateway.csp /app/static

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    GATEWAY_STATIC_DIR=/app/static
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/static /app/static

RUN useradd --system --uid 10001 app
USER app

EXPOSE 8080
CMD ["python", "-m", "api_gateway", "serve"]
