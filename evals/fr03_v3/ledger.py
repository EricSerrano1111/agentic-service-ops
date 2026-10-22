"""The harness ledger for FR-03's third attempt (ADR-114, "Budget, kept in the harness ledger").

An append-only JSONL file, `evals/fr03_v3/ledger.jsonl`. It is the only source of truth for the
request and spend caps; the per-process `LLM_MAX_*` caps are a backstop. The file is only ever
opened in append mode for writing: nothing rewrites, truncates or edits an earlier line.

Events, one line each: `balance_reading`, `run_start`, `run_end`, `verdict`, `refused`, `stop`.
Every constant below is copied from ADR-114 and does not change once the first model call is made.

Not named `evals/ledger.py` (the Sprint 5 ledger, imported by `run_seed.py` as `ledger`): load this
file by path, never as the bare module name `ledger`.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import statistics
import subprocess
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEDGER_PATH = HERE / "ledger.jsonl"

REQUEST_CAP = 1550  # retries counted (ADR-114 budget table)
SPEND_CAP_USD = 2.50  # list price, summed across every phase
PROJECTION_FACTOR = 1.25
MIN_BALANCE_USD = 7.50
CEILING_COST_PER_CALL_USD = 0.003  # P0's drop threshold; the projection before a probe result
P95_LATENCY_CEILING_S = 10.0  # P0's drop threshold (P1's G5 also uses it)
LEVELS = ("minimal", "low", "medium", "high")
#: 2026-11-07 23:59 CT. The window is CST (UTC-6) by then: daylight saving ends 2026-11-01.
TIMEBOX_END_UTC = dt.datetime(2026, 11, 8, 5, 59, tzinfo=dt.UTC)


class Refused(RuntimeError):
    """The run would cross a cap, or a precondition does not hold; nothing was sent."""


@dataclass(frozen=True)
class Projection:
    requests: int
    usd: float
    basis: str  # "probe" (measured mean cost for the level) or "ceiling"


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def stamp(when: dt.datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def percentile_95(values: list[float]) -> float | None:
    """Nearest rank: the smallest value with at least 95% of the sample at or below it."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def latency_summary(latencies: list[float]) -> dict:
    if not latencies:
        return {"median_s": None, "p95_s": None}
    return {"median_s": round(statistics.median(latencies), 3), "p95_s": percentile_95(latencies)}


def git_state() -> dict:
    def git(*args: str) -> str:
        out = subprocess.run(["git", *args], capture_output=True, text=True, cwd=HERE, check=False)
        return out.stdout.strip()

    return {"git_commit": git("rev-parse", "HEAD"), "git_dirty": bool(git("status", "--short"))}


