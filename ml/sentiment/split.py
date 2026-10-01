"""Sentiment split v1: near-duplicate groups, then a stratified group split (ADR-064).

    python -m ml.sentiment.split            # compute and report; writes nothing
    python -m ml.sentiment.split --write    # also write split_v1.csv and its manifest

Reads training rows as `app_train` (`feedback_id`, `feedback_text`, the label columns) and
neutral kinds from the committed corpus via `corpus_id`. Text is used only to find
near-duplicates; no text or label is written to the split file.

1. Near-duplicate groups. Text is lowercased and whitespace-collapsed; each text becomes
   its set of character 5-grams; Jaccard similarity is computed for every pair through a
   sparse matrix product; pairs above 0.6 are linked (ADR-036's within-cell rule, here
   across all rows); connected components are the groups.
2. Whole groups are assigned to train / validation / test, about 70/15/15, within each
   `true_sentiment` × `hard_case_type` stratum, with one seed. A group whose members carry
   different strata takes its majority stratum.
3. Acceptance checks and stop rules are enforced here: `--write` refuses to write if any
   fails. The threshold and seed are never tuned to make them pass (ADR-064).

Prints statistics, and at most ten mixed-label example pairs, truncated.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections import Counter, defaultdict
from datetime import date

import numpy as np
from scipy import sparse
from scipy.sparse.csgraph import connected_components

from ml.sentiment import data

SEED = 20261001
THRESHOLD = 0.6
SHINGLE = 5
FRACTIONS = {"train": 0.70, "validation": 0.15, "test": 0.15}
VERSION = "v1"

# Acceptance checks and stop rules (ADR-064), fixed before the split was computed.
TOLERANCE_PP = 2.0  # each split's share, for strata of at least MIN_STRATUM_FOR_TOLERANCE
MIN_STRATUM_FOR_TOLERANCE = 100
MIN_TEST_ROWS = 10
MAX_LARGEST_GROUP = 75
MAX_SHARE_IN_GROUPS = 0.05
MAX_SHARE_MIXED_LABEL = 0.01
_BLOCK = 512


def normalise(text: str) -> str:
    """Lowercase and collapse every run of whitespace to one space."""
    return " ".join(text.lower().split())


def shingles(text: str, k: int = SHINGLE) -> set[str]:
    """Character k-grams of the normalised text; a text shorter than k is one shingle."""
    t = normalise(text)
    if len(t) <= k:
        return {t}
    return {t[i : i + k] for i in range(len(t) - k + 1)}


def near_duplicate_pairs(texts: list[str], threshold: float = THRESHOLD) -> list[tuple[int, int]]:
    """Every pair (i, j), i < j, whose shingle-set Jaccard similarity exceeds `threshold`."""
    vocab: dict[str, int] = {}
    indptr, indices = [0], []
    for t in texts:
        for s in shingles(t):
            indices.append(vocab.setdefault(s, len(vocab)))
        indptr.append(len(indices))
    x = sparse.csr_matrix(
        (np.ones(len(indices), dtype=np.float32), indices, indptr),
        shape=(len(texts), len(vocab)),
    )
    sizes = np.asarray(x.sum(axis=1)).ravel()
    xt = x.T.tocsc()
    pairs: list[tuple[int, int]] = []
    for start in range(0, len(texts), _BLOCK):
        stop = min(start + _BLOCK, len(texts))
        inter = (x[start:stop] @ xt).toarray()
        union = sizes[start:stop, None] + sizes[None, :] - inter
        jaccard = inter / union
        rows, cols = np.nonzero(jaccard > threshold)
        for r, c in zip(rows, cols, strict=True):
            i = start + int(r)
            if int(c) > i:
                pairs.append((i, int(c)))
    return pairs


def group_ids(n: int, pairs: list[tuple[int, int]]) -> np.ndarray:
    """Connected-component label for each of the n rows."""
    if not pairs:
        return np.arange(n)
    i, j = np.array(pairs).T
    graph = sparse.coo_matrix((np.ones(len(pairs)), (i, j)), shape=(n, n))
    _, labels = connected_components(graph, directed=False)
    return labels


def majority(strata: list[tuple[str, str]]) -> tuple[str, str]:
    """Most common stratum; ties go to the lexicographically smallest, deterministically."""
    counts = Counter(strata)
    return min(counts, key=lambda s: (-counts[s], s))


def assign_splits(groups: np.ndarray, strata: list[tuple[str, str]], seed: int = SEED) -> list[str]:
    """Whole groups to splits, per majority stratum, filling each split's largest deficit."""
    members: dict[int, list[int]] = defaultdict(list)
    for idx, g in enumerate(groups):
        members[int(g)].append(idx)
    by_stratum: dict[tuple[str, str], list[int]] = defaultdict(list)
    for g, idxs in members.items():
        by_stratum[majority([strata[i] for i in idxs])].append(g)

    rng = np.random.default_rng(seed)
    assignment = [""] * len(groups)
    for stratum in sorted(by_stratum):
        gs = sorted(by_stratum[stratum], key=lambda g: min(members[g]))
        total = sum(len(members[g]) for g in gs)
        filled = dict.fromkeys(FRACTIONS, 0)
        for k in rng.permutation(len(gs)):
            g = gs[k]
            target = max(FRACTIONS, key=lambda s: FRACTIONS[s] * total - filled[s])
            filled[target] += len(members[g])
            for i in members[g]:
                assignment[i] = target
    return assignment


