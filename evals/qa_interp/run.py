"""Run the interpretation gate's pairs through QA's interpretation call. Live: calls Gemini.

    .venv\\Scripts\\python evals/qa_interp/run.py --prompt qa_interp_v1 --k 3 --budget 252
    .venv\\Scripts\\python evals/qa_interp/run.py --prompt qa_interp_v1 --k 3 --resume FILE.json

Uses `agent_qa.interpretation.Interpreter`, the prompt file and the readings the service
itself uses, on the QA role's model and the free key, so it measures what ships (ADR-089). One
call per (run, pair); the judgement is `faithful` as the model wrote it, never retried on a
wrong answer. Paces under the free-tier per-minute limit, stops at `--budget` requests (retries
included) and on a daily-quota 429, and writes after every pair so a stopped run is resumable
with `--resume` (only the cells not yet judged are called). Writes
evals/results/qa_interp/<date>/interp_<prompt>_k<k>_<time>.json (a new file every run).
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
HERE = Path(__file__).resolve().parent
PAIRS = HERE / "pairs_v1.jsonl"
#: Fixed with the pairs, before any live call.
AS_OF = dt.date(2026, 8, 30)
sys.path.insert(0, str(ROOT / "services" / "agent_qa" / "src"))
sys.path.insert(0, str(HERE))


def default_rpm(model: str) -> float:
    """Stay under the free-tier per-minute limits (ADR-029), as the other evals do."""
    return 12.0 if "flash-lite" in model else 4.0


def reading_for(pair: dict, as_of: dt.date) -> str:
    """The model's input for a pair: the same readings the service builds (never the label)."""
    from agent_qa.interpretation import reading_forecast, reading_reporting
    from agent_qa.reporting import decline_reason, last_full_month
    from schemas import ForecastRequest, ReportingRequest

    if pair["domain"] == "forecast":
        return reading_forecast(ForecastRequest(**pair["request"]), as_of)
    request = ReportingRequest(**pair["request"])
    named = request.start is not None
    if decline_reason(request):  # a decline never resolved a range
        return reading_reporting(
            request, request.start if named else None, request.end if named else None, False, as_of
        )
    if named:
        return reading_reporting(request, request.start, request.end, False, as_of)
    start, end = last_full_month(as_of)
    return reading_reporting(request, start, end, True, as_of)


def write(path: Path, meta: dict, runs: list[list[dict]]) -> None:
    path.write_text(json.dumps({**meta, "runs": runs}, indent=2) + "\n", encoding="utf-8")


async def run(args: argparse.Namespace) -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    from agent_qa.interpretation import Interpreter, load_interp_prompt
    from llm import LLMClient, LLMDailyQuotaExhausted, LLMError
    from llm.redact import redact

    pairs = [json.loads(line) for line in PAIRS.read_text("utf-8").splitlines() if line]
    client = LLMClient.from_env("qa")
    if client.settings.mode != "free":
        raise SystemExit("this eval runs on the free key only (LLM_MODE=free)")
    model = client.settings.default_model
    interpreter = Interpreter(client, load_interp_prompt(args.prompt))
    as_of = AS_OF
    thinking = client.thinking_level_for(model)
    gap = 60.0 / default_rpm(model)

    runs: list[list[dict]] = [[] for _ in range(args.k)]
    if args.resume:
        previous = json.loads(Path(args.resume).read_text("utf-8"))
        for i, rows in enumerate(previous["runs"][: args.k]):
            runs[i] = [r for r in rows if r["faithful"] is not None]  # re-call failed cells
    done = {(i, r["id"]) for i, rows in enumerate(runs) for r in rows}
    todo = sum(1 for i in range(args.k) for p in pairs if (i, p["id"]) not in done)
    print(
        f"{len(pairs)} pairs x k={args.k}, model {model} (free key), thinking {thinking}, prompt "
        f"{interpreter.prompt.version} ({interpreter.prompt.sha}), as-of {as_of}, "
        f"{todo} calls to make, budget {args.budget} requests"
    )

    out = ROOT / "evals" / "results" / "qa_interp" / args.date
    out.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%H%M%S")
    path = out / f"interp_{interpreter.prompt.version}_k{args.k}_{stamp}.json"
    meta = {
        "evidence": "observed",
        "not_blind": "correct pairs come from parse sets drafted by assistants (L-69); "
        "mutations are synthetic (seed fixed in build_sets.py)",
        "model": model,
        "key": "free",
        "thinking_level": thinking,
        "prompt": interpreter.prompt.version,
        "prompt_sha": interpreter.prompt.sha,
        "as_of": as_of.isoformat(),
        "k": args.k,
        "resumed_from": args.resume,
    }
    stopped = None
    last = 0.0
    for i in range(args.k):
        for pair in pairs:
            if (i, pair["id"]) in done:
                continue
            if client.totals.requests >= args.budget:
                stopped = f"budget of {args.budget} requests reached"
                break
            wait = last + gap - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            last = time.monotonic()
            cell = {
                "id": pair["id"],
                "domain": pair["domain"],
                "label": pair["label"],
                "faithful": None,
                "differs_in": None,
                "note": None,
                "error": None,
            }
            try:
                judgement = await interpreter.judge(
                    pair["domain"],
                    pair["question"],
                    reading_for(pair, as_of),
                    trace_id=f"interp-{pair['id']}-k{i + 1}",
                )
                cell |= {
                    "meaning": judgement.meaning,
                    "faithful": judgement.faithful,
                    "differs_in": list(judgement.differs_in),
                    "note": judgement.note,
                }
            except LLMDailyQuotaExhausted as exc:
                stopped = f"daily quota exhausted ({exc})"
                break
            except LLMError as exc:
                cell["error"] = f"{type(exc).__name__}: {redact(str(exc), ())[:200]}"
            runs[i].append(cell)
            write(path, {**meta, "stopped": stopped, "requests": client.totals.requests}, runs)
            right = (cell["faithful"] is True) == (pair["label"] == "matches")
            mark = "ok  " if right and cell["faithful"] is not None else "MISS"
            print(f"  k{i + 1} {mark} {pair['id']} [{pair['label']}] faithful={cell['faithful']}")
        if stopped:
            print(f"stopped: {stopped}")
            break

    write(
        path,
        {
            **meta,
            "stopped": stopped,
            "calls": client.totals.calls,
            "requests": client.totals.requests,
        },
        runs,
    )
    print(f"calls {client.totals.calls}, requests {client.totals.requests} (retries included)")
    print(f"wrote {path.relative_to(ROOT)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--prompt", default="qa_interp_v1")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--budget", type=int, default=252, help="stop at this many requests")
    ap.add_argument("--resume", default=None, help="a stopped run's file: judge only what is left")
    ap.add_argument("--date", default=dt.date.today().isoformat())
    return asyncio.run(run(ap.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
