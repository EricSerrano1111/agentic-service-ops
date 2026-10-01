"""Temperature scaling and the review threshold for `bert_v1`, exactly as ADR-066 fixes them.

    python -m ml.sentiment.calibrate [--out-date YYYY-MM-DD]

Validation only: reads validation rows as `app_train`, never test.

- **Temperature.** One scalar T > 0 minimising the mean negative log-likelihood of the
  validation labels under softmax(logits / T). It never changes the predicted class.
- **ECE.** Expected calibration error over 15 equal-width bins of the top-class
  probability, bins (0, 1/15], ..., (14/15, 1]: the sum over bins of
  (share of comments in the bin) x |accuracy in the bin - mean confidence in the bin|.
- **Threshold τ.** The smallest calibrated top-class probability at which the predictions
  at or above it are at least 99% accurate on validation; comments below τ are flagged.
  If that flags more than 20% of validation, τ is instead the calibrated top-class
  probability at sorted position floor(0.20 n), so at most 20% are flagged, and the
  accuracy reached is reported.

Stops, writing nothing to the manifest, if T is outside [0.5, 5] or ECE is higher after
scaling than before. Otherwise writes T, τ and the rule that set τ into the artifact
manifest, and `calibration.json` into `evals/results/sentiment/<date>_bert_v1/`.

The functions above the CLI are pure (numpy and scipy only) so the scorer can import them.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import date

import numpy as np

N_BINS = 15
TARGET_ACCURACY = 0.99
MAX_FLAG_RATE = 0.20
T_BOUNDS = (0.5, 5.0)  # stop rule, not the search range
T_SEARCH = (0.05, 20.0)


def softmax(logits: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    z = np.asarray(logits, dtype=np.float64) / temperature
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def nll(logits: np.ndarray, y: np.ndarray, temperature: float) -> float:
    """Mean negative log-likelihood of integer labels `y` under softmax(logits / T)."""
    z = np.asarray(logits, dtype=np.float64) / temperature
    z = z - z.max(axis=1, keepdims=True)
    log_p = z - np.log(np.exp(z).sum(axis=1, keepdims=True))
    return float(-log_p[np.arange(len(y)), y].mean())


def fit_temperature(logits: np.ndarray, y: np.ndarray) -> float:
    """The T minimising validation NLL (bounded scalar search; NLL is smooth in T)."""
    from scipy.optimize import minimize_scalar

    res = minimize_scalar(
        lambda t: nll(logits, y, t), bounds=T_SEARCH, method="bounded", options={"xatol": 1e-6}
    )
    return float(res.x)


def ece(confidence: np.ndarray, correct: np.ndarray, n_bins: int = N_BINS) -> float:
    """Expected calibration error over `n_bins` equal-width bins, (lo, hi] each."""
    confidence = np.asarray(confidence, dtype=np.float64)
    correct = np.asarray(correct, dtype=np.float64)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        in_bin = (confidence > lo) & (confidence <= hi)
        if in_bin.any():
            total += in_bin.mean() * abs(correct[in_bin].mean() - confidence[in_bin].mean())
    return float(total)


def ece_from_proba(proba: np.ndarray, y: np.ndarray, n_bins: int = N_BINS) -> float:
    proba = np.asarray(proba, dtype=np.float64)
    return ece(proba.max(axis=1), proba.argmax(axis=1) == np.asarray(y), n_bins)


@dataclass(frozen=True)
class Threshold:
    tau: float
    rule: str  # "target_99" or "cap_20"
    n: int
    n_flagged: int
    flag_rate: float
    accuracy_unflagged: float | None


def choose_threshold(
    confidence: np.ndarray,
    correct: np.ndarray,
    target: float = TARGET_ACCURACY,
    max_flag_rate: float = MAX_FLAG_RATE,
) -> Threshold:
    """ADR-066's τ. Comments with confidence < τ are flagged; ties at τ are kept."""
    conf = np.asarray(confidence, dtype=np.float64)
    ok = np.asarray(correct, dtype=bool)
    n = len(conf)
    order = np.argsort(conf, kind="stable")
    cs, cok = conf[order], ok[order]
    # correct_from[i]: correct predictions among sorted positions i..n-1.
    correct_from = np.concatenate([np.cumsum(cok[::-1])[::-1], [0]])

    def at(tau: float, rule: str) -> Threshold:
        i = int(np.searchsorted(cs, tau, side="left"))  # number with conf < tau
        kept = n - i
        return Threshold(
            tau=float(tau),
            rule=rule,
            n=n,
            n_flagged=i,
            flag_rate=i / n,
            accuracy_unflagged=float(correct_from[i] / kept) if kept else None,
        )

    for tau in np.unique(cs):  # ascending: the first that meets the target is the smallest
        i = int(np.searchsorted(cs, tau, side="left"))
        if correct_from[i] / (n - i) >= target:
            chosen = at(tau, "target_99")
            if chosen.flag_rate <= max_flag_rate:
                return chosen
            break
    return at(cs[math.floor(max_flag_rate * n)], "cap_20")


