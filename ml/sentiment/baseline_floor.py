"""Two DIAGNOSTIC floors for the sentiment baselines (ADR-064). Not candidate models.

    python -m ml.sentiment.baseline_floor [--out-date YYYY-MM-DD]

- `diagnostic_majority`: always the most frequent training class; probabilities are the
  training class shares.
- `diagnostic_length_logreg`: logistic regression on word count and character count only
  (standardised, `class_weight="balanced"`, no tuning). It tests whether length alone
  separates the classes, which ADR-036's per-cell length rules could make possible.

Reads as `app_train` with split v1 (hash-verified), trains on train, and writes validation
and test predictions in the shared format, with `"diagnostic": true` in the sidecar.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from ml.sentiment import data, predictions
from ml.sentiment.baseline_tfidf import RESULTS_ROOT, SEED, load_split_rows


def length_features(texts: list[str]) -> np.ndarray:
    return np.array([[len(t.split()), len(t)] for t in texts], dtype=float)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out-date", default=date.today().isoformat())
    args = ap.parse_args(argv)
    out = RESULTS_ROOT / f"{args.out_date}_baselines"

    by_split = load_split_rows()
    train = by_split["train"]
    scored = by_split["validation"] + by_split["test"]
    ids = [r.feedback_id for r in scored]
    splits = ["validation"] * len(by_split["validation"]) + ["test"] * len(by_split["test"])
    y_train = [r.true_sentiment for r in train]

    shares = Counter(y_train)
    prior = np.array([shares[label] / len(y_train) for label in data.LABELS])
    predictions.write(
        out / "diagnostic_majority.predictions.csv",
        ids,
        splits,
        np.tile(prior, (len(scored), 1)),
        {
            "model": "diagnostic_majority",
            "diagnostic": True,
            "config": {"rule": "most frequent training class", "trained_on": "train"},
            "split": "v1",
        },
    )

    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(class_weight="balanced", max_iter=5000, random_state=SEED),
    ).fit(length_features([r.feedback_text for r in train]), y_train)
    proba = predictions.ordered_proba(
        model.classes_, model.predict_proba(length_features([r.feedback_text for r in scored]))
    )
    predictions.write(
        out / "diagnostic_length_logreg.predictions.csv",
        ids,
        splits,
        np.asarray(proba),
        {
            "model": "diagnostic_length_logreg",
            "diagnostic": True,
            "config": {
                "features": ["word_count", "char_count"],
                "scaling": "standardised",
                "logreg": {"C": 1.0, "class_weight": "balanced", "max_iter": 5000},
                "trained_on": "train",
            },
            "split": "v1",
            "seed": SEED,
        },
    )
    print(f"DIAGNOSTIC floors written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
