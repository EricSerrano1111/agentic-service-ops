"""Score a filled-in bake-off blind review against its key.

Joins review_blind.csv to review_key.csv on review_id, validates every reviewer field, and
writes review_scored.json. Stops with a list of problems rather than guessing.

Usage:
    python data/generator/experiments/score_review.py data/generator/experiments/bakeoff/<date>
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

SENTIMENTS = {"positive", "neutral", "negative", "mixed"}
STYLES = ["plain", "sarcastic", "implicit"]


def load(run: Path) -> list[dict]:
    with (run / "review_blind.csv").open(encoding="utf-8-sig", newline="") as f:
        blind = {r["review_id"].strip(): r for r in csv.DictReader(f)}
    with (run / "review_key.csv").open(encoding="utf-8-sig", newline="") as f:
        key = {r["review_id"].strip(): r for r in csv.DictReader(f)}

    problems = []
    if len(blind) != 40 or len(key) != 40:
        problems.append(f"expected 40 rows each; blind={len(blind)} key={len(key)}")
    for rid in sorted(blind.keys() ^ key.keys()):
        problems.append(f"{rid}: present in only one file")

    rows = []
    for rid in sorted(blind.keys() & key.keys()):
        b, k = blind[rid], key[rid]
        mine = b["my_sentiment"].strip().lower()
        bel = b["believable_1to3"].strip()
        ai = b["sounds_ai_yn"].strip().lower()
        if mine not in SENTIMENTS:
            problems.append(f"{rid}: my_sentiment={b['my_sentiment']!r}")
        if bel not in {"1", "2", "3"}:
            problems.append(f"{rid}: believable_1to3={b['believable_1to3']!r}")
        if ai not in {"y", "n"}:
            problems.append(f"{rid}: sounds_ai_yn={b['sounds_ai_yn']!r}")
        rows.append(
            {
                "review_id": rid,
                "model": k["model"],
                "spec_id": int(k["spec_id"]),
                "style": k["style"],
                "intended": k["intended_sentiment"],
                "incident": bool(k["incident_type"]),
                "mine": mine,
                "believable": int(bel) if bel.isdigit() else None,
                "sounds_ai": ai == "y",
                "text": b["text"],
                "notes": b["notes"],
            }
        )
    if problems:
        sys.exit("Validation failed:\n  " + "\n  ".join(problems))
    return rows


def agree(rows: list[dict]) -> dict:
    n = len(rows)
    a = sum(r["mine"] == r["intended"] for r in rows)
    return {"agree": a, "n": n, "rate": round(a / n, 3) if n else None}


def score(rows: list[dict]) -> dict:
    out = {}
    for model in sorted({r["model"] for r in rows}):
        rs = [r for r in rows if r["model"] == model]
        out[model] = {
            "agreement_overall": agree(rs),
            "agreement_by_style": {s: agree([r for r in rs if r["style"] == s]) for s in STYLES},
            "agreement_by_incident": {
                "incident": agree([r for r in rs if r["incident"]]),
                "no_incident": agree([r for r in rs if not r["incident"]]),
            },
            "mean_believable_1to3": round(sum(r["believable"] for r in rs) / len(rs), 2),
            "sounds_ai_y": {
                "y": sum(r["sounds_ai"] for r in rs),
                "n": len(rs),
                "rate": round(sum(r["sounds_ai"] for r in rs) / len(rs), 3),
            },
        }
    disagreements = [
        {k: r[k] for k in ("review_id", "model", "spec_id", "style", "intended", "mine", "text")}
        for r in sorted(rows, key=lambda r: (r["model"], r["style"], r["review_id"]))
        if r["mine"] != r["intended"]
    ]
    return {"per_model": out, "disagreements": disagreements, "rows": rows}


def fmt(a: dict) -> str:
    return f"{a['agree']}/{a['n']}"


def main() -> None:
    run = Path(sys.argv[1])
    result = score(load(run))
    (run / "review_scored.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    models = list(result["per_model"])
    lines = [
        ("overall", lambda m: fmt(m["agreement_overall"])),
        *[(s, lambda m, s=s: fmt(m["agreement_by_style"][s])) for s in STYLES],
        ("incident", lambda m: fmt(m["agreement_by_incident"]["incident"])),
        ("no incident", lambda m: fmt(m["agreement_by_incident"]["no_incident"])),
        ("mean believable", lambda m: f"{m['mean_believable_1to3']:.2f}"),
        ("sounds AI = y", lambda m: f"{m['sounds_ai_y']['y']}/{m['sounds_ai_y']['n']}"),
    ]
    w = max(len(m) for m in models) + 2
    print(f"{'':18}" + "".join(f"{m:>{w}}" for m in models))
    for label, f in lines:
        print(f"{label:18}" + "".join(f"{f(result['per_model'][m]):>{w}}" for m in models))
    print(f"\nDisagreements ({len(result['disagreements'])}):")
    for d in result["disagreements"]:
        print(f"- {d['model']} | {d['style']} | intended {d['intended']} | mine {d['mine']}")
        print(f"    {d['text']}")


if __name__ == "__main__":
    main()
