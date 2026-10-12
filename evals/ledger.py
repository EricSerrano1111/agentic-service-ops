"""Session ledger for the Sprint 5 paid gate runs (Prompt W): one file every runner invocation
reads before each call and appends to after it, so the cap holds across processes.

Per-process caps alone are not enough (each invocation has its own counter). The ledger is the
source for the report's calls-and-cost table. It counts HTTP requests (retries included) and
list-price cost from the client's response metadata, per path (A1, A2, C1, C2).

A call is refused before it is made if it would exceed the request cap, or if the cost already
spent plus the largest single-call cost seen so far (and the caller's estimate) would exceed the
spend cap. A call that retries can overshoot the request count by its retries; the next call is
then refused. Never raise, reset or work around a cap mid-run: the caps are set at file creation
and a later invocation that passes different ones is refused.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
from pathlib import Path

CAP_REQUESTS = 561
CAP_USD = 3.00
PATHS = ("A1", "A2", "C1", "C2")
DEFAULT_PATH = Path(__file__).resolve().parent / "results" / "sprint5_w_ledger.json"


class LedgerRefused(RuntimeError):
    """The ledger would be exceeded by the next call; nothing was sent."""


class Ledger:
    def __init__(
        self,
        path: Path | str = DEFAULT_PATH,
        *,
        cap_requests: int = CAP_REQUESTS,
        cap_usd: float = CAP_USD,
    ) -> None:
        self.path = Path(path)
        self._create_if_missing(cap_requests, cap_usd)
        state = self._load()
        if (state["cap_requests"], state["cap_usd"]) != (cap_requests, cap_usd):
            raise LedgerRefused(
                f"ledger caps are {state['cap_requests']} requests and ${state['cap_usd']:.2f}; "
                f"caps are never changed after the file is created (asked for {cap_requests}, "
                f"${cap_usd:.2f})"
            )

    # ------------------------------------------------------------------ file

    def _create_if_missing(self, cap_requests: int, cap_usd: float) -> None:
        if self.path.exists():
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._save(
            {
                "cap_requests": cap_requests,
                "cap_usd": cap_usd,
                "requests": 0,
                "calls": 0,
                "cost_usd": 0.0,
                "max_call_cost_usd": 0.0,
                "by_path": {},
                "events": [],
            }
        )

    def _load(self) -> dict:
        return json.loads(self.path.read_text("utf-8"))

    def _save(self, state: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    # ------------------------------------------------------------------ use

    def totals(self) -> dict:
        return self._load()

    def check(self, path: str, estimate_usd: float = 0.0) -> None:
        """Raise `LedgerRefused` if one more call could exceed a cap."""
        if path not in PATHS:
            raise LedgerRefused(f"unknown ledger path {path!r}; expected one of {PATHS}")
        s = self._load()
        if s["requests"] + 1 > s["cap_requests"]:
            raise LedgerRefused(
                f"request cap: {s['requests']} of {s['cap_requests']} already counted"
            )
        worst = max(estimate_usd, s["max_call_cost_usd"])
        if s["cost_usd"] + worst > s["cap_usd"]:
            raise LedgerRefused(
                f"spend cap: ${s['cost_usd']:.4f} counted, next call ~${worst:.4f}, "
                f"cap ${s['cap_usd']:.2f}"
            )

    def record(self, path: str, requests: int, cost_usd: float, *, label: str = "") -> None:
        s = self._load()
        s["requests"] += requests
        s["calls"] += 1
        s["cost_usd"] = round(s["cost_usd"] + cost_usd, 8)
        s["max_call_cost_usd"] = max(s["max_call_cost_usd"], cost_usd)
        bp = s["by_path"].setdefault(path, {"requests": 0, "calls": 0, "cost_usd": 0.0})
        bp["requests"] += requests
        bp["calls"] += 1
        bp["cost_usd"] = round(bp["cost_usd"] + cost_usd, 8)
        s["events"].append(
            {
                "at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "path": path,
                "requests": requests,
                "cost_usd": round(cost_usd, 8),
                "label": label,
            }
        )
        self._save(s)

    @contextlib.contextmanager
    def call(self, client, path: str, *, label: str = ""):
        """Around exactly one model call made with `client`: refuse before, count after (also
        when the call raised, since a failed call still sent requests)."""
        self.check(path)
        r0, c0 = client.totals.requests, client.totals.cost_usd
        try:
            yield
        finally:
            self.record(
                path,
                client.totals.requests - r0,
                client.totals.cost_usd - c0,
                label=label,
            )


def require_paid(flag: bool, settings_mode: str, path: str | None) -> None:
    """The explicit paid mode: `--paid` and `LLM_MODE=paid` together, or neither."""
    if flag and settings_mode != "paid":
        raise SystemExit("--paid needs LLM_MODE=paid (and the paid key, caps)")
    if settings_mode == "paid" and not flag:
        raise SystemExit("LLM_MODE=paid is set: pass --paid (with --path) to spend, or unset it")
    if flag and path not in PATHS:
        raise SystemExit(f"--paid needs --path one of {', '.join(PATHS)}")
