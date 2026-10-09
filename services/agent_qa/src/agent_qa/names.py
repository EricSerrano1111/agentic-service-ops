"""Name lookup for technician and account filters, from data dictionary §6 (ADR-087).

§6: "every word of the query must be a whole word of the name, case-insensitive; at most 5
matches plus the total count; pattern and wildcard characters rejected". A word is a
whitespace-separated token of the case-folded text. This is QA's own statement of the rule: it
is used to confirm that a name the user typed picks out exactly the technician or account a
filtered answer is about, and that a "no match" or "several matches" decline was right.

The tokenisation (whitespace) is the one reading of "whole word" §6 leaves open; it is recorded
in the limitations log (L-72).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Letters, spaces, apostrophes, hyphens and periods only; everything else is a pattern or
#: wildcard character and is rejected (§6).
_ALLOWED = re.compile(r"^[^\W\d_]+(?:[ '.\-]+[^\W\d_]+)*\.?$")
MAX_NAME_CHARS = 100
MAX_LISTED = 5


@dataclass(frozen=True)
class Matches:
    rejected: bool  # the name has characters no name has
    total: int
    listed: tuple[tuple[int, str], ...]  # (id, name), at most 5, by name then id


def match(query: str, candidates: list[tuple[int, str]]) -> Matches:
    cleaned = " ".join(query.split()) if isinstance(query, str) else ""
    if not cleaned or len(cleaned) > MAX_NAME_CHARS or not _ALLOWED.match(cleaned):
        return Matches(True, 0, ())
    wanted = cleaned.casefold().split()
    found = [(i, n) for i, n in candidates if all(w in n.casefold().split() for w in wanted)]
    found.sort(key=lambda m: (m[1].casefold(), m[0]))
    return Matches(False, len(found), tuple(found[:MAX_LISTED]))
