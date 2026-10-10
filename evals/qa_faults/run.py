"""Run the frozen fault catalogue against QA's real checks (Prompt N, sections 3 and 4).

    .venv\\Scripts\\python evals/qa_faults/run.py --out evals/results/qa_faults/<date> [--no-qa]

Reads `base_answers.json` from --out (built by base.py). Every clean base answer is a control.
Every fault is then applied to up to 10 applicable base answers in the generator's order; each
mutated answer is sent as a `VerificationRequest` straight to QA's verification code with the
real checks, the real local database and a fake interpretation client that always says
`faithful` (the interpretation check is advisory, L-74). Database faults run inside a
transaction that is always rolled back; row counts and a checksum of the predictions are
compared before and after. No model is called.

`--no-qa` makes the mutated answers and writes what was applicable, skipped and schema-valid,
and nothing else: no verdict is produced.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import sys
import time
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import faults as F  # noqa: E402
import generate as G  # noqa: E402
from schemas import VerificationRequest  # noqa: E402
from world import Stack  # noqa: E402

CATALOGUE = HERE / "catalogue_v1.yaml"


def to_request(agent: str, question: str, p: F.Prepared) -> VerificationRequest:
    return VerificationRequest(
        domain=agent,
        kind=p.kind,
        question=question,
        text=p.text,
        answer=p.answer if p.kind == "answer" else None,
        error_code=p.error_code if p.kind == "decline" else None,
        parsed_request=p.parsed_request if p.kind == "decline" else None,
    )


def summarise_verdict(verdict, interpreter) -> dict:
    reading = interpreter.readings[-1][1] if interpreter.readings else None
    return {
        "verdict": verdict.verdict,
        "failed_checks": [c.code for c in verdict.failed],
        "failed_details": {c.code: c.detail for c in verdict.failed},
        "checks_run": [c.code for c in verdict.checks],
        "rating_detail": next(
            (c.detail for c in verdict.checks if c.code == "rating_contradiction"), None
        ),
        "advisories_failed": [c.code for c in verdict.advisories if not c.passed],
        "interpretation_reading": reading,
    }


async def run_controls(stack: Stack, bases: list[F.Base]) -> list[dict]:
    out = []
    for b in bases:
        prepared = F.Prepared(
            b.text,
            b.answer,
            b.kind,
            b.error_code,
            b.parsed_request if b.kind == "decline" else None,
        )
        stack.interpreter.readings.clear()
        verdict = await stack.verify(to_request(b.agent, b.question, prepared))
        out.append(
            {
                "base_id": b.base_id,
                "agent": b.agent,
                "kind": b.kind,
                "question": b.question,
                **summarise_verdict(verdict, stack.interpreter),
            }
        )
    return out


async def run_case(stack: Stack, fault: F.Fault, base: F.Base, qa: bool) -> dict:
    ctx = F.Ctx(stack=stack, rng=G.case_rng(fault.id, base.base_id), source=stack.source)
    record: dict = {
        "case_id": G.case_id(fault.id, base.base_id),
        "fault_id": fault.id,
        "base_id": base.base_id,
        "agent": base.agent,
        "question": base.question,
    }
    if fault.needs_db:
        before = stack.checksum()
        with stack.shared_transaction() as (conn, source):
            ctx.conn, ctx.source = conn, source
            record |= await _apply_and_verify(stack, fault, base, ctx, qa, source)
        after = stack.checksum()
        record["database_unchanged"] = before == after
        record["database_before"] = before
    else:
        record |= await _apply_and_verify(stack, fault, base, ctx, qa, None)
    return record


async def _apply_and_verify(stack, fault, base, ctx, qa, source) -> dict:
    try:
        prepared = await fault.apply(base, ctx)
    except F.Skip as skip:
        return {"status": "skipped", "reason": str(skip)}
    except Exception as exc:  # noqa: BLE001 - a harness error, kept visible
        return {"status": "error", "reason": f"{type(exc).__name__}: {exc}"[:300]}
    out = {"status": "run", "note": prepared.note, "prediction": prepared.prediction}
    try:
        request = to_request(base.agent, base.question, prepared)
    except Exception as exc:  # noqa: BLE001 - a mutated shape the request contract rejects
        return {
            "status": "skipped",
            "reason": f"verification request invalid: {type(exc).__name__}",
        }
    if not qa:
        return out
    stack.interpreter.readings.clear()
    verdict = await stack.verify(request, source)
    return out | summarise_verdict(verdict, stack.interpreter)


async def main() -> None:
    logging.disable(logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--no-qa", action="store_true")
    parser.add_argument("--faults", nargs="*", help="only these fault ids (a smoke run)")
    args = parser.parse_args()
    out = Path(args.out)
    qa = not args.no_qa
    catalogue = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))
    raw = json.loads((out / "base_answers.json").read_text(encoding="utf-8"))
    bases = [F.Base(**{k: v for k, v in b.items() if k != "anchor_for"}) for b in raw["bases"]]
    anchors: dict[str, set[str]] = {}
    for b in raw["bases"]:
        for fid in b.get("anchor_for", []):
            anchors.setdefault(fid, set()).add(b["base_id"])
    by_id = {b.base_id: b for b in bases}

    stack = Stack.open()
    started = time.time()
    results: dict = {
        "catalogue": "catalogue_v1.yaml",
        "seed": G.SEED,
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
        "qa_ran": qa,
        "frozen_sha256": {
            name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
            for name in ("catalogue_v1.yaml", "faults.py", "generate.py", "report_format.md")
        },
        "controls": [],
        "cases": [],
    }
    try:
        before = stack.checksum()
        if qa:
            results["controls"] = await run_controls(stack, bases)
        for entry in catalogue["faults"]:
            fid = entry["id"]
            if args.faults and fid not in args.faults:
                continue
            fault = F.REGISTRY[fid]
            applicable = [
                b
                for b in raw["bases"]
                if fault.agent == b["agent"] and fault.applies(by_id[b["base_id"]])
            ]
            order = G.candidate_order(fid, applicable, anchors.get(fid, set()))
            taken = 0
            for base_id in order:
                if taken >= G.MAX_CASES:
                    break
                record = await run_case(stack, fault, by_id[base_id], qa)
                record["attribute_applicable"] = len(applicable)
                results["cases"].append(record)
                if record["status"] == "run":
                    taken += 1
            results.setdefault("fault_summary", {})[fid] = {
                "applicable_bases": len(applicable),
                "cases_run": taken,
            }
            print(fid, len(applicable), taken, flush=True)
        results["database_before"] = before
        results["database_after"] = stack.checksum()
        results["database_unchanged"] = before == results["database_after"]
    finally:
        stack.close()
    name = "results.json" if qa else "mutation_check.json"
    (out / name).write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    print("wrote", out / name, "database unchanged:", results.get("database_unchanged"))


if __name__ == "__main__":
    asyncio.run(main())
