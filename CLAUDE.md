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
- Course deliverables and due dates → `docs/academic/` (numbered files; calendar in
  `docs/architecture.md` §10)

## `docs/academic/` rules

- `00-Weekly-Status-Reports.md` is never edited by Claude, in any task. It is a rolling
  weekly assignment Eric maintains himself.
- `03` to `06` are authored by Eric in separate Claude Project chats. Don't edit them
  unless explicitly asked; report what they will need to reflect instead.
- `01` and `02` are submitted assignments kept as reference copies. Keep them factually in
  sync with later decisions (ADRs) without changing their argument, structure or voice, and
  never touch the Due Date lines or reviewer table. Add a revision-history row for each
  update; the submitted v1.0 stays in git history.

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
.venv\Scripts\pip install -e ".[generator]" -e "packages/db_models[dev]"   # same as CI

.venv\Scripts\python -m pytest tests/unit -q      # offline: schema, access matrix, generator, corpus
.venv\Scripts\python -m pytest tests/integration -q -rs   # live grants suite; needs migrated Postgres
.venv\Scripts\python -m ruff check packages data tests
.venv\Scripts\python -m ruff format packages data tests   # ruff pinned (0.16.8) so local = CI

docker compose up -d postgres                     # needs Docker Desktop running
.venv\Scripts\python -m alembic upgrade head      # schema, then roles + grants
.venv\Scripts\python -m alembic check             # asserts migrations still match the models
.venv\Scripts\python -m alembic revision --autogenerate -m "..."
```

The integration suite skips when no database is configured or reachable. Set
`REQUIRE_INTEGRATION_DB=1` to turn every skip into a failure; CI always sets it.

**CI** (`.github/workflows/ci.yml`, GitHub Actions, every push and PRs to main): lint
(ruff check + format --check), unit (offline suite), and integration (Postgres 16 service
container, `alembic upgrade head`, `alembic check`, then the grants suite). CI uses its own
ephemeral role credentials and never `.env`; nothing in CI calls a model.

**Generator pipeline** (`data/generator/`, order matters):

```
.venv\Scripts\python data/generator/build_corpus.py --status     # no API calls
.venv\Scripts\python data/generator/build_corpus.py --run        # regenerates the corpus: deliberate act only (ADR-030)
.venv\Scripts\python data/generator/load.py --corpus data/generator/corpus/feedback_text.jsonl   # runs generate.py, loads as app_generator
.venv\Scripts\python data/generator/load.py --corpus <path> --dry-run   # generate + row counts, no DB
.venv\Scripts\python data/generator/validate.py                  # writes data/generator/validation/<date>/
```

1. `build_corpus.py` writes the frozen corpus (`corpus/feedback_text.jsonl` +
   `provenance.json`). The corpus is complete and committed; don't rerun it as part of
   normal work. It uses the free key (`GOOGLE_AI_API_KEY`) by default; `--paid` opts in to
   the separate spend-capped paid project (`GOOGLE_AI_API_KEY_PAID`) for Flash-Lite, capped
   per session by `--paid-max-requests` (ADR-041). The Gemma judge always uses the free key.
2. `generate.py` is pure (no DB, no network, no clock) and is not run on its own: `load.py`
   calls it and reloads every generated table in one transaction as `app_generator`
   (ADR-042).
3. `validate.py` checks the loaded database against `generation_parameters`, reading as
   `app_forecast` and `app_qa`. Rerun it after any regeneration (R-07).

`alembic check` is the real guard on `packages/db_models/` — the initial migration was
hand-written, so a model change that isn't migrated only shows up there. Run it after
touching any model.

## Decisions log format (permanent)

`docs/decisions-log.md` is a single running file, not a `docs/decisions/`
folder of per-ADR files. Append new entries to the end of that one file
using the existing ADR-XXX numbering and format. Never create files under
a `docs/decisions/` path.