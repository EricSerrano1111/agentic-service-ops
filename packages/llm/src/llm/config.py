"""LLM client settings from the environment, and the price table.

Free mode is the default and needs only the free key. Paid mode is an explicit opt-in
(`LLM_MODE=paid`) and refuses to start unless its own key, a request cap and a spend
cap are all set (ADR-048). Keys live in `Secret`, which never prints its value.
"""

from __future__ import annotations

import datetime as dt
import os
import tomllib
from dataclasses import dataclass, field
from importlib.resources import files
from typing import Literal

from .errors import LLMConfigError

# Variable names shared with data/generator/build_corpus.py (ADR-041).
FREE_KEY_VAR = "GOOGLE_AI_API_KEY"
PAID_KEY_VAR = "GOOGLE_AI_API_KEY_PAID"

#: Model per caller role; the names already exist in .env.example (ADR-029).
ROLE_MODEL_VARS = {
    "orchestrator": "GEMINI_MODEL_ORCHESTRATOR",
    "specialist": "GEMINI_MODEL_SPECIALIST",
    "qa": "GEMINI_MODEL_QA",
}

Mode = Literal["free", "paid"]
Role = Literal["orchestrator", "specialist", "qa"]

#: Free mode's per-process request cap when LLM_MAX_REQUESTS is unset: generous, but
#: under Flash-Lite's 500 requests per day twice over, so a runaway loop still stops.
FREE_DEFAULT_MAX_REQUESTS = 1000
DEFAULT_MAX_RETRY_WAIT_S = 30.0  # well inside ADR-034's 120 s
DEFAULT_REQUEST_TIMEOUT_S = 30.0
DEFAULT_TEMPERATURE = 0.0  # parsing and classification: least variance
DEFAULT_THINKING_LEVEL = "minimal"  # as build_corpus.py; cheapest thinking setting


class Secret:
    """A string that never appears in `repr`, `str`, logs or exception messages."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "Secret('***')"

    __str__ = __repr__


@dataclass(frozen=True)
class Price:
    input_per_m: float
    output_per_m: float
    source: str
    as_of: dt.date
    note: str = ""

    @property
    def confirmed(self) -> bool:
        return self.source != "UNCONFIRMED"

    def cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        """List-price USD, the same arithmetic as build_corpus.request_cost()."""
        return (input_tokens * self.input_per_m + output_tokens * self.output_per_m) / 1_000_000


def load_price_table(text: str | None = None) -> dict[str, Price]:
    """Parse the packaged prices.toml (or `text`, for tests)."""
    raw = tomllib.loads(text if text is not None else (files("llm") / "prices.toml").read_text())
    table = {}
    for model, entry in raw.get("models", {}).items():
        table[model] = Price(
            input_per_m=float(entry["input_per_m"]),
            output_per_m=float(entry["output_per_m"]),
            source=str(entry["source"]),
            as_of=dt.date.fromisoformat(str(entry["as_of"])),
            note=str(entry.get("note", "")),
        )
    return table


def _float(name: str, default: float | None) -> float | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise LLMConfigError(f"{name} must be a number, got {raw!r}") from None
    if value <= 0:
        raise LLMConfigError(f"{name} must be positive, got {raw!r}")
    return value


def _int(name: str, default: int | None) -> int | None:
    value = _float(name, None if default is None else float(default))
    if value is None:
        return None
    if value != int(value):
        raise LLMConfigError(f"{name} must be a whole number, got {value!r}")
    return int(value)


@dataclass(frozen=True)
class LLMSettings:
    mode: Mode
    api_key: Secret = field(repr=False)
    default_model: str
    max_requests: int
    max_spend_usd: float | None = None  # enforced in paid mode only
    max_retry_wait_s: float = DEFAULT_MAX_RETRY_WAIT_S
    request_timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S
    temperature: float = DEFAULT_TEMPERATURE
    thinking_level: str = DEFAULT_THINKING_LEVEL

    @property
    def key_var(self) -> str:
        return PAID_KEY_VAR if self.mode == "paid" else FREE_KEY_VAR

    @classmethod
    def from_env(cls, role: Role) -> LLMSettings:
        """Read settings for a caller role. Fails at startup on anything missing."""
        env = os.environ.get
        mode = (env("LLM_MODE") or "free").strip().lower()
        if mode not in ("free", "paid"):
            raise LLMConfigError(f"LLM_MODE must be 'free' or 'paid', got {mode!r}")

        model_var = ROLE_MODEL_VARS.get(role)
        if model_var is None:
            raise LLMConfigError(f"unknown role {role!r}; expected one of {list(ROLE_MODEL_VARS)}")
        model = (env(model_var) or "").strip()
        if not model:
            raise LLMConfigError(f"{model_var} must be set (see .env.example)")

        key_var = PAID_KEY_VAR if mode == "paid" else FREE_KEY_VAR
        key = (env(key_var) or "").strip()

        if mode == "paid":
            missing = [
                name
                for name, present in (
                    (PAID_KEY_VAR, bool(key)),
                    ("LLM_MAX_REQUESTS", bool((env("LLM_MAX_REQUESTS") or "").strip())),
                    ("LLM_MAX_SPEND_USD", bool((env("LLM_MAX_SPEND_USD") or "").strip())),
                )
                if not present
            ]
            if missing:
                raise LLMConfigError(
                    "LLM_MODE=paid requires " + ", ".join(missing) + " to be set; paid calls "
                    "are an explicit opt-in with a separate key and caps (ADR-048)"
                )
        elif not key:
            raise LLMConfigError(f"{FREE_KEY_VAR} must be set (see .env.example)")

        return cls(
            mode=mode,  # type: ignore[arg-type]
            api_key=Secret(key),
            default_model=model,
            max_requests=_int(
                "LLM_MAX_REQUESTS", None if mode == "paid" else FREE_DEFAULT_MAX_REQUESTS
            ),
            max_spend_usd=_float("LLM_MAX_SPEND_USD", None),
            max_retry_wait_s=_float("LLM_MAX_RETRY_WAIT_S", DEFAULT_MAX_RETRY_WAIT_S),
            request_timeout_s=_float("LLM_REQUEST_TIMEOUT_S", DEFAULT_REQUEST_TIMEOUT_S),
            temperature=float(env("LLM_TEMPERATURE") or DEFAULT_TEMPERATURE),
            thinking_level=(env("LLM_THINKING_LEVEL") or DEFAULT_THINKING_LEVEL).strip(),
        )
