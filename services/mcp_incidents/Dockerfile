# Build from the repo root:  docker build -f services/mcp_incidents/Dockerfile .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Only what this service imports. Siblings install in the same pip command so the
# unpinned local names (db-models, service-ops-*) resolve to these paths, not PyPI.
COPY packages/common packages/common
COPY packages/schemas packages/schemas
COPY packages/db_models packages/db_models
COPY services/mcp_incidents services/mcp_incidents
RUN pip install ./packages/common ./packages/schemas ./packages/db_models ./services/mcp_incidents

RUN useradd --system --uid 10001 app
USER app

EXPOSE 8101
CMD ["python", "-m", "mcp_incidents"]
