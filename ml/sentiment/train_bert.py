"""Fine-tune the pinned `bert-base-uncased` for sentiment (ADR-059, ADR-065).

    python -m ml.sentiment.train_bert --lr 2e-5                    # a full run
    python -m ml.sentiment.train_bert --lr 2e-5 --run-id <id> --resume
    python -m ml.sentiment.train_bert --lr 2e-5 --timing-steps 50  # timing only

A plain PyTorch loop, no `transformers` Trainer, so every step is visible. Everything but
the learning rate is fixed by ADR-065 (`ml/sentiment/config.py`): class-balanced
cross-entropy, AdamW (weight decay 0.01), 10% warmup then linear decay, batch 16, at most
4 epochs with early stopping on validation macro-F1 (patience 1), seed 20261001.

Data comes from split v1 through the hash-verified loader, train and validation only:
`load_rows` refuses the test split, and test rows are filtered out in SQL, so they never
leave the database (as `app_train`). The model sees `feedback_text` only.

Writes `models/sentiment/<run_id>/` (gitignored):
- `epoch_<k>/`: model weights plus optimiser, scheduler and RNG state, written to a temp
  folder and renamed, so a kill or a sleeping machine can't leave a half-written one;
- `state.json`: the latest complete epoch and the best epoch (atomic rename);
- `train_log.jsonl`: step, epoch, loss, seconds per step;
- `val_epoch_<k>.predictions.csv` (+ `.meta.json`): validation predictions per epoch in
  the shared format `evals/sentiment/score.py` reads;
- `run.json`: revision, max_length, learning rate, seed, git commit and dirty flag, torch
  thread count, wall time, and the per-epoch validation macro-F1.

`--resume` continues from the latest complete epoch. Each epoch's data order depends only
on the seed and the epoch number, and the RNG state is restored, so a resumed run
continues exactly as an uninterrupted one would.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import shutil
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import f1_score

from ml.sentiment import config, data, predictions

MODELS_ROOT = data.ROOT / "models" / "sentiment"
LABEL_INDEX = {label: i for i, label in enumerate(data.LABELS)}
RUN_FIELDS = (
    "run_id",
    "model_id",
    "revision",
    "max_length",
    "learning_rate",
    "seed",
    "batch_size",
    "max_epochs",
    "patience",
    "weight_decay",
    "warmup_fraction",
    "class_weights",
    "n_train",
    "n_validation",
    "split",
    "split_sha256",
    "git_commit",
    "git_dirty",
    "torch_version",
    "torch_threads",
    "started_at",
    "wall_time_s",
    "epochs_completed",
    "val_macro_f1_by_epoch",
    "best_epoch",
    "best_val_macro_f1",
    "stopped_early",
)


# --------------------------------------------------------------------------- data


def load_rows(splits: Sequence[str] = ("train", "validation")) -> dict[str, list]:
    """Train and/or validation rows from split v1, as `app_train`. Refuses the test split."""
    if "test" in splits:
        raise ValueError("training never loads the test split (ADR-064, ADR-065)")
    rows = data.load_training_rows(tuple(splits))
    split = data.load_split("v1")
    by_split: dict[str, list] = {s: [] for s in splits}
    for r in rows:
        s = split[r.feedback_id]
        if s not in by_split:  # cannot happen: filtered in SQL; asserted anyway
            raise AssertionError(f"feedback_id {r.feedback_id} is in {s!r}")
        by_split[s].append(r)
    return by_split


def balanced_class_weights(labels: Sequence[str]) -> list[float]:
    """scikit-learn's "balanced": n_samples / (n_classes * count), in `data.LABELS` order."""
    counts = Counter(labels)
    missing = [label for label in data.LABELS if counts[label] == 0]
    if missing:
        raise ValueError(f"no training examples for {missing}")
    n, k = len(labels), len(data.LABELS)
    return [n / (k * counts[label]) for label in data.LABELS]


def encode(tokenizer, texts: Sequence[str], max_length: int) -> list[list[int]]:
    return tokenizer(list(texts), truncation=True, max_length=max_length)["input_ids"]


