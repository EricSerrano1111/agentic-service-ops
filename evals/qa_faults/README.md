# QA fault injection and catch rate (Sprint 4, phase 5; ADR-091)

Measures how much of a catalogue of injected faults QA's checks catch. Local only, no model
calls: QA's interpretation check is advisory (L-74), so the harness runs QA with a fake
interpretation client that always says `faithful`.

| File | What it is |
|---|---|
| `catalogue_v1.yaml` | the faults, their mutations, expected outcomes and expected checks, the owner's anchors and the rating rule's pre-registered table. Frozen before the first run. |
| `faults.py` | the mutations (one function per fault) and `rating_rule_fails`. |
| `generate.py` | seed `20261010`, at most 10 cases per fault, the order base answers are tried in. |
| `world.py` | the specialists and tool servers in process, QA's real checks, the rolled-back transaction. |
| `base.py` | builds the clean base answers from the three parse sets and the owner's anchors, no parse call. |
| `run.py` | controls, then every fault's cases through QA's verification code. |
| `report.py`, `report_format.md` | the tables, fixed in advance. |

```
.venv\Scripts\python evals/qa_faults/base.py --out evals/results/qa_faults/<date>
.venv\Scripts\python evals/qa_faults/run.py  --out evals/results/qa_faults/<date> --no-qa   # mutations only, no verdicts
.venv\Scripts\python evals/qa_faults/run.py  --out evals/results/qa_faults/<date>           # the measurement
.venv\Scripts\python evals/qa_faults/report.py --out evals/results/qa_faults/<date>
```

Needs the compose Postgres up, migrated and loaded, with the sentiment predictions backfilled
and the `volume_v2` artifact present locally. Not part of CI. A miss is a finding, reported as
measured; a fix is a separate PR that re-runs this same catalogue and seed.
