"""Run the reporting parse set through the agent's own parser, k times. Live: calls Gemini.

    .venv\\Scripts\\python evals/reporting_parse/run.py --k 3 --budget 48

Uses `agent_reporting.parsing.Parser` and its prompt, on the specialist model and the
free key, so it measures what the agent runs. It scores the model's reading *before*
code applies a default range (`Resolved.request`), field by field and as a whole
request; `technician_name` is compared case-insensitively (see README).
A failed parse scores as wrong on every field. Paces under the free-tier per-minute
limit (as `evals/routing/run_seed.py`), stops at `--budget` requests, and stops on a
daily-quota 429. Writes evals/results/reporting_agent/<date>/parse_<prompt>_k<k>.json.
Not a test; never in CI.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SET = Path(__file__).resolve().parent
FIELDS = ("metric", "group_by", "technician_name", "start", "end")


def same(field: str, got, expected) -> bool:
    if field == "technician_name" and got is not None and expected is not None:
        return " ".join(got.split()).casefold() == " ".join(expected.split()).casefold()
    return got == expected


def default_rpm(model: str) -> float:
    """Stay under the free-tier per-minute limits (ADR-029), as run_seed.py does."""
    return 12.0 if "flash-lite" in model else 4.0


async def run(args: argparse.Namespace) -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    import agent_reporting.parsing as parsing_mod
    from agent_reporting.config import Settings
    from agent_reporting.parsing import Parser
    from llm import LLMClient, LLMDailyQuotaExhausted, LLMError
    from llm.prompts import load_prompt
    from llm.redact import redact

    items = [
        json.loads(line)
        for line in (SET / f"{args.file}.jsonl").read_text("utf-8").splitlines()
        if line
    ]
    client = LLMClient.from_env("specialist")
    if client.settings.mode != "free":
        raise SystemExit("this eval runs on the free key only (LLM_MODE=free)")
    model = client.settings.default_model
    prompt = load_prompt("agent_reporting", args.prompt, parsing_mod.__file__)
    parser = Parser(client, Settings.from_env().as_of, prompt)
    gap = 60.0 / default_rpm(model)
    print(
        f"{args.file}: {len(items)} questions x k={args.k}, model {model} (free key), prompt "
        f"{parser.prompt.version} ({parser.prompt.sha}), as-of {parser.as_of}, budget "
        f"{args.budget} requests"
    )

    runs: list[list[dict]] = []
    stopped = None
    last = 0.0
    for k in range(1, args.k + 1):
        rows = []
        for item in items:
            if client.totals.requests >= args.budget:
                stopped = f"budget of {args.budget} requests reached"
                break
            wait = last + gap - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            last = time.monotonic()
            row = {"id": item["id"], "category": item["category"], "got": None, "error": None}
            try:
                resolved = await parser.parse(item["question"], trace_id=f"parse-{item['id']}-k{k}")
                row["got"] = resolved.request.model_dump(mode="json")
            except LLMDailyQuotaExhausted as exc:
                stopped = f"daily quota exhausted ({exc})"
                break
            except LLMError as exc:
                row["error"] = f"{type(exc).__name__}: {redact(str(exc), ())[:200]}"
            row["fields"] = {
                f: row["got"] is not None and same(f, row["got"][f], item["expected"][f])
                for f in FIELDS
            }
            row["exact"] = all(row["fields"].values())
            rows.append(row)
            mark = "ok  " if row["exact"] else "MISS"
            wrong = [f for f, ok in row["fields"].items() if not ok]
            print(f"  k{k} {mark} {item['id']} [{item['category']}] {', '.join(wrong) or ''}")
        runs.append(rows)
        if stopped:
            print(f"stopped: {stopped}")
            break

    summary = summarise(items, runs)
    print(json.dumps(summary["per_run"], indent=1))
    print("flips:", summary["flips"] or "none")
    print(f"calls {client.totals.calls}, requests {client.totals.requests} (retries included)")
    out = ROOT / "evals" / "results" / "reporting_agent" / args.date
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"parse_{parser.prompt.version}_k{args.k}.json"
    path.write_text(
        json.dumps(
            {
                "evidence": "observed",
                "set": args.file,
                "model": model,
                "key": "free",
                "prompt": parser.prompt.version,
                "prompt_sha": parser.prompt.sha,
                "as_of": parser.as_of.isoformat(),
                "k": args.k,
                "stopped": stopped,
                "calls": client.totals.calls,
                "requests": client.totals.requests,
                **summary,
                "runs": runs,
                "expected": {i["id"]: i["expected"] for i in items},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {path.relative_to(ROOT)}")
    return 0


def summarise(items: list[dict], runs: list[list[dict]]) -> dict:
    per_run = []
    for k, rows in enumerate(runs, 1):
        per_run.append(
            {
                "run": k,
                "n": len(rows),
                "exact": sum(r["exact"] for r in rows),
                "fields": {f: sum(r["fields"][f] for r in rows) for f in FIELDS},
                "errors": sum(r["error"] is not None for r in rows),
            }
        )
    by_id: dict[str, list[dict]] = {}
    for rows in runs:
        for r in rows:
            by_id.setdefault(r["id"], []).append(r)
    flips = {
        i: [r["got"] if r["got"] is not None else r["error"] for r in rs]
        for i, rs in by_id.items()
        if len({json.dumps(r["got"], sort_keys=True) if r["got"] else r["error"] for r in rs}) > 1
    }
    exact = [p["exact"] for p in per_run]
    return {
        "per_run": per_run,
        "exact_range": [min(exact), max(exact)] if exact else None,
        "flips": flips,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--file", default="parse_v3")
    ap.add_argument("--prompt", default="parse_v3")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--budget", type=int, default=48, help="stop at this many requests")
    ap.add_argument("--date", default=dt.date.today().isoformat())
    return asyncio.run(run(ap.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
