"""Criterion 1 of ADR-095: QA's recompute equals `forecast_runtime`'s unrounded output.

QA's code (`agent_qa.forecast_model`, pure Python) is compared with the runtime's
(`forecast_runtime.forecast_record`, numpy) for every slice and horizon 1 to 26, on the weekly
point and the four interval ends, to 1e-9 relative. The records are synthetic (the real files are
not in git), plus the real `volume_v2` files when they are present in `models/`. The largest
relative difference per number type is printed (`pytest -s`) and recorded in the ADR's result.
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

import numpy as np
import pytest
from agent_qa.forecast_model import ForecastModel
from forecast_runtime import HORIZON_CAP, N_WEEKS, forecast_record

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "ml" / "forecast" / "artifacts" / "volume_v2.manifest.json"
REAL_DIR = ROOT / "models" / "forecast" / "volume_v2"
SLICES = ("total", "inspection", "install", "maintenance", "repair", "upgrade")
NUMBERS = ("point", "lo80", "hi80", "lo95", "hi95")
RUNTIME_KEY = {"point": "median"}
TOL = 1e-9


def synthetic_record(slice_: str, rng: random.Random, k: int) -> dict:
    width = 2 + 1 + 2 * k
    a = np.array([[rng.uniform(-1, 1) for _ in range(width)] for _ in range(width)])
    spd = (a @ a.T) * 1e-4 + np.eye(width) * 1e-3  # symmetric positive definite
    return {
        "slice": slice_,
        "k": k,
        "year_end": True,
        "params": [4.5, 0.0015, -0.15] + [rng.uniform(-0.1, 0.1) for _ in range(2 * k)],
        "scale": rng.uniform(0.05, 0.2),
        "xtwx_inv": spd.tolist(),
        "last_t": N_WEEKS - 1,
        "period": 52.1775,
        "horizon_cap": 26,
    }


def build(tmp_path: Path, recs: list[dict]) -> tuple[ForecastModel, dict[str, dict]]:
    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    doc["files"] = {}
    for rec in recs:
        raw = json.dumps(rec).encode()
        (tmp_path / f"{rec['slice']}.json").write_bytes(raw)
        doc["files"][f"{rec['slice']}.json"] = hashlib.sha256(raw).hexdigest()
    return ForecastModel.load(tmp_path, doc), {r["slice"]: r for r in recs}


def compare(model: ForecastModel, recs: dict[str, dict]) -> dict[str, float]:
    worst = dict.fromkeys(NUMBERS, 0.0)
    t = np.arange(N_WEEKS, N_WEEKS + HORIZON_CAP)
    for name, rec in recs.items():
        want = forecast_record(rec, t)
        for h in range(1, HORIZON_CAP + 1):
            got = model.predict(name, h)
            for key in NUMBERS:
                ref = float(want[RUNTIME_KEY.get(key, key)][h - 1])
                worst[key] = max(worst[key], abs(got[key] - ref) / abs(ref))
    return worst


def test_qa_recompute_equals_the_runtime_on_synthetic_records(tmp_path):
    rng = random.Random(20261011)
    recs = [synthetic_record(s, rng, k) for s, k in zip(SLICES, (0, 2, 2, 6, 2, 1), strict=True)]
    model, by_slice = build(tmp_path, recs)
    worst = compare(model, by_slice)
    print("synthetic max relative difference:", worst)
    assert all(v <= TOL for v in worst.values()), worst


@pytest.mark.skipif(not REAL_DIR.is_dir(), reason="the volume_v2 files are not in git")
def test_qa_recompute_equals_the_runtime_on_the_real_volume_v2_files():
    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    model = ForecastModel.load(REAL_DIR, doc)
    recs = {s: json.loads((REAL_DIR / f"{s}.json").read_text(encoding="utf-8")) for s in SLICES}
    worst = compare(model, recs)
    print("real volume_v2 max relative difference:", worst)
    assert all(v <= TOL for v in worst.values()), worst
