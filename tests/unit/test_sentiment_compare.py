"""ADR-065's comparison statistics, on hand-built fixtures. Assembled: no model, no database."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from sklearn.metrics import f1_score

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from evals.sentiment import compare, score  # noqa: E402
from ml.sentiment.data import GoldLabel  # noqa: E402


def test_mcnemar_by_hand() -> None:
    """b = 8 (only A right), c = 2 (only B right); 5 both right, 3 both wrong.

    Exact two-sided p = 2 x P(X <= 2 | n=10, 0.5) = 2 x (1 + 10 + 45) / 1024 = 0.109375.
    """
    a = [True] * 8 + [False] * 2 + [True] * 5 + [False] * 3
    b = [False] * 8 + [True] * 2 + [True] * 5 + [False] * 3
    m = compare.mcnemar(a, b)
    assert (m["n"], m["b_only_a_right"], m["c_only_b_right"]) == (18, 8, 2)
    assert m["p"] == pytest.approx(0.109375)
    assert compare.verdict_mcnemar(m) == "not distinguishable"


def test_mcnemar_with_no_discordance_is_p_one() -> None:
    m = compare.mcnemar([True, False], [True, False])
    assert (m["b_only_a_right"], m["c_only_b_right"], m["p"]) == (0, 0, 1.0)


def test_mcnemar_verdict_directions() -> None:
    """b = 10, c = 0: p = 2 / 1024 < 0.05, BERT better; the mirror is TF-IDF better."""
    m = compare.mcnemar([True] * 10, [False] * 10)
    assert m["p"] == pytest.approx(2 / 1024)
    assert compare.verdict_mcnemar(m) == "BERT better"
    assert compare.verdict_mcnemar(compare.mcnemar([False] * 10, [True] * 10)) == "TF-IDF better"


def test_interval_verdicts() -> None:
    assert compare.verdict_interval([0.001, 0.02]) == "BERT better"
    assert compare.verdict_interval([-0.01, 0.02]) == "not distinguishable"
    assert compare.verdict_interval([-0.03, -0.001]) == "TF-IDF better"


def test_macro_f1_batch_matches_sklearn() -> None:
    rng = np.random.default_rng(1)
    y, p = rng.integers(0, 4, 200), rng.integers(0, 4, 200)
    expected = f1_score(y, p, average="macro", labels=[0, 1, 2, 3], zero_division=0)
    assert compare.macro_f1_batch(y, p, 4)[0] == pytest.approx(expected)


def test_bootstrap_is_reproducible_with_a_fixed_seed() -> None:
    rng = np.random.default_rng(2)
    y = rng.integers(0, 4, 300)
    a = np.where(rng.random(300) < 0.9, y, (y + 1) % 4)
    b = np.where(rng.random(300) < 0.8, y, (y + 1) % 4)
    first = compare.paired_bootstrap(y, a, b, 4, n_resamples=500, seed=20261001)
    again = compare.paired_bootstrap(y, a, b, 4, n_resamples=500, seed=20261001)
    other = compare.paired_bootstrap(y, a, b, 4, n_resamples=500, seed=1)
    assert first == again
    assert first["ci95"] != other["ci95"]
    assert first["ci95"][0] <= first["difference"] <= first["ci95"][1]


def test_identical_models_give_a_zero_interval_and_no_examples() -> None:
    gold = {i: GoldLabel("positive" if i % 2 else "negative", "none", f"c{i}") for i in range(20)}
    rows = [{"feedback_id": i, "predicted": "positive"} for i in range(20)]
    r = compare.compute(rows, rows, gold, {f"c{i}": "t" for i in range(20)}, n_resamples=200)
    assert r["macro_f1"]["bootstrap"]["ci95"] == [0.0, 0.0]
    assert r["macro_f1"]["verdict"] == "not distinguishable"
    assert r["examples"] == {"only_bert_right": [], "only_tfidf_right": []}
    assert set(r["mcnemar"]) == {"full", "sarcastic", "implicit", "mixed"}


def test_examples_and_subsets() -> None:
    """Ids 0-3: BERT right only on 0 (sarcastic) and 1 (mixed); TF-IDF right only on 2."""
    gold = {
        0: GoldLabel("negative", "sarcastic", "c0"),
        1: GoldLabel("mixed", "none", "c1"),
        2: GoldLabel("neutral", "implicit", "c2"),
        3: GoldLabel("positive", "none", "c3"),
    }
    bert = [
        {"feedback_id": 0, "predicted": "negative"},
        {"feedback_id": 1, "predicted": "mixed"},
        {"feedback_id": 2, "predicted": "positive"},
        {"feedback_id": 3, "predicted": "positive"},
    ]
    tfidf = [
        {"feedback_id": 0, "predicted": "positive"},
        {"feedback_id": 1, "predicted": "negative"},
        {"feedback_id": 2, "predicted": "neutral"},
        {"feedback_id": 3, "predicted": "positive"},
    ]
    texts = {f"c{i}": f"text {i}" for i in range(4)}
    r = compare.compute(bert, tfidf, gold, texts, n_resamples=100)
    m = r["mcnemar"]
    assert (m["full"]["b_only_a_right"], m["full"]["c_only_b_right"]) == (2, 1)
    assert (m["sarcastic"]["b_only_a_right"], m["sarcastic"]["c_only_b_right"]) == (1, 0)
    assert (m["mixed"]["b_only_a_right"], m["implicit"]["c_only_b_right"]) == (1, 1)
    assert [e["feedback_id"] for e in r["examples"]["only_bert_right"]] == [0, 1]
    only_tfidf = r["examples"]["only_tfidf_right"]
    assert only_tfidf == [
        {
            "feedback_id": 2,
            "corpus_id": "c2",
            "text": "text 2",
            "true": "neutral",
            "hard_case_type": "implicit",
            "bert": "positive",
            "tfidf": "neutral",
        }
    ]


def test_a_second_comparison_is_refused(tmp_path: Path) -> None:
    ledger = tmp_path / "test_ledger.jsonl"
    entry = {"type": "comparison", "model": "comparison:bert_v1_vs_tfidf_logreg"}
    score.append_ledger(entry, ledger)
    with pytest.raises(score.LedgerRefusal):
        score.append_ledger(entry, ledger)
    assert [json.loads(x)["type"] for x in ledger.read_text("utf-8").splitlines()] == ["comparison"]
