"""The case generator (frozen with catalogue_v1.yaml; seed 20261010).

For each fault: the base answers whose attributes make it applicable, in an order fixed by the
seed. Owner faults list their anchor (the owner's exact question) first. The harness walks
this order and takes the first `MAX_CASES` for which the mutation can be made; a base answer
it cannot be made on is recorded as skipped with the reason. Nothing is hand-picked.
"""

from __future__ import annotations

import random

SEED = 20261010
MAX_CASES = 10


def case_id(fault_id: str, base_id: str) -> str:
    return f"{fault_id}|{base_id}"


def case_rng(fault_id: str, base_id: str) -> random.Random:
    return random.Random(f"{SEED}:{fault_id}:{base_id}")


def candidate_order(fault_id: str, applicable: list[dict], anchors: set[str]) -> list[str]:
    """Anchors first (sorted), then every other applicable base id in the seeded shuffle."""
    ids = sorted(b["base_id"] for b in applicable)
    first = [i for i in ids if i in anchors]
    rest = [i for i in ids if i not in anchors]
    random.Random(f"{SEED}:{fault_id}").shuffle(rest)
    return first + rest
