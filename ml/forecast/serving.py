"""ADR-071's serving rule, written into the `volume_v2` manifest. No refit, no re-scoring.

    python -m ml.forecast.serving --holdout 2026-10-02_holdout --production 2026-10-02_volume_v2

A slice-band is served only if it passes ADR-070's gate on fold B and its `volume_v2`
holdout MAPE is at most 20%. The error shown with it, and used by QA (ADR-055), is the
larger of the two. The holdout errors are read from the committed holdout results.

Before writing, every artifact file is checked against the manifest's SHA-256 (they must
be unchanged), and the artifact is reloaded from disk: its 26-week forecasts must equal the
committed production forecast exactly at that file's 4-decimal precision. The original
1e-9 check compared against an in-memory fit, which would need a refit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys

import numpy as np

from ml.forecast import data, evaluate, export, metrics, model

SERVING_CEILING = 20.0
V2 = "loglinear_robust_v2"


def serve(gate_pass: bool, holdout_mape: float, ceiling: float = SERVING_CEILING) -> bool:
    return bool(gate_pass) and holdout_mape <= ceiling


def serving_table(gate_slices: dict, holdout_slices: dict) -> dict:
    """slice -> band -> foldB_mape, holdout_mape, gate_ADR070, served, shown_error."""
    out = {}
    for name, g in gate_slices.items():
        out[name] = {}
        for band in metrics.BANDS:
            fold_b = g["bands"][band]["model_mape"]
            holdout = holdout_slices[name]["model"][band]["mape"]
            gate_pass = g["bands"][band]["pass"]
            out[name][band] = {
                "foldB_mape": fold_b,
                "holdout_mape": holdout,
                "gate_ADR070": gate_pass,
                "served": serve(gate_pass, holdout),
                "shown_error": max(fold_b, holdout),
            }
    return out


def served_set(table: dict) -> list[tuple[str, str]]:
    return [(s, b) for s, bands in table.items() for b, v in bands.items() if v["served"]]


def verify_artifact(manifest: dict, production: dict) -> dict:
    """File hashes unchanged, and reloaded forecasts equal the committed production ones."""
    loaded = export.load(export.ARTIFACT_DIR, manifest)  # raises on any hash mismatch
    t_next = np.arange(data.N_WEEKS, data.N_WEEKS + model.HORIZON_CAP)
    mismatches = 0
    for name, rec in loaded.items():
        fc = export.forecast_record(rec, t_next)
        for i, row in enumerate(production["forecast"][name]):
            for key in fc:
                if round(float(fc[key][i]), 4) != row[key]:
                    mismatches += 1
    return {
        "files_checked": len(manifest["files"]),
        "hashes_unchanged": True,
        "forecast_mismatches": mismatches,
        "compared_to": "committed production_forecast.json (4 decimals)",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--holdout", required=True)
    ap.add_argument("--production", required=True)
    args = ap.parse_args(argv)

    manifest = json.loads(export.MANIFEST.read_text(encoding="utf-8"))
    holdout_path = evaluate.RESULTS / args.holdout / "holdout.json"
    holdout = json.loads(holdout_path.read_text(encoding="utf-8"))
    production = json.loads(
        (evaluate.RESULTS / args.production / "production_forecast.json").read_text("utf-8")
    )
    check = verify_artifact(manifest, production)
    print(json.dumps(check, indent=1))
    if check["forecast_mismatches"]:
        print("RELOAD CHECK FAILED", file=sys.stderr)
        return 1

    table = serving_table(manifest["gate"]["slices"], holdout["models"][V2])
    files_before = dict(manifest["files"])
    manifest["holdout"] = {
        "window": [evaluate.HOLDOUT.test_start.isoformat(), evaluate.HOLDOUT.test_end.isoformat()],
        "source": holdout_path.relative_to(evaluate.ledger.ROOT).as_posix(),
        "source_sha256": hashlib.sha256(holdout_path.read_bytes()).hexdigest(),
        "slices": {
            name: {band: r["model"][band]["mape"] for band in ("overall", *metrics.BANDS)}
            for name, r in holdout["models"][V2].items()
        },
    }
    manifest["serving_rule"] = "ADR-071"
    manifest["serving"] = {
        "rule": "served only if the slice-band passes ADR-070's gate on fold B and its volume_v2 "
        "holdout MAPE is at most 20%; shown_error is the larger of the two (ADR-071)",
        "ceiling_mape": SERVING_CEILING,
        "slices": table,
    }
    assert manifest["files"] == files_before
    export.MANIFEST.write_bytes((json.dumps(manifest, indent=2) + "\n").encode("utf-8"))
    print("served:", served_set(table))
    return 0


if __name__ == "__main__":
    sys.exit(main())