# --------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    from ml.sentiment import export
    from ml.sentiment.train_bert import LABEL_INDEX, load_rows

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out-date", default=date.today().isoformat())
    args = ap.parse_args(argv)

    model, tokenizer, manifest = export.load_artifact()
    val = load_rows(("validation",))["validation"]
    logits = export.predict_logits(
        model, tokenizer, [r.feedback_text for r in val], manifest["max_length"]
    )
    y = np.array([LABEL_INDEX[r.true_sentiment] for r in val])

    t = round(fit_temperature(logits, y), 6)
    raw, cal = softmax(logits), softmax(logits, t)
    if not np.array_equal(raw.argmax(1), cal.argmax(1)):
        raise AssertionError("temperature scaling changed a predicted class")
    correct = cal.argmax(1) == y
    ece_before, ece_after = ece_from_proba(raw, y), ece_from_proba(cal, y)
    thr = choose_threshold(cal.max(1), correct)
    flagged = cal.max(1) < thr.tau
    result = {
        "evidence": "observed",
        "artifact": manifest["artifact"],
        "fitted_on": "validation",
        "n_validation": len(val),
        "temperature": t,
        "nll_before": round(nll(logits, y, 1.0), 6),
        "nll_after": round(nll(logits, y, t), 6),
        "ece_before": round(ece_before, 6),
        "ece_after": round(ece_after, 6),
        "n_bins": N_BINS,
        "threshold": asdict(thr),
        "accuracy_flagged": float(correct[flagged].mean()) if flagged.any() else None,
        "accuracy_overall": float(correct.mean()),
        "note": "T and τ were fitted on the split used to select the run and epoch, so "
        "these validation figures are optimistic (ADR-066); only test figures are results.",
    }
    print(json.dumps(result, indent=1))

    stops = []
    if not T_BOUNDS[0] <= t <= T_BOUNDS[1]:
        stops.append(f"T={t} is outside [{T_BOUNDS[0]}, {T_BOUNDS[1]}]")
    if ece_after > ece_before:
        stops.append(f"ECE rose after scaling ({ece_before:.4f} -> {ece_after:.4f})")
    out = export.RESULTS_ROOT / f"{args.out_date}_{manifest['artifact']}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "calibration.json").write_text(
        json.dumps({**result, "stop_rules_fired": stops}, indent=2) + "\n", encoding="utf-8"
    )
    if stops:
        print("STOP: " + "; ".join(stops) + ". Manifest not updated.", file=sys.stderr)
        return 1

    manifest["calibration"] = {
        **export.EMPTY_CALIBRATION,
        "temperature": t,
        "threshold": thr.tau,
        "threshold_rule": thr.rule,
        "ece_validation_before": result["ece_before"],
        "ece_validation_after": result["ece_after"],
        "flag_rate_validation": round(thr.flag_rate, 6),
        "accuracy_unflagged_validation": round(thr.accuracy_unflagged, 6),
        "decided_by": "ADR-066",
    }
    export.write_manifest(manifest)
    print(f"wrote T={t}, tau={thr.tau!r} ({thr.rule}) to {export.MANIFEST_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
