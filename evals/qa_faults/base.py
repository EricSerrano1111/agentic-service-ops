"""Clean base answers: real answers built without a parse call (Prompt N, section 1).

For each labelled item of the reporting, forecast and sentiment parse sets, the item's expected
parsed request is handed to the real specialist (through the real A2A SDK and the real tool
servers, in process) and what comes back is kept: the data part and the text of an answer, or
the code, text and parsed request of a decline. Items that end in anything else are excluded
and counted. The owner's anchor questions (catalogue_v1.yaml) are built the same way.

    .venv\\Scripts\\python evals/qa_faults/base.py --out evals/results/qa_faults/<date>

No model is called. QA is not run here.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parents[1]

from world import Stack  # noqa: E402

SETS = {
    "reporting": REPO / "evals" / "reporting_parse" / "parse_v4.jsonl",
    "forecast": REPO / "evals" / "forecast_parse" / "parse_v1.jsonl",
    "sentiment": REPO / "evals" / "sentiment_parse" / "parse_v1.jsonl",
}
CATALOGUE = HERE / "catalogue_v1.yaml"


def _base(agent, item_id, source, category, question, request, reply) -> dict:
    return {
        "base_id": f"{agent}:{item_id}" if source == "parse_set" else f"owner:{item_id}",
        "agent": agent,
        "item_id": item_id,
        "source": source,
        "category": category,
        "question": question,
        "request": request,
        "kind": reply.kind,
        "error_code": reply.error_code,
        "text": reply.text,
        "answer": reply.answer,
        "parsed_request": reply.parsed_request,
    }


async def build(stack: Stack) -> dict:
    bases: list[dict] = []
    excluded: list[dict] = []
    for agent, path in SETS.items():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            reply = await stack.ask(agent, row["expected"])
            if reply.kind == "other":
                excluded.append(
                    {
                        "agent": agent,
                        "item": row["id"],
                        "code": reply.error_code,
                        "text": reply.text,
                    }
                )
                continue
            bases.append(
                _base(
                    agent,
                    row["id"],
                    "parse_set",
                    row["category"],
                    row["question"],
                    row["expected"],
                    reply,
                )
            )
    catalogue = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))
    for anchor in catalogue["anchors"]:
        agent, request = anchor["agent"], anchor["request"]
        if anchor["id"] == "A4b":
            request = await single_job_technician(stack, bases)
        reply = await stack.ask(agent, request)
        if reply.kind != "answer":
            excluded.append({"agent": agent, "item": anchor["id"], "code": reply.error_code})
            continue
        item = _base(agent, anchor["id"], "owner", "anchor", anchor["question"], request, reply)
        item["anchor_for"] = anchor["faults"]
        bases.append(item)
    return {"bases": bases, "excluded": excluded}


async def single_job_technician(stack: Stack, bases: list[dict]) -> dict:
    """A4b: a technician with exactly one SLA case in the west in August 2026, taken from A4a's
    grouped answer (the lowest technician id whose full name resolves to that technician)."""
    a4a = next(b for b in bases if b["item_id"] == "A4a")
    groups = sorted(a4a["answer"]["figures"]["groups"], key=lambda g: g["group_id"])
    for g in groups:
        if g["denominator"] != 1:
            continue
        request = {
            "metric": "sla_compliance",
            "technician_name": g["group"],
            "region": "west",
            "start": "2026-08-01",
            "end": "2026-08-30",
        }
        reply = await stack.ask("reporting", request)
        if reply.kind == "answer" and reply.answer["figures"]["technician_id"] == g["group_id"]:
            return request
    raise SystemExit("no single-job technician resolves to one technician")


async def main() -> None:
    logging.disable(logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stack = Stack.open()
    try:
        # anchors are built after the parse sets, so A4a is available to A4b
        result = await build(stack)
    finally:
        stack.close()
    (out / "base_answers.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    per = {}
    for b in result["bases"]:
        key = (b["agent"], b["source"], b["kind"])
        per[key] = per.get(key, 0) + 1
    for key, n in sorted(per.items()):
        print(*key, n)
    print("excluded:", len(result["excluded"]))
    for e in result["excluded"]:
        print("  ", e)


if __name__ == "__main__":
    asyncio.run(main())
