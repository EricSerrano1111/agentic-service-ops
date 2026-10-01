"""Compare two models' test predictions on the same comments, as ADR-065 fixes it.

    python -m evals.sentiment.compare <bert predictions.csv> <tfidf predictions.csv> --out <dir>

Model A is BERT and model B is TF-IDF throughout; differences are A minus B.

- **Macro-F1 difference** with a paired bootstrap: 10,000 resamples of the test comments
  with replacement (seed 20261001), both models scored on each resample, and the 95%
  percentile interval of the difference.
- **McNemar's exact test** on per-comment correctness, for the full test set and the
  sarcastic, implicit and mixed (true label) subsets: b = only A right, c = only B right,
  p = two-sided exact binomial test of b against b + c at 0.5 (`scipy.stats.binomtest`).
  b, c and p are reported for every subset, whatever the result.
- **Verdict** (ADR-065): A is better on macro-F1 only if the interval excludes zero, and on
  a subset only if p < 0.05. The mirror case is reported as B better; anything else as not
  distinguishable.
- **Examples:** up to 10 comments for each direction of discordance (the lowest
  `feedback_id`s, so the choice involves no judgement), with text from the committed
  corpus, the true label and both predictions.

Test labels are read once, as `app_eval`. Both models must already have their own test
line in the ledger; the comparison appends one more, of type `comparison`, and is refused
if that pair was already compared.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

from evals.sentiment import score
from ml.sentiment import data, predictions

N_RESAMPLES = 10_000
SEED = 20261001
ALPHA = 0.05
N_EXAMPLES = 10
SUBSETS = ("sarcastic", "implicit", "mixed")


def macro_f1_batch(y: np.ndarray, p: np.ndarray, k: int) -> np.ndarray:
    """Macro-F1 per row of integer label arrays shaped (R, n); F1 is 0 for an empty class."""
    y, p = np.atleast_2d(y), np.atleast_2d(p)
    f1 = []
    for c in range(k):
        yt, pp = y == c, p == c
        tp = (yt & pp).sum(axis=1)
        denom = 2 * tp + (~yt & pp).sum(axis=1) + (yt & ~pp).sum(axis=1)
        f1.append(np.where(denom > 0, 2 * tp / np.maximum(denom, 1), 0.0))
    return np.mean(f1, axis=0)


def paired_bootstrap(
    y: np.ndarray,
    pred_a: np.ndarray,
    pred_b: np.ndarray,
    k: int,
    n_resamples: int = N_RESAMPLES,
    seed: int = SEED,
    chunk: int = 1000,
) -> dict:
    """Macro-F1(A) - macro-F1(B): point estimate and the 95% percentile interval."""
    y, pred_a, pred_b = map(np.asarray, (y, pred_a, pred_b))
    rng = np.random.default_rng(seed)
    n = len(y)
    diffs = []
    for start in range(0, n_resamples, chunk):
        idx = rng.integers(0, n, size=(min(chunk, n_resamples - start), n))
        diffs.append(
            macro_f1_batch(y[idx], pred_a[idx], k) - macro_f1_batch(y[idx], pred_b[idx], k)
        )
    d = np.concatenate(diffs)
    point = float(macro_f1_batch(y, pred_a, k)[0] - macro_f1_batch(y, pred_b, k)[0])
    lo, hi = np.percentile(d, [2.5, 97.5])
    return {
        "difference": point,
        "ci95": [float(lo), float(hi)],
        "n_resamples": n_resamples,
        "seed": seed,
        "method": "paired bootstrap, percentile interval",
    }


def mcnemar(correct_a: Sequence[bool], correct_b: Sequence[bool]) -> dict:
    """Exact McNemar: b = only A right, c = only B right, two-sided binomial p."""
    a, b_ = np.asarray(correct_a, dtype=bool), np.asarray(correct_b, dtype=bool)
    b = int((a & ~b_).sum())
    c = int((~a & b_).sum())
    p = binomtest(b, b + c, 0.5, alternative="two-sided").pvalue if b + c else 1.0
    return {"n": len(a), "b_only_a_right": b, "c_only_b_right": c, "p": float(p)}


def verdict_interval(ci: Sequence[float]) -> str:
    if ci[0] > 0:
        return "BERT better"
    if ci[1] < 0:
        return "TF-IDF better"
    return "not distinguishable"


def verdict_mcnemar(m: dict) -> str:
    if m["p"] < ALPHA and m["b_only_a_right"] > m["c_only_b_right"]:
        return "BERT better"
    if m["p"] < ALPHA and m["c_only_b_right"] > m["b_only_a_right"]:
        return "TF-IDF better"
    return "not distinguishable"


def in_subset(g: data.GoldLabel, subset: str) -> bool:
    return g.true_sentiment == "mixed" if subset == "mixed" else g.hard_case_type == subset


def compute(
    rows_a: list[dict],
    rows_b: list[dict],
    gold: Mapping[int, data.GoldLabel],
    texts: Mapping[str, str],
    n_resamples: int = N_RESAMPLES,
) -> dict:
    """The whole comparison. Pure: no I/O. `texts` maps `corpus_id` to comment text."""
    by_b = {r["feedback_id"]: r for r in rows_b}
    ids = sorted(r["feedback_id"] for r in rows_a)
    if set(ids) != set(by_b):
        raise ValueError("the two predictions files cover different comments")
    by_a = {r["feedback_id"]: r for r in rows_a}
    index = {label: i for i, label in enumerate(data.LABELS)}
    y = np.array([index[gold[i].true_sentiment] for i in ids])
    pa = np.array([index[by_a[i]["predicted"]] for i in ids])
    pb = np.array([index[by_b[i]["predicted"]] for i in ids])
    ca, cb = pa == y, pb == y

    boot = paired_bootstrap(y, pa, pb, len(data.LABELS), n_resamples=n_resamples)
    tests = {"full": mcnemar(ca, cb)}
    for s in SUBSETS:
        mask = np.array([in_subset(gold[i], s) for i in ids])
        tests[s] = mcnemar(ca[mask], cb[mask])

    def example(pos: int) -> dict:
        g = gold[ids[pos]]
        return {
            "feedback_id": ids[pos],
            "corpus_id": g.corpus_id,
            "text": texts[g.corpus_id],
            "true": g.true_sentiment,
            "hard_case_type": g.hard_case_type,
            "bert": by_a[ids[pos]]["predicted"],
            "tfidf": by_b[ids[pos]]["predicted"],
        }

    only_a = [example(i) for i in np.flatnonzero(ca & ~cb)[:N_EXAMPLES]]
    only_b = [example(i) for i in np.flatnonzero(~ca & cb)[:N_EXAMPLES]]
    return {
        "n": len(ids),
        "macro_f1": {
            "bert": round(float(macro_f1_batch(y, pa, len(data.LABELS))[0]), 4),
            "tfidf": round(float(macro_f1_batch(y, pb, len(data.LABELS))[0]), 4),
            "bootstrap": boot,
            "verdict": verdict_interval(boot["ci95"]),
        },
        "mcnemar": {k: {**v, "verdict": verdict_mcnemar(v)} for k, v in tests.items()},
        "examples": {"only_bert_right": only_a, "only_tfidf_right": only_b},
    }


def corpus_texts(path: Path = data.CORPUS_PATH) -> dict[str, str]:
    with path.open(encoding="utf-8") as fh:
        return {r["corpus_id"]: r["text"] for r in map(json.loads, fh)}


def ledger_models(ledger: Path) -> set[str]:
    if not ledger.exists():
        return set()
    return {json.loads(x)["model"] for x in ledger.read_text("utf-8").splitlines() if x.strip()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("bert", type=Path)
    ap.add_argument("tfidf", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    rows_a, meta_a = predictions.read(args.bert)
    rows_b, meta_b = predictions.read(args.tfidf)
    name = f"comparison:{meta_a['model']}_vs_{meta_b['model']}"
    scored = ledger_models(score.LEDGER)
    missing = [m for m in (meta_a["model"], meta_b["model"]) if m not in scored]
    if missing:
        raise SystemExit(f"{missing} not yet scored on test; score each model first")
    score.check_not_scored(name)  # before any gold label is read
    split = data.load_split("v1")
    rows_a = score.select_split(rows_a, "test", split)
    rows_b = score.select_split(rows_b, "test", split)
    result = compute(rows_a, rows_b, data.load_gold_labels(), corpus_texts())

    commit, dirty = score._git()
    m = result["mcnemar"]
    score.append_ledger(
        {
            "type": "comparison",
            "date": date.today().isoformat(),
            "model": name,
            "diagnostic": False,
            "config": {"n_resamples": N_RESAMPLES, "seed": SEED, "alpha": ALPHA},
            "git_commit": commit,
            "git_dirty": dirty,
            "split": "v1",
            "split_sha256": data.sha256_file(data.split_paths("v1")[0]),
            "predictions": [args.bert.name, args.tfidf.name],
            "predictions_sha256": [data.sha256_file(args.bert), data.sha256_file(args.tfidf)],
            "macro_f1_difference": round(result["macro_f1"]["bootstrap"]["difference"], 4),
            "ci95": [round(x, 4) for x in result["macro_f1"]["bootstrap"]["ci95"]],
            "mcnemar": {
                k: [v["b_only_a_right"], v["c_only_b_right"], round(v["p"], 4)]
                for k, v in m.items()
            },
        }
    )
    args.out.mkdir(parents=True, exist_ok=True)
    examples = result.pop("examples")
    common = {
        "bert": {"model": meta_a["model"], "predictions": str(args.bert.as_posix())},
        "tfidf": {"model": meta_b["model"], "predictions": str(args.tfidf.as_posix())},
        "split": "test",
        "split_version": "v1",
    }
    (args.out / "comparison.json").write_text(
        json.dumps({**common, **result}, indent=2) + "\n", encoding="utf-8"
    )
    (args.out / "comparison_examples.json").write_text(
        json.dumps({**common, **examples}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=1))
    print(f"wrote comparison.json and comparison_examples.json to {args.out}; ledger appended")
    return 0


if __name__ == "__main__":
    sys.exit(main())
