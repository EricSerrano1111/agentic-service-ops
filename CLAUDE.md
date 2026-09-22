# Agentic Service Operations Intelligence Platform

Northwestern capstone. Multi-agent system over a synthetic field-service
dispatch database — orchestrator routes intents via A2A to reporting,
sentiment, and forecast agents, each calling scoped tools through its own
MCP server, with a QA agent verifying output before it returns. Solo,
Agile (six 2-week sprints), Python, deployed on GCP. Target is
production-grade.

## Which doc to check

Read the relevant file before making a change — don't infer schema,
architecture, or past reasoning from the code alone if a doc covers it.

- Schema, enums, constraints, metrics, access matrix → `docs/data-dictionary.md`
- Architecture, protocols, security model, stack, budget, sprint plan → `docs/architecture.md`
- Why something was chosen, what was rejected → `docs/decisions-log.md`
- Sprint status, retros → `docs/sprint-log.md`
- Known risks, mitigations → `docs/risk-register.md`

## Keeping docs in sync with the code

When you make a change that contradicts a locked decision, stop and say so
before proceeding — name the ADR. If a decision genuinely needs to change,
append a new entry to `docs/decisions-log.md` marked "Supersedes ADR-XXX."
Never edit a past entry in place.

If you complete or materially change something covered in `docs/sprint-log.md`
for the current sprint, update it directly rather than waiting to be asked.

## How to work

- Frank and direct. Flag weak reasoning, scope creep, and hand-waving —
  I'm the only reviewer this project has, so don't soften that.
- I'm an intermediate ML practitioner. Plain-English explanations of
  unfamiliar concepts help; skip the basics on Python, SQL, general ML.
- Prefer Plan Mode for anything touching schema, security scoping, or
  more than one service — I want to review before you execute, not after.
- Generator and corpus scripts (`data/generator/`) print progress and
  summaries only, never generated rows — keeps tool output small (ADR-030).
- Commit messages must not include a `Co-Authored-By` trailer or any
  other AI attribution. Same for pull request descriptions.
- Distinguish what's genuinely required at this scale from what's
  demonstrated deliberately for portfolio value, and say which is which.

## Commands

Windows paths shown; on POSIX substitute `.venv/bin/`.

```
py -m venv .venv                                  # first time only
.venv\Scripts\pip install -e "packages/db_models[dev]"

.venv\Scripts\python -m pytest tests/unit -q      # schema + access-matrix contract tests
.venv\Scripts\python -m ruff check packages data tests
.venv\Scripts\python -m ruff format packages data tests

docker compose up -d postgres                     # needs Docker Desktop running
.venv\Scripts\python -m alembic upgrade head      # schema, then roles + grants
.venv\Scripts\python -m alembic check             # asserts migrations still match the models
.venv\Scripts\python -m alembic revision --autogenerate -m "..."
```

`alembic check` is the real guard on `packages/db_models/` — the initial migration was
hand-written, so a model change that isn't migrated only shows up there. Run it after
touching any model.

## Decisions log format (permanent)

`docs/decisions-log.md` is a single running file, not a `docs/decisions/`
folder of per-ADR files. Append new entries to the end of that one file
using the existing ADR-XXX numbering and format. Never create files under
a `docs/decisions/` path.