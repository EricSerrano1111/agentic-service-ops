"""The sentiment scorer on a hand-built predictions fixture (ADR-064).

Ten rows, every expected figure worked out by hand from the table below; nothing is
computed by the code under test. Confusion matrix (rows true, columns predicted, in
positive / neutral / negative / mixed order):

    positive  [1, 1, 0, 0]
    neutral   [1, 2, 0, 0]
    negative  [1, 0, 2, 0]
    mixed     [0, 0, 1, 1]

Accuracy 6/10. F1: positive 0.4 (P 1/3, R 1/2), neutral 2/3, negative 2/3, mixed 2/3
(P 1, R 1/2); macro-F1 (0.4 + 3 x 2/3) / 4 = 0.6.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from evals.sentiment import score  # noqa: E402
from ml.sentiment.data import CorpusMeta, GoldLabel  # noqa: E402

# id: (true_sentiment, hard_case_type, neutral_kind, judge_disagreement, predicted)
FIXTURE = {
    1: ("positive", "none", None, False, "positive"),
    2: ("positive", "implicit", None, False, "neutral"),
    3: ("neutral", "none", "administrative", False, "neutral"),
    4: ("neutral", "none", "status", False, "positive"),
    5: ("neutral", "none", "administrative", False, "neutral"),
    6: ("negative", "sarcastic", None, True, "positive"),
    7: ("negative", "sarcastic", None, False, "negative"),
    8: ("negative", "none", None, False, "negative"),
    9: ("mixed", "none", None, False, "mixed"),
    10: ("mixed", "none", None, False, "negative"),
}

GOLD = {i: GoldLabel(s, h, f"c{i}") for i, (s, h, _, _, _) in FIXTURE.items()}
CORPUS = {f"c{i}": CorpusMeta(k, "x", d) for i, (_, _, k, d, _) in FIXTURE.items()}
ROWS = [
    {"feedback_id": i, "split": "test", "predicted": p, "proba": [0.25] * 4}
    for i, (*_, p) in FIXTURE.items()
]


@pytest.fixture(scope="module")
def metrics() -> dict:
    return score.compute(ROWS, GOLD, CORPUS)


def test_headline_and_accuracy(metrics: dict) -> None:
    assert metrics["n"] == 10
    assert metrics["macro_f1"] == pytest.approx(0.6, abs=1e-4)
    assert metrics["accuracy"] == pytest.approx(0.6)


def test_confusion_matrix(metrics: dict) -> None:
    assert metrics["confusion_matrix"]["labels"] == ["positive", "neutral", "negative", "mixed"]
    assert metrics["confusion_matrix"]["rows_true_columns_predicted"] == [
        [1, 1, 0, 0],
        [1, 2, 0, 0],
        [1, 0, 2, 0],
        [0, 0, 1, 1],
    ]


def test_per_class(metrics: dict) -> None:
    pc = metrics["per_class"]
    assert (pc["positive"]["precision"], pc["positive"]["recall"]) == pytest.approx((0.3333, 0.5))
    assert pc["positive"]["f1"] == pytest.approx(0.4)
    assert pc["neutral"]["f1"] == pytest.approx(0.6667)
    assert pc["negative"]["support"] == 3
    assert (pc["mixed"]["precision"], pc["mixed"]["recall"]) == (1.0, 0.5)


def test_hard_cases_with_n_and_judge_disagreement(metrics: dict) -> None:
    assert metrics["hard_cases"]["sarcastic"] == {
        "n": 2,
        "accuracy": 0.5,
        "judge_disagreement_rate": 0.5,
    }
    assert metrics["hard_cases"]["implicit"] == {
        "n": 1,
        "accuracy": 0.0,
        "judge_disagreement_rate": 0.0,
    }


def test_neutral_by_kind(metrics: dict) -> None:
    assert metrics["neutral_by_kind"] == {
        "administrative": {"n": 2, "accuracy": 1.0},
        "status": {"n": 1, "accuracy": 0.0},
    }


def test_mixed_called_out(metrics: dict) -> None:
    assert metrics["mixed"] == {"recall": 0.5, "f1": 0.6667, "n": 2}


def test_select_split_requires_exact_coverage() -> None:
    split = {i: "test" for i in FIXTURE} | {11: "validation"}
    assert len(score.select_split(ROWS, "test", split)) == 10
    with pytest.raises(ValueError, match="must match exactly"):
        score.select_split(ROWS[:-1], "test", split)
    with pytest.raises(ValueError, match="must match exactly"):
        score.select_split(ROWS + [ROWS[0]], "test", split)


def test_select_split_rejects_an_unknown_label() -> None:
    bad = [dict(r, predicted="angry") if r["feedback_id"] == 1 else r for r in ROWS]
    with pytest.raises(ValueError, match="unknown predicted label"):
        score.select_split(bad, "test", {i: "test" for i in FIXTURE})


def test_ledger_appends_once_per_model(tmp_path: Path) -> None:
    ledger = tmp_path / "test_ledger.jsonl"
    score.append_ledger({"model": "m1", "macro_f1": 0.5}, ledger)
    score.append_ledger({"model": "m2", "macro_f1": 0.6}, ledger)
    with pytest.raises(score.LedgerRefusal, match="already scored on test"):
        score.append_ledger({"model": "m1", "macro_f1": 0.9}, ledger)

    lines = [json.loads(x) for x in ledger.read_text(encoding="utf-8").splitlines()]
    assert [x["model"] for x in lines] == ["m1", "m2"]
