"""ADR-114 phases P1 and P2 (as amended by ADR-115): development selection, then go or no-go.

    .venv\\Scripts\\python evals/fr03_v3/p1.py --dry-run   # plan and authorize each run; no call
    .venv\\Scripts\\python evals/fr03_v3/p1.py             # baseline, medium, then high if needed

Order: the baseline (`route_v6` at `minimal` on `routing_heldout_v1`, k=3), then `medium` on all
four sets (k=3), scored; `high` only if `medium` failed a go criterion. P2 writes `p2_decision`.
`route_v6`, `gemini-3.5-flash-lite`, the paid key, as-of 2026-08-30. Each run (one pass over one
set at one level) is authorized by the ledger before it starts; the per-process backstops are
LLM_MAX_SPEND_USD = min($1.00, $2.50 - ledger total) and LLM_MAX_REQUESTS = planned calls x 1.2.

A restart re-runs only incomplete runs: a `run_start` with no `run_end`, or a `run_end` that
stopped early. It counts what the ledger already holds. Counts and item IDs only are printed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # probe.py loads the Sprint 5 `ledger` by path, not by name
import probe  # noqa: E402  (keeps this folder off sys.path, loads the ledger and run_seed)

ledger_mod = probe.fr03_ledger
run_seed = probe.run_seed
ROOT = probe.ROOT
RESULTS_DIR = probe.RESULTS_DIR
score = probe.load_by_path("fr03_v3_p1_score", HERE / "p1_score.py")

RUNS = 3
RPM = "60"  # pacing only; latency is measured per call and is unaffected
MAX_RUN_SPEND_USD = 1.00
#: name -> (run_seed `--file` value, items)
SETS = {
    "seed_v2": ("seed_v2", 31),
    "routing_v2": ("routing_v2", 18),
    "fr03_fresh_v2": ("evals/generated/sets/fr03_fresh_v2.jsonl", 16),
    "routing_heldout_v1": ("evals/generated/sets/routing_heldout_v1.jsonl", 50),
}
LEVEL_ORDER = ("medium", "high")


def run_id(level: str, name: str, rep: int) -> str:
    return f"P1:{level}:{name}:r{rep}"


def run_spec(level: str, name: str, rep: int) -> dict:
    return {
        **probe.run_spec(level),
        "phase": "P1",
        "run_id": run_id(level, name, rep),
        "set": f"{name}.jsonl",
        "rep": rep,
        "k": 1,
        "items": SETS[name][1],
    }


def is_complete(end: dict | None, items: int) -> bool:
    return bool(end) and not end.get("stopped") and end["calls"] == items


def plan(level: str, names: list[str]) -> list[tuple[str, int]]:
    return [(name, rep) for rep in range(1, RUNS + 1) for name in names]


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


async def run_one(ledger, level: str, name: str, rep: int) -> dict:
    """One pass over one set at one level, authorized, metered and recorded."""
    from llm import LLMClient

    run = run_spec(level, name, rep)
    ledger.authorize(run)
    totals = ledger.totals()
    spend = min(MAX_RUN_SPEND_USD, ledger_mod.SPEND_CAP_USD - totals["cost_usd"])
    backstop_requests = math.ceil(run["items"] * 1.2)
    start = ledger.run_start(run)
    if start["code_dirty"]:
        reason = f"code_dirty at the start of {run['run_id']}: the run is not attributable"
        ledger.stop(reason)
        raise probe.SessionStop(reason)
    probe.configure_env(level, str(backstop_requests), f"{spend:.4f}")
    client = LLMClient.from_env("orchestrator")
    meter = probe.Meter(client)
    before = (
        set(RESULTS_DIR.glob(f"routing_{Path(SETS[name][0]).stem}_*"))
        if RESULTS_DIR.exists()
        else set()
    )
    args = run_seed.build_parser().parse_args(
        [
            "--file", SETS[name][0],
            "--prompt", probe.PROMPT,
            "--model", probe.MODEL,
            "--rpm", RPM,
            "--thinking-level", level,
            "--results-dir", str(RESULTS_DIR),
        ]
    )  # fmt: skip
    stop = None
    try:
        await run_seed.run(args, client=client)
    except probe.SessionStop as exc:
        stop = f"{exc} at call {len(meter.calls)} of {run['items']}"
    finally:
        summary = probe.summarize(meter.calls)
        after = set(RESULTS_DIR.glob(f"routing_{Path(SETS[name][0]).stem}_*"))
        new = sorted(after - before)
        calls_path = RESULTS_DIR / (
            f"p1_calls_{level}_{name}_r{rep}_{ledger_mod.utc_now().strftime('%Y%m%dT%H%M%SZ')}.json"
        )
        files = {
            "routing_file": rel(new[-1]) if new else None,
            "calls_file": rel(calls_path),
        }
        ids = [run_seed.map_generated(json.loads(x)) for x in _lines(SETS[name][0])]
        for call, item in zip(meter.calls, ids, strict=False):
            call.update(id=item["id"], expected=item["expected"], tag=item["tag"])
        calls_path.write_text(
            json.dumps({"run_id": run["run_id"], "level": level, "calls": meter.calls}, indent=1)
            + "\n",
            encoding="utf-8",
        )
        ledger.run_end(run, summary | files | {"stopped": stop, "expected_calls": run["items"]})
    if stop:
        ledger.stop(f"{stop} ({run['run_id']})")
        raise probe.SessionStop(stop)
    return summary


def _lines(file_arg: str) -> list[str]:
    path = (
        Path(file_arg)
        if file_arg.endswith(".jsonl")
        else ROOT / "evals" / "routing" / f"{file_arg}.jsonl"
    )
    path = path if path.is_absolute() else ROOT / path
    return [x for x in path.read_text(encoding="utf-8").splitlines() if x]


async def run_level(ledger, level: str, names: list[str], dry_run: bool) -> bool:
    """Run the level's incomplete runs. True when all of them are complete."""
    ends = ledger.run_ends("P1", level)
    for name, rep in plan(level, names):
        rid = run_id(level, name, rep)
        if is_complete(ends.get(rid), SETS[name][1]):
            continue
        if dry_run:
            p = ledger.authorize(run_spec(level, name, rep), dry_run=True)
            print(f"  {rid}: would authorize {p.requests} requests, ${p.usd:.4f} ({p.basis})")
            continue
        await run_one(ledger, level, name, rep)
        print(f"  {rid}: done")
    ends = ledger.run_ends("P1", level)
    return all(
        is_complete(ends.get(run_id(level, n, r)), SETS[n][1]) for n, r in plan(level, names)
    )


