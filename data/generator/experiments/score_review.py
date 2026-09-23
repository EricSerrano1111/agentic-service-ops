"""Score a filled-in bake-off blind review against its key.

Joins review_blind.csv to review_key.csv on review_id, validates every reviewer field, and
writes review_scored.json. Stops with a list of problems rather than guessing.

A key with a judge_label column (prompt v1 runs onward) is scored three-way: human vs
intended vs the Gemma judge, with the neutral, implicit, and positive-vs-mixed breakdowns.
A key with a group column (prompt v2 runs onward) is scored per spec group instead: three-way
agreement by group and neutral kind, the human pass criteria, and ratings by channel/opening.
Older keys are scored per model exactly as before.

Usage:
    python data/generator/experiments/score_review.py data/generator/experiments/bakeoff/<date>
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

SENTIMENTS = {"positive", "neutral", "negative", "mixed"}
STYLES = ["plain", "sarcastic", "implicit"]


def load(run: Path) -> list[dict]:
    with (run / "review_blind.csv").open(encoding="utf-8-sig", newline="") as f:
        blind = {r["review_id"].strip(): r for r in csv.DictReader(f)}
    with (run / "review_key.csv").open(encoding="utf-8-sig", newline="") as f:
        key = {r["review_id"].strip(): r for r in csv.DictReader(f)}

    problems = []
    # The key defines the review size; the blind sheet must match it exactly.
    if not key:
        problems.append("review_key.csv has no rows")
    if len(blind) != len(key):
        problems.append(f"row counts differ; blind={len(blind)} key={len(key)}")
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
        if "judge_label" in k:  # v1+ keys; v0 rows stay exactly as before
            judge = k["judge_label"].strip().lower()
            if judge not in SENTIMENTS:
                problems.append(f"{rid}: judge_label={k['judge_label']!r} in key")
            rows[-1].update(
                judge=judge,
                incident_severity=k["incident_severity"] or None,
                incident_type=k["incident_type"] or None,
                channel=k["channel"],
                focus=k["focus"],
                opening=k["opening"],
            )
        if "group" in k:  # v2+ keys; v0/v1 rows stay exactly as before
            rows[-1].update(group=k["group"], neutral_kind=k["neutral_kind"] or None)
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


# --------------------------------------------------------------------------- v1: three-way

SENTIMENT_ORDER = ["positive", "neutral", "negative", "mixed"]
PAIRS = {  # name -> (label field a, label field b)
    "human_vs_intended": ("mine", "intended"),
    "judge_vs_intended": ("judge", "intended"),
    "human_vs_judge": ("mine", "judge"),
}
NEUTRAL_CELLS = [
    "generator (human=positive, judge=positive)",
    "judge (human=neutral, judge!=neutral)",
    "works (human=neutral, judge=neutral)",
    "definition not operational (anything else)",
]


def pair_agree(rows: list[dict], a: str, b: str) -> dict:
    n = len(rows)
    k = sum(r[a] == r[b] for r in rows)
    return {"agree": k, "n": n, "rate": round(k / n, 3) if n else None}


def splits(rows: list[dict], a: str, b: str) -> dict:
    return {
        "overall": pair_agree(rows, a, b),
        "by_intended": {
            s: pair_agree([r for r in rows if r["intended"] == s], a, b) for s in SENTIMENT_ORDER
        },
        "by_style": {s: pair_agree([r for r in rows if r["style"] == s], a, b) for s in STYLES},
        "by_incident": {
            "incident": pair_agree([r for r in rows if r["incident"]], a, b),
            "no_incident": pair_agree([r for r in rows if not r["incident"]], a, b),
        },
    }


def incident_str(r: dict) -> str:
    return f"{r['incident_severity']} {r['incident_type']}" if r["incident_type"] else "none"


def neutral_cell(r: dict) -> str:
    if r["mine"] == "positive" and r["judge"] == "positive":
        return NEUTRAL_CELLS[0]
    if r["mine"] == "neutral":
        return NEUTRAL_CELLS[2] if r["judge"] == "neutral" else NEUTRAL_CELLS[1]
    return NEUTRAL_CELLS[3]


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def score_three_way(run: Path, rows: list[dict]) -> dict:
    """v1 review: human vs intended vs judge, plus the neutral / implicit / positive dives."""
    specs = {s["id"]: s for s in read_jsonl(run / "specs.jsonl")}
    judge_all = {
        r["id"]: (r["label"] or "").lower() for r in read_jsonl(run / "judge_labels.jsonl")
    }
    (comments_file,) = run.glob("comments_*.jsonl")
    text_all = {r["id"]: r["text"] for r in read_jsonl(comments_file)}
    human_by_spec = {r["spec_id"]: r["mine"] for r in rows}

    agreement = {name: splits(rows, a, b) for name, (a, b) in PAIRS.items()}

    neutral_rows = [r for r in rows if r["intended"] == "neutral"]
    cells = {c: 0 for c in NEUTRAL_CELLS}
    neutral_list = []
    for r in sorted(neutral_rows, key=lambda r: r["review_id"]):
        cell = neutral_cell(r)
        cells[cell] += 1
        neutral_list.append(
            {
                "review_id": r["review_id"],
                "style": r["style"],
                "incident": incident_str(r),
                "focus": r["focus"],
                "human": r["mine"],
                "judge": r["judge"],
                "cell": cell,
                "text": r["text"],
            }
        )

    implicit_ids = [i for i, s in specs.items() if s["style"] == "implicit"]
    implicit = {}
    for se in SENTIMENT_ORDER:
        ids = [i for i in implicit_ids if specs[i]["sentiment"] == se]
        if not ids:
            continue
        hr = [r for r in rows if r["style"] == "implicit" and r["intended"] == se]
        implicit[se] = {
            "judge_all80": {
                "agree": sum(judge_all.get(i) == se for i in ids),
                "n": len(ids),
            },
            "human_reviewed": {"agree": sum(r["mine"] == se for r in hr), "n": len(hr)},
        }

    positive_ids = [i for i, s in specs.items() if s["sentiment"] == "positive"]
    pos_mixed = []
    for i in sorted(positive_ids):
        s, judge, human = specs[i], judge_all.get(i), human_by_spec.get(i)
        if judge == "mixed" or human == "mixed":
            pos_mixed.append(
                {
                    "spec_id": i,
                    "style": s["style"],
                    "focus": s["focus"],
                    "opening": s["opening"],
                    "incident": incident_str(s),
                    "channel": s["channel"],
                    "judge": judge,
                    "human": human or "not reviewed",
                    "text": text_all.get(i),
                }
            )
    focus_all = Counter(specs[i]["focus"] for i in positive_ids)
    focus_flagged = Counter(p["focus"] for p in pos_mixed)
    watched = ("billing", "scheduling")
    base = sum(focus_all[f] for f in watched)
    hit = sum(focus_flagged[f] for f in watched)
    overrep = {
        "billing_or_scheduling_in_flagged": {"count": hit, "n": len(pos_mixed)},
        "billing_or_scheduling_in_all_positive": {"count": base, "n": len(positive_ids)},
        "flagged_share": round(hit / len(pos_mixed), 3) if pos_mixed else None,
        "base_share": round(base / len(positive_ids), 3),
        "focus_flagged": dict(focus_flagged.most_common()),
        "focus_all_positive": dict(focus_all.most_common()),
    }

    bel = Counter(r["believable"] for r in rows)
    ratings = {
        "n": len(rows),
        "mean_believable_1to3": round(sum(r["believable"] for r in rows) / len(rows), 2),
        "believable_distribution": {str(k): bel.get(k, 0) for k in (1, 2, 3)},
        "sounds_ai_y": {
            "y": sum(r["sounds_ai"] for r in rows),
            "n": len(rows),
            "rate": round(sum(r["sounds_ai"] for r in rows) / len(rows), 3),
        },
    }
    return {
        "three_way_agreement": agreement,
        "neutral_diagnosis": {"cells": cells, "rows": neutral_list},
        "implicit_by_intended": implicit,
        "positive_labelled_mixed": {"rows": pos_mixed, "focus_overrepresentation": overrep},
        "ratings": ratings,
        "rows": rows,
    }


def print_three_way(res: dict) -> None:
    ag = res["three_way_agreement"]
    names = list(PAIRS)
    print(f"== 2. Three-way agreement ({len(res['rows'])} reviewed)")
    print(f"{'':22}" + "".join(f"{n:>20}" for n in names))

    def line(label, get):
        print(f"{label:22}" + "".join(f"{fmt(get(ag[n])):>20}" for n in names))

    line("overall", lambda a: a["overall"])
    for s in SENTIMENT_ORDER:
        line(f"intended {s}", lambda a, s=s: a["by_intended"][s])
    for s in STYLES:
        line(s, lambda a, s=s: a["by_style"][s])
    line("incident", lambda a: a["by_incident"]["incident"])
    line("no incident", lambda a: a["by_incident"]["no_incident"])

    nd = res["neutral_diagnosis"]
    print(f"\n== 3. Neutral diagnosis ({len(nd['rows'])} intended-neutral rows)")
    for c, n in nd["cells"].items():
        print(f"  {n:2}  {c}")
    for r in nd["rows"]:
        print(
            f"- {r['review_id']} | {r['style']} | incident: {r['incident']} | focus: {r['focus']}"
            f" | human {r['human']} | judge {r['judge']}"
        )
        print(f"    {r['text']}")

    print("\n== 4a. Implicit by intended sentiment")
    for se, d in res["implicit_by_intended"].items():
        print(
            f"  {se:9} judge (all 80) {fmt(d['judge_all80'])}   "
            f"human (reviewed) {fmt(d['human_reviewed'])}"
        )
    pm = res["positive_labelled_mixed"]
    print(f"\n== 4b. Intended positive, labelled mixed by judge or me ({len(pm['rows'])})")
    for r in pm["rows"]:
        print(
            f"- spec {r['spec_id']} | {r['style']} | focus: {r['focus']} | opening: {r['opening']}"
            f" | incident: {r['incident']} | {r['channel']} | judge {r['judge']}"
            f" | human {r['human']}"
        )
        print(f"    {r['text']}")
    o = pm["focus_overrepresentation"]
    print(
        f"  billing/scheduling focus: {fmt_c(o['billing_or_scheduling_in_flagged'])} flagged vs "
        f"{fmt_c(o['billing_or_scheduling_in_all_positive'])} of all intended-positive specs"
    )
    print(f"  flagged focus counts: {o['focus_flagged']}")

    rt = res["ratings"]
    d = rt["believable_distribution"]
    print(f"\n== 5. Ratings (all {rt['n']})")
    print(
        f"  mean believable {rt['mean_believable_1to3']:.2f}  "
        f"(1s: {d['1']}, 2s: {d['2']}, 3s: {d['3']});  "
        f"sounds AI = y {rt['sounds_ai_y']['y']}/{rt['sounds_ai_y']['n']}"
    )


def fmt_c(c: dict) -> str:
    return f"{c['count']}/{c['n']}"


# --------------------------------------------------------------------------- v2+: grouped

GROUPS = ["neutral", "positive_serious", "mixed_incident", "distractor"]
NEUTRAL_KINDS = ["minimal", "administrative", "status"]
HUMAN_PASS = {"neutral_min_share": 0.7, "sounds_ai_max_share": 0.25}
ROW_FIELDS = ["review_id", "detail", "focus", "opening", "intended", "mine", "judge", "text"]


def row_detail(r: dict) -> str:
    return f"kind: {r['neutral_kind']}" if r["neutral_kind"] else f"incident: {incident_str(r)}"


def rating_summary(rows: list[dict]) -> dict:
    n = len(rows)
    bel = Counter(r["believable"] for r in rows)
    ai = sum(r["sounds_ai"] for r in rows)
    return {
        "n": n,
        "believable_distribution": {str(k): bel.get(k, 0) for k in (1, 2, 3)},
        "mean_believable_1to3": round(sum(r["believable"] for r in rows) / n, 2),
        "sounds_ai_y": {"y": ai, "n": n, "rate": round(ai / n, 3)},
    }


def score_grouped(rows: list[dict]) -> dict:
    """v2+ review (spec groups): three-way agreement per group, human pass criteria, lists."""
    subsets = {"overall": rows}
    for g in GROUPS:
        subsets[g] = [r for r in rows if r["group"] == g]
        if g == "neutral":
            for k in NEUTRAL_KINDS:
                subsets[f"neutral/{k}"] = [r for r in rows if r["neutral_kind"] == k]
    agreement = {
        name: {pair: pair_agree(rs, a, b) for pair, (a, b) in PAIRS.items()}
        for name, rs in subsets.items()
    }

    neutral = subsets["neutral"]
    n_agree = sum(r["mine"] == r["intended"] for r in neutral)
    ai = sum(r["sounds_ai"] for r in rows)
    human_pass = {
        "human agrees with intended on neutral >= 70%": {
            "value": f"{n_agree}/{len(neutral)}",
            "pass": bool(neutral) and n_agree / len(neutral) >= HUMAN_PASS["neutral_min_share"],
        },
        "sounds_ai_yn = y <= 25% of rows": {
            "value": f"{ai}/{len(rows)}",
            "pass": ai / len(rows) <= HUMAN_PASS["sounds_ai_max_share"],
        },
    }

    def listed(r):
        return {**{f: r[f] for f in ROW_FIELDS if f != "detail"}, "detail": row_detail(r)}

    focus_rows = [r for r in rows if r["intended"] in ("neutral", "mixed")]
    other_disagree = [
        r
        for r in rows
        if r["intended"] not in ("neutral", "mixed")
        and len({r["intended"], r["mine"], r["judge"]}) > 1
    ]

    def by_id(rs):
        return sorted(rs, key=lambda r: (r["intended"], r["review_id"]))

    ratings = {
        "all": rating_summary(rows),
        "by_channel": {
            c: rating_summary([r for r in rows if r["channel"] == c])
            for c in sorted({r["channel"] for r in rows})
        },
        "by_opening": {
            o: rating_summary([r for r in rows if r["opening"] == o])
            for o in sorted({r["opening"] for r in rows})
        },
    }
    return {
        "three_way_agreement": agreement,
        "human_pass_criteria": human_pass,
        "neutral_and_mixed_rows": [listed(r) for r in by_id(focus_rows)],
        "other_disagreement_rows": [listed(r) for r in by_id(other_disagree)],
        "ratings": ratings,
        "rows": rows,
    }


def print_grouped(res: dict) -> None:
    ag = res["three_way_agreement"]
    names = list(PAIRS)
    print(f"== 2. Three-way agreement ({res['ratings']['all']['n']} reviewed)")
    print(f"{'':26}" + "".join(f"{n:>20}" for n in names))
    for sub, d in ag.items():
        label = f"  {sub.split('/')[1]}" if "/" in sub else sub
        print(f"{label:26}" + "".join(f"{fmt(d[n]):>20}" for n in names))

    print("\n== 3. Human pass criteria")
    for name, c in res["human_pass_criteria"].items():
        print(f"  {'PASS' if c['pass'] else 'FAIL'}  {name:48} {c['value']}")

    def show(rows):
        for r in rows:
            print(
                f"- {r['review_id']} | {r['detail']} | focus: {r['focus']} | "
                f"opening: {r['opening']} | intended {r['intended']} | human {r['mine']} | "
                f"judge {r['judge']}"
            )
            print(f"    {r['text']}")

    print(f"\n== 4a. Neutral and mixed rows ({len(res['neutral_and_mixed_rows'])})")
    show(res["neutral_and_mixed_rows"])
    print(f"\n== 4b. Other rows with any disagreement ({len(res['other_disagreement_rows'])})")
    show(res["other_disagreement_rows"])

    def rline(label, s):
        d = s["believable_distribution"]
        print(
            f"  {label:26} n={s['n']:2}  believable 1/2/3 = {d['1']}/{d['2']}/{d['3']}  "
            f"mean {s['mean_believable_1to3']:.2f}  sounds AI {s['sounds_ai_y']['y']}/{s['n']}"
        )

    rt = res["ratings"]
    print("\n== 5. Ratings")
    rline("all", rt["all"])
    for key in ("by_channel", "by_opening"):
        print(f"  {key.replace('_', ' ')}:")
        for k, s in rt[key].items():
            rline(f"  {k}", s)


def main() -> None:
    run = Path(sys.argv[1])
    rows = load(run)
    if "group" in rows[0]:
        result = score_grouped(rows)
        (run / "review_scored.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print_grouped(result)
        return
    if "judge" in rows[0]:
        result = score_three_way(run, rows)
        (run / "review_scored.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print_three_way(result)
        return
    result = score(rows)
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