def collate(batch_ids: Sequence[Sequence[int]], pad_id: int) -> dict[str, torch.Tensor]:
    """Pad to the longest sequence in the batch; mask the padding."""
    width = max(len(x) for x in batch_ids)
    ids = torch.full((len(batch_ids), width), pad_id, dtype=torch.long)
    mask = torch.zeros((len(batch_ids), width), dtype=torch.long)
    for i, x in enumerate(batch_ids):
        ids[i, : len(x)] = torch.tensor(x, dtype=torch.long)
        mask[i, : len(x)] = 1
    return {"input_ids": ids, "attention_mask": mask}


def epoch_order(n: int, epoch: int, seed: int) -> list[int]:
    """The shuffle for one epoch: depends on the seed and epoch only, so resume is exact."""
    g = torch.Generator().manual_seed(seed * 1000 + epoch)
    return torch.randperm(n, generator=g).tolist()


# --------------------------------------------------------------------------- run setup


@dataclass
class TrainSettings:
    learning_rate: float
    run_id: str
    max_length: int = config.MAX_LENGTH
    batch_size: int = config.BATCH_SIZE
    max_epochs: int = config.MAX_EPOCHS
    patience: int = config.PATIENCE
    weight_decay: float = config.WEIGHT_DECAY
    warmup_fraction: float = config.WARMUP_FRACTION
    seed: int = config.SEED
    timing_steps: int | None = None
    extra: dict = field(default_factory=dict)


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    # Deterministic kernels where the CPU build supports them; warn rather than fail on
    # the rest, so the run still proceeds and the warning is visible in the log.
    torch.use_deterministic_algorithms(True, warn_only=True)


def git_state() -> tuple[str, bool]:
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=data.ROOT, capture_output=True, text=True
        ).stdout.strip()
        dirty = subprocess.run(["git", "diff", "--quiet", "HEAD"], cwd=data.ROOT).returncode != 0
        return head or "unknown", dirty
    except OSError:
        return "unknown", True


def linear_warmup_decay(total_steps: int, warmup_steps: int) -> Callable[[int], float]:
    def factor(step: int) -> float:
        if step < warmup_steps:
            return (step + 1) / max(1, warmup_steps)
        return max(0.0, (total_steps - step) / max(1, total_steps - warmup_steps))

    return factor


