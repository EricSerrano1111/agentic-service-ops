"""Post-process for starts.json. It does not change evals/l106/extract_starts.py.

    python -I evals/results/l106/2026-11-10/fill_round.py LOGS.json STARTS.json ROUND QMAP.json

1. first_line for the single-container services, whose stdout entries carry no
   labels.container_name (the extractor leaves the field empty for them).
2. question and trace fields, from QMAP.json (start time to question and trace).

Reads only the three files it is given and imports the committed extractor. Holds no
credential and prints no log text beyond short fields.
"""

import json
import sys

sys.path.insert(0, "evals/l106")
import extract_starts as x  # noqa: E402

SOLE = {"ops-gateway": "gateway", "ops-orchestrator": "orchestrator", "ops-qa": "agent-qa"}


def fill_first_line(row: dict, entries: list[dict]) -> None:
    container = SOLE.get(row["service"])
    if container is None:
        return
    slot = row["containers"].setdefault(container, {})
    if "first_line" in slot:
        return
    t0 = x.ts(row["start_ts"])
    for e in entries:
        same_instance = (
            e["resource"]["labels"]["service_name"] == row["service"]
            and e.get("labels", {}).get("instanceId") == row["instanceId"]
        )
        if e["_stream"] in ("stdout", "stderr") and same_instance:
            slot["first_line"] = {
                "stream": e["_stream"],
                "secs_after_start": round((e["_t"] - t0).total_seconds(), 3),
                "text": x.text_of(e)[:160],
                "filled_by": "fill_round.py (no container_name label)",
            }
            return


def main(argv: list[str]) -> int:
    logs, starts, rnd, qmap = argv[1:5]
    entries = x.load(logs)
    with open(starts, encoding="utf-8") as f:
        rows = json.load(f)
    with open(qmap, encoding="utf-8") as f:
        questions = json.load(f)
    for row in rows:
        if row["round"] != rnd:
            continue
        fill_first_line(row, entries)
        found = questions.get(row["start_ts"][:23])
        if found:
            row["question"], row["trace"] = found["question"], found["trace"]
    with open(starts, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1)
    for row in rows:
        if row["round"] == rnd:
            first = {
                c: v.get("first_line", {}).get("secs_after_start")
                for c, v in row["containers"].items()
            }
            print(
                row["start_ts"][11:23], row["service"][4:], row["verdict"], first, row["question"]
            )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
