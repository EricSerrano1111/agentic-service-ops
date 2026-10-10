"""The text-matches-data check (ADR-087): every number a specialist's answer text states must be
one the verified data supports, and the headline numbers must be there.

What it catches: a number in the text that is in no figure (a stale or invented one), and a
headline figure missing from the text. What it cannot catch: two real figures swapped with each
other, a wrong label next to a right number, or a sentence that reads the right numbers
wrongly. Those limits are recorded in the limitations log (L-72); the answer text is rendered
from a template by the specialist, not written by a model, which is why a number check is
worth having at all.

Names, ISO dates and ADR references are removed before numbers are read, so a name with a digit
in it or a date is never mistaken for a figure.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from collections.abc import Iterable
from decimal import Decimal

_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_ADR = re.compile(r"\bADR-\d+\b")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def strip_names(text: str, names: Iterable[str]) -> str:
    for name in sorted({n for n in names if n}, key=len, reverse=True):
        text = text.replace(name, " ")
    return text


def numbers_in(text: str, names: Iterable[str] = ()) -> list[str]:
    """The numbers the text states, commas removed ("1,234" -> "1234")."""
    text = _ADR.sub(" ", _DATE.sub(" ", strip_names(text, names)))
    found = []
    for token in _NUMBER.findall(text):
        found.append(token.rstrip(",").replace(",", ""))
    return found


def percent(rate: str) -> str:
    """A 4-place fraction as a 2-place percentage, exactly: "0.8881" -> "88.81"."""
    return f"{Decimal(rate) * 100:.2f}"


def int_forms(value: int) -> set[str]:
    return {str(value)}


def approx_forms(value: float) -> set[str]:
    """A figure shown rounded to a whole number: either neighbour counts as that figure."""
    return {str(math.floor(value)), str(math.ceil(value)), str(round(value))}


def one_decimal(value: float) -> str:
    return f"{value:.1f}"


def compare(
    text: str,
    allowed: set[str],
    required: list[set[str]],
    names: Iterable[str] = (),
) -> list[str]:
    """Problems found, as fixed codes. `allowed` is every number the text may state; each
    entry of `required` is a set of spellings of one headline number, any one of which must
    appear."""
    stated = set(numbers_in(text, names))
    problems = []
    if stated - allowed:
        problems.append("text_states_unsupported_number")
    for forms in required:
        if not (forms & stated):
            problems.append("text_misses_headline_number")
            break
    return problems


def window_dates(*dates: dt.date) -> set[str]:
    return {d.isoformat() for d in dates}
