"""Score a sentiment predictions file against gold labels (ADR-040, ADR-064).

    python -m evals.sentiment.score <predictions.csv> --split validation|test

Gold labels are read as `app_eval`, never as a runtime role; neutral kinds and judge
labels come from the committed corpus via `corpus_id`. Every model, BERT included, is
scored by this file unchanged.

Reports macro-F1 (headline), accuracy, per-class precision/recall/F1, the confusion matrix
(rows true, columns predicted, in `LABELS` order), hard-case accuracy for sarcastic and
implicit with n and the judge's disagreement rate on the same rows, neutral accuracy by
neutral kind with n, and mixed-class recall and F1, called out separately.

For a calibrated predictions file (calibrated probabilities and a `flagged` column,
ADR-066) it also reports ECE (15 equal-width bins) on the raw and the calibrated
probabilities, the flag rate, accuracy on un-flagged and on flagged predictions, and the
share of the model's errors that are flagged, overall and for sarcastic, implicit and
mixed (true label) comments.

**Test is scored once per model.** A test scoring appends one line to
`evals/results/sentiment/test_ledger.jsonl` (date, model, config, git commit) and is
refused if that model already has a line. The ledger is append-only.

Writes `<predictions stem>.<split>.metrics.json` next to the predictions file.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from collections.abc import Mapping
from datetime import date
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support

from ml.sentiment import data, predictions
from ml.sentiment.calibrate import N_BINS, ece_from_proba

LEDGER = data.ROOT / "evals" / "results" / "sentiment" / "test_ledger.jsonl"
HARD_CASE_TYPES = ("sarcastic", "implicit")
ERROR_SUBSETS = ("sarcastic", "implicit", "mixed")


class LedgerRefusal(RuntimeError):
    """This model has already been scored on test."""


def _accuracy(pairs: list[tuple[str, str]]) -> float | None:
    return round(sum(t == p for t, p in pairs) / len(pairs), 4) if pairs else None


def compute(
    rows: list[dict],
    gold: Mapping[int, data.GoldLabel],
    corpus: Mapping[str, data.CorpusMeta],
) -> dict:
    """Every metric for one split's predictions. Pure: no I/O."""
    y_true = [gold[r["feedback_id"]].true_sentiment for r in rows]
    y_pred = [r["predicted"] for r in rows]
    labels = list(data.LABELS)
    p, r, f, s = precision_recall_fscore_support(y_true, y_pred, labels=labels, zero_division=0)
    per_class = {
        label: {
            "precision": round(float(p[i]), 4),
            "recall": round(float(r[i]), 4),
            "f1": round(float(f[i]), 4),
            "support": int(s[i]),
        }
        for i, label in enumerate(labels)
    }

    hard = {}
    for kind in HARD_CASE_TYPES:
        subset = [x for x in rows if gold[x["feedback_id"]].hard_case_type == kind]
        judged = [corpus[gold[x["feedback_id"]].corpus_id].judge_disagreement for x in subset]
        hard[kind] = {
            "n": len(subset),
            "accuracy": _accuracy(
                [(gold[x["feedback_id"]].true_sentiment, x["predicted"]) for x in subset]
            ),
            "judge_disagreement_rate": round(sum(judged) / len(judged), 4) if judged else None,
        }

    by_kind: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for x in rows:
        g = gold[x["feedback_id"]]
        if g.true_sentiment == "neutral":
            by_kind[str(corpus[g.corpus_id].neutral_kind)].append(("neutral", x["predicted"]))
    neutral = {k: {"n": len(v), "accuracy": _accuracy(v)} for k, v in sorted(by_kind.items())}

    result = {
        "n": len(rows),
        "macro_f1": round(float(np.mean(f)), 4),
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "per_class": per_class,
        "confusion_matrix": {
            "labels": labels,
            "rows_true_columns_predicted": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
        },
        "hard_cases": hard,
        "neutral_by_kind": neutral,
        "mixed": {
            "recall": per_class["mixed"]["recall"],
            "f1": per_class["mixed"]["f1"],
            "n": per_class["mixed"]["support"],
        },
    }
    if rows and all("calibrated" in x for x in rows):
        result["calibration"] = calibration_metrics(rows, gold)
    return result


def _in_subset(g: data.GoldLabel, subset: str) -> bool:
    return g.true_sentiment == "mixed" if subset == "mixed" else g.hard_case_type == subset


