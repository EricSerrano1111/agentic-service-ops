# Agentic Service Operations Intelligence Platform

Northwestern capstone. A multi-agent system over a synthetic field-service dispatch
database: an orchestrator routes natural-language intent via A2A to reporting,
sentiment, and forecast agents, each calling scoped tools through its own MCP server,
with a QA agent verifying output before it returns.

Design documents live in [docs/](docs/) — start with
[architecture.md](docs/architecture.md). Schema detail is in
[data-dictionary.md](docs/data-dictionary.md); the reasoning behind every locked
decision is in [decisions-log.md](docs/decisions-log.md).

## Status

Sprint 1, in progress. The database layer exists; the synthetic data generator is next.

## Local setup

Requires Python 3.12+ and (for the database) Docker Desktop.

```
py -m venv .venv
.venv\Scripts\pip install -e "packages/db_models[dev]"

copy .env.example .env      # then fill in POSTGRES_* and DB_ROLE_*_PASSWORD
```

`.env` is gitignored and holds every credential. Nothing is hardcoded: Alembic builds
its connection string from `POSTGRES_ADMIN_USER` / `POSTGRES_ADMIN_PASSWORD` /
`POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_DB`, and the role passwords come from
`DB_ROLE_*_PASSWORD`. In deployment the same variables come from GCP Secret Manager.

```
docker compose up -d postgres
.venv\Scripts\python -m alembic upgrade head
```

That applies two migrations: the schema, then the five least-privilege agent roles
with the grants from [data-dictionary.md §7](docs/data-dictionary.md).

Postgres stays local through Sprint 4; Cloud SQL is provisioned only from Sprint 5
(ADR-007), so the same migrations run against both.

## Verifying the database layer

```
.venv\Scripts\python -m pytest tests/unit -q   # no database needed
.venv\Scripts\python -m pytest tests/integration -q   # live grants; skips if no database
.venv\Scripts\python -m alembic check          # "No new upgrade operations detected."
```

`alembic check` matters more than usual here: the initial migration was written by
hand (no database was reachable at the time), so it is the authoritative proof that
the migration and `packages/db_models/` agree. If it reports pending operations, the
migration is wrong, not the models.

### Confirming the security boundary

The least-privilege claim is worth demonstrating rather than asserting. Connect as
each role and check that the walls are where the access matrix says they are:

```sql
-- as app_sentiment: its entire world is four columns of one table
SELECT feedback_text FROM service_feedback LIMIT 1;   -- succeeds
SELECT rating FROM service_feedback LIMIT 1;          -- ERROR: permission denied (R-04)
SELECT * FROM incidents LIMIT 1;                      -- ERROR: permission denied
SELECT * FROM sentiment_labels LIMIT 1;               -- ERROR: permission denied

-- as app_reporting: can aggregate ratings, cannot read the customer's words
SELECT avg(rating) FROM service_feedback;             -- succeeds
SELECT feedback_text FROM service_feedback LIMIT 1;   -- ERROR: permission denied

-- as any agent role: customer PII is unreachable
SELECT * FROM contacts LIMIT 1;                       -- ERROR: permission denied
```

Those failures are the point of the design: the sentiment agent cannot verify itself
against its own ground truth, cannot see the rating QA checks it against, staff-written
incident notes cannot reach the sentiment pipeline, and customer PII never enters an
LLM context window. Each is enforced by a database grant rather than a code convention
— see ADR-023, ADR-025 and ADR-027.

`tests/integration/test_access_matrix_grants.py` automates this: it logs in as every
role and probes every table for reads and for INSERT/UPDATE/DELETE, plus every column
of `service_feedback`, with the expected outcome computed from `db_models.access_matrix`.

## Repository layout

See [architecture.md §11](docs/architecture.md). Implemented so far:

```
packages/db_models/     SQLAlchemy models, controlled vocabularies, §7 access matrix
data/migrations/        Alembic — identical local and Cloud SQL
tests/unit/             schema and access-matrix contract tests
docker-compose.yml      local Postgres 16
```