# --------------------------------------------------------------------------- statistics


def group_statistics(groups, labels: list[str], texts: list[str]) -> tuple[dict, list[dict]]:
    members: dict[int, list[int]] = defaultdict(list)
    for idx, g in enumerate(groups):
        members[int(g)].append(idx)
    n = len(groups)
    sizes = Counter(len(m) for m in members.values())
    largest = max(members.values(), key=len)
    multi_rows = sum(len(m) for m in members.values() if len(m) > 1)
    mixed = [m for m in members.values() if len({labels[i] for i in m}) > 1]
    examples = []
    for m in sorted(mixed, key=min)[:10]:
        a = m[0]
        b = next(i for i in m if labels[i] != labels[a])
        examples.append(
            {
                "a": (labels[a], texts[a][:160]),
                "b": (labels[b], texts[b][:160]),
                "group_size": len(m),
            }
        )
    stats = {
        "rows": n,
        "groups": len(members),
        "size_distribution": {str(k): v for k, v in sorted(sizes.items())},
        "largest_group_size": len(largest),
        "largest_group_labels": dict(Counter(labels[i] for i in largest)),
        "rows_in_groups_gt1": multi_rows,
        "share_rows_in_groups_gt1": round(multi_rows / n, 6),
        "mixed_label_groups": len(mixed),
        "mixed_label_rows": sum(len(m) for m in mixed),
        "share_rows_mixed_label": round(sum(len(m) for m in mixed) / n, 6),
    }
    return stats, examples


def split_table(assignment: list[str], strata: list[tuple[str, str]]) -> dict:
    table: dict[str, dict[str, int]] = defaultdict(lambda: dict.fromkeys(FRACTIONS, 0))
    for s, a in zip(strata, assignment, strict=True):
        table[f"{s[0]}|{s[1]}"][a] += 1
    return {k: table[k] for k in sorted(table)}


def acceptance(table: dict, groups, assignment: list[str]) -> list[str]:
    """Failed acceptance checks, as messages; empty means every check passed."""
    failures = []
    for stratum, counts in table.items():
        total = sum(counts.values())
        if total >= MIN_STRATUM_FOR_TOLERANCE:
            for split, frac in FRACTIONS.items():
                share = 100 * counts[split] / total
                if abs(share - 100 * frac) > TOLERANCE_PP:
                    failures.append(f"{stratum}: {split} is {share:.2f}% (target {frac:.0%})")
        if counts["test"] < MIN_TEST_ROWS:
            failures.append(f"{stratum}: only {counts['test']} test rows")
    spans = defaultdict(set)
    for g, a in zip(groups, assignment, strict=True):
        spans[int(g)].add(a)
    crossing = [g for g, s in spans.items() if len(s) > 1]
    if crossing:
        failures.append(f"{len(crossing)} groups span two splits")
    return failures


