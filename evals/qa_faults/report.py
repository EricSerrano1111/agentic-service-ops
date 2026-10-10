"""Turn results.json into the tables of report_format.md.

    .venv\\Scripts\\python evals/qa_faults/report.py --out evals/results/qa_faults/<date>

Frozen with the catalogue: the tables, their order and their definitions are those of
report_format.md. Misses are listed as measured; the reasons they were missed are written by
hand, after the run, in the results' README, never here.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
AGENTS = ("reporting", "forecast", "sentiment")


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """95% Wilson score interval for k successes of n."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def pct(k: int, n: int) -> str:
    if n == 0:
        return "n/a (0 cases)"
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {100 * k / n:.1f}% (95% Wilson {100 * lo:.1f}-{100 * hi:.1f}%)"


def table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def ran(results: dict) -> list[dict]:
    return [c for c in results["cases"] if c["status"] == "run"]


def caught(case: dict) -> bool:
    return case.get("verdict") == "fail"


def by_expected(case: dict, expected_checks: list[str]) -> bool:
    if not caught(case):
        return False
    if not expected_checks or expected_checks == ["any"]:
        return True
    return bool(set(case["failed_checks"]) & set(expected_checks))


def build(results: dict, catalogue: dict, bases: dict) -> str:
    faults = {f["id"]: f for f in catalogue["faults"]}
    cases = ran(results)
    out: list[str] = ["# QA fault-injection results", ""]
    out.append(
        f"Catalogue v1, seed {results['seed']}, run started {results['started_utc']}. "
        f"QA ran: {results['qa_ran']}."
    )

    # 1. base answers and controls
    out += ["", "## 1. Clean base answers and controls", ""]
    rows = []
    for agent in AGENTS:
        mine = [b for b in bases["bases"] if b["agent"] == agent]
        controls = [c for c in results["controls"] if c["agent"] == agent]
        failed = [c for c in controls if c["verdict"] == "fail"]
        rows.append(
            [
                agent,
                sum(b["kind"] == "answer" for b in mine),
                sum(b["kind"] == "decline" for b in mine),
                len(controls),
                len(failed),
            ]
        )
    out.append(table(["agent", "answers", "declines", "controls run", "false alarms"], rows))
    out.append(f"\nExcluded (neither an answer nor a decline): {len(bases['excluded'])}.")

    # 2. overall catch rate, assistant-drafted, caught-expected
    def group(cls: set[str], expected: str = "caught") -> list[dict]:
        return [
            c
            for c in cases
            if faults[c["fault_id"]]["class"] in cls
            and faults[c["fault_id"]]["expected"] == expected
        ]

    out += ["", "## 2. Overall catch rate (assistant-drafted faults expected to be caught)", ""]
    out.append(
        "Classes: injected and database. Rating contradictions, consistent misparses and the "
        "owner-selected faults are reported in their own sections."
    )
    rows = []
    mine_all = group({"injected", "database"})
    for agent in (*AGENTS, "total"):
        mine = [c for c in mine_all if agent == "total" or c["agent"] == agent]
        n_faults = len({c["fault_id"] for c in mine})
        k = sum(caught(c) for c in mine)
        k_exp = sum(by_expected(c, faults[c["fault_id"]]["expected_checks"]) for c in mine)
        rows.append([agent, n_faults, len(mine), pct(k, len(mine)), pct(k_exp, len(mine))])
    out.append(
        table(
            ["agent", "faults", "cases", "caught (any check)", "caught by an expected check"],
            rows,
        )
    )

    # 3. per fault
    out += ["", "## 3. Per fault", ""]
    skipped = Counter(c["fault_id"] for c in results["cases"] if c["status"] != "run")
    rows = []
    for fid, f in faults.items():
        mine = [c for c in cases if c["fault_id"] == fid]
        fired = Counter(code for c in mine if caught(c) for code in c["failed_checks"])
        rows.append(
            [
                fid,
                f["class"],
                f["expected"],
                f.get("description") or f.get("variant", ""),
                len(mine),
                sum(caught(c) for c in mine),
                sum(by_expected(c, f["expected_checks"]) for c in mine),
                ", ".join(f"{k} x{v}" for k, v in fired.most_common()) or "-",
                skipped.get(fid, 0),
            ]
        )
    out.append(
        table(
            [
                "id",
                "class",
                "expected",
                "fault",
                "cases",
                "caught",
                "by expected check",
                "checks that fired",
                "skipped",
            ],
            rows,
        )
    )

    # 4. misses
    out += ["", "## 4. Misses (caught-expected cases that passed)", ""]
    rows = []
    for c in cases:
        f = faults[c["fault_id"]]
        if (
            f["expected"] == "caught"
            and f["class"] in ("injected", "database", "owner")
            and not caught(c)
        ):
            rows.append(
                [
                    c["case_id"],
                    f.get("authorship", "assistant-drafted"),
                    c["question"][:70],
                    ", ".join(c.get("checks_run", [])),
                    json.dumps(c.get("note"))[:120],
                ]
            )
    out.append(
        table(["case", "authorship", "question", "checks that ran (all passed)", "note"], rows)
        if rows
        else "No misses."
    )

    # 5. false alarms
    out += ["", "## 5. False alarms (failed controls)", ""]
    rows = [
        [
            a,
            sum(1 for c in results["controls"] if c["agent"] == a and c["verdict"] == "fail"),
            sum(1 for c in results["controls"] if c["agent"] == a),
        ]
        for a in AGENTS
    ]
    out.append(table(["agent", "failed controls", "controls run"], rows))
    bad = [c for c in results["controls"] if c["verdict"] == "fail"]
    for c in bad:
        out.append(f"\n- {c['base_id']}: {c['failed_checks']} {c['failed_details']}")

    # 6. rating sensitivity
    out += ["", "## 6. Rating sensitivity against the pre-registered rule (ADR-087)", ""]
    rows = []
    for fid in ("K05", "K10", "K20", "K40", "K80"):
        mine = [c for c in cases if c["fault_id"] == fid]
        if not mine:
            rows.append([fid, "-", 0, "-", "-", "-", "-"])
            continue
        predicted = sum(c["prediction"]["predicted_caught"] for c in mine)
        actual = sum(caught(c) for c in mine)
        agree = sum(c["prediction"]["predicted_caught"] == caught(c) for c in mine)
        ns = [c["prediction"]["n"] for c in mine]
        rows.append(
            [
                fid,
                faults[fid]["rate"],
                len(mine),
                f"{min(ns)}-{max(ns)}",
                f"{predicted}/{len(mine)}",
                f"{actual}/{len(mine)}",
                f"{agree}/{len(mine)}",
            ]
        )
    out.append(
        table(
            [
                "level",
                "rate",
                "cases",
                "covered n",
                "rule predicts caught",
                "QA caught",
                "QA agrees with the rule",
            ],
            rows,
        )
    )
    for c in cases:
        if (
            c["fault_id"].startswith("K")
            and c.get("prediction")
            and (c["prediction"]["predicted_caught"] != caught(c))
        ):
            out.append(
                f"\n- DISAGREES {c['case_id']}: rule {c['prediction']}, QA {c['verdict']} "
                f"({c.get('rating_detail')})"
            )

    # 7. known gaps
    out += ["", "## 7. Known gaps: consistent misparse (interpretation is advisory, L-74)", ""]
    rows = []
    for agent in AGENTS:
        mine = [
            c for c in cases if faults[c["fault_id"]]["class"] == "misparse" and c["agent"] == agent
        ]
        rows.append(
            [
                agent,
                len(mine),
                pct(sum(caught(c) for c in mine), len(mine)),
                sum(bool(c.get("advisories_failed")) for c in mine),
            ]
        )
    out.append(table(["agent", "cases", "caught", "cases with an advisory logged"], rows))
    out.append(
        "\nThe interpretation client in this harness is a fake that always says `faithful`, so "
        "an advisory can never be logged here; the reading QA would have shown a real "
        "interpretation call is kept per case in results.json (`interpretation_reading`)."
    )

    # 8. owner-selected faults
    out += ["", "## 8. Owner-selected, AI-co-written faults (reported separately)", ""]
    rows = []
    for fid, f in faults.items():
        if f["class"] != "owner":
            continue
        mine = [c for c in cases if c["fault_id"] == fid]
        anchor = next((c for c in mine if c["base_id"].startswith("owner:")), None)
        rows.append(
            [
                fid,
                f.get("variant", ""),
                f["expected"],
                len(mine),
                sum(caught(c) for c in mine),
                (anchor or {}).get("verdict", "-"),
                ", ".join((anchor or {}).get("failed_checks", [])) or "-",
            ]
        )
    out.append(
        table(
            [
                "id",
                "variant",
                "owner's expected",
                "cases",
                "caught",
                "owner's exact question: verdict",
                "checks that fired there",
            ],
            rows,
        )
    )
    for c in cases:
        if faults[c["fault_id"]]["class"] == "owner" and c["base_id"].startswith("owner:"):
            out.append(
                f"\n- {c['case_id']}: {json.dumps(c.get('note'))} rating: {c.get('rating_detail')}"
            )

    # 9. integrity
    out += ["", "## 9. Database integrity", ""]
    db_cases = [c for c in cases if "database_unchanged" in c]
    out.append(
        f"Database-fault cases: {len(db_cases)}; unchanged after rollback: "
        f"{sum(c['database_unchanged'] for c in db_cases)}. Whole run: "
        f"before {results.get('database_before')}"
        f", after {results.get('database_after')}, unchanged {results.get('database_unchanged')}."
    )

    # 10. skips and applicability
    out += ["", "## 10. Applicability and skipped cases", ""]
    rows = []
    for fid in faults:
        sk = [c for c in results["cases"] if c["fault_id"] == fid and c["status"] != "run"]
        why = Counter(c["reason"][:70] for c in sk)
        rows.append(
            [
                fid,
                results.get("fault_summary", {}).get(fid, {}).get("applicable_bases", "-"),
                results.get("fault_summary", {}).get(fid, {}).get("cases_run", "-"),
                "; ".join(f"{v}x {k}" for k, v in why.most_common(3)) or "-",
            ]
        )
    out.append(table(["fault", "applicable base answers", "cases run", "skipped (reason)"], rows))
    out += [
        "",
        "## 11. Not blind",
        "",
        "Most of this catalogue (R, F, S, K, M) was written by the assistant that built QA, which "
        "knows what QA checks. The owner-selected faults (O) were chosen by the owner and "
        "co-written with the assistant; they are not independent of the project's design the way "
        "faults the owner wrote alone would be.",
    ]
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    catalogue = yaml.safe_load((HERE / "catalogue_v1.yaml").read_text(encoding="utf-8"))
    results = json.loads((out / "results.json").read_text(encoding="utf-8"))
    bases = json.loads((out / "base_answers.json").read_text(encoding="utf-8"))
    (out / "report.md").write_text(build(results, catalogue, bases), encoding="utf-8")
    print("wrote", out / "report.md")


if __name__ == "__main__":
    main()
