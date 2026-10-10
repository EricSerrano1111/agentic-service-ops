"""Measurement 1 against measurement 2 (ADR-092): the same frozen catalogue and seed, run against
the QA of measurement 1 and the QA after the fixes.

    .venv\\Scripts\\python evals/qa_faults/compare.py --m1 <dir> --m2 <dir>

Appends a side-by-side section to `<m2>/report.md` (written first by report.py in the frozen
format). It never rewrites an expectation: an owner fault whose outcome differs from its
recorded expectation is reported with the expectation, both results and what closed it.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
AGENTS = ("reporting", "forecast", "sentiment")
CLOSED_BY = {
    "O4a": (
        "the section 6 small-sample rule: groups under 20 are not ranked and the left-out "
        "count is QA's own"
    ),
    "O4b": "the section 6 small-sample rule: a filtered rate under 20 cases carries the marking",
}


def load(path: Path) -> dict:
    return json.loads((path / "results.json").read_text(encoding="utf-8"))


def ran(r: dict) -> dict[str, dict]:
    return {c["case_id"]: c for c in r["cases"] if c["status"] == "run"}


def caught(c: dict) -> bool:
    return c.get("verdict") == "fail"


def outcome(n: int, total: int) -> str:
    return "passed" if n == 0 else f"caught {n} of {total}"


def build(m1: dict, m2: dict, catalogue: dict) -> str:
    faults = {f["id"]: f for f in catalogue["faults"]}
    a, b = ran(m1), ran(m2)
    out = ["", "# Measurement 1 against measurement 2", ""]
    out.append(
        "The same frozen catalogue and seed (`catalogue_v1.yaml`, `faults.py`, `generate.py`, "
        "`report_format.md`, seed 20261010) against QA before and after the fixes of ADR-092. "
        "**The fixes were designed after seeing measurement 1's misses.** Measurement 2 shows "
        "they work on those cases; it is not new evidence that QA catches faults it has not "
        "seen. Both measurements are upper bounds (L-85)."
    )
    same = sorted(set(a) & set(b))
    out.append(f"\nCases run in both: {len(same)} of {len(a)} and {len(b)}.")

    def group(classes: set[str]):
        return [
            c
            for c in same
            if faults[c.split("|")[0]]["class"] in classes
            and faults[c.split("|")[0]]["expected"] == "caught"
        ]

    out += ["", "## Assistant-drafted faults expected caught: per agent", ""]
    rows = ["| agent | cases | m1 caught | m2 caught |", "|---|---|---|---|"]
    mine_all = group({"injected", "database"})
    for agent in (*AGENTS, "total"):
        mine = [c for c in mine_all if agent == "total" or a[c]["agent"] == agent]
        rows.append(
            f"| {agent} | {len(mine)} | {sum(caught(a[c]) for c in mine)} | "
            f"{sum(caught(b[c]) for c in mine)} |"
        )
    out += rows

    out += [
        "",
        "## Per fault",
        "",
        "| fault | cases | m1 caught | m2 caught | m2 checks that fired |",
        "|---|---|---|---|---|",
    ]
    for fid in faults:
        mine = [c for c in same if c.split("|")[0] == fid]
        fired = Counter(code for c in mine if caught(b[c]) for code in b[c]["failed_checks"])
        out.append(
            f"| {fid} | {len(mine)} | {sum(caught(a[c]) for c in mine)} | "
            f"{sum(caught(b[c]) for c in mine)} | "
            f"{', '.join(f'{k} x{v}' for k, v in fired.most_common()) or '-'} |"
        )

    out += [
        "",
        "## Controls (false alarms)",
        "",
        "| agent | controls | m1 failed | m2 failed |",
        "|---|---|---|---|",
    ]
    for agent in AGENTS:
        c1 = [c for c in m1["controls"] if c["agent"] == agent]
        c2 = [c for c in m2["controls"] if c["agent"] == agent]
        out.append(
            f"| {agent} | {len(c2)} | {sum(c['verdict'] == 'fail' for c in c1)} | "
            f"{sum(c['verdict'] == 'fail' for c in c2)} |"
        )
    newly = [
        c["base_id"]
        for c in m2["controls"]
        if c["verdict"] == "fail"
        and next(x for x in m1["controls"] if x["base_id"] == c["base_id"])["verdict"] == "pass"
    ]
    out.append(f"\nControls that newly fail in m2: {newly or 'none'}.")

    out += [
        "",
        "## Rating sensitivity",
        "",
        "| level | cases | rule predicts caught | m1 caught | m2 caught |",
        "|---|---|---|---|---|",
    ]
    for fid in ("K05", "K10", "K20", "K40", "K80"):
        mine = [c for c in same if c.split("|")[0] == fid]
        predicted = sum(a[c]["prediction"]["predicted_caught"] for c in mine)
        out.append(
            f"| {fid} | {len(mine)} | {predicted} | "
            f"{sum(caught(a[c]) for c in mine)} | {sum(caught(b[c]) for c in mine)} |"
        )

    out += [
        "",
        "## Known gaps (consistent misparse)",
        "",
        "| agent | cases | m1 caught | m2 caught |",
        "|---|---|---|---|",
    ]
    for agent in AGENTS:
        mine = [
            c
            for c in same
            if faults[c.split("|")[0]]["class"] == "misparse" and a[c]["agent"] == agent
        ]
        out.append(
            f"| {agent} | {len(mine)} | {sum(caught(a[c]) for c in mine)} | "
            f"{sum(caught(b[c]) for c in mine)} |"
        )

    out += [
        "",
        "## Owner-selected, AI-co-written faults (expectations as recorded, never rewritten)",
        "",
    ]
    for fid, f in faults.items():
        if f["class"] != "owner":
            continue
        mine = [c for c in same if c.split("|")[0] == fid]
        c1, c2 = sum(caught(a[c]) for c in mine), sum(caught(b[c]) for c in mine)
        exp = f["expected"]
        variant = f.get("variant", "")[:70]
        line = (
            f"- **{fid}** ({variant}): expectation: {exp}; m1: {outcome(c1, len(mine))}; "
            f"m2: {outcome(c2, len(mine))}"
        )
        if exp == "known_gap" and c2 > c1:
            line += f" (closed by {CLOSED_BY.get(fid, 'a fix of this PR')})"
        out.append(line)

    changed = [c for c in same if caught(a[c]) != caught(b[c])]
    out += ["", "## Every case whose verdict changed", ""]
    if not changed:
        out.append("None.")
    for c in changed:
        out.append(f"- `{c}`: m1 {a[c]['verdict']}, m2 {b[c]['verdict']} {b[c]['failed_checks']}")
    regress = [c for c in changed if caught(a[c]) and not caught(b[c])]
    out.append(f"\nCases caught in m1 and passed in m2: {regress or 'none'}.")
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--m1", required=True)
    parser.add_argument("--m2", required=True)
    args = parser.parse_args()
    catalogue = yaml.safe_load((HERE / "catalogue_v1.yaml").read_text(encoding="utf-8"))
    text = build(load(Path(args.m1)), load(Path(args.m2)), catalogue)
    report = Path(args.m2) / "report.md"
    report.write_text(report.read_text(encoding="utf-8") + text, encoding="utf-8")
    print("appended to", report)


if __name__ == "__main__":
    main()
