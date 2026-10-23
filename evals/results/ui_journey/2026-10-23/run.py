"""One bounded local run for real answer journeys (Prompt I step 5; ADR-117 item 5).

Sends a fixed list of questions to the local orchestrator (free key, `LLM_MODE: free`) and saves
each full response beside this file. Before every question it reads the append-only ledger and
refuses
one that could cross a cap: at most 8 questions, 40 model calls and $0.10 list price. It stops
on any 429, 503, daily-quota or auth error and never switches key. Run from the repository root:

    .venv\\Scripts\\python evals/results/ui_journey/2026-10-23/run.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
LEDGER = HERE / "ledger.jsonl"
URL = "http://127.0.0.1:8000/ask"
MAX_QUESTIONS, MAX_CALLS, MAX_USD = 8, 40, 0.10
#: What one question could add in the worst case: routing, up to three parses and three QA calls
#: (the revision loop), and a few cents of list-price cost. A question that could cross a cap
#: on top of the running totals is refused.
RESERVE_CALLS, RESERVE_USD = 7, 0.01
STOP_STATUSES = (401, 403, 429, 503)

QUESTIONS = [
    ("reporting_sla", "What was SLA compliance in the Northeast last month?"),
    ("reporting_types", "Which incident types were most common in July 2026?"),
    ("sentiment_trend", "Is negative feedback trending up in the West?"),
    ("sentiment_examples", "Show examples of negative comments from last month"),
    ("forecast", "What weekly request volume should we expect for the next 8 weeks?"),
    ("clarification", "How did Lina do on first-time fixes last quarter?"),
]


def ledger() -> list[dict]:
    if not LEDGER.exists():
        return []
    return [json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines() if line]


def append(entry: dict) -> None:
    with LEDGER.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def totals(rows: list[dict]) -> tuple[int, int, float]:
    done = [r for r in rows if r["event"] == "answered"]
    return (
        len(rows_asked(rows)),
        sum(r["model_calls"] for r in done),
        sum(r["cost_usd"] for r in done),
    )


def rows_asked(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["event"] in ("answered", "error")]


def ask(question: str) -> tuple[int, dict]:
    request = urllib.request.Request(
        URL,
        data=json.dumps({"question": question}).encode(),
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=150) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def main() -> int:
    for name, question in QUESTIONS:
        asked, calls, usd = totals(ledger())
        if (
            asked + 1 > MAX_QUESTIONS
            or calls + RESERVE_CALLS > MAX_CALLS
            or usd + RESERVE_USD > MAX_USD
        ):
            append({"event": "refused", "name": name, "asked": asked, "calls": calls, "usd": usd})
            print(f"refused {name}: running totals {asked} questions, {calls} calls, ${usd:.4f}")
            return 1
        append({"event": "sending", "name": name, "question": question})
        began = time.perf_counter()
        status, body = ask(question)
        seconds = round(time.perf_counter() - began, 1)
        (HERE / f"{name}.json").write_text(
            json.dumps(
                {"question": question, "http_status": status, "seconds": seconds, "response": body},
                indent=1,
            ),
            encoding="utf-8",
        )
        if status != 200:
            append(
                {"event": "error", "name": name, "http_status": status, "error": body.get("error")}
            )
            print(f"{name}: HTTP {status} {body.get('error')}")
            if status in STOP_STATUSES or body.get("error") in (
                "daily_quota_exhausted",
                "rate_limited",
            ):
                print("stopping: quota, auth or backstop error (no key switch)")
                return 2
            continue
        journey = body.get("journey") or {}
        append(
            {
                "event": "answered",
                "name": name,
                "outcome": body["outcome"],
                "qa_status": body["qa_status"],
                "model_calls": journey.get("model_calls", 0),
                "cost_usd": journey.get("cost_usd", 0.0),
                "seconds": seconds,
            }
        )
        print(
            f"{name}: {body['outcome']} / {body['qa_status']} in {seconds}s, "
            f"{journey.get('model_calls')} calls, ${journey.get('cost_usd')}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
