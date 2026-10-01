"""Runs inside the latency-proxy container (ADR-065). Never imported by the host or a service.

    python bench.py cold  --threads N
    python bench.py warm  --threads N --slices '{"name": [size, repeats], ...}'

The model is `bert-base-uncased` at the pinned revision with a randomly initialised
4-class head. Fine-tuning changes weights, not compute, so this costs what the trained
model will cost. Texts are real train-split comments mounted read-only at /data; there is
no network. Classification here means tokenise (truncation at MAX_LENGTH, padding to the
longest comment in the batch) plus a forward pass under `torch.inference_mode()`.

`cold` prints FIRST_PREDICTION as soon as one comment is classified, so the host can time
container start to first prediction. `warm` prints one JSON line of results.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time

T_START = time.perf_counter()

MODEL_DIR = "/model"
TEXTS = "/data/texts.json"
MAX_LENGTH = 64
BATCH_SIZES = (16, 32, 64)
THROUGHPUT_TEXTS = 1024
REPEATS = 3


def load(threads: int):
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    torch.set_num_threads(threads)
    torch.manual_seed(20261001)  # the random head; its values don't change the compute
    tok = AutoTokenizer.from_pretrained(MODEL_DIR)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR, num_labels=4)
    model.eval()
    return torch, tok, model


def classify(torch, tok, model, texts: list[str], batch_size: int) -> list[int]:
    out: list[int] = []
    with torch.inference_mode():
        for i in range(0, len(texts), batch_size):
            enc = tok(
                texts[i : i + batch_size],
                truncation=True,
                max_length=MAX_LENGTH,
                padding=True,
                return_tensors="pt",
            )
            out.extend(model(**enc).logits.argmax(-1).tolist())
    return out


def memory_peak_bytes() -> int | None:
    try:
        with open("/sys/fs/cgroup/memory.peak") as fh:
            return int(fh.read().strip())
    except OSError:
        return None


def cold(threads: int) -> None:
    with open(TEXTS, encoding="utf-8") as fh:
        text = json.load(fh)[0]
    torch, tok, model = load(threads)
    t_loaded = time.perf_counter()
    classify(torch, tok, model, [text], 1)
    t_done = time.perf_counter()
    print("FIRST_PREDICTION", flush=True)
    print(
        json.dumps(
            {
                "in_process_s": round(t_done - T_START, 3),
                "imports_and_load_s": round(t_loaded - T_START, 3),
                "first_prediction_s": round(t_done - t_loaded, 3),
            }
        ),
        flush=True,
    )


def _cycle(texts: list[str], n: int) -> list[str]:
    return [texts[i % len(texts)] for i in range(n)]


def warm(threads: int, slices: dict[str, list[int]]) -> None:
    with open(TEXTS, encoding="utf-8") as fh:
        texts = json.load(fh)
    torch, tok, model = load(threads)
    classify(torch, tok, model, texts[:64], 16)  # warm-up, not timed

    sample = _cycle(texts, THROUGHPUT_TEXTS)
    throughput = {}
    for bs in BATCH_SIZES:
        rates = []
        for _ in range(REPEATS):
            t0 = time.perf_counter()
            classify(torch, tok, model, sample, bs)
            rates.append(len(sample) / (time.perf_counter() - t0))
        throughput[bs] = {
            "median_per_s": round(statistics.median(rates), 2),
            "min_per_s": round(min(rates), 2),
            "runs": [round(r, 2) for r in rates],
        }
        print(f"bs={bs}: {throughput[bs]['median_per_s']}/s", file=sys.stderr, flush=True)
    best = max(BATCH_SIZES, key=lambda b: throughput[b]["median_per_s"])

    slice_s = {}
    for name, (size, repeats) in slices.items():
        batch = _cycle(texts, size)
        runs = []
        for _ in range(repeats):
            t0 = time.perf_counter()
            classify(torch, tok, model, batch, best)
            runs.append(time.perf_counter() - t0)
        slice_s[name] = {
            "size": size,
            "repeats": repeats,
            "median_s": round(statistics.median(runs), 3),
            "max_s": round(max(runs), 3),
            "runs": [round(r, 3) for r in runs],
        }
        print(f"{name} ({size}): {slice_s[name]['median_s']}s", file=sys.stderr, flush=True)

    print(
        json.dumps(
            {
                "threads": threads,
                "torch": torch.__version__,
                "throughput": throughput,
                "best_batch_size": best,
                "slices": slice_s,
                "cgroup_memory_peak_bytes": memory_peak_bytes(),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("cold", "warm"))
    ap.add_argument("--threads", type=int, required=True)
    ap.add_argument("--slices", default="{}")
    a = ap.parse_args()
    cold(a.threads) if a.mode == "cold" else warm(a.threads, json.loads(a.slices))