class Ledger:
    def __init__(self, path: Path | str = LEDGER_PATH) -> None:
        self.path = Path(path)

    # ------------------------------------------------------------------ file

    def append(self, event: str, **fields) -> dict:
        line = {"event": event, "at": stamp(utc_now()), **fields}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(line, sort_keys=False) + "\n")
        return line

    def events(self) -> list[dict]:
        if not self.path.exists():
            return []
        text = self.path.read_text(encoding="utf-8")
        return [json.loads(row) for row in text.splitlines() if row.strip()]

    # ------------------------------------------------------------------ reading it back

    def totals(self) -> dict:
        """Requests, calls and list-price dollars summed over every `run_end`, plus the probe's
        measured mean cost per call for each level. The only source of truth for the caps."""
        requests, calls, cost = 0, 0, 0.0
        probe_mean: dict[str, float] = {}
        for e in self.events():
            if e["event"] != "run_end":
                continue
            requests += e["requests"]
            calls += e["calls"]
            cost += e["cost_usd"]
            if e["phase"] == "P0" and e["calls"] > 0:
                probe_mean[e["level"]] = e["cost_usd"] / e["calls"]
        return {
            "requests": requests,
            "calls": calls,
            "cost_usd": round(cost, 6),
            "probe_mean_cost_per_call": probe_mean,
        }

    def latest_balance(self) -> float | None:
        readings = [e for e in self.events() if e["event"] == "balance_reading"]
        return readings[-1]["balance_usd"] if readings else None

    # ------------------------------------------------------------------ projection and gate

    def project(self, level: str, n_items: int, k: int) -> Projection:
        """Requests are items x k (retries are only known afterwards). Dollars are the probe's
        measured mean cost per call for the level x items x k x 1.25; before a probe result for
        the level exists, the $0.003 ceiling stands in for the mean."""
        measured = self.totals()["probe_mean_cost_per_call"].get(level)
        per_call = CEILING_COST_PER_CALL_USD if measured is None else measured
        return Projection(
            requests=n_items * k,
            usd=per_call * n_items * k * PROJECTION_FACTOR,
            basis="ceiling" if measured is None else "probe",
        )

    def record_balance(self, balance_usd: float) -> dict:
        """The owner-entered prepaid balance. A reading below the minimum is recorded (it is a
        fact) and makes `authorize` refuse every run."""
        return self.append("balance_reading", balance_usd=round(float(balance_usd), 2))

    def authorize(
        self, run: dict, *, now: dt.datetime | None = None, dry_run: bool = False
    ) -> Projection:
        """Refuse (raise `Refused`, and write a `refused` line unless `dry_run`) if the run would
        cross a cap or a precondition fails. `run` carries phase, level, items and k."""
        now = now or utc_now()
        level, n_items, k = run["level"], run["items"], run["k"]
        totals = self.totals()
        projection = self.project(level, n_items, k) if level in LEVELS else None
        balance = self.latest_balance()
        reason = None
        if level not in LEVELS:
            reason = f"unknown thinking level {level!r}"
        elif now > TIMEBOX_END_UTC:
            reason = f"the timebox ended {stamp(TIMEBOX_END_UTC)} (2026-11-07 23:59 CT)"
        elif balance is None:
            reason = "no balance_reading in the ledger: the owner records the prepaid balance first"
        elif balance < MIN_BALANCE_USD:
            reason = f"prepaid balance ${balance:.2f} is below the ${MIN_BALANCE_USD:.2f} minimum"
        elif totals["requests"] + projection.requests > REQUEST_CAP:
            reason = (
                f"request cap: {totals['requests']} counted + {projection.requests} projected "
                f"> {REQUEST_CAP}"
            )
        elif round(totals["cost_usd"] + projection.usd, 6) > SPEND_CAP_USD:
            reason = (
                f"spend cap: ${totals['cost_usd']:.4f} counted + ${projection.usd:.4f} projected "
                f"> ${SPEND_CAP_USD:.2f}"
            )
        if reason:
            if not dry_run:
                self.append(
                    "refused",
                    **{k_: v for k_, v in run.items() if k_ != "dry_run"},
                    reason=reason,
                    counted_requests=totals["requests"],
                    counted_usd=totals["cost_usd"],
                )
            raise Refused(reason)
        return projection

    # ------------------------------------------------------------------ run events

    def run_start(self, run: dict) -> dict:
        return self.append("run_start", **run, **git_state())

    def run_end(self, run: dict, summary: dict) -> dict:
        """`summary` carries calls, requests, input/output/thinking tokens, cost_usd, latency
        median and p95, and errors by type."""
        return self.append("run_end", **run, **summary)

    def verdict(self, level: str, kept: bool, reason: str, **numbers) -> dict:
        return self.append("verdict", phase="P0", level=level, kept=kept, reason=reason, **numbers)

    def stop(self, reason: str, **fields) -> dict:
        return self.append("stop", reason=reason, **fields)


def all_zero_thinking(level: str, thinking_tokens: list[int]) -> bool:
    """ADR-114 P0's stop: every call at a level above `minimal` reported zero thinking tokens."""
    return level != "minimal" and bool(thinking_tokens) and not any(thinking_tokens)


def probe_verdict(mean_cost: float, p95_s: float | None) -> tuple[bool, str]:
    """ADR-114 P0's drop rule: mean cost per call above $0.003, or p95 latency above 10 s."""
    reasons = []
    if mean_cost > CEILING_COST_PER_CALL_USD:
        reasons.append(f"mean cost ${mean_cost:.5f} per call is above ${CEILING_COST_PER_CALL_USD}")
    if p95_s is not None and p95_s > P95_LATENCY_CEILING_S:
        reasons.append(f"p95 latency {p95_s:.2f} s is above {P95_LATENCY_CEILING_S:g} s")
    return (not reasons, "; ".join(reasons) or "within the cost and latency ceilings")
