"""The predictions file every sentiment model writes and `evals/sentiment/score.py` reads.

One CSV per model: `feedback_id`, `split`, `predicted`, then one probability column per
label in `data.LABELS` order. A sidecar `<name>.meta.json` names the model and its config
and says whether it is a diagnostic. BERT writes the same format (ADR-064).
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from ml.sentiment.data import LABELS

PROBA_COLUMNS = tuple(f"p_{label}" for label in LABELS)
HEADER = ("feedback_id", "split", "predicted", *PROBA_COLUMNS)


def meta_path(predictions_path: Path) -> Path:
    return predictions_path.with_name(predictions_path.name.removesuffix(".csv") + ".meta.json")


def write(
    path: Path,
    feedback_ids: Sequence[int],
    splits: Sequence[str],
    proba: np.ndarray,
    meta: dict,
) -> None:
    """Write predictions (argmax of `proba`, columns in LABELS order) and the sidecar."""
    if proba.shape != (len(feedback_ids), len(LABELS)):
        raise ValueError(f"proba has shape {proba.shape}, expected ({len(feedback_ids)}, 4)")
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(HEADER)
    for fid, split, p in zip(feedback_ids, splits, proba, strict=True):
        w.writerow([fid, split, LABELS[int(np.argmax(p))], *(f"{x:.6f}" for x in p)])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf.getvalue().encode("utf-8"))
    meta_path(path).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def read(path: Path) -> tuple[list[dict], dict]:
    """(rows, meta). Each row: feedback_id (int), split, predicted, proba (list of 4)."""
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if tuple(reader.fieldnames or ()) != HEADER:
            raise ValueError(f"{path.name}: header {reader.fieldnames} is not {list(HEADER)}")
        rows = [
            {
                "feedback_id": int(r["feedback_id"]),
                "split": r["split"],
                "predicted": r["predicted"],
                "proba": [float(r[c]) for c in PROBA_COLUMNS],
            }
            for r in reader
        ]
    meta = json.loads(meta_path(path).read_text(encoding="utf-8"))
    return rows, meta


def ordered_proba(model_classes: Sequence[str], proba: np.ndarray) -> np.ndarray:
    """Reorder a scikit-learn `predict_proba` matrix from `classes_` order to LABELS order."""
    index = [list(model_classes).index(label) for label in LABELS]
    return proba[:, index]
