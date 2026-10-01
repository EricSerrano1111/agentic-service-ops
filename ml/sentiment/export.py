"""Export the selected BERT checkpoint as artifact `bert_v1` (ADR-066).

    python -m ml.sentiment.export            # export, then the reload check
    python -m ml.sentiment.export --verify   # reload check only

The selected model is `lr2e-5_v1` at epoch 4, by ADR-065's rule; nothing here selects.

Writes `models/sentiment/bert_v1/` (gitignored): `model.safetensors` (copied byte for
byte from the checkpoint, no optimiser state), `config.json` (the checkpoint's, with the
label names added), the tokenizer files of the pinned revision, and `label_map.json`.
Writes the committed manifest `ml/sentiment/artifacts/bert_v1.manifest.json`: source run
and epoch, revision, `max_length`, label order, a SHA-256 per artifact file, and the
calibration fields, which stay null until `calibrate.py` fills them. Re-exporting keeps
calibration values already in the manifest only if every file hash is unchanged.

The reload check loads `bert_v1` from disk alone (hashes verified, no Hub access), predicts
validation, and requires the predicted class to match the training checkpoint's own
validation predictions on every comment and macro-F1 to reproduce the run's 0.9767. It
exits non-zero on any mismatch.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import numpy as np

from ml.sentiment import config, data, predictions

MODELS_ROOT = data.ROOT / "models" / "sentiment"
ARTIFACT = "bert_v1"
SOURCE_RUN = "lr2e-5_v1"
SOURCE_EPOCH = 4
ARTIFACT_DIR = MODELS_ROOT / ARTIFACT
MANIFEST_PATH = Path(__file__).resolve().parent / "artifacts" / f"{ARTIFACT}.manifest.json"
RESULTS_ROOT = data.ROOT / "evals" / "results" / "sentiment"
INFERENCE_BATCH = 64  # what training's validation pass used (batch 16 x 4)
EMPTY_CALIBRATION = {
    "method": "temperature_scaling",
    "fitted_on": "validation",
    "temperature": None,
    "threshold": None,
    "threshold_rule": None,
}


class ArtifactIntegrityError(RuntimeError):
    """An artifact file is missing or does not match the manifest's SHA-256."""


def _source_run() -> dict:
    return json.loads((MODELS_ROOT / SOURCE_RUN / "run.json").read_text(encoding="utf-8"))


def export(out: Path = ARTIFACT_DIR, manifest_path: Path = MANIFEST_PATH) -> dict:
    """Write the artifact folder and its manifest. Returns the manifest."""
    from transformers import AutoConfig, AutoTokenizer

    run = _source_run()
    if run["best_epoch"] != SOURCE_EPOCH or run["git_dirty"]:
        raise SystemExit(f"{SOURCE_RUN}: best epoch {run['best_epoch']}, dirty {run['git_dirty']}")
    ckpt = MODELS_ROOT / SOURCE_RUN / f"epoch_{SOURCE_EPOCH}"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)

    shutil.copyfile(ckpt / "model.safetensors", out / "model.safetensors")
    cfg = AutoConfig.from_pretrained(ckpt)
    cfg.id2label = dict(enumerate(data.LABELS))
    cfg.label2id = {label: i for i, label in enumerate(data.LABELS)}
    cfg.save_pretrained(out)
    AutoTokenizer.from_pretrained(config.MODEL_ID, revision=config.REVISION).save_pretrained(out)
    (out / "label_map.json").write_text(
        json.dumps({"labels": list(data.LABELS)}, indent=2) + "\n", encoding="utf-8"
    )

    files = {p.name: data.sha256_file(p) for p in sorted(out.iterdir()) if p.is_file()}
    if files["model.safetensors"] != data.sha256_file(ckpt / "model.safetensors"):
        raise ArtifactIntegrityError("copied weights differ from the checkpoint")
    calibration = dict(EMPTY_CALIBRATION)
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        if old.get("files") == files:
            calibration = old["calibration"]
    manifest = {
        "artifact": ARTIFACT,
        "source_run": SOURCE_RUN,
        "source_epoch": SOURCE_EPOCH,
        "source_git_commit": run["git_commit"],
        "selected_by": "best validation macro-F1 over runs and epochs (ADR-065, ADR-066)",
        "val_macro_f1": run["val_macro_f1_by_epoch"][str(SOURCE_EPOCH)],
        "model_id": config.MODEL_ID,
        "revision": config.REVISION,
        "max_length": config.MAX_LENGTH,
        "labels": list(data.LABELS),
        "split": "v1",
        "split_sha256": run["split_sha256"],
        "files": files,
        "calibration": calibration,
    }
    write_manifest(manifest, manifest_path)
    return manifest


