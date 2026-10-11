"""QA's own reimplementation of the `volume_v2` prediction (ADR-095, data dictionary §6,
"Forecast recompute (QA)").

Written from the model's equations and the stored parameters, in pure Python (`math`): no
`forecast_runtime`, no numpy, no fitting library. The only inputs are the artifact's per-slice
JSON files (verified against the manifest's SHA-256 map) and the manifest itself. If this module
imported the runtime, a bug there would pass its own check.

The model (ADR-069, ADR-070): OLS on the log weekly count with an intercept, a linear trend, a
year-end indicator and `k` sine/cosine pairs, robust refit. The point forecast is the median,
`exp(x·β)`; an interval at level L is `exp(x·β ± z_L · s · sqrt(1 + xᵀAx))`.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

HORIZON_CAP = 26
LEVELS = ("80", "95")
#: Relative distance from a rounding boundary inside which either adjacent whole number passes
#: (data dictionary §6, "Forecast recompute (QA)", rule 5). The only tolerance there is.
BOUNDARY_REL_TOL = 1e-9


def is_year_end(monday: dt.date) -> bool:
    """An ISO week (Monday start) containing December 25 or January 1 (ADR-070)."""
    days = [monday + dt.timedelta(days=i) for i in range(7)]
    return any((d.month, d.day) in ((12, 25), (1, 1)) for d in days)


class ModelUnavailable(RuntimeError):
    """A listed parameter file is missing, altered, or lacks a value the recompute needs."""


@dataclass(frozen=True)
class SliceParams:
    k: int
    year_end: bool
    params: tuple[float, ...]
    scale: float
    xtwx_inv: tuple[tuple[float, ...], ...]
    last_t: int
    period: float


@dataclass
class ForecastModel:
    start: dt.date  # Monday of week 0 (`trained_on[0]`)
    z: dict[str, float]
    slices: dict[str, SliceParams]
    #: How many comparisons landed within the boundary tolerance (reported with the run).
    boundary_fired: int = field(default=0, compare=False)

    # ------------------------------------------------------------------ loading

    @classmethod
    def load(cls, directory: Path, manifest: dict) -> ForecastModel:
        model_doc = manifest.get("model", {})
        z = {level: float(model_doc["interval_z"][level]) for level in LEVELS}
        out: dict[str, SliceParams] = {}
        for name, expected in manifest["files"].items():
            path = Path(directory) / name
            try:
                raw = path.read_bytes()
            except OSError as exc:
                raise ModelUnavailable(f"{name} is not readable: {type(exc).__name__}") from None
            if hashlib.sha256(raw).hexdigest() != expected:
                raise ModelUnavailable(f"{name} does not match the manifest's SHA-256")
            rec = json.loads(raw)
            try:
                out[rec["slice"]] = SliceParams(
                    k=int(rec["k"]),
                    year_end=bool(rec["year_end"]),
                    params=tuple(float(v) for v in rec["params"]),
                    scale=float(rec["scale"]),
                    xtwx_inv=tuple(tuple(float(v) for v in row) for row in rec["xtwx_inv"]),
                    last_t=int(rec["last_t"]),
                    period=float(rec["period"]),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ModelUnavailable(f"{name} lacks a parameter: {exc!r}") from None
            width = 2 + int(out[rec["slice"]].year_end) + 2 * out[rec["slice"]].k
            if len(out[rec["slice"]].params) != width or len(out[rec["slice"]].xtwx_inv) != width:
                raise ModelUnavailable(f"{name} has the wrong number of coefficients")
        return cls(start=dt.date.fromisoformat(manifest["trained_on"][0]), z=z, slices=out)

    # ------------------------------------------------------------------ prediction

    def predict(self, slice_: str, horizon: int) -> dict[str, float]:
        """Unrounded point and interval ends for one week, `horizon` weeks after the last
        training week (1 to 26)."""
        if not 1 <= horizon <= HORIZON_CAP:
            raise ValueError("horizon outside 1 to 26")
        m = self.slices[slice_]
        t = m.last_t + horizon
        monday = self.start + dt.timedelta(weeks=t)
        x = [1.0, float(t)]
        if m.year_end:
            x.append(1.0 if is_year_end(monday) else 0.0)
        for j in range(1, m.k + 1):
            angle = 2 * math.pi * j * t / m.period
            x += [math.sin(angle), math.cos(angle)]
        mu = sum(c * b for c, b in zip(x, m.params, strict=True))
        leverage = sum(
            x[i] * sum(m.xtwx_inv[i][j] * x[j] for j in range(len(x))) for i in range(len(x))
        )
        se = m.scale * math.sqrt(1.0 + leverage)
        out = {"point": math.exp(mu)}
        for level, z in self.z.items():
            out[f"lo{level}"] = math.exp(mu - z * se)
            out[f"hi{level}"] = math.exp(mu + z * se)
        return out

    # ------------------------------------------------------------------ comparison

    def same_when_displayed(self, claimed: float, recomputed: float) -> bool:
        """Equal after the display rule (nearest whole, a tie to the even number), with the one
        narrow boundary rule: within 1e-9 relative of a half, either neighbour passes."""
        floor = math.floor(recomputed)
        near_boundary = abs(recomputed - (floor + 0.5)) <= BOUNDARY_REL_TOL * abs(recomputed)
        if near_boundary:
            self.boundary_fired += 1
            return round(claimed) in (floor, floor + 1)
        return round(claimed) == round(recomputed)
