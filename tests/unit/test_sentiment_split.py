"""Sentiment split v1 is intact, and its loader refuses a tampered file (ADR-064).

The committed split is checked directly: its manifest hash matches the CSV, and no
`feedback_id` sits in two splits. The grouping and assignment functions are checked on
hand-built toy texts, so these tests need no database.
"""

from __future__ import annotations

import csv
import shutil
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from ml.sentiment import data  # noqa: E402
from ml.sentiment import split as sp  # noqa: E402

CSV_PATH, MANIFEST_PATH = data.split_paths("v1")


def _rows() -> list[dict]:
    with CSV_PATH.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_manifest_hash_matches_the_csv() -> None:
    import json

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["csv_sha256"] == data.sha256_file(CSV_PATH)
    assert manifest["seed"] == 20261001


def test_no_feedback_id_in_two_splits() -> None:
    counts = Counter(r["feedback_id"] for r in _rows())
    assert [fid for fid, n in counts.items() if n > 1] == []


def test_csv_holds_no_labels_and_no_text() -> None:
    with CSV_PATH.open(encoding="utf-8", newline="") as fh:
        assert next(csv.reader(fh)) == ["feedback_id", "corpus_id", "split"]


def test_load_split_verifies_and_returns_every_row() -> None:
    split = data.load_split("v1")
    assert len(split) == len(_rows())
    assert set(split.values()) == set(data.SPLITS)


def test_load_split_refuses_a_mismatched_file(tmp_path: Path) -> None:
    shutil.copy(MANIFEST_PATH, tmp_path / MANIFEST_PATH.name)
    tampered = CSV_PATH.read_bytes().replace(b",test\n", b",train\n", 1)
    (tmp_path / CSV_PATH.name).write_bytes(tampered)

    with pytest.raises(data.SplitIntegrityError, match="SHA-256"):
        data.load_split("v1", directory=tmp_path)


def test_normalise_lowercases_and_collapses_whitespace() -> None:
    assert sp.normalise("  The  TECH\tarrived\n late ") == "the tech arrived late"


def test_near_duplicates_are_grouped_and_distinct_texts_are_not() -> None:
    texts = [
        "The technician fixed the router quickly.",
        "the technician  fixed the router quickly!",
        "Invoice arrived; nothing else to report this month.",
        "Badge reader replaced, every door working again.",
    ]
    groups = sp.group_ids(len(texts), sp.near_duplicate_pairs(texts))
    assert groups[0] == groups[1]
    assert len({groups[0], groups[2], groups[3]}) == 3


def test_whole_groups_stay_in_one_split() -> None:
    groups = np.array([0, 0, 0, 1, 2, 3, 3, 4, 5, 6] * 10) + np.repeat(np.arange(10) * 7, 10)
    strata = [("positive", "none")] * len(groups)
    assignment = sp.assign_splits(groups, strata, seed=1)
    for g in set(groups.tolist()):
        assert len({assignment[i] for i, gg in enumerate(groups) if gg == g}) == 1


def test_mixed_label_group_takes_its_majority_stratum() -> None:
    assert sp.majority([("neutral", "none"), ("positive", "none"), ("neutral", "none")]) == (
        "neutral",
        "none",
    )