def calibration_metrics(rows: list[dict], gold: Mapping[int, data.GoldLabel]) -> dict:
    """ADR-066's calibration and review-flag figures. Pure: no I/O."""
    index = {label: i for i, label in enumerate(data.LABELS)}
    y = np.array([index[gold[x["feedback_id"]].true_sentiment] for x in rows])
    correct = np.array([gold[x["feedback_id"]].true_sentiment == x["predicted"] for x in rows])
    flagged = np.array([x["flagged"] for x in rows])

    def errors_flagged(mask: np.ndarray) -> dict:
        wrong = mask & ~correct
        n_err = int(wrong.sum())
        n_flag = int((wrong & flagged).sum())
        return {
            "n": int(mask.sum()),
            "errors": n_err,
            "errors_flagged": n_flag,
            "share_flagged": round(n_flag / n_err, 4) if n_err else None,
        }

    everyone = np.ones(len(rows), dtype=bool)
    return {
        "n_bins": N_BINS,
        "ece_raw": round(ece_from_proba(np.array([x["proba"] for x in rows]), y), 4),
        "ece_calibrated": round(ece_from_proba(np.array([x["calibrated"] for x in rows]), y), 4),
        "n_flagged": int(flagged.sum()),
        "flag_rate": round(float(flagged.mean()), 4),
        "accuracy_unflagged": round(float(correct[~flagged].mean()), 4)
        if (~flagged).any()
        else None,
        "accuracy_flagged": round(float(correct[flagged].mean()), 4) if flagged.any() else None,
        "errors_flagged": {
            "overall": errors_flagged(everyone),
            **{
                k: errors_flagged(np.array([_in_subset(gold[x["feedback_id"]], k) for x in rows]))
                for k in ERROR_SUBSETS
            },
        },
    }


def select_split(rows: list[dict], split_name: str, split: Mapping[int, str]) -> list[dict]:
    """The rows for `split_name`, which must cover that split of split v1 exactly."""
    chosen = [r for r in rows if r["split"] == split_name]
    expected = {fid for fid, s in split.items() if s == split_name}
    got = [r["feedback_id"] for r in chosen]
    if len(got) != len(set(got)) or set(got) != expected:
        raise ValueError(
            f"predictions for {split_name!r} cover {len(set(got))} ids ({len(got)} rows); "
            f"split v1 has {len(expected)}, and the sets must match exactly"
        )
    for r in chosen:
        if r["split"] != split[r["feedback_id"]]:
            raise ValueError(f"feedback_id {r['feedback_id']} is labelled with the wrong split")
        if r["predicted"] not in data.LABELS:
            raise ValueError(f"unknown predicted label {r['predicted']!r}")
    return chosen


def _git() -> tuple[str, bool]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=data.ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    # Tracked changes only: new result files are expected to be untracked at this point.
    dirty = subprocess.run(["git", "diff", "--quiet", "HEAD"], cwd=data.ROOT).returncode != 0
    return head, dirty


def check_not_scored(model: str, ledger: Path | None = None) -> None:
    """Refuse a model that already has a test line. Called before any label is read."""
    ledger = ledger or LEDGER
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            if line.strip() and json.loads(line)["model"] == model:
                raise LedgerRefusal(
                    f"{model} was already scored on test. Test is scored once per "
                    "model (ADR-064); choose settings on validation."
                )


def append_ledger(entry: dict, ledger: Path | None = None) -> None:
    """Append one test scoring; refuse a model that already has a line."""
    ledger = ledger or LEDGER
    check_not_scored(entry["model"], ledger)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("predictions", type=Path)
    ap.add_argument("--split", required=True, choices=("validation", "test"))
    args = ap.parse_args(argv)

    rows, meta = predictions.read(args.predictions)
    if args.split == "test":
        check_not_scored(meta["model"])  # before any gold label is read
    split = data.load_split("v1")
    chosen = select_split(rows, args.split, split)
    metrics = compute(chosen, data.load_gold_labels(), data.load_corpus_meta())
    tag = "DIAGNOSTIC " if meta.get("diagnostic") else ""
    result = {
        "model": meta["model"],
        "diagnostic": bool(meta.get("diagnostic")),
        "split": args.split,
        "split_version": "v1",
        **metrics,
    }

    if args.split == "test":
        commit, dirty = _git()
        append_ledger(
            {
                "date": date.today().isoformat(),
                "model": meta["model"],
                "diagnostic": bool(meta.get("diagnostic")),
                "config": meta.get("config"),
                "git_commit": commit,
                "git_dirty": dirty,
                "split": "v1",
                "split_sha256": data.sha256_file(data.split_paths("v1")[0]),
                "predictions": args.predictions.name,
                "predictions_sha256": data.sha256_file(args.predictions),
                "macro_f1": metrics["macro_f1"],
            }
        )

    out = args.predictions.with_name(
        args.predictions.name.removesuffix(".predictions.csv") + f".{args.split}.metrics.json"
    )
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        f"{tag}{meta['model']} on {args.split} (n={metrics['n']}): "
        f"macro-F1 {metrics['macro_f1']:.4f}, accuracy {metrics['accuracy']:.4f}"
    )
    print(
        json.dumps(
            {
                k: metrics[k]
                for k in (
                    "per_class",
                    "hard_cases",
                    "neutral_by_kind",
                    "mixed",
                    "confusion_matrix",
                    "calibration",
                )
                if k in metrics
            },
            indent=1,
        )
    )
    print(f"wrote {out.name}" + ("; ledger appended" if args.split == "test" else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
