# Build from the repo root:  docker build -f services/orchestrator/Dockerfile .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# No db_models, no database driver, no MCP SDK: the orchestrator talks only to agents.
COPY packages/common packages/common
COPY packages/schemas packages/schemas
COPY services/orchestrator services/orchestrator
RUN pip install ./packages/common ./packages/schemas ./services/orchestrator

RUN useradd --system --uid 10001 app
USER app

EXPOSE 8000
CMD ["python", "-m", "orchestrator", "serve"]
