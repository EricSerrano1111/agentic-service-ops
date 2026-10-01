"""The BERT training loop's guarantees, on a tiny random BERT (ADR-065). Assembled.

No pretrained weights and no database: a two-layer, 32-wide BERT and a toy vocabulary
stand in for `bert-base-uncased`, so this runs offline in CI in seconds. What is tested is
the loop, not the model: the test split is refused, class weights are scikit-learn's
"balanced", a killed run resumes to exactly the losses an uninterrupted run produces, and
run.json carries every field.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from ml.sentiment import train_bert as tb  # noqa: E402
from ml.sentiment.data import FeedbackRow  # noqa: E402

WORDS = [
    "great",
    "fine",
    "slow",
    "late",
    "broken",
    "thanks",
    "invoice",
    "done",
    "tech",
    "router",
    "quick",
    "rude",
    "ok",
]
LABELS = ("positive", "neutral", "negative", "mixed")


@pytest.fixture(scope="module")
def tokenizer(tmp_path_factory):
    vocab = tmp_path_factory.mktemp("vocab") / "vocab.txt"
    vocab.write_text("\n".join(["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", *WORDS]) + "\n")
    return transformers.BertTokenizerFast(vocab_file=str(vocab))


def tiny_model(tokenizer):
    torch.manual_seed(7)
    cfg = transformers.BertConfig(
        vocab_size=tokenizer.vocab_size,
        hidden_size=32,
        num_hidden_layers=2,
        num_attention_heads=2,
        intermediate_size=64,
        max_position_embeddings=64,
        num_labels=4,
    )
    return transformers.BertForSequenceClassification(cfg)


def rows(n: int, offset: int = 0) -> list[FeedbackRow]:
    return [
        FeedbackRow(
            feedback_id=offset + i,
            feedback_text=" ".join(WORDS[(i + k) % len(WORDS)] for k in range(3 + i % 4)),
            true_sentiment=LABELS[i % 4],
            hard_case_type="none",
            corpus_id=f"fb-{offset + i:06d}",
        )
        for i in range(n)
    ]


DATA = {"train": rows(32), "validation": rows(8, offset=100)}


def settings(run_id: str) -> tb.TrainSettings:
    return tb.TrainSettings(learning_rate=1e-3, run_id=run_id, max_epochs=2, max_length=16)


def losses(run_dir: Path) -> dict[int, float]:
    lines = (run_dir / "train_log.jsonl").read_text(encoding="utf-8").splitlines()
    return {e["step"]: e["loss"] for e in map(json.loads, lines)}


@pytest.mark.parametrize("splits", [("test",), ("train", "test"), ("train", "validation", "test")])
def test_loader_refuses_the_test_split(splits) -> None:
    with pytest.raises(ValueError, match="never loads the test split"):
        tb.load_rows(splits)


def test_class_weights_are_sklearns_balanced() -> None:
    import numpy as np
    from sklearn.utils.class_weight import compute_class_weight

    labels = ["positive"] * 6 + ["neutral"] * 3 + ["negative"] * 2 + ["mixed"]
    expected = compute_class_weight("balanced", classes=np.array(LABELS), y=np.array(labels))
    assert tb.balanced_class_weights(labels) == pytest.approx(expected.tolist())
    assert tb.balanced_class_weights(labels) == pytest.approx([0.5, 1.0, 1.5, 3.0])


def test_class_weights_refuse_a_missing_class() -> None:
    with pytest.raises(ValueError, match="no training examples"):
        tb.balanced_class_weights(["positive", "neutral", "negative"])


@pytest.fixture(scope="module")
def uninterrupted(tokenizer, tmp_path_factory):
    run_dir = tmp_path_factory.mktemp("runs") / "full"
    record = tb.train(settings("full"), DATA, tiny_model(tokenizer), tokenizer, run_dir)
    return run_dir, record


def test_a_killed_run_resumes_to_the_same_next_step_loss(
    tokenizer, uninterrupted, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """32 comments, batch 16: epoch 1 is 2 steps. Kill after its checkpoint, resume."""
    full_dir, _ = uninterrupted
    run_dir = tmp_path / "killed"
    real_write = tb._write_json_atomic

    def write_then_die(path, obj):
        real_write(path, obj)
        if path.name == "state.json" and obj["latest_epoch"] == 1:
            raise KeyboardInterrupt  # the machine sleeps, or the process is killed

    monkeypatch.setattr(tb, "_write_json_atomic", write_then_die)
    with pytest.raises(KeyboardInterrupt):
        tb.train(settings("killed"), DATA, tiny_model(tokenizer), tokenizer, run_dir)
    monkeypatch.setattr(tb, "_write_json_atomic", real_write)

    assert (run_dir / "epoch_1" / "model.safetensors").exists()
    assert not list(run_dir.glob(".epoch_*.tmp"))  # nothing half-written left behind
    assert sorted(losses(run_dir)) == [1, 2]

    # A different starting model: everything after resume must come from the checkpoint.
    torch.manual_seed(999)
    tb.train(settings("killed"), DATA, tiny_model(tokenizer), tokenizer, run_dir, resume=True)

    full, resumed = losses(full_dir), losses(run_dir)
    assert sorted(resumed) == [1, 2, 3, 4]
    assert resumed[3] == pytest.approx(full[3], abs=1e-6)
    assert resumed[4] == pytest.approx(full[4], abs=1e-6)


def test_run_json_has_every_field(uninterrupted) -> None:
    run_dir, record = uninterrupted
    on_disk = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert set(tb.RUN_FIELDS) <= set(on_disk)
    assert on_disk == record
    assert on_disk["revision"] == tb.config.REVISION
    assert on_disk["epochs_completed"] == 2
    assert set(on_disk["val_macro_f1_by_epoch"]) == {"1", "2"}


def test_each_epoch_writes_validation_predictions_and_a_checkpoint(uninterrupted) -> None:
    run_dir, _ = uninterrupted
    for epoch in (1, 2):
        assert (run_dir / f"val_epoch_{epoch}.predictions.csv").exists()
        assert (run_dir / f"epoch_{epoch}" / "trainer_state.pt").exists()
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert state["latest_epoch"] == 2 and state["best_epoch"] in (1, 2)
