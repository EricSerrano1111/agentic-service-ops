"""Apply the owner's skim to the draft sets (Prompt R, section 2). No model, no database.

    .venv\\Scripts\\python evals/generated/apply_skim.py            # writes sets/skim_applied.json
    .venv\\Scripts\\python evals/generated/apply_skim.py --check    # fails if the file is stale

Rules (plan.md's replacement rule, made precise for skim coverage):

- Every N row that sits in a set is removed from that set.
- A slot the skim covers (an `ambiguous` item in any set, or any `fr03_fresh_v2` item) is
  refilled only from the reserve items that were skimmed and marked Y, of the same category and,
  when the item has one, the same area, in reserve (seed) order. If none remains the set shrinks.
  An unskimmed item never fills a skim-covered slot.
- Any other slot would be refilled by the next reserve item of the same category and area
  (plan.md); the eligibility test for `interp_fresh_v1` is applied in `build_pairs.py`, which
  owns the full eligibility rule.
- Sets are served in plan.md's selection order, so a reserve item goes to the first set that
  needs it: interp_fresh_v1, fr03_fresh_v2, routing_heldout_v1, parse_filters_v1.
- A reserve item marked N leaves the reserve.

Only whole items are removed or substituted. No question and no label is read or edited here.
Output: IDs only.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SETS = HERE / "sets"
SKIM = HERE / "skim" / "skim.csv"
OUT = SETS / "skim_applied.json"

#: plan.md's selection order, which is also the order replacements are allocated in.
SET_ORDER = ("interp_fresh_v1", "fr03_fresh_v2", "routing_heldout_v1", "parse_filters_v1")
SKIM_COVERED_SET = "fr03_fresh_v2"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]


def read_skim() -> dict[str, str]:
    with SKIM.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    verdicts = {r["id"]: r["owner_agree"].strip() for r in rows}
    bad = {v for v in verdicts.values() if v not in ("Y", "N")}
    if bad:
        raise SystemExit(f"owner_agree has values other than Y/N: {sorted(bad)}")
    return verdicts


def apply() -> dict:
    verdicts = read_skim()
    drafts = {n: read_jsonl(SETS / f"{n}.draft.jsonl") for n in SET_ORDER}
    reserve = sorted(read_jsonl(SETS / "reserve.jsonl"), key=lambda r: r["rank"])

    def skim_covered(set_name: str, row: dict) -> bool:
        return row["category"] == "ambiguous" or set_name == SKIM_COVERED_SET

    # A reserve item marked N is removed from the reserve; skimmed-Y items are the pool for
    # skim-covered slots.
    removed_from_reserve = [r["uid"] for r in reserve if verdicts.get(r["uid"]) == "N"]
    available = [r for r in reserve if verdicts.get(r["uid"]) != "N"]
    skimmed_y = [r for r in available if verdicts.get(r["uid"]) == "Y"]
    used: set[str] = set()

    sets_out: dict[str, dict] = {}
    for name in SET_ORDER:
        rows = drafts[name]
        dropped = [r for r in rows if verdicts.get(r["uid"]) == "N"]
        replacements: list[dict] = []
        unfilled: list[str] = []
        for gone in dropped:
            covered = skim_covered(name, gone)
            source = skimmed_y if covered else available
            pick = next(
                (
                    r
                    for r in source
                    if r["uid"] not in used
                    and r["category"] == gone["category"]
                    and r["area"] == gone["area"]
                ),
                None,
            )
            if pick is None:
                unfilled.append(gone["uid"])
                continue
            used.add(pick["uid"])
            replacements.append(
                {"replaces": gone["uid"], "uid": pick["uid"], "skim_covered_slot": covered}
            )
        sets_out[name] = {
            "draft_size": len(rows),
            "dropped": [r["uid"] for r in dropped],
            "replacements": replacements,
            "unfilled_slots": unfilled,
            "final_size": len(rows) - len(dropped) + len(replacements),
        }

    return {
        "order": list(SET_ORDER),
        "sets": sets_out,
        "reserve_removed_n": removed_from_reserve,
        "reserve_used": sorted(used),
        "skim": {
            "rows": len(verdicts),
            "Y": sum(v == "Y" for v in verdicts.values()),
            "N": sum(v == "N" for v in verdicts.values()),
        },
    }


def render(obj: dict) -> str:
    return json.dumps(obj, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    check = "--check" in (argv if argv is not None else sys.argv[1:])
    text = render(apply())
    if check:
        if not OUT.exists() or OUT.read_text("utf-8") != text:
            print("skim_applied.json is stale", file=sys.stderr)
            return 1
        print("skim_applied.json is current")
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    summary = {
        n: (s["draft_size"], len(s["dropped"]), len(s["replacements"]), s["final_size"])
        for n, s in json.loads(text)["sets"].items()
    }
    print("wrote skim_applied.json; (draft, dropped, replaced, final):", summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
