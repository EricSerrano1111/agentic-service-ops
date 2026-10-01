"""TF-IDF plus logistic regression, the required sentiment baseline (ADR-059, ADR-064).

    python -m ml.sentiment.baseline_tfidf [--out-date YYYY-MM-DD]

Reads training rows as `app_train` and split v1 (hash-verified). Fits every config of a
fixed six-config grid on train, selects by validation macro-F1, and writes validation and
test predictions for the selected config. Test labels are never looked at here: test is
scored once, by `evals/sentiment/score.py`, which records it in the ledger.

The grid is the whole search and is never extended (ADR-064): features are word 1-2-grams
or `char_wb` 2-5-grams, and C is 0.1, 1 or 10. Everything else is fixed: TfidfVectorizer
defaults otherwise (lowercase, min_df=1), and LogisticRegression with
`class_weight="balanced"`, lbfgs, max_iter=5000. Ties go to the earlier config in grid
order. The model sees `feedback_text` only.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.pipeline import make_pipeline

from ml.sentiment import data, predictions

SEED = 20261001
MODEL = "tfidf_logreg"
FEATURES = {
    "word_1_2": {"analyzer": "word", "ngram_range": (1, 2)},
    "char_wb_2_5": {"analyzer": "char_wb", "ngram_range": (2, 5)},
}
CS = (0.1, 1.0, 10.0)
GRID = [{"features": f, "C": c} for f in FEATURES for c in CS]
#: L-26 follow-up only: larger C, validation only. Never used to select or re-score.
EXTENSION_CS = (30.0, 100.0)
RESULTS_ROOT = data.ROOT / "evals" / "results" / "sentiment"


def build(config: dict):
    return make_pipeline(
        TfidfVectorizer(**FEATURES[config["features"]]),
        LogisticRegression(
            C=config["C"], class_weight="balanced", max_iter=5000, random_state=SEED
        ),
    )


def load_split_rows(
    splits: tuple[str, ...] = data.SPLITS,
) -> dict[str, list[data.FeedbackRow]]:
    split = data.load_split("v1")
    rows = data.load_training_rows(splits)
    if {r.feedback_id for r in rows} != {fid for fid, s in split.items() if s in splits}:
        raise SystemExit("database rows and split_v1 disagree on the set of feedback_ids")
    by_split: dict[str, list[data.FeedbackRow]] = {s: [] for s in splits}
    for r in rows:
        by_split[split[r.feedback_id]].append(r)
    return by_split


def grid_extension(out) -> int:
    """L-26 follow-up: C in EXTENSION_CS on validation only. Test is never fetched."""
    by_split = load_split_rows(("train", "validation"))
    train, val = by_split["train"], by_split["validation"]
    x_train, y_train = [r.feedback_text for r in train], [r.true_sentiment for r in train]
    x_val, y_val = [r.feedback_text for r in val], [r.true_sentiment for r in val]
    rows = []
    for features in FEATURES:
        for c in EXTENSION_CS:
            config = {"features": features, "C": c}
            pred = build(config).fit(x_train, y_train).predict(x_val)
            rows.append(
                {
                    **config,
                    "val_macro_f1": round(float(f1_score(y_val, pred, average="macro")), 4),
                    "val_accuracy": round(float(accuracy_score(y_val, pred)), 4),
                }
            )
            print(f"{features:12} C={c:<6} macro-F1 {rows[-1]['val_macro_f1']:.4f}")
    path = out / "grid_extension_validation_only.json"
    path.write_text(
        json.dumps(
            {
                "purpose": "L-26 follow-up; validation only; selected config unchanged; "
                "test not fetched",
                "date": date.today().isoformat(),
                "results": rows,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out-date", default=date.today().isoformat())
    ap.add_argument(
        "--grid-extension",
        action="store_true",
        help="L-26 follow-up: C in {30, 100}, validation only; writes nothing else",
    )
    args = ap.parse_args(argv)
    out = RESULTS_ROOT / f"{args.out_date}_baselines"
    if args.grid_extension:
        return grid_extension(out)

    by_split = load_split_rows()
    train, val = by_split["train"], by_split["validation"]
    x_train, y_train = [r.feedback_text for r in train], [r.true_sentiment for r in train]
    x_val, y_val = [r.feedback_text for r in val], [r.true_sentiment for r in val]
    print(f"train {len(train)}, validation {len(val)}, test {len(by_split['test'])}")

    grid_rows = []
    for config in GRID:
        model = build(config).fit(x_train, y_train)
        pred = model.predict(x_val)
        row = {
            **config,
            "val_macro_f1": round(float(f1_score(y_val, pred, average="macro")), 4),
            "val_accuracy": round(float(accuracy_score(y_val, pred)), 4),
        }
        grid_rows.append(row)
        print(f"{config['features']:12} C={config['C']:<5} macro-F1 {row['val_macro_f1']:.4f}")
    best = max(range(len(GRID)), key=lambda i: (grid_rows[i]["val_macro_f1"], -i))
    selected = GRID[best]
    print(f"selected: {selected}")

    out.mkdir(parents=True, exist_ok=True)
    (out / "tfidf_validation_grid.json").write_text(
        json.dumps(grid_rows, indent=2) + "\n", encoding="utf-8"
    )
    (out / "tfidf_selected_config.json").write_text(
        json.dumps({**selected, "selected_by": "validation macro-F1", **grid_rows[best]}, indent=2)
        + "\n",
        encoding="utf-8",
    )

    model = build(selected).fit(x_train, y_train)
    scored = val + by_split["test"]
    proba = predictions.ordered_proba(
        model.classes_, model.predict_proba([r.feedback_text for r in scored])
    )
    predictions.write(
        out / f"{MODEL}.predictions.csv",
        [r.feedback_id for r in scored],
        ["validation"] * len(val) + ["test"] * len(by_split["test"]),
        np.asarray(proba),
        {
            "model": MODEL,
            "diagnostic": False,
            "config": {
                **selected,
                "tfidf": {
                    k: list(v) if isinstance(v, tuple) else v
                    for k, v in FEATURES[selected["features"]].items()
                },
                "logreg": {"class_weight": "balanced", "max_iter": 5000, "solver": "lbfgs"},
                "trained_on": "train",
            },
            "split": "v1",
            "seed": SEED,
        },
    )
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
