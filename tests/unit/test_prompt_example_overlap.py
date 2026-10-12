"""Prompt examples must be newly written and generic (Prompt W, Part A): no quoted example in
`route_v6` or `qa_interp_v3` may be close to a question in the used development sets.

The examples are extracted from the prompt files themselves, so inherited text is checked as
well as new text. This test reads the used development sets only, never `evals/generated/`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JACCARD_LIMIT = 0.6
MIN_WORDS = 4
PROMPTS = [
    ROOT / "services" / "orchestrator" / "prompts" / "route_v6.md",
    ROOT / "services" / "agent_qa" / "prompts" / "qa_interp_v3.md",
]
SETS = [
    *(
        ROOT / "evals" / "routing" / f"{n}.jsonl"
        for n in ("seed_v1", "seed_v2", "routing_v1", "routing_v2", "fr03_fresh_v1")
    ),
    ROOT / "evals" / "qa_interp" / "pairs_v1.jsonl",
]
_QUOTED = re.compile(r'"([^"\n]+)"')


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9']+", text.lower()))


def questions() -> list[str]:
    out: list[str] = []
    for path in SETS:
        for line in path.read_text("utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line)["question"])
    return out


def examples(path: Path) -> list[str]:
    found = []
    for m in _QUOTED.finditer(path.read_text("utf-8")):
        text = m.group(1).strip()
        if "{{" in text or "<" in text or len(words(text)) < MIN_WORDS:
            continue
        found.append(text)
    return found


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def test_only_the_used_development_sets_are_read():
    assert not any("generated" in str(p) for p in SETS)


@pytest.mark.parametrize("path", [p for p in PROMPTS if p.exists()], ids=lambda p: p.stem)
def test_no_example_is_close_to_a_development_question(path):
    qs = [(q, words(q)) for q in questions()]
    exs = examples(path)
    assert exs, "the extraction found no examples: the pattern is stale"
    for ex in exs:
        w = words(ex)
        for q, qw in qs:
            assert jaccard(w, qw) <= JACCARD_LIMIT, f"{path.name}: {ex!r} is close to a set item"
            assert ex.lower() not in q.lower(), f"{path.name}: {ex!r} is inside a set item"
            assert q.lower() not in ex.lower(), f"{path.name}: a set item is inside {ex!r}"
