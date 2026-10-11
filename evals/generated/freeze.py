"""Assemble the final evaluation sets from the drafts, the skim and the pair build (ADR-094).

    .venv\\Scripts\\python evals/generated/freeze.py

Inputs (all committed): the `*.draft.jsonl` files and `reserve.jsonl`, `sets/skim_applied.json`
(`apply_skim.py`) and `pairs_provenance.json` (`build_pairs.py`: the interpretation set's removals
and refills). No model, no database. Whole items only: nothing is edited.

Writes the final files and removes the drafts. Final sets are append-never: a later change is a
new version (`_v2`) under a new ADR. `manifest.json` is written after the commit, by
`write_manifest.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SETS = HERE / "sets"

#: draft name -> final name
FINAL = {
    "routing_heldout_v1": "routing_heldout_v1.jsonl",
    "fr03_fresh_v2": "fr03_fresh_v2.jsonl",
    "interp_fresh_v1": "interp_fresh_v1.jsonl",
    "parse_filters_v1": "parse_filters_v1.jsonl",
}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_bytes(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows).encode(
            "utf-8"
        )
    )


def assemble() -> dict[str, list[dict]]:
    skim = json.loads((SETS / "skim_applied.json").read_text("utf-8"))
    prov = json.loads((HERE / "pairs_provenance.json").read_text("utf-8"))
    reserve = {r["uid"]: r for r in read_jsonl(SETS / "reserve.jsonl")}
    out: dict[str, list[dict]] = {}
    moved: set[str] = set()

    for name in FINAL:
        rows = read_jsonl(SETS / f"{name}.draft.jsonl")
        swaps = {x["replaces"]: x["uid"] for x in skim["sets"][name]["replacements"]}
        dropped = set(skim["sets"][name]["dropped"])
        if name == "interp_fresh_v1":
            removed = {x["uid"] for x in prov["interp_set"]["removed"]}
            for x in prov["interp_set"]["refill"]:
                swaps[x["replaces"]] = x["uid"]
            dropped |= removed
        final: list[dict] = []
        for row in rows:
            if row["uid"] not in dropped:
                final.append(row)
                continue
            new_uid = swaps.get(row["uid"])
            if new_uid is None:
                continue  # the set shrinks (reported)
            moved.add(new_uid)
            final.append({**reserve[new_uid], "set": name, "stratum": row["stratum"]})
        out[name] = final

    out["reserve"] = [r for uid, r in reserve.items() if uid not in moved]
    return out


def main() -> int:
    sets = assemble()
    prov = json.loads((HERE / "pairs_provenance.json").read_text("utf-8"))
    assert sorted(r["uid"] for r in sets["interp_fresh_v1"]) == sorted(
        prov["interp_set"]["final_ids"]
    ), "interp_fresh_v1 does not match the pair build"
    for name, final_name in FINAL.items():
        write_jsonl(SETS / final_name, sets[name])
        (SETS / f"{name}.draft.jsonl").unlink()
    write_jsonl(SETS / "reserve.jsonl", sets["reserve"])
    print({name: len(rows) for name, rows in sets.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
