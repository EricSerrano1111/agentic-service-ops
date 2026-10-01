"""ADR-066's calibration rules and the scorer's calibration figures, on hand-built fixtures.

Every expected figure is worked out by hand in the test that uses it; nothing is computed
by the code under test. Assembled, not observed: no model and no database.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from evals.sentiment import score  # noqa: E402
from ml.sentiment import calibrate, predictions  # noqa: E402
from ml.sentiment.data import GoldLabel  # noqa: E402

CONF = np.array([0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.97, 0.99])


# --------------------------------------------------------------------------- ECE


def test_ece_by_hand() -> None:
    """Two bins, each holding half the comments.

    (13/15, 14/15]: confidences 0.9, 0.9, one right: 0.5 x |0.5 - 0.9| = 0.2.
    (9/15, 10/15]: confidences 0.65, 0.65, both right: 0.5 x |1.0 - 0.65| = 0.175.
    ECE = 0.375.
    """
    conf = np.array([0.9, 0.9, 0.65, 0.65])
    correct = np.array([1, 0, 1, 1], dtype=bool)
    assert calibrate.ece(conf, correct) == pytest.approx(0.375)


def test_ece_puts_confidence_one_in_the_last_bin_and_is_zero_when_calibrated() -> None:
    assert calibrate.ece(np.array([1.0, 1.0]), np.array([True, True])) == pytest.approx(0.0)
    # 0.75 confident, 3 of 4 right: perfectly calibrated.
    assert calibrate.ece(np.full(4, 0.75), np.array([1, 1, 1, 0], bool)) == pytest.approx(0.0)


def test_ece_from_proba_uses_the_top_class() -> None:
    proba = np.array([[0.9, 0.1, 0, 0], [0.2, 0.8, 0, 0]])
    # Top classes 0 (0.9, right) and 1 (0.8, wrong); separate bins:
    # 0.5 x |1 - 0.9| + 0.5 x |0 - 0.8| = 0.05 + 0.4 = 0.45.
    assert calibrate.ece_from_proba(proba, np.array([0, 0])) == pytest.approx(0.45)


# --------------------------------------------------------------------------- threshold


def test_threshold_target_branch_takes_the_smallest_qualifying_tau() -> None:
    """At or above 0.3: 8/10; 0.4: 8/9; 0.5: 8/8 = 100%. Smallest is 0.5 (0.6+ also
    qualify). Flags 2 of 10 = 20%, within the cap."""
    correct = np.array([0, 0, 1, 1, 1, 1, 1, 1, 1, 1], dtype=bool)
    t = calibrate.choose_threshold(CONF, correct)
    assert (t.tau, t.rule, t.n_flagged, t.flag_rate) == (0.5, "target_99", 2, 0.2)
    assert t.accuracy_unflagged == 1.0


def test_threshold_cap_branch_when_the_target_flags_more_than_20_percent() -> None:
    """At or above 0.3: 8/10; 0.4: 7/9; 0.5: 7/8; 0.6: 7/7. The target needs tau 0.6,
    flagging 3 of 10 = 30%. Cap: tau at sorted position floor(0.2 x 10) = 2, i.e. 0.5,
    flagging 2; accuracy reached 7/8."""
    correct = np.array([1, 0, 1, 0, 1, 1, 1, 1, 1, 1], dtype=bool)
    t = calibrate.choose_threshold(CONF, correct)
    assert (t.tau, t.rule, t.n_flagged, t.flag_rate) == (0.5, "cap_20", 2, 0.2)
    assert t.accuracy_unflagged == pytest.approx(0.875)


def test_threshold_cap_branch_when_no_tau_reaches_the_target() -> None:
    """The most confident prediction is wrong, so no subset at or above any tau is 99%."""
    correct = np.array([1] * 9 + [0], dtype=bool)
    t = calibrate.choose_threshold(CONF, correct)
    assert (t.tau, t.rule, t.n_flagged) == (0.5, "cap_20", 2)
    assert t.accuracy_unflagged == pytest.approx(7 / 8)


def test_threshold_keeps_ties_at_tau() -> None:
    """At or above 0.5: 3/4; at or above 0.9: 2/2. Both 0.9s are kept (>= tau)."""
    conf = np.array([0.5, 0.5, 0.9, 0.9])
    correct = np.array([0, 1, 1, 1], dtype=bool)
    t = calibrate.choose_threshold(conf, correct, max_flag_rate=0.5)
    assert (t.tau, t.rule, t.n_flagged) == (0.9, "target_99", 2)


# --------------------------------------------------------------------------- temperature


def test_temperature_recovers_a_known_temperature_and_keeps_the_argmax() -> None:
    rng = np.random.default_rng(0)
    logits = rng.normal(0, 3, size=(20_000, 4))
    p_true = calibrate.softmax(logits, 2.0)
    y = np.array([rng.choice(4, p=p) for p in p_true])
    t = calibrate.fit_temperature(logits, y)
    assert t == pytest.approx(2.0, abs=0.1)
    assert np.array_equal(calibrate.softmax(logits, t).argmax(1), logits.argmax(1))


# --------------------------------------------------------------------------- scorer


def test_calibrated_predictions_round_trip(tmp_path: Path) -> None:
    proba = np.array([[0.7, 0.1, 0.1, 0.1], [0.1, 0.1, 0.2, 0.6]])
    cal = np.array([[0.6, 0.2, 0.1, 0.1], [0.2, 0.2, 0.2, 0.4]])
    path = tmp_path / "m.predictions.csv"
    predictions.write(path, [1, 2], ["test", "test"], proba, {"model": "m"}, cal, [False, True])
    rows, meta = predictions.read(path)
    assert meta == {"model": "m"}
    assert [r["flagged"] for r in rows] == [False, True]
    assert rows[1]["calibrated"] == [0.2, 0.2, 0.2, 0.4]
    with pytest.raises(ValueError, match="changed a predicted class"):
        predictions.write(path, [1], ["test"], proba[:1], {}, cal[1:], [False])


def test_scorer_calibration_figures_by_hand() -> None:
    """Six comments. Right: 1, 2, 4, 6 (4/6). Flagged: 2, 3, 5.

    Un-flagged {1, 4, 6}: all right, accuracy 1.0. Flagged {2, 3, 5}: 2 right, 1/3.
    Errors {3, 5}, both flagged: share 1.0. Sarcastic {3, 4}: 1 error (3), flagged.
    Implicit {5}: 1 error, flagged. Mixed (true) {6}: no errors, share None.
    """
    gold = {
        1: GoldLabel("positive", "none", "c1"),
        2: GoldLabel("neutral", "none", "c2"),
        3: GoldLabel("negative", "sarcastic", "c3"),
        4: GoldLabel("negative", "sarcastic", "c4"),
        5: GoldLabel("negative", "implicit", "c5"),
        6: GoldLabel("mixed", "none", "c6"),
    }
    pred = {1: "positive", 2: "neutral", 3: "positive", 4: "negative", 5: "neutral", 6: "mixed"}
    flagged = {2, 3, 5}
    rows = [
        {
            "feedback_id": i,
            "split": "test",
            "predicted": pred[i],
            "proba": [0.25] * 4,
            "calibrated": [0.25] * 4,
            "flagged": i in flagged,
        }
        for i in gold
    ]
    for r in rows:  # top-class probability 0.97 on the predicted class, raw and calibrated
        k = ["positive", "neutral", "negative", "mixed"].index(r["predicted"])
        r["proba"] = [0.97 if j == k else 0.01 for j in range(4)]
        r["calibrated"] = [0.7 if j == k else 0.1 for j in range(4)]
    c = score.calibration_metrics(rows, gold)
    assert (c["n_flagged"], c["flag_rate"]) == (3, 0.5)
    assert (c["accuracy_unflagged"], c["accuracy_flagged"]) == (1.0, 0.3333)
    # Raw: one bin at 0.97, accuracy 4/6: |0.6667 - 0.97| = 0.3033.
    # Calibrated: one bin at 0.7: |0.6667 - 0.7| = 0.0333.
    assert (c["ece_raw"], c["ece_calibrated"]) == (0.3033, 0.0333)
    ef = c["errors_flagged"]
    assert ef["overall"] == {"n": 6, "errors": 2, "errors_flagged": 2, "share_flagged": 1.0}
    assert ef["sarcastic"] == {"n": 2, "errors": 1, "errors_flagged": 1, "share_flagged": 1.0}
    assert ef["implicit"] == {"n": 1, "errors": 1, "errors_flagged": 1, "share_flagged": 1.0}
    assert ef["mixed"] == {"n": 1, "errors": 0, "errors_flagged": 0, "share_flagged": None}


# --------------------------------------------------------------------------- ledger


def test_the_ledger_refuses_a_second_bert_test_scoring(tmp_path: Path) -> None:
    ledger = tmp_path / "test_ledger.jsonl"
    ledger.write_text(json.dumps({"model": "tfidf_logreg"}) + "\n", encoding="utf-8")
    score.append_ledger({"model": "bert_v1", "macro_f1": 0.95}, ledger)
    with pytest.raises(score.LedgerRefusal, match="bert_v1 was already scored on test"):
        score.append_ledger({"model": "bert_v1", "macro_f1": 0.99}, ledger)
    assert len(ledger.read_text(encoding="utf-8").splitlines()) == 2
