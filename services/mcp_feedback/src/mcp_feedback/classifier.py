"""The sentiment classifier behind the tools: `bert_v1`, loaded on first need.

Confidence is the calibrated top-class probability, softmax(logits / T), and a comment is
flagged for human review when that is below τ (ADR-066). Both come from the manifest. The
flag is decided on the unrounded probability; storage rounds confidence to 4 places.

Tests replace `BertClassifier` with a stub implementing the same `predict`.
"""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from .artifact import Artifact

log = logging.getLogger("mcp_feedback")


@dataclass(frozen=True)
class Prediction:
    label: str
    confidence: float
    flagged: bool


class Classifier(Protocol):
    def predict(self, texts: Sequence[str]) -> list[Prediction]: ...


def calibrated(logits: np.ndarray, temperature: float) -> np.ndarray:
    z = np.asarray(logits, dtype=np.float64) / temperature
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def to_predictions(proba: np.ndarray, labels: Sequence[str], threshold: float) -> list[Prediction]:
    top = proba.argmax(axis=1)
    conf = proba.max(axis=1)
    return [
        Prediction(labels[int(i)], float(c), bool(c < threshold))
        for i, c in zip(top, conf, strict=True)
    ]


def container_cpus(cgroup_root: Path = Path("/sys/fs/cgroup")) -> int:
    """CPUs this container may use: the cgroup quota, not the host's core count.

    cgroup v2 `cpu.max` ("<quota> <period>" or "max <period>"), then cgroup v1
    `cpu.cfs_quota_us` / `cpu.cfs_period_us`; with no quota, the visible core count.
    """
    host = os.cpu_count() or 1
    try:
        quota, period = (cgroup_root / "cpu.max").read_text().split()
        if quota != "max":
            return max(1, min(host, math.ceil(int(quota) / int(period))))
        return host
    except (OSError, ValueError):
        pass
    try:
        quota_us = int((cgroup_root / "cpu" / "cpu.cfs_quota_us").read_text())
        period_us = int((cgroup_root / "cpu" / "cpu.cfs_period_us").read_text())
        if quota_us > 0 and period_us > 0:
            return max(1, min(host, math.ceil(quota_us / period_us)))
    except (OSError, ValueError):
        pass
    return host


class BertClassifier:
    """`bert_v1` from the verified artifact folder, loaded the first time it's needed."""

    def __init__(self, artifact: Artifact, batch_size: int) -> None:
        self.artifact = artifact
        self.batch_size = batch_size
        self._lock = threading.Lock()
        self._model = None
        self._tokenizer = None
        self.load_seconds: float | None = None

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def _load(self) -> None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        began = time.perf_counter()
        threads = container_cpus()
        torch.set_num_threads(threads)
        directory = self.artifact.directory
        self._tokenizer = AutoTokenizer.from_pretrained(directory, local_files_only=True)
        model = AutoModelForSequenceClassification.from_pretrained(directory, local_files_only=True)
        model.eval()
        self._model = model
        self.load_seconds = round(time.perf_counter() - began, 2)
        log.info(
            "model loaded",
            extra={
                "artifact": self.artifact.name,
                "torch_threads": threads,
                "load_seconds": self.load_seconds,
            },
        )

    def predict(self, texts: Sequence[str]) -> list[Prediction]:
        import torch

        with self._lock:  # one inference at a time on a 1-CPU container
            if self._model is None:
                self._load()
            out = []
            with torch.inference_mode():
                for i in range(0, len(texts), self.batch_size):
                    batch = self._tokenizer(
                        list(texts[i : i + self.batch_size]),
                        truncation=True,
                        max_length=self.artifact.max_length,
                        padding=True,
                        return_tensors="pt",
                    )
                    logits = self._model(
                        input_ids=batch["input_ids"], attention_mask=batch["attention_mask"]
                    ).logits
                    out.append(logits.numpy())
        if not out:
            return []
        proba = calibrated(np.concatenate(out), self.artifact.temperature)
        return to_predictions(proba, self.artifact.labels, self.artifact.threshold)
