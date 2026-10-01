"""Predict validation and test with `bert_v1` and its manifest's T and τ (ADR-066).

    python -m ml.sentiment.predict_bert [--out-date YYYY-MM-DD]

Reads `feedback_text` only, as `app_train`: no label column is selected, so no test label
enters this process. Test is scored once, by `evals/sentiment/score.py`, which records it
in the ledger.

Writes `bert_v1.predictions.csv` (+ `.meta.json`) to
`evals/results/sentiment/<date>_bert_v1/`, in the calibrated format: raw softmax `p_*`,
calibrated `c_*` = softmax(logits / T), and `flagged` = calibrated top-class probability
below τ. Refuses a manifest whose calibration is not filled in.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

import numpy as np

from ml.sentiment import data, export, predictions
from ml.sentiment.calibrate import softmax


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out-date", default=date.today().isoformat())
    args = ap.parse_args(argv)

    model, tokenizer, manifest = export.load_artifact()
    cal = manifest["calibration"]
    if cal["temperature"] is None or cal["threshold"] is None:
        raise SystemExit("manifest has no calibration values; run ml.sentiment.calibrate first")
    t, tau = float(cal["temperature"]), float(cal["threshold"])

    split = data.load_split("v1")
    rows = data.load_texts(("validation", "test"))
    logits = export.predict_logits(model, tokenizer, [x for _, x in rows], manifest["max_length"])
    raw, calibrated = softmax(logits), softmax(logits, t)
    flagged = calibrated.max(axis=1) < tau
    order = sorted(range(len(rows)), key=lambda i: (split[rows[i][0]] != "validation", i))
    out = export.RESULTS_ROOT / f"{args.out_date}_{manifest['artifact']}"
    path = out / f"{manifest['artifact']}.predictions.csv"
    predictions.write(
        path,
        [rows[i][0] for i in order],
        [split[rows[i][0]] for i in order],
        raw[order],
        {
            "model": manifest["artifact"],
            "diagnostic": False,
            "config": {
                "source_run": manifest["source_run"],
                "source_epoch": manifest["source_epoch"],
                "revision": manifest["revision"],
                "max_length": manifest["max_length"],
                "temperature": t,
                "threshold": tau,
                "threshold_rule": cal["threshold_rule"],
                "manifest_sha256": data.sha256_file(export.MANIFEST_PATH),
                "trained_on": "train",
            },
            "split": "v1",
        },
        calibrated=calibrated[order],
        flagged=flagged[order].tolist(),
    )
    n_test = sum(split[fid] == "test" for fid, _ in rows)
    print(
        f"wrote {path.name}: validation {len(rows) - n_test}, test {n_test}; "
        f"flagged {int(np.sum(flagged))} of {len(rows)} at tau={tau:.6f}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
