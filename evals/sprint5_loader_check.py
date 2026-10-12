"""No-model-call check that the runners can read the frozen generated sets (Prompt W, Part C).

Prints key names, counts of short categorical values and role/domain counts. Never prints an
item's text (long strings and nested values are shown as a kind only). Any fix it forces is
format mapping only (evals/sprint5_gates.md).
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETS = ROOT / "evals" / "generated" / "sets"
SHORT = 24  # characters: longer strings are item text and are never printed
MAX_DISTINCT = 12
ROUTING_KEYS = {"id", "question", "expected", "tag"}
PAIR_KEYS = {"id", "domain", "label", "question", "request"}


def describe(name: str, needed: set[str]) -> list[dict]:
    rows = [json.loads(x) for x in (SETS / name).read_text("utf-8").splitlines() if x.strip()]
    keys = Counter(k for r in rows for k in r)
    print(f"{name}: {len(rows)} rows")
    for key, n in sorted(keys.items()):
        values = [r[key] for r in rows if key in r]
        kinds = Counter(type(v).__name__ for v in values)
        shown = [str(v) for v in values if isinstance(v, str)]
        categorical = (
            shown
            and len(shown) == len(values)
            and all(len(s) <= SHORT for s in shown)
            and len(set(shown)) <= MAX_DISTINCT
        )
        detail = dict(Counter(shown)) if categorical else dict(kinds)
        print(f"  {key}: in {n} rows; {detail}")
    missing = needed - set(keys)
    print(f"  runner needs {sorted(needed)}; missing: {sorted(missing) or 'none'}")
    return rows


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    fresh = describe("fr03_fresh_v2.jsonl", ROUTING_KEYS)
    split = Counter(
        "ambiguous" if r.get("expected") == "ambiguous" else "non-ambiguous" for r in fresh
    )
    print(f"  fr03_fresh_v2 split: {dict(split)} (expected 8 and 8)")
    pairs = describe("interp_pairs_v1.jsonl", PAIR_KEYS)
    roles = Counter((r.get("domain"), r.get("label")) for r in pairs)
    for (domain, label), n in sorted(roles.items(), key=str):
        print(f"  pairs {domain} / {label}: {n}")
    print("  expected: 23 matches + 23 mismatch; reporting 10, forecast 7, sentiment 6 per role")
    return 0


if __name__ == "__main__":
    sys.exit(main())
