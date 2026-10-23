"""ADR-114 phase P0: the thinking probe. 30 live calls on the paid key, and nothing else.

    .venv\\Scripts\\python evals/fr03_v3/probe.py --balance 12.34   # the owner's reading, no call
    .venv\\Scripts\\python evals/fr03_v3/probe.py --dry-run         # project and authorize, no call
    .venv\\Scripts\\python evals/fr03_v3/probe.py                   # low, medium, high; k=1 each

The first 10 items of `seed_v2`, in file order, with `route_v6` on `gemini-3.5-flash-lite`,
as-of 2026-08-30. Each level is authorized through the ledger before it runs. The routing code is
`run_seed.py`'s, called in-process with a client this wrapper meters; nothing is copied from it.

Per-process backstops (the ledger is the control): LLM_MAX_REQUESTS=40, LLM_MAX_SPEND_USD=0.20,
one client per level. The session stops, with a `stop` ledger line, on a daily-quota 429, an
`LLMAuthError`, a backstop cap firing, or every call at a level above `minimal` reporting zero
thinking tokens. The routes are recorded for information; they are not a selection input.
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EVALS = ROOT / "evals"
# Run as a script, this folder leads sys.path and its `ledger.py` would shadow the Sprint 5
# `evals/ledger.py` that run_seed imports as `ledger`. Keep this folder off the path.
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != HERE]
sys.path.insert(0, str(EVALS))


def load_by_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


fr03_ledger = load_by_path("fr03_v3_ledger", HERE / "ledger.py")
run_seed = load_by_path("fr03_v3_run_seed", EVALS / "routing" / "run_seed.py")

MODEL = "gemini-3.5-flash-lite"
PROMPT = "route_v6"
PROMPT_SHA = "a160b528247b"  # ADR-101; the sha of services/orchestrator/prompts/route_v6.md
AS_OF = "2026-08-30"
SET = "seed_v2"
N_ITEMS = 10
LEVELS = ("low", "medium", "high")
BACKSTOP_REQUESTS, BACKSTOP_SPEND_USD = "40", "0.20"
RESULTS_DIR = ROOT / "evals" / "results" / "fr03_v3"
SEED_FILE = ROOT / "evals" / "routing" / f"{SET}.jsonl"


class SessionStop(Exception):
    """A stop rule fired; the whole session ends (not only the level)."""


class Meter:
    """Wraps a client so every call is recorded with the thinking tokens the client itself folds
    into `output_tokens`, and with its latency. Records only; changes nothing about a call."""

    STOP_ON = (
        "LLMDailyQuotaExhausted",
        "LLMAuthError",
        "LLMRequestCapReached",
        "LLMBudgetExceeded",
    )

    def __init__(self, client) -> None:
        self.client = client
        self.calls: list[dict] = []
        self._thinking = 0
        self._responses = 0
        real_transport = client._transport
        meter = self

        class Transport:
            async def generate(self, **kwargs):
                response = await real_transport.generate(**kwargs)
                usage = getattr(response, "usage_metadata", None)
                meter._thinking += int(getattr(usage, "thoughts_token_count", None) or 0)
                meter._responses += 1
                return response

        client._transport = Transport()
        real_generate = client.generate

        async def generate(prompt, **kwargs):
            t = client.totals
            before = (t.requests, t.input_tokens, t.output_tokens, t.cost_usd)
            self._thinking = self._responses = 0
            began = time.perf_counter()
            record = {"route": None, "domains": None, "error": None}
            try:
                result = await real_generate(prompt, **kwargs)
                record["route"] = result.parsed.route
                record["domains"] = list(result.parsed.domains)
                return result
            except Exception as exc:
                record["error"] = type(exc).__name__
                raise
            finally:
                self.calls.append(
                    {
                        **record,
                        "requests": t.requests - before[0],
                        "input_tokens": t.input_tokens - before[1],
                        "output_tokens": t.output_tokens - before[2],  # thinking included
                        "thinking_tokens": self._thinking,
                        "answer_tokens": t.output_tokens - before[2] - self._thinking,
                        "cost_usd": round(t.cost_usd - before[3], 8),
                        "latency_s": round(time.perf_counter() - began, 3),
                        "responded": self._responses > 0,
                    }
                )
                if record["error"] in self.STOP_ON:
                    raise SessionStop(record["error"]) from None

        client.generate = generate


def summarize(calls: list[dict]) -> dict:
    latencies = [c["latency_s"] for c in calls]
    errors = collections.Counter(c["error"] for c in calls if c["error"])
    n = len(calls)

    def total(key: str):
        return sum(c[key] for c in calls)

    return {
        "calls": n,
        "requests": total("requests"),
        "input_tokens": total("input_tokens"),
        "output_tokens": total("output_tokens"),
        "thinking_tokens": total("thinking_tokens"),
        "cost_usd": round(total("cost_usd"), 8),
        "mean_cost_per_call_usd": round(total("cost_usd") / n, 8) if n else None,
        "mean_input_tokens": round(total("input_tokens") / n, 1) if n else None,
        "mean_output_tokens": round(total("output_tokens") / n, 1) if n else None,
        "mean_thinking_tokens": round(total("thinking_tokens") / n, 1) if n else None,
        "latency": fr03_ledger.latency_summary(latencies),
        "errors": dict(errors),
    }


def seed_items() -> list[dict]:
    rows = [json.loads(x) for x in SEED_FILE.read_text(encoding="utf-8").splitlines() if x]
    return rows[:N_ITEMS]


def preconditions() -> None:
    import orchestrator.routing as routing_mod
    from llm.prompts import load_prompt

    prompt = load_prompt("orchestrator", PROMPT, routing_mod.__file__)
    if prompt.sha != PROMPT_SHA:
        raise SystemExit(f"stop: {PROMPT} hashes to {prompt.sha}, not {PROMPT_SHA} (ADR-114 P0)")
    if len(seed_items()) != N_ITEMS:
        raise SystemExit(f"stop: {SET}.jsonl has fewer than {N_ITEMS} items")


def configure_env(level: str) -> None:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    os.environ.update(
        LLM_MODE="paid",  # the paid key (GOOGLE_AI_API_KEY_PAID, from .env), as the Sprint 5 runs
        LLM_MAX_REQUESTS=BACKSTOP_REQUESTS,
        LLM_MAX_SPEND_USD=BACKSTOP_SPEND_USD,
        GEMINI_MODEL_ORCHESTRATOR=MODEL,
        REPORTING_AS_OF_DATE=AS_OF,
        LLM_THINKING_LEVEL_ORCHESTRATOR=level,
    )


def run_spec(level: str) -> dict:
    return {
        "phase": "P0",
        "set": SET,
        "prompt": PROMPT,
        "prompt_sha": PROMPT_SHA,
        "model": MODEL,
        "level": level,
        "k": 1,
        "items": N_ITEMS,
        "as_of": AS_OF,
    }


async def run_level(ledger, level: str) -> dict:
    from llm import LLMClient

    run = run_spec(level)
    ledger.authorize(run)
    ledger.run_start(run)
    configure_env(level)
    client = LLMClient.from_env("orchestrator")
    meter = Meter(client)
    args = run_seed.build_parser().parse_args(
        [
            "--file", SET,
            "--prompt", PROMPT,
            "--model", MODEL,
            "--limit", str(N_ITEMS),
            "--thinking-level", level,
            "--results-dir", str(RESULTS_DIR),
        ]
    )  # fmt: skip
    stop = None
    try:
        await run_seed.run(args, client=client)
    except SessionStop as exc:
        stop = f"{exc} at call {len(meter.calls)} of {N_ITEMS}"
    finally:
        summary = summarize(meter.calls)
        ledger.run_end(run, summary | {"stopped": stop})
    items = seed_items()
    for call, item in zip(meter.calls, items, strict=False):
        call.update(id=item["id"], tag=item["tag"], expected=item["expected"])
    level_result = {"level": level, "summary": summary, "calls": meter.calls, "stopped": stop}
    if stop:
        ledger.stop(f"{stop} (level {level})")
        return level_result
    thinking = [c["thinking_tokens"] for c in meter.calls if c["responded"]]
    if fr03_ledger.all_zero_thinking(level, thinking):
        reason = f"every call at {level} reported zero thinking tokens: meter or setting broken"
        ledger.stop(reason)
        level_result["stopped"] = reason
        return level_result
    kept, why = fr03_ledger.probe_verdict(
        summary["mean_cost_per_call_usd"] or 0.0, summary["latency"]["p95_s"]
    )
    ledger.verdict(
        level,
        kept,
        why,
        mean_cost_per_call_usd=summary["mean_cost_per_call_usd"],
        p95_latency_s=summary["latency"]["p95_s"],
    )
    level_result["verdict"] = {"kept": kept, "reason": why}
    return level_result


def write_results(ledger, results: list[dict]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    now = fr03_ledger.utc_now()
    path = RESULTS_DIR / f"p0_probe_{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    for r in results:
        scored = [c for c in r["calls"] if c["route"]]
        r["info_only_accuracy_not_a_selection_input"] = (
            f"{sum(c['route'] == c['expected'] for c in scored)}/{len(r['calls'])}"
        )
    path.write_text(
        json.dumps(
            {
                "phase": "P0",
                "adr": "ADR-114",
                "written_at": fr03_ledger.stamp(now),
                "set": SET,
                "items": N_ITEMS,
                "prompt": PROMPT,
                "prompt_sha": PROMPT_SHA,
                "model": MODEL,
                "as_of": AS_OF,
                "k": 1,
                **fr03_ledger.git_state(),
                "levels": results,
                "ledger_totals_after": ledger.totals(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


async def main_async(args: argparse.Namespace) -> int:
    ledger = fr03_ledger.Ledger()
    if args.balance is not None:
        line = ledger.record_balance(args.balance)
        ok = args.balance >= fr03_ledger.MIN_BALANCE_USD
        verdict = "ok" if ok else "BELOW MINIMUM"
        print(f"balance_reading ${line['balance_usd']:.2f} recorded; {verdict}")
        return 0 if ok else 2
    preconditions()
    if args.dry_run:
        refused = False
        for level in LEVELS:
            try:
                p = ledger.authorize(run_spec(level), dry_run=True)
                print(f"{level}: would authorize {p.requests} requests, ${p.usd:.4f} ({p.basis})")
            except fr03_ledger.Refused as exc:
                refused = True
                print(f"{level}: would be REFUSED: {exc}")
        print(f"ledger now: {ledger.totals()}")
        return 2 if refused else 0

    results: list[dict] = []
    code = 0
    try:
        for level in LEVELS:
            result = await run_level(ledger, level)
            results.append(result)
            print(f"{level}: {result.get('verdict') or result['stopped']}")
            if result["stopped"]:
                code = 1
                break
    except fr03_ledger.Refused as exc:
        print(f"refused: {exc}")
        code = 2
    finally:
        if results:
            print(f"wrote {write_results(ledger, results)}")
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="project and authorize; no call")
    parser.add_argument("--balance", type=float, help="record the owner's prepaid balance, USD")
    args = parser.parse_args(argv)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