def _write_json_atomic(path: Path, obj: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def save_checkpoint(run_dir: Path, epoch: int, model, optimizer, scheduler, step: int) -> None:
    """Write epoch_<k>/ via a temp folder and a rename: never a half-written checkpoint."""
    final = run_dir / f"epoch_{epoch}"
    tmp = run_dir / f".epoch_{epoch}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    model.save_pretrained(tmp, safe_serialization=True)
    torch.save(
        {
            "optimizer": optimizer.state_dict(),
            "scheduler": scheduler.state_dict(),
            "torch_rng": torch.get_rng_state(),
            "numpy_rng": np.random.get_state(),
            "python_rng": random.getstate(),
            "step": step,
            "epoch": epoch,
        },
        tmp / "trainer_state.pt",
    )
    shutil.rmtree(final, ignore_errors=True)
    os.replace(tmp, final)


def load_checkpoint(run_dir: Path, epoch: int, model, optimizer, scheduler) -> int:
    from safetensors.torch import load_file

    ckpt = run_dir / f"epoch_{epoch}"
    model.load_state_dict(load_file(ckpt / "model.safetensors"))
    state = torch.load(ckpt / "trainer_state.pt", weights_only=False)
    optimizer.load_state_dict(state["optimizer"])
    scheduler.load_state_dict(state["scheduler"])
    torch.set_rng_state(state["torch_rng"])
    np.random.set_state(state["numpy_rng"])
    random.setstate(state["python_rng"])
    return int(state["step"])


# --------------------------------------------------------------------------- loop


def evaluate(model, ids: list[list[int]], pad_id: int, batch_size: int) -> np.ndarray:
    """Softmax probabilities in `data.LABELS` order."""
    model.eval()
    out = []
    with torch.inference_mode():
        for i in range(0, len(ids), batch_size * 4):
            logits = model(**collate(ids[i : i + batch_size * 4], pad_id)).logits
            out.append(torch.softmax(logits, dim=-1).numpy())
    model.train()
    return np.concatenate(out)


def train(
    settings: TrainSettings,
    rows: dict[str, list],
    model,
    tokenizer,
    run_dir: Path,
    resume: bool = False,
) -> dict:
    """Run (or resume) one training run. Returns the run record also written to run.json."""
    started = time.perf_counter()
    started_at = datetime.now(UTC).isoformat(timespec="seconds")
    run_dir.mkdir(parents=True, exist_ok=True)
    seed_everything(settings.seed)
    train_rows, val_rows = rows["train"], rows["validation"]
    pad_id = tokenizer.pad_token_id
    train_ids = encode(tokenizer, [r.feedback_text for r in train_rows], settings.max_length)
    val_ids = encode(tokenizer, [r.feedback_text for r in val_rows], settings.max_length)
    y_train = torch.tensor([LABEL_INDEX[r.true_sentiment] for r in train_rows])
    y_val = [r.true_sentiment for r in val_rows]

    weights = balanced_class_weights([r.true_sentiment for r in train_rows])
    loss_fn = torch.nn.CrossEntropyLoss(weight=torch.tensor(weights, dtype=torch.float))
    no_decay = ("bias", "LayerNorm.weight", "layer_norm.weight")
    groups = [
        {
            "params": [p for n, p in model.named_parameters() if not n.endswith(no_decay)],
            "weight_decay": settings.weight_decay,
        },
        {
            "params": [p for n, p in model.named_parameters() if n.endswith(no_decay)],
            "weight_decay": 0.0,
        },
    ]
    optimizer = torch.optim.AdamW(groups, lr=settings.learning_rate)
    steps_per_epoch = math.ceil(len(train_ids) / settings.batch_size)
    total_steps = steps_per_epoch * settings.max_epochs
    warmup_steps = round(settings.warmup_fraction * total_steps)
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer, linear_warmup_decay(total_steps, warmup_steps)
    )

    state_path = run_dir / "state.json"
    state = {"latest_epoch": 0, "best_epoch": None, "best_val_macro_f1": None, "f1": {}}
    step = 0
    if resume:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state["latest_epoch"]:
            step = load_checkpoint(run_dir, state["latest_epoch"], model, optimizer, scheduler)
    commit, dirty = git_state()
    log = (run_dir / "train_log.jsonl").open("a", encoding="utf-8")
    model.train()
    # Early stopping: stop once `patience` epochs in a row fail to beat the best.
    epochs_since_best = 0
    if state["best_epoch"] is not None:
        epochs_since_best = state["latest_epoch"] - state["best_epoch"]
    stopped_early = epochs_since_best >= settings.patience > 0

    for epoch in range(state["latest_epoch"] + 1, settings.max_epochs + 1):
        if stopped_early:
            break
        order = epoch_order(len(train_ids), epoch, settings.seed)
        for b in range(steps_per_epoch):
            idx = order[b * settings.batch_size : (b + 1) * settings.batch_size]
            t0 = time.perf_counter()
            logits = model(**collate([train_ids[i] for i in idx], pad_id)).logits
            loss = loss_fn(logits, y_train[idx])
            loss.backward()
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad(set_to_none=True)
            step += 1
            entry = {
                "step": step,
                "epoch": epoch,
                "loss": round(loss.item(), 6),
                "lr": scheduler.get_last_lr()[0],
                "seconds": round(time.perf_counter() - t0, 4),
            }
            log.write(json.dumps(entry) + "\n")
            log.flush()
            if settings.timing_steps and step >= settings.timing_steps:
                t_val = time.perf_counter()
                evaluate(model, val_ids, pad_id, settings.batch_size)
                log.close()
                return {"timing_steps": step, "validation_pass_s": time.perf_counter() - t_val}

        proba = evaluate(model, val_ids, pad_id, settings.batch_size)
        pred = [data.LABELS[i] for i in proba.argmax(1)]
        f1 = float(f1_score(y_val, pred, average="macro", labels=list(data.LABELS)))
        predictions.write(
            run_dir / f"val_epoch_{epoch}.predictions.csv",
            [r.feedback_id for r in val_rows],
            ["validation"] * len(val_rows),
            proba,
            {
                "model": f"bert_{settings.run_id}_epoch{epoch}",
                "diagnostic": False,
                "config": {"learning_rate": settings.learning_rate, "epoch": epoch},
                "split": "v1",
            },
        )
        save_checkpoint(run_dir, epoch, model, optimizer, scheduler, step)
        state["f1"][str(epoch)] = round(f1, 4)
        if state["best_val_macro_f1"] is None or f1 > state["best_val_macro_f1"]:
            state["best_epoch"], state["best_val_macro_f1"] = epoch, round(f1, 4)
            epochs_since_best = 0
        else:
            epochs_since_best += 1
        state["latest_epoch"] = epoch
        _write_json_atomic(state_path, state)
        print(f"epoch {epoch}: validation macro-F1 {f1:.4f} (best epoch {state['best_epoch']})")
        stopped_early = epochs_since_best >= settings.patience and epoch < settings.max_epochs
    log.close()

    previous: dict = {}
    run_json = run_dir / "run.json"
    if resume and run_json.exists():
        previous = json.loads(run_json.read_text(encoding="utf-8"))
    record = {
        "run_id": settings.run_id,
        "model_id": config.MODEL_ID,
        "revision": config.REVISION,
        "max_length": settings.max_length,
        "learning_rate": settings.learning_rate,
        "seed": settings.seed,
        "batch_size": settings.batch_size,
        "max_epochs": settings.max_epochs,
        "patience": settings.patience,
        "weight_decay": settings.weight_decay,
        "warmup_fraction": settings.warmup_fraction,
        "class_weights": dict(zip(data.LABELS, (round(w, 6) for w in weights), strict=True)),
        "n_train": len(train_rows),
        "n_validation": len(val_rows),
        "split": "v1",
        "split_sha256": data.sha256_file(data.split_paths("v1")[0]),
        "git_commit": commit,
        "git_dirty": dirty,
        "torch_version": torch.__version__,
        "torch_threads": torch.get_num_threads(),
        "started_at": previous.get("started_at", started_at),
        "wall_time_s": round(previous.get("wall_time_s", 0.0) + time.perf_counter() - started, 1),
        "epochs_completed": state["latest_epoch"],
        "val_macro_f1_by_epoch": state["f1"],
        "best_epoch": state["best_epoch"],
        "best_val_macro_f1": state["best_val_macro_f1"],
        "stopped_early": stopped_early,
        **settings.extra,
    }
    _write_json_atomic(run_json, record)
    return record


