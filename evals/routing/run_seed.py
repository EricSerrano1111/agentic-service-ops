"""Run the routing seed set through the orchestrator's classifier. Live: calls Gemini.

    .venv\\Scripts\\python evals/routing/run_seed.py        # GEMINI_MODEL_ORCHESTRATOR
    .venv\\Scripts\\python evals/routing/run_seed.py --model gemini-3.5-flash-lite
    .venv\\Scripts\\python evals/routing/run_seed.py --file routing_v1
    .venv\\Scripts\\python evals/routing/run_seed.py --file seed_v2 --prompt route_v3

Uses the service's own `Router` and prompt (`services/orchestrator/prompts/`), so it
measures what the orchestrator runs. Prints accuracy overall and per tag, a confusion
table, every misroute with the model's reason, calls made and list-price cost. Writes
the full result to evals/results/routing_<set>_<model>_<prompt>_<UTC time>.json, where
<set> is the file stem (seed_v1, routing_v1).

Quota: on the free key, Flash models allow 5 requests a minute and 20 a day (ADR-049).
The script paces itself under the per-minute limit, and on a daily-quota 429 it stops
and writes what it has. Use --skip/--limit to split the set across days, or run with
LLM_MODE=paid (and its caps, ADR-048) to use the paid key. Not a test; never in CI.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SETS = ROOT / "evals" / "routing"
RESULTS = ROOT / "evals" / "results"
ROUTES = ("reporting", "sentiment", "forecast", "multi_domain", "out_of_scope", "ambiguous")


def default_rpm(model: str) -> float:
    """Stay under the free-tier per-minute limits in ADR-029."""
    return 12.0 if "flash-lite" in model else 4.0


async def run(args: argparse.Namespace) -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    import orchestrator.routing as routing_mod
    from llm import LLMClient, LLMDailyQuotaExhausted, LLMError
    from llm.prompts import load_prompt
    from llm.redact import redact
    from orchestrator.config import Settings
    from orchestrator.routing import Router

    source = SETS / f"{args.file}.jsonl"
    items = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line]
    items = items[args.skip :]
    if args.limit:
        items = items[: args.limit]

    client = LLMClient.from_env("orchestrator")
    model = args.model or client.settings.default_model
    as_of = Settings.from_env().as_of  # REPORTING_AS_OF_DATE, as the service reads it
    prompt = load_prompt("orchestrator", args.prompt, routing_mod.__file__) if args.prompt else None
    router = Router(client, prompt=prompt, model=model, as_of=as_of)
    thinking = client.thinking_level_for(model)
    rpm = args.rpm or default_rpm(model)
    gap = 60.0 / rpm
    print(
        f"{source.name}: {len(items)} questions, model {model} ({client.settings.mode} key), "
        f"thinking {thinking}, prompt {router.prompt.version} ({router.prompt.sha}), "
        f"as-of {as_of}, "
        f"pacing {rpm:g}/min"
    )

    rows: list[dict] = []
    stopped = None
    last = 0.0
    for n, item in enumerate(items, 1):
        wait = last + gap - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        last = time.monotonic()
        row = {**item, "predicted": None, "domains": None, "candidates": None, "reason": None}
        row |= {"error": None, "error_message": None}
        try:
            decision = await router.classify(item["question"], trace_id=f"seed-{item['id']}")
            row.update(
                predicted=decision.route,
                domains=decision.domains,
                candidates=decision.candidates,
                dropped_candidates=decision.dropped_candidates,
                reason=decision.reason,
            )
        except LLMDailyQuotaExhausted as exc:
            stopped = f"daily quota exhausted at question {n} ({exc})"
            print(f"  {item['id']}: {stopped}; stopping")
            break
        except LLMError as exc:  # LLMOutputInvalid included
            # Google's message, as the client already scrubbed it, redacted and truncated:
            # the class name alone hid the 2026-09-30 thinking-level 400.
            row["error"] = type(exc).__name__
            row["error_message"] = redact(str(exc), ())[:300]
        rows.append(row)
        mark = "ok " if row["predicted"] == item["expected"] else "MISS"
        print(
            f"  {mark} {item['id']} [{item['tag']}] expected {item['expected']}, "
            f"got {row['predicted'] or row['error']}"
        )

    report(rows, client.totals, model, thinking, router, stopped, client.settings.mode, source)
    return 0


def report(rows, totals, model, thinking, router, stopped, mode, source: Path) -> None:
    prompt = router.prompt
    correct = [r for r in rows if r["predicted"] == r["expected"]]
    by_tag: dict[str, list[bool]] = defaultdict(list)
    for r in rows:
        by_tag[r["tag"]].append(r["predicted"] == r["expected"])

    def pct(hits: list[bool]) -> str:
        return f"{sum(hits)}/{len(hits)} ({100 * sum(hits) / len(hits):.0f}%)" if hits else "-"

    print(f"\naccuracy: {pct([r['predicted'] == r['expected'] for r in rows])}")
    for tag, hits in sorted(by_tag.items()):
        print(f"  {tag:<13} {pct(hits)}")

    predicted_labels = [*ROUTES, "error"]
    confusion = Counter((r["expected"], r["predicted"] or "error") for r in rows)
    width = 13
    print("\nconfusion (rows expected, columns predicted):")
    print(" " * width + "".join(f"{p[:11]:>12}" for p in predicted_labels))
    for expected in ROUTES:
        cells = "".join(f"{confusion.get((expected, p), 0) or '.':>12}" for p in predicted_labels)
        print(f"{expected:<{width}}{cells}")

    misses = [r for r in rows if r["predicted"] != r["expected"]]
    if misses:
        print("\nmisroutes:")
        for r in misses:
            got = r["predicted"] or r["error"]
            print(f"  {r['id']} [{r['tag']}] {r['question']}")
            print(f"      expected {r['expected']}, got {got}: {r['reason'] or '-'}")
            if r["error_message"]:
                print(f"      {r['error_message']}")

    print(
        f"\ncalls {totals.calls}, requests {totals.requests} (retries included), tokens "
        f"{totals.input_tokens} in / {totals.output_tokens} out, list-price cost "
        f"${totals.cost_usd:.4f} ({mode} key{'' if mode == 'paid' else ', not billed'})"
    )
    if stopped:
        print(f"stopped early: {stopped}")

    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    path = RESULTS / f"routing_{source.stem}_{model}_{prompt.version}_{stamp}.json"
    path.write_text(
        json.dumps(
            {
                "seed_set": source.name,
                "model": model,
                "mode": mode,
                "thinking_level": thinking,
                "prompt_version": prompt.version,
                "prompt_sha": prompt.sha,
                "as_of": router.as_of.isoformat() if "{{as_of}}" in prompt.text else None,
                "run_at": stamp,
                "answered": len(rows),
                "correct": len(correct),
                "accuracy_by_tag": {t: pct(h) for t, h in sorted(by_tag.items())},
                "stopped_early": stopped,
                "calls": totals.calls,
                "requests": totals.requests,
                "input_tokens": totals.input_tokens,
                "output_tokens": totals.output_tokens,
                "list_price_cost_usd": round(totals.cost_usd, 6),
                "rows": rows,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model", help="override GEMINI_MODEL_ORCHESTRATOR for this run")
    parser.add_argument(
        "--file", default="seed_v1", help="set in evals/routing/, by stem (default: seed_v1)"
    )
    parser.add_argument(
        "--prompt", help="routing prompt by stem, e.g. route_v3 (default: the service's)"
    )
    parser.add_argument("--rpm", type=float, help="requests per minute (default: per model)")
    parser.add_argument("--skip", type=int, default=0, help="skip the first N questions")
    parser.add_argument("--limit", type=int, default=0, help="run at most N questions")
    return asyncio.run(run(parser.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