def stop_rules(stats: dict) -> list[str]:
    fired = []
    if stats["largest_group_size"] > MAX_LARGEST_GROUP:
        fired.append(f"largest group {stats['largest_group_size']} > {MAX_LARGEST_GROUP}")
    if stats["share_rows_in_groups_gt1"] > MAX_SHARE_IN_GROUPS:
        fired.append(f"{stats['share_rows_in_groups_gt1']:.2%} of rows in groups > 1 (max 5%)")
    if stats["share_rows_mixed_label"] > MAX_SHARE_MIXED_LABEL:
        fired.append(f"mixed-label groups cover {stats['share_rows_mixed_label']:.2%} (max 1%)")
    return fired


# --------------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--write", action="store_true", help="write the split and its manifest")
    args = ap.parse_args(argv)

    rows = data.load_training_rows()
    meta = data.load_corpus_meta()
    texts = [r.feedback_text for r in rows]
    labels = [r.true_sentiment for r in rows]
    strata = [(r.true_sentiment, r.hard_case_type) for r in rows]
    print(f"{len(rows)} rows read as app_train")

    pairs = near_duplicate_pairs(texts)
    groups = group_ids(len(rows), pairs)
    stats, examples = group_statistics(groups, labels, texts)
    stats["linked_pairs"] = len(pairs)
    print(json.dumps(stats, indent=1))
    for k, ex in enumerate(examples, 1):
        print(f"mixed-label example {k} (group of {ex['group_size']}):")
        print(f"  [{ex['a'][0]}] {ex['a'][1]}")
        print(f"  [{ex['b'][0]}] {ex['b'][1]}")

    assignment = assign_splits(groups, strata)
    table = split_table(assignment, strata)
    neutral = defaultdict(lambda: dict.fromkeys(FRACTIONS, 0))
    for r, a in zip(rows, assignment, strict=True):
        if r.true_sentiment == "neutral":
            neutral[str(meta[r.corpus_id].neutral_kind)][a] += 1
    neutral_kinds = {k: neutral[k] for k in sorted(neutral)}
    print("stratum                 train  valid   test")
    for stratum, c in table.items():
        print(f"{stratum:22} {c['train']:6} {c['validation']:6} {c['test']:6}")
    print("neutral kind            train  valid   test")
    for kind, c in neutral_kinds.items():
        print(f"{kind:22} {c['train']:6} {c['validation']:6} {c['test']:6}")

    fired = stop_rules(stats)
    failed = acceptance(table, groups, assignment)
    for msg in fired:
        print(f"STOP RULE: {msg}")
    for msg in failed:
        print(f"ACCEPTANCE FAILED: {msg}")
    if fired or failed:
        print("Nothing written. The threshold and seed are not tuned to pass (ADR-064).")
        return 1
    print("All acceptance checks pass; no stop rule fired.")
    if not args.write:
        return 0

    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["feedback_id", "corpus_id", "split"])
    for r, a in sorted(zip(rows, assignment, strict=True), key=lambda x: x[0].feedback_id):
        writer.writerow([r.feedback_id, r.corpus_id, a])
    csv_path, manifest_path = data.split_paths(VERSION)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_bytes(buf.getvalue().encode("utf-8"))

    manifest = {
        "version": VERSION,
        "created": date.today().isoformat(),
        "adr": "ADR-064",
        "seed": SEED,
        "fractions": FRACTIONS,
        "near_duplicates": {
            "normalisation": "lowercase; every whitespace run collapsed to one space",
            "representation": f"set of character {SHINGLE}-grams (whole text if shorter)",
            "similarity": "Jaccard, all pairs, scipy sparse matrix product",
            "threshold": f"> {THRESHOLD}",
            "grouping": "connected components of linked pairs",
            "mixed_label_groups": "assigned by majority stratum",
        },
        "strata": "true_sentiment x hard_case_type",
        "source": {
            "rows": len(rows),
            "read_as": "app_train",
            "corpus_sha256": data.sha256_file(data.CORPUS_PATH),
        },
        "group_statistics": stats,
        "counts_by_stratum": table,
        "neutral_kind_counts": neutral_kinds,
        "split_totals": dict(Counter(assignment)),
        "acceptance": {
            "tolerance_pp": TOLERANCE_PP,
            "min_stratum_for_tolerance": MIN_STRATUM_FOR_TOLERANCE,
            "min_test_rows": MIN_TEST_ROWS,
            "passed": True,
        },
        "csv": csv_path.name,
        "csv_sha256": data.sha256_file(csv_path),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {csv_path.name} ({manifest['csv_sha256'][:12]}...) and {manifest_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
