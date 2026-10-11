"""Clean false-alarm check for QA's forecast recompute (ADR-095, criterion 2).

    .venv/Scripts/python scripts/qa_forecast_clean_check.py

Runs QA's recompute over unmodified served forecasts and counts mismatches (expected 0):

1. the faults harness's clean base answers (m2's `base_answers.json`,
   byte-identical to measurement 1's): every forecast answer;
2. the recorded end-to-end answers of the forecast agent (`evals/results/forecast_agent/2026-10-02/
   e2e.json`) whose `model_version` equals the current manifest's;
3. a sweep of the serving path itself: for every slice, the weeks `Artifact.forecast` serves for
   horizons 1 to 26 (156 slice-horizon forecasts, the numbers `mcp_volume` returns, unmodified).

Fixtures that carry invented numbers (the agents' unit tests) are not recorded forecasts and are
not included. Neither `evals/golden/` nor `evals/generated/` is opened. No model, no database.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for rel in ("services/agent_qa/src", "services/mcp_volume/src"):
    sys.path.insert(0, str(ROOT / rel))

from agent_qa.forecast import Manifest  # noqa: E402
from mcp_volume.artifact import load_verified  # noqa: E402
from schemas import ForecastAnswer  # noqa: E402

MANIFEST = ROOT / "ml" / "forecast" / "artifacts" / "volume_v2.manifest.json"
MODEL_DIR = ROOT / "models" / "forecast" / "volume_v2"
BASE = ROOT / "evals" / "results" / "qa_faults" / "2026-10-10-m2" / "base_answers.json"
E2E = ROOT / "evals" / "results" / "forecast_agent" / "2026-10-02" / "e2e.json"
OUT = ROOT / "evals" / "results" / "qa_forecast_recompute" / "2026-10-11" / "clean_check.json"


def numbers_in(weeks, has_total: bool) -> int:
    return sum(3 for w in weeks if w["served"]) + (1 if has_total else 0)


def main() -> int:
    manifest = Manifest.load(MANIFEST, MODEL_DIR)
    model = manifest.model
    report: dict = {"manifest_version": manifest.version, "sources": {}}
    mismatches: list[str] = []

    def check_week_numbers(slice_: str, weeks: list[dict], total) -> tuple[int, list[str]]:
        """(numbers compared, mismatching field names). Same comparison as the check."""
        bad: list[str] = []
        compared = 0
        unrounded_total = 0.0
        for w in weeks:
            if not w["served"]:
                continue
            want = model.predict(slice_, w["horizon"])
            unrounded_total += want["point"]
            for name, key in (("point", "point"), ("lo80", "lo80"), ("hi80", "hi80")):
                compared += 1
                if not model.same_when_displayed(w[key], want[name]):
                    bad.append(name)
        if total is not None:
            compared += 1
            if not model.same_when_displayed(total, unrounded_total):
                bad.append("period_total")
        return compared, bad

    # 1. the harness's clean base answers
    base = json.loads(BASE.read_text(encoding="utf-8"))["bases"]
    answers = [b for b in base if b["agent"] == "forecast" and b["kind"] == "answer"]
    n_numbers = 0
    for b in answers:
        a = ForecastAnswer.model_validate(b["answer"])
        d = a.model_dump(mode="json")
        c, bad = check_week_numbers(a.request.slice, d["weeks"], d["period_total"])
        n_numbers += c
        mismatches += [f"{b['base_id']}:{x}" for x in bad]
    report["sources"]["fault_harness_clean_base_answers"] = {
        "forecasts": len(answers),
        "numbers": n_numbers,
    }

    # 2. recorded end-to-end answers on the current artifact
    e2e = json.loads(E2E.read_text(encoding="utf-8"))["runs"]
    used = skipped = n_numbers = 0
    for run in e2e:
        data = run["response"].get("forecast")
        if not data or data.get("unsupported") or "weeks" not in data:
            skipped += 1
            continue
        if data["model_version"] != manifest.version:
            skipped += 1
            continue
        a = ForecastAnswer.model_validate(data)
        d = a.model_dump(mode="json")
        c, bad = check_week_numbers(a.request.slice, d["weeks"], d["period_total"])
        used += 1
        n_numbers += c
        mismatches += [f"e2e:{run['id']}:{x}" for x in bad]
    report["sources"]["recorded_forecast_agent_e2e"] = {
        "forecasts": used,
        "skipped_not_a_forecast_answer": skipped,
        "numbers": n_numbers,
    }

    # 3. the serving path, every slice and horizon
    artifact = load_verified(MODEL_DIR, MANIFEST)
    forecasts = n_numbers = 0
    for slice_ in artifact.slices:
        for horizon in range(1, 27):
            vf = artifact.forecast(slice_, horizon)
            weeks = [w.model_dump(mode="json") for w in vf.weeks]
            served = [w for w in vf.weeks if w.served]
            total = sum(w.point for w in served) if served and len(served) == len(weeks) else None
            c, bad = check_week_numbers(slice_, weeks, total if len(weeks) > 1 else None)
            forecasts += 1
            n_numbers += c
            mismatches += [f"sweep:{slice_}:{horizon}:{x}" for x in bad]
    report["sources"]["serving_path_sweep"] = {"forecasts": forecasts, "numbers": n_numbers}

    report["forecasts_checked"] = sum(s["forecasts"] for s in report["sources"].values())
    report["numbers_checked"] = sum(s["numbers"] for s in report["sources"].values())
    report["mismatches"] = mismatches
    report["boundary_rule_fired"] = model.boundary_fired
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