def write_manifest(manifest: dict, path: Path = MANIFEST_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(manifest, indent=2) + "\n").encode("utf-8"))


def read_manifest(path: Path = MANIFEST_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_files(directory: Path, manifest: dict) -> None:
    """Every file the manifest lists exists with its recorded SHA-256."""
    for name, expected in manifest["files"].items():
        p = directory / name
        if not p.is_file():
            raise ArtifactIntegrityError(f"{name} is missing from {directory}")
        if data.sha256_file(p) != expected:
            raise ArtifactIntegrityError(f"{name} does not match the manifest's SHA-256")


def load_artifact(directory: Path = ARTIFACT_DIR, manifest_path: Path = MANIFEST_PATH):
    """(model, tokenizer, manifest), hash-checked, from local files only."""
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    manifest = read_manifest(manifest_path)
    verify_files(directory, manifest)
    tokenizer = AutoTokenizer.from_pretrained(directory, local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(directory, local_files_only=True)
    model.eval()
    return model, tokenizer, manifest


def predict_logits(model, tokenizer, texts: Sequence[str], max_length: int) -> np.ndarray:
    """Raw logits in `data.LABELS` order, batched as training's validation pass was."""
    import torch

    from ml.sentiment.train_bert import collate, encode

    ids = encode(tokenizer, texts, max_length)
    out = []
    with torch.inference_mode():
        for i in range(0, len(ids), INFERENCE_BATCH):
            batch = collate(ids[i : i + INFERENCE_BATCH], tokenizer.pad_token_id)
            out.append(model(**batch).logits.numpy())
    return np.concatenate(out).astype(np.float64)


def reload_check(out_dir: Path) -> dict:
    """Observed: bert_v1 alone reproduces the checkpoint's validation predictions."""
    from sklearn.metrics import f1_score

    from ml.sentiment.calibrate import softmax
    from ml.sentiment.train_bert import load_rows

    model, tokenizer, manifest = load_artifact()
    val = load_rows(("validation",))["validation"]
    proba = softmax(
        predict_logits(model, tokenizer, [r.feedback_text for r in val], manifest["max_length"])
    )
    pred = [data.LABELS[i] for i in proba.argmax(1)]

    ref_rows, _ = predictions.read(
        MODELS_ROOT / SOURCE_RUN / f"val_epoch_{SOURCE_EPOCH}.predictions.csv"
    )
    ref = {r["feedback_id"]: r for r in ref_rows}
    ids = [r.feedback_id for r in val]
    if set(ids) != set(ref):
        raise SystemExit("validation ids differ from the checkpoint's predictions file")
    matches = sum(ref[fid]["predicted"] == p for fid, p in zip(ids, pred, strict=True))
    max_diff = float(
        max(np.abs(np.array(ref[fid]["proba"]) - proba[i]).max() for i, fid in enumerate(ids))
    )
    f1 = round(
        float(f1_score([r.true_sentiment for r in val], pred, average="macro", labels=data.LABELS)),
        4,
    )
    result = {
        "evidence": "observed",
        "artifact": ARTIFACT,
        "loaded_from": "models/sentiment/bert_v1 only (hashes verified, local_files_only)",
        "reference": f"models/sentiment/{SOURCE_RUN}/val_epoch_{SOURCE_EPOCH}.predictions.csv",
        "n_validation": len(ids),
        "predicted_class_matches": matches,
        "max_abs_probability_difference": round(max_diff, 7),
        "val_macro_f1": f1,
        "expected_val_macro_f1": manifest["val_macro_f1"],
        "passed": matches == len(ids) and f1 == manifest["val_macro_f1"],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "reload_check.json").write_text(json.dumps(result, indent=2) + "\n", "utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--verify", action="store_true", help="reload check only")
    ap.add_argument("--out-date", default=date.today().isoformat())
    args = ap.parse_args(argv)
    if not args.verify:
        manifest = export()
        print(f"exported {ARTIFACT}: {len(manifest['files'])} files; wrote {MANIFEST_PATH.name}")
    result = reload_check(RESULTS_ROOT / f"{args.out_date}_{ARTIFACT}")
    print(json.dumps(result, indent=1))
    if not result["passed"]:
        print("RELOAD CHECK FAILED", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
