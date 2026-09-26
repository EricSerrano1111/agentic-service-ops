# Build from the repo root:  docker build -f services/agent_reporting/Dockerfile .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# No db_models and no database driver: this agent reaches data only through MCP.
COPY packages/common packages/common
COPY packages/schemas packages/schemas
COPY services/agent_reporting services/agent_reporting
RUN pip install ./packages/common ./packages/schemas ./services/agent_reporting

RUN useradd --system --uid 10001 app
USER app

EXPOSE 8001
CMD ["python", "-m", "agent_reporting"]
