"""Shared data access for sentiment training and evaluation (ADR-063, ADR-064).

Three sources, each through exactly one door:

- Training rows from the database as `app_train`: `feedback_id`, `feedback_text`, and the
  label columns `true_sentiment`, `hard_case_type`, `corpus_id`. `app_train` has no grant
  on `rating` or `generation_parameters`, so nothing here can read them.
- Gold labels for scoring as `app_eval`, never as a runtime role.
- Corpus metadata (`neutral_kind`, `judge_label`, `judge_disagreement`) from the committed
  corpus file via `corpus_id`, never from the database. It is used for stratification
  and reporting only, never as a model feature.

The split is loaded only through `load_split()`, which verifies the manifest's SHA-256
and refuses a mismatched file.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = ROOT / "data" / "generator" / "corpus" / "feedback_text.jsonl"
SPLITS_DIR = Path(__file__).resolve().parent / "splits"

#: Label order used everywhere: probabilities columns, confusion matrices, reports.
LABELS: tuple[str, ...] = ("positive", "neutral", "negative", "mixed")
SPLITS: tuple[str, ...] = ("train", "validation", "test")

_ROLE_VARS = {
    "app_train": ("DB_ROLE_TRAIN_USER", "DB_ROLE_TRAIN_PASSWORD"),
    "app_eval": ("DB_ROLE_EVAL_USER", "DB_ROLE_EVAL_PASSWORD"),
}


@dataclass(frozen=True)
class FeedbackRow:
    feedback_id: int
    feedback_text: str
    true_sentiment: str
    hard_case_type: str
    corpus_id: str


@dataclass(frozen=True)
class GoldLabel:
    true_sentiment: str
    hard_case_type: str
    corpus_id: str


@dataclass(frozen=True)
class CorpusMeta:
    neutral_kind: str | None
    judge_label: str
    judge_disagreement: bool


class SplitIntegrityError(RuntimeError):
    """The split CSV does not match the SHA-256 its manifest records."""


# --------------------------------------------------------------------------- database


def connect(role: str):
    """A read-only connection as `app_train` or `app_eval`; no other role is offered."""
    import psycopg
    from common import connect_timeout_s
    from dotenv import load_dotenv

    if role not in _ROLE_VARS:
        raise ValueError(f"offline scripts connect as app_train or app_eval, not {role!r}")
    load_dotenv(ROOT / ".env", override=False)
    user_var, password_var = _ROLE_VARS[role]
    need = ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", user_var, password_var)
    missing = [v for v in need if not os.environ.get(v)]
    if missing:
        raise SystemExit(f"Missing environment variables: {', '.join(missing)}")
    return psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ[user_var],
        password=os.environ[password_var],
        connect_timeout=connect_timeout_s(),
    )


def load_training_rows(splits: tuple[str, ...] | None = None) -> list[FeedbackRow]:
    """Feedback rows with their labels, read as `app_train`, ordered by `feedback_id`.

    With `splits`, only rows in those splits of split v1 (hash-verified) are fetched; the
    filter runs in SQL, so rows of any other split never leave the database.
    """
    query = """
        SELECT f.feedback_id, f.feedback_text, s.true_sentiment, s.hard_case_type,
               s.corpus_id
        FROM service_feedback f JOIN sentiment_labels s USING (feedback_id)
    """
    params: tuple = ()
    if splits is not None:
        unknown = set(splits) - set(SPLITS)
        if unknown:
            raise ValueError(f"unknown split(s): {sorted(unknown)}")
        wanted = [fid for fid, s in load_split("v1").items() if s in splits]
        query += " WHERE f.feedback_id = ANY(%s)"
        params = (wanted,)
    with connect("app_train") as conn:
        rows = conn.execute(query + " ORDER BY f.feedback_id", params).fetchall()
    return [FeedbackRow(*r) for r in rows]


def load_gold_labels() -> dict[int, GoldLabel]:
    """`feedback_id` → gold label, read as `app_eval` (scoring only)."""
    with connect("app_eval") as conn:
        rows = conn.execute(
            "SELECT feedback_id, true_sentiment, hard_case_type, corpus_id FROM sentiment_labels"
        ).fetchall()
    return {fid: GoldLabel(sent, hard, cid) for fid, sent, hard, cid in rows}


# --------------------------------------------------------------------------- corpus


def load_corpus_meta(path: Path = CORPUS_PATH) -> dict[str, CorpusMeta]:
    """`corpus_id` → the metadata used for stratification and reporting. Never features."""
    meta = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            meta[r["corpus_id"]] = CorpusMeta(
                r["neutral_kind"], r["judge_label"], bool(r["judge_disagreement"])
            )
    return meta


# --------------------------------------------------------------------------- split


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def split_paths(version: str = "v1", directory: Path = SPLITS_DIR) -> tuple[Path, Path]:
    return directory / f"split_{version}.csv", directory / f"split_{version}.manifest.json"


def load_split(version: str = "v1", directory: Path = SPLITS_DIR) -> dict[int, str]:
    """`feedback_id` → split. Verifies the CSV against its manifest's SHA-256 first."""
    csv_path, manifest_path = split_paths(version, directory)
    expected = json.loads(manifest_path.read_text(encoding="utf-8"))["csv_sha256"]
    actual = sha256_file(csv_path)
    if actual != expected:
        raise SplitIntegrityError(
            f"{csv_path.name} has SHA-256 {actual}, but its manifest records {expected}. "
            "The split is frozen; a change is a new version and a new ADR (ADR-064)."
        )
    split: dict[int, str] = {}
    with csv_path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            fid = int(row["feedback_id"])
            if fid in split:
                raise SplitIntegrityError(f"feedback_id {fid} appears twice in {csv_path.name}")
            if row["split"] not in SPLITS:
                raise SplitIntegrityError(f"unknown split {row['split']!r} for {fid}")
            split[fid] = row["split"]
    return split
