"""Production refit `volume_v2` (ADR-070): fit every slice on all 156 weeks, export, reload.

    python -m ml.forecast.export --folds <date>_folds_v2 [--out-date YYYY-MM-DD]

`volume_v2` is the ADR-069 model plus the calendar year-end indicator (ADR-070); it is the
production model whatever the holdout showed.

Writes `models/forecast/volume_v2/<slice>.json` (gitignored): K, the year-end flag,
coefficients, robust scale, (XᵀWX)⁻¹ and the last training week (everything
`model.forecast_from` needs for the median and intervals), the year-end coefficient with
its 95% CI, the down-weighted weeks and the training-series hash. Floats are written with
`repr`, so they round-trip exactly.

Writes the committed manifest `ml/forecast/artifacts/volume_v2.manifest.json`: file
hashes, the model specification, and from fold B the per-slice x per-band error table,
the corrected-gate verdicts, the 20% ceiling and `gate_rule: "ADR-070"`. QA and
`mcp_volume` read the error table and verdicts from here (ADR-055, ADR-070).

Then the reload check: the artifact is loaded from disk alone, and its 26-week forecasts
must equal the in-memory fit's to 1e-9 for every slice, or this exits non-zero.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

from ml.forecast import data, evaluate, ledger, metrics, model

ARTIFACT = "volume_v2"
ARTIFACT_DIR = ledger.ROOT / "models" / "forecast" / ARTIFACT
MANIFEST = Path(__file__).resolve().parent / "artifacts" / f"{ARTIFACT}.manifest.json"
TOLERANCE = 1e-9


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def slice_record(name: str, counts: np.ndarray, f: model.Fit) -> dict:
    return {
        "slice": name,
        "k": f.k,
        "year_end": f.year_end,
        "year_end_effect": f.year_end_effect(),
        "params": [float(x) for x in f.params],
        "scale": f.scale,
        "xtwx_inv": [[float(x) for x in row] for row in f.xtwx_inv],
        "last_t": f.last_t,
        "train": [data.week_start(0).isoformat(), data.week_start(f.last_t).isoformat()],
        "series_sha256": data.series_sha256(counts),
        "downweighted_weeks": [data.week_start(w).isoformat() for w in f.downweighted()],
        "period": model.PERIOD,
        "horizon_cap": model.HORIZON_CAP,
    }


def load(directory: Path, manifest: dict) -> dict[str, dict]:
    """Every slice's record, hash-checked against the manifest."""
    out = {}
    for name, expected in manifest["files"].items():
        path = directory / name
        if _sha(path) != expected:
            raise RuntimeError(f"{name} does not match the manifest's SHA-256")
        rec = json.loads(path.read_text(encoding="utf-8"))
        out[rec["slice"]] = rec
    return out


def forecast_record(rec: dict, t: np.ndarray) -> dict[str, np.ndarray]:
    return model.forecast_from(
        rec["k"],
        np.array(rec["params"]),
        rec["scale"],
        np.array(rec["xtwx_inv"]),
        rec["last_t"],
        t,
        rec["year_end"],
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--folds", required=True, help="the <date>_folds results folder name")
    ap.add_argument("--out-date", default=dt.date.today().isoformat())
    args = ap.parse_args(argv)

    folds_dir = evaluate.RESULTS / args.folds
    gates = json.loads((folds_dir / "gates.json").read_text(encoding="utf-8"))
    series = data.load_series()
    t_all = np.arange(data.N_WEEKS)
    t_next = np.arange(data.N_WEEKS, data.N_WEEKS + model.HORIZON_CAP)

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    fits, files, records = {}, {}, {}
    for name, counts in series.items():
        f = model.fit(counts[t_all], t_all, year_end=True)
        fits[name] = f
        rec = slice_record(name, counts, f)
        records[name] = rec
        path = ARTIFACT_DIR / f"{name}.json"
        path.write_bytes((json.dumps(rec, indent=1) + "\n").encode("utf-8"))
        files[path.name] = _sha(path)

    commit, dirty = ledger.git_state()
    manifest = {
        "artifact": ARTIFACT,
        "trained_on": [
            data.week_start(0).isoformat(),
            data.week_start(data.N_WEEKS - 1).isoformat(),
        ],
        "series_sha256": {n: r["series_sha256"] for n, r in records.items()},
        "model": {
            "adr": "ADR-069",
            "adr_model": "ADR-070",
            "form": "OLS on log weekly count: intercept, linear trend, a calendar year-end "
            "indicator (ISO weeks containing Dec 25 or Jan 1), K sine/cosine pairs; K by AICc; "
            "robust refit (RLM, Tukey biweight, MAD scale); median point forecast",
            "year_end_indicator": True,
            "period_weeks": model.PERIOD,
            "k_range": [min(model.K_RANGE), max(model.K_RANGE)],
            "tukey_c": model.TUKEY_C,
            "interval_z": model.Z,
            "horizon_cap_weeks": model.HORIZON_CAP,
        },
        "k": {n: f.k for n, f in fits.items()},
        "year_end_effect": {n: f.year_end_effect() for n, f in fits.items()},
        "files": files,
        "gate_rule": "ADR-070",
        "gate": {
            "fold": "fold_B",
            "rule": gates["rule"],
            "ceiling_mape": gates["ceiling_mape"],
            "bands": list(metrics.BANDS),
            "source": f"evals/results/forecast/{args.folds}/gates.json",
            "source_sha256": _sha(folds_dir / "gates.json"),
            "slices": gates["v2_corrected"],
        },
        "git_commit": commit,
        "git_dirty": dirty,
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_bytes((json.dumps(manifest, indent=2) + "\n").encode("utf-8"))

    # Reload check: from disk alone, against the in-memory fits.
    loaded = load(ARTIFACT_DIR, json.loads(MANIFEST.read_text(encoding="utf-8")))
    worst = 0.0
    tables = {}
    for name, f in fits.items():
        mem = model.forecast(f, t_next)
        disk = forecast_record(loaded[name], t_next)
        for key in mem:
            worst = max(worst, float(np.max(np.abs(mem[key] - disk[key]))))
        tables[name] = [
            {
                "week_start": data.week_start(t).isoformat(),
                **{key: round(float(disk[key][i]), 4) for key in disk},
            }
            for i, t in enumerate(t_next)
        ]
    check = {"evidence": "observed", "max_abs_difference": worst, "tolerance": TOLERANCE}
    check["passed"] = worst <= TOLERANCE
    out = evaluate.RESULTS / f"{args.out_date}_{ARTIFACT}"
    evaluate._write(out / "reload_check.json", check)
    evaluate._write(
        out / "production_forecast.json",
        {
            "evidence": "observed",
            "artifact": ARTIFACT,
            "manifest_sha256": _sha(MANIFEST),
            "horizon": [
                data.week_start(t_next[0]).isoformat(),
                data.week_start(t_next[-1]).isoformat(),
            ],
            "k": manifest["k"],
            "downweighted_weeks": {n: r["downweighted_weeks"] for n, r in records.items()},
            "forecast": tables,
        },
    )
    print(json.dumps({"k": manifest["k"], **check}, indent=1))
    if not check["passed"]:
        print("RELOAD CHECK FAILED", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
