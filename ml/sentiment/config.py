"""Fixed BERT settings (ADR-065). Changing any of these is a new ADR, not a tweak.

Everything that loads the model or tokenizer passes `revision=REVISION`, so a later
change on the Hugging Face Hub can never change what is trained or measured.
"""

from __future__ import annotations

from typing import Final

#: `bert-base-uncased` on the Hub, pinned to the commit resolved on 2026-10-01
#: (last modified upstream 2024-02-19).
MODEL_ID: Final = "google-bert/bert-base-uncased"
REVISION: Final = "86b5e0934494bd15c9632b12f734a8a67f723594"
#: The files the tokenizer and model load; also what the latency image copies in.
MODEL_FILES: Final = (
    "config.json",
    "model.safetensors",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
)

#: Smallest of 32/64/96/128 covering at least 99.5% of train comments (ADR-065).
#: Train token counts, [CLS] and [SEP] included: p50 25, p90 37, p99 47, p99.5 50,
#: max 60, so 64 covers 100%; 0 of 1,129 validation comments are truncated.
MAX_LENGTH: Final = 64

SEED: Final = 20261001
BATCH_SIZE: Final = 16
MAX_EPOCHS: Final = 4
PATIENCE: Final = 1
WEIGHT_DECAY: Final = 0.01
WARMUP_FRACTION: Final = 0.10
#: The learning rates ADR-065's budget rule can allow; each run takes one from the CLI.
ALLOWED_LEARNING_RATES: Final = (2e-5, 3e-5)
