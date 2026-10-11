"""The frozen evaluation sets (ADR-094) still match `evals/generated/manifest.json`.

Recomputes each file's SHA-256, git blob hash and line count from the bytes. It never asks git
for a commit, so it holds in a shallow clone. Final sets are append-never: a change is a new
version under a new ADR, never an edit that makes this test pass.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GENERATED = ROOT / "evals" / "generated"
MANIFEST = GENERATED / "manifest.json"
FINAL_SETS = {
    "routing_heldout_v1",
    "fr03_fresh_v2",
    "interp_fresh_v1",
    "interp_pairs_v1",
    "parse_filters_v1",
    "reserve",
}


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _all_files(manifest: dict) -> dict[str, dict]:
    return {**manifest["sets"], **manifest["supporting"]}


def _jsonl(name: str) -> list[dict]:
    path = GENERATED / "sets" / f"{name}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_manifest_lists_every_final_set() -> None:
    manifest = _manifest()
    names = {Path(p).stem for p in manifest["sets"]}
    assert names == FINAL_SETS
    assert len(manifest["freeze_commit"]) == 40
    assert manifest["freeze_time"]


def test_every_manifest_hash_is_recomputed_from_the_file() -> None:
    manifest = _manifest()
    mismatches = []
    for rel, recorded in _all_files(manifest).items():
        data = (ROOT / rel).read_bytes()
        actual = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "git_blob": hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest(),
            "lines": data.count(b"\n"),
        }
        if actual != recorded:
            mismatches.append(rel)
    assert not mismatches, f"frozen files changed: {mismatches}"


def test_frozen_files_are_lf_and_no_draft_remains() -> None:
    for rel in _all_files(_manifest()):
        assert b"\r" not in (ROOT / rel).read_bytes(), rel
    assert not list((GENERATED / "sets").glob("*.draft.jsonl"))


def test_sets_are_disjoint_and_pairs_cover_the_interpretation_set() -> None:
    seen: dict[str, str] = {}
    for name in FINAL_SETS - {"interp_pairs_v1"}:
        for row in _jsonl(name):
            assert row["uid"] not in seen, f"{row['uid']} is in {name} and {seen[row['uid']]}"
            seen[row["uid"]] = name
    interp = {r["uid"] for r in _jsonl("interp_fresh_v1")}
    pairs = _jsonl("interp_pairs_v1")
    assert {p["source_id"] for p in pairs} == interp
    for uid in interp:
        roles = sorted(p["role"] for p in pairs if p["source_id"] == uid)
        assert roles == ["correct", "wrong"], uid