# --------------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--lr", type=float, required=True, help="learning rate (ADR-065 budget)")
    ap.add_argument("--run-id", help="default: lr<lr>_<UTC timestamp>")
    ap.add_argument("--resume", action="store_true", help="continue --run-id from its last epoch")
    ap.add_argument("--threads", type=int, help="torch threads (default: torch's own)")
    ap.add_argument("--timing-steps", type=int, help="train this many steps, time, and stop")
    args = ap.parse_args(argv)
    if args.lr not in config.ALLOWED_LEARNING_RATES and not args.timing_steps:
        raise SystemExit(f"--lr must be one of {config.ALLOWED_LEARNING_RATES} (ADR-065)")
    if args.resume and not args.run_id:
        raise SystemExit("--resume needs --run-id")
    if args.threads:
        torch.set_num_threads(args.threads)

    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    run_id = args.run_id or f"lr{args.lr:g}_{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    settings = TrainSettings(learning_rate=args.lr, run_id=run_id, timing_steps=args.timing_steps)
    seed_everything(settings.seed)  # before the head is initialised
    tokenizer = AutoTokenizer.from_pretrained(config.MODEL_ID, revision=config.REVISION)
    model = AutoModelForSequenceClassification.from_pretrained(
        config.MODEL_ID, revision=config.REVISION, num_labels=len(data.LABELS)
    )
    rows = load_rows(("train", "validation"))
    print(
        f"run {run_id}: train {len(rows['train'])}, validation {len(rows['validation'])}, "
        f"threads {torch.get_num_threads()}"
    )
    result = train(settings, rows, model, tokenizer, MODELS_ROOT / run_id, resume=args.resume)
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