def level_inputs(ledger, level: str, names: list[str]) -> tuple[list[dict], list[dict]]:
    ends = ledger.run_ends("P1", level)
    files, calls = [], []
    for name, rep in plan(level, names):
        end = ends[run_id(level, name, rep)]
        files.append(score.gate.load(ROOT / end["routing_file"]))
        calls += json.loads((ROOT / end["calls_file"]).read_text(encoding="utf-8"))["calls"]
    return files, calls


def baseline(ledger) -> dict:
    files, calls = level_inputs(ledger, "minimal", ["routing_heldout_v1"])
    c1 = score.load_files(score.c1_paths())
    result = score.baseline_g1(files + c1)
    held = score.by_set(files)["routing_heldout_v1.jsonl"]
    result["heldout_per_run_non_ambiguous_correct"] = [
        score.gate.non_ambiguous_correct(r["rows"]) for r in held
    ]
    result["heldout_ambiguous_recognised"] = score.recognised(
        score.by_set(files), ("routing_heldout_v1.jsonl",)
    )
    result["latency_cost"] = score.latency_cost(calls)
    return result


def write_json(name: str, data: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / name
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


async def main_async(args: argparse.Namespace) -> int:
    ledger = ledger_mod.Ledger()
    probe.preconditions()
    decided = [e for e in ledger.events() if e["event"] == "p2_decision"]
    if decided and not args.dry_run:
        print(f"p2_decision already recorded: {decided[-1]['decision']} {decided[-1]['level']}")
        return 0
    if args.dry_run:
        for level, names in (
            ("minimal", ["routing_heldout_v1"]),
            ("medium", list(SETS)),
            ("high", list(SETS)),
        ):
            print(f"{level}:")
            try:
                await run_level(ledger, level, names, True)
            except ledger_mod.Refused as exc:
                print(f"  would be REFUSED: {exc}")
                return 2
        print(f"ledger now: {ledger.totals()}")
        return 0
    try:
        print("baseline: route_v6 at minimal on routing_heldout_v1, k=3")
        if not await run_level(ledger, "minimal", ["routing_heldout_v1"], False):
            return 1
        base = baseline(ledger)
        write_json("p1_baseline.json", base)
        print(
            f"  baseline: heldout correct {base['heldout_per_run_non_ambiguous_correct']}, "
            f"ambiguous recognised {base['heldout_ambiguous_recognised']['count']} of "
            f"{base['heldout_ambiguous_recognised']['of']}; G1 baseline {base['count']} of "
            f"{base['of']}"
        )
        names = list(SETS)
        for level in LEVEL_ORDER:
            print(f"{level}: all four sets, k=3")
            if not await run_level(ledger, level, names, False):
                return 1
            files, calls = level_inputs(ledger, level, names)
            scored = score.score_level(files, calls, base)
            write_json(f"p1_score_{level}.json", scored)
            print(" ", score.table(level, scored))
            if not any(e["event"] == "p1_verdict" and e["level"] == level for e in ledger.events()):
                ledger.p1_verdict(
                    level, scored["pass"], scored["criteria"], failed=scored["failed"]
                )
            if scored["pass"]:
                ledger.p2_decision("go", level=level, reason="every go criterion met")
                print(f"P2: go, selected level {level}")
                return 0
        ledger.p2_decision("no_go", reason="no level met every go criterion")
        print("P2: no_go (no level met every go criterion)")
        return 0
    except ledger_mod.Refused as exc:
        print(f"refused: {exc}")
        if exc.kind in ("request_cap", "spend_cap"):
            ledger.p2_decision("no_go", reason="budget")
            print("P2: no_go (budget)")
            return 0
        return 2
    except probe.SessionStop as exc:
        print(f"session stopped: {exc}")
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="plan and authorize; no call")
    return asyncio.run(main_async(parser.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
