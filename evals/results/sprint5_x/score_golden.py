"""Score the golden_v2 run mechanically, as fixed in golden_scoring.md (Prompt X).

    .venv\\Scripts\\python evals/results/sprint5_x/score_golden.py

Reads evals/results/golden_v2/2026-10-13/run1.json (harness output), the item file and the
expected figures. Writes score.json beside the run and golden_owner_review.csv here. It does not
judge `must` / `must_not`: those go to the owner.
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUN = ROOT / "evals" / "results" / "golden_v2" / "2026-10-13" / "run1.json"
ITEMS = ROOT / "evals" / "golden" / "golden_v2.jsonl"
EXPECTED = ROOT / "evals" / "golden" / "golden_v2.expected.json"
TOL = 1e-6
MIN_CASES = 20


def route_of(body: dict) -> str | None:
    return (body.get("route") or {}).get("route")


def c1_outcome(item: dict, body: dict) -> tuple[bool, str]:
    outcome, reason, route = body.get("outcome"), body.get("reason"), route_of(body)
    for a in item["acceptable_outcomes"]:
        code = a.get("reason") or a.get("error_code")
        if a["outcome"] != outcome:
            continue
        if code is not None and code != reason:
            continue
        if a.get("route") is not None and a["route"] != route:
            continue
        return True, ""
    return False, f"outcome={outcome} reason={reason} route={route}"


def c2_route(item: dict, body: dict) -> tuple[bool, str]:
    route = route_of(body)
    return route in item["acceptable_routes"], f"route={route}"


def groups_prefix(figs: dict, expected_list: list[dict], name: str = "groups") -> list[str]:
    got = [g for g in (figs.get(name) or []) if g["denominator"] >= MIN_CASES]
    want = [
        e for e in expected_list if e.get("in_text", e.get("denominator", MIN_CASES) >= MIN_CASES)
    ]
    problems = []
    for i, e in enumerate(want):
        if i >= len(got):
            problems.append(f"group {i} missing ({e['group']})")
            continue
        g = got[i]
        a = (g["group"], g["numerator"], g["denominator"], g["rate"])
        b = (e["group"], e["numerator"], e["denominator"], e["rate"])
        if a != b:
            problems.append(f"group {i}: got {a}, expected {b}")
    return problems


def rate_overall(figs: dict, exp: dict) -> list[str]:
    o = exp["overall"]
    got = (figs.get("numerator"), figs.get("denominator"), figs.get("rate"))
    want = (o["numerator"], o["denominator"], o["rate"])
    return [] if got == want else [f"overall got {got}, expected {want}"]


def range_check(ans: dict, exp: dict) -> list[str]:
    got = (ans.get("start"), ans.get("end"))
    want = (exp["start"], exp["end"])
    return [] if got == want else [f"range got {got}, expected {want}"]


def figs_reporting(item: dict, body: dict, exp: dict) -> list[str]:
    ans = body.get("reporting")
    if not ans:
        return ["no reporting payload"]
    figs = ans["figures"]
    oracle = item["oracle"]
    want_group = item["expected"].get("group_by")
    p: list[str] = []
    if oracle != "g02":
        p += range_check(ans, exp)
    if oracle in ("g03", "g11", "g13", "g17", "g12", "g15"):
        p += rate_overall(figs, exp if oracle != "g15" else {"overall": exp})
        if figs.get("group_by") != want_group:
            p.append(f"group_by got {figs.get('group_by')}, expected {want_group}")
        key = "worst_first_in_text" if oracle == "g12" else "worst_first"
        if key in exp:
            p += groups_prefix(figs, exp[key])
        if oracle == "g12" and figs.get("group_count") != exp["group_count"]:
            p.append(f"group_count got {figs.get('group_count')}, expected {exp['group_count']}")
        if oracle == "g15" and figs.get("technician_name") != "Priya Kim":
            p.append(f"technician_name got {figs.get('technician_name')}")
    elif oracle == "g14":
        if figs.get("incident_count") != exp["incident_count"]:
            p.append(f"incident_count got {figs.get('incident_count')}")
        if figs.get("by_severity") != exp["by_severity"]:
            p.append(f"by_severity got {figs.get('by_severity')}")
        if figs.get("group_by") not in item["expected"].get("acceptable_group_by", [None]):
            p.append(f"group_by got {figs.get('group_by')}")
    elif oracle == "g18":
        if figs.get("group_by") != "region":
            p.append(f"group_by got {figs.get('group_by')}")
        ov = figs["overall"]
        want = exp["overall"]
        if (ov["jobs"], ov["repeated"], ov["rate"]) != (
            want["jobs"],
            want["repeated"],
            want["rate"],
        ):
            p.append(f"overall got {ov}, expected {want}")
        by = {g["group"]: g for g in figs["groups"]}
        for e in exp["groups"]:
            g = by.get(e["group"])
            if g is None:
                p.append(f"group {e['group']} missing")
                continue
            a = (g["this"]["jobs"], g["this"]["repeated"], g["this"]["rate"])
            b = (e["jobs"], e["repeated"], e["rate"])
            if a != b or g["compared"] != e["compared"] or g["stands_out"] != e["stands_out"]:
                p.append(f"group {e['group']}: got {a} {g['compared']} {g['stands_out']}")
    elif oracle == "g02":
        region = figs.get("region")
        want_block = {None: "all_regions", "central": "central"}.get(region)
        if want_block is None:
            return [f"answered for region {region}, which is neither all-region nor Central"]
        ov = figs["overall"]
        w = exp[want_block]
        if (ov["jobs"], ov["repeated"], ov["rate"]) != (w["jobs"], w["repeated"], w["rate"]):
            p.append(f"overall got {ov}, expected {w} ({want_block})")
        p += range_check(ans, exp)
    return p


def figs_sentiment(item: dict, body: dict, exp: dict) -> list[str]:
    ans = body.get("sentiment")
    if not ans:
        return ["no sentiment payload"]
    oracle = item["oracle"]
    s = ans["summary"]
    if oracle == "g22":
        p = range_check(ans, exp)
        ex = ans.get("examples") or []
        if len(ex) != exp["examples_expected"]:
            p.append(f"{len(ex)} examples, expected {exp['examples_expected']}")
        for e in ex:
            if e["feedback_id"] not in exp["eligible_feedback_ids"] or e["label"] != "mixed":
                p.append(f"example {e['feedback_id']} not an eligible mixed comment")
        return p
    block = exp
    if oracle in ("g04", "g05"):
        block = next(
            (b for b in exp.values() if (b["start"], b["end"]) == (ans["start"], ans["end"])),
            None,
        )
        if block is None:
            return [f"range {ans['start']}..{ans['end']} is not an acceptable range"]
    p = range_check(ans, block)
    if s.get("region") != block.get("region"):
        p.append(f"region got {s.get('region')}, expected {block.get('region')}")
    if s["n_comments"] != block["comments"]:
        p.append(f"comments got {s['n_comments']}, expected {block['comments']}")
    if s["counts"] != block["counts"]:
        p.append(f"counts got {s['counts']}, expected {block['counts']}")
    if s["shares"] != block["shares"]:
        p.append(f"shares got {s['shares']}, expected {block['shares']}")
    if s["flagged_count"] != block["flagged"]:
        p.append(f"flagged got {s['flagged_count']}, expected {block['flagged']}")
    if oracle == "g21":
        got = {b["bucket"]: b for b in s["buckets"]}
        for name, b in exp["buckets"].items():
            g = got.get(name)
            if g is None or g["n_scored"] != b["comments"] or g["counts"] != b["counts"]:
                p.append(f"bucket {name} differs")
            elif g["flagged_count"] != b["flagged"]:
                p.append(f"bucket {name} flagged differs")
        t = ans.get("trend") or {}
        if t.get("verdict") != exp["verdict"]:
            p.append(f"verdict got {t.get('verdict')}, expected {exp['verdict']}")
        lat, ear = exp["latest"], exp["earlier"]
        if (t.get("latest_n"), t.get("latest_negative")) != (lat["comments"], lat["negative"]):
            p.append("latest side differs")
        if (t.get("earlier_n"), t.get("earlier_negative")) != (ear["comments"], ear["negative"]):
            p.append("earlier side differs")
        if t.get("p_value") is None or abs(t["p_value"] - exp["p_value"]) > TOL:
            p.append(f"p_value got {t.get('p_value')}, expected {exp['p_value']}")
    return p


def figs_forecast(item: dict, body: dict, exp: dict) -> list[str]:
    ans = body.get("forecast")
    if not ans:
        return ["no forecast payload"]
    p = []
    if ans.get("model_version") != exp["manifest_sha256"]:
        p.append("model_version differs from the manifest")
    got = {w["week_start"]: w for w in ans["weeks"]}
    want = {w["week_start"]: w for w in exp["weeks"]}
    if set(got) != set(want):
        p.append(f"weeks differ: {len(got)} returned, {len(want)} expected")
    for d, e in want.items():
        g = got.get(d)
        if g is None:
            continue
        if g["served"] != e["served"]:
            p.append(f"{d}: served got {g['served']}, expected {e['served']}")
        elif e["served"]:
            if abs(g["point"] - e["point"]) > TOL:
                p.append(f"{d}: point {g['point']} vs {e['point']}")
        elif any(g.get(k) is not None for k in ("point", "lo80", "hi80", "lo95", "hi95")):
            p.append(f"{d}: unserved week carries numbers")
    if item["oracle"] == "g07" and not ans.get("beyond_horizon_weeks"):
        p.append("beyond_horizon_weeks is 0; the request goes past the 26-week cap")
    return p


def score_item(item: dict, row: dict, expected: dict) -> dict:
    body = row.get("response") or {}
    usable = row.get("http_status") == 200 and "outcome" in body
    res = {
        "id": item["id"],
        "author": item["author"],
        "stretch": item["stretch"],
        "behaviour": item["expected_behaviour"],
        "seconds": row["seconds"],
        "outcome": body.get("outcome"),
        "reason": body.get("reason"),
        "route": route_of(body),
        "qa_status": body.get("qa_status"),
        "escalate": body.get("escalate"),
    }
    if not usable:
        res |= {"c1": False, "c2": False, "c3": None, "pass": False, "why": ["error or timeout"]}
        return res
    c1, w1 = c1_outcome(item, body)
    c2, w2 = c2_route(item, body)
    c3, w3 = None, []
    if item["oracle"] and body.get("outcome") == "answered" and c1:
        exp = expected[item["id"]]
        domain = item["expected"].get("domain")
        fn = {"reporting": figs_reporting, "sentiment": figs_sentiment, "forecast": figs_forecast}
        w3 = fn[domain](item, body, exp)
        c3 = not w3
    why = ([w1] if not c1 else []) + ([w2] if not c2 else []) + w3
    res |= {"c1": c1, "c2": c2, "c3": c3, "pass": c1 and c2 and c3 is not False, "why": why}
    return res


def main() -> int:
    items = [json.loads(x) for x in ITEMS.read_text("utf-8").splitlines() if x.strip()]
    expected = json.loads(EXPECTED.read_text("utf-8"))["items"]
    run = json.loads(RUN.read_text("utf-8"))
    rows = {r["id"]: r for r in run["rows"]}
    results = [score_item(i, rows[i["id"]], expected) for i in items if i["id"] in rows]
    secs = [r["seconds"] for r in results]
    out = {
        "n_scored": len(results),
        "n_items": len(items),
        "complete": run.get("complete", False),
        "passed": sum(r["pass"] for r in results),
        "by_behaviour": {},
        "by_author": {},
        "stretch": {r["id"]: r["pass"] for r in results if r["stretch"]},
        "median_s": round(statistics.median(secs), 2) if secs else None,
        "max_s": max(secs) if secs else None,
        "over_120s": [r["id"] for r in results if r["seconds"] > 120],
        "items": results,
    }
    for key, field in (("by_behaviour", "behaviour"), ("by_author", "author")):
        for r in results:
            n = out[key].setdefault(r[field], [0, 0])
            n[0] += r["pass"]
            n[1] += 1
    (RUN.parent / "score.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    with (HERE / "golden_owner_review.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "question", "answer", "must", "must_not", "owner_pass", "owner_note"])
        for i in items:
            if i["id"] not in rows:
                continue
            w.writerow(
                [
                    i["id"],
                    i["question"],
                    (rows[i["id"]].get("response") or {}).get("answer", ""),
                    " | ".join(i["must"]),
                    " | ".join(i["must_not"]),
                    "",
                    "",
                ]
            )
    print(f"mechanical pass: {out['passed']}/{out['n_scored']} (of {out['n_items']})")
    print("by behaviour:", out["by_behaviour"])
    print("by author:", out["by_author"])
    print("stretch:", out["stretch"])
    for r in results:
        if not r["pass"]:
            print("FAIL", r["id"], r["outcome"], r["reason"], r["route"], "|", "; ".join(r["why"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
