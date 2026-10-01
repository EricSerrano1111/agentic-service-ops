"""The predictions file every sentiment model writes and `evals/sentiment/score.py` reads.

One CSV per model: `feedback_id`, `split`, `predicted`, then one probability column per
label in `data.LABELS` order. A sidecar `<name>.meta.json` names the model and its config
and says whether it is a diagnostic. BERT writes the same format (ADR-064).

A calibrated model (ADR-066) appends one calibrated probability column per label
(`c_<label>`) and a `flagged` column (1 if the calibrated top-class probability is below
the review threshold, else 0). `p_<label>` stays the raw softmax, so ECE can be compared
before and after calibration from the one file.
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
CALIBRATED_COLUMNS = tuple(f"c_{label}" for label in LABELS)
CALIBRATED_HEADER = (*HEADER, *CALIBRATED_COLUMNS, "flagged")


def meta_path(predictions_path: Path) -> Path:
    return predictions_path.with_name(predictions_path.name.removesuffix(".csv") + ".meta.json")


def write(
    path: Path,
    feedback_ids: Sequence[int],
    splits: Sequence[str],
    proba: np.ndarray,
    meta: dict,
    calibrated: np.ndarray | None = None,
    flagged: Sequence[bool] | None = None,
) -> None:
    """Write predictions (argmax of `proba`, columns in LABELS order) and the sidecar.

    With `calibrated` and `flagged`, writes the calibrated format. Calibration must not
    change the predicted class.
    """
    if proba.shape != (len(feedback_ids), len(LABELS)):
        raise ValueError(f"proba has shape {proba.shape}, expected ({len(feedback_ids)}, 4)")
    if (calibrated is None) != (flagged is None):
        raise ValueError("calibrated and flagged go together")
    if calibrated is not None:
        if calibrated.shape != proba.shape or len(flagged) != len(feedback_ids):
            raise ValueError("calibrated/flagged do not match proba")
        if not np.array_equal(calibrated.argmax(1), proba.argmax(1)):
            raise ValueError("calibration changed a predicted class")
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(HEADER if calibrated is None else CALIBRATED_HEADER)
    for i, (fid, split, p) in enumerate(zip(feedback_ids, splits, proba, strict=True)):
        row = [fid, split, LABELS[int(np.argmax(p))], *(f"{x:.6f}" for x in p)]
        if calibrated is not None:
            row += [*(f"{x:.6f}" for x in calibrated[i]), int(bool(flagged[i]))]
        w.writerow(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf.getvalue().encode("utf-8"))
    meta_path(path).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def read(path: Path) -> tuple[list[dict], dict]:
    """(rows, meta). Each row: feedback_id (int), split, predicted, proba (list of 4).

    A calibrated file's rows also carry `calibrated` (list of 4) and `flagged` (bool).
    """
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        header = tuple(reader.fieldnames or ())
        if header not in (HEADER, CALIBRATED_HEADER):
            raise ValueError(f"{path.name}: header {reader.fieldnames} is not {list(HEADER)}")
        rows = []
        for r in reader:
            row = {
                "feedback_id": int(r["feedback_id"]),
                "split": r["split"],
                "predicted": r["predicted"],
                "proba": [float(r[c]) for c in PROBA_COLUMNS],
            }
            if header == CALIBRATED_HEADER:
                if r["flagged"] not in ("0", "1"):
                    raise ValueError(f"{path.name}: flagged must be 0 or 1, not {r['flagged']!r}")
                row["calibrated"] = [float(r[c]) for c in CALIBRATED_COLUMNS]
                row["flagged"] = r["flagged"] == "1"
            rows.append(row)
    meta = json.loads(meta_path(path).read_text(encoding="utf-8"))
    return rows, meta


def ordered_proba(model_classes: Sequence[str], proba: np.ndarray) -> np.ndarray:
    """Reorder a scikit-learn `predict_proba` matrix from `classes_` order to LABELS order."""
    index = [list(model_classes).index(label) for label in LABELS]
    return proba[:, index]
