"""The `volume_v2` artifact: hash-checked at start-up, served through `forecast_runtime`.

Every file the manifest lists must exist under `MODELS_DIR` with its recorded SHA-256, or
the server refuses to start (ADR-072). Forecasts come from `forecast_runtime.forecast_record`,
the same code path `ml/forecast` evaluated and exported with; nothing is reimplemented.

Served-only numbers: `forecast()` puts a week's point and ranges in the result only when
the manifest's serving table (ADR-071) marks that slice-band served.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from forecast_runtime import (
    HORIZON_CAP,
    N_WEEKS,
    forecast_record,
    load,
    week_start,
    year_end_indicator,
)
from schemas import (
    MAX_HORIZON_WEEKS,
    BandVerdict,
    ForecastWeek,
    VolumeForecast,
    band_of,
)


class ArtifactIntegrityError(RuntimeError):
    """A listed file is missing or doesn't match the manifest. The server won't start."""


@dataclass(frozen=True)
class Artifact:
    model_version: str
    trained_through: dt.date
    records: dict[str, dict]
    serving: dict[str, dict[str, dict]]

    @property
    def slices(self) -> tuple[str, ...]:
        return tuple(self.records)

    def forecast(self, slice_: str, horizon_weeks: int) -> VolumeForecast:
        if not 1 <= horizon_weeks <= MAX_HORIZON_WEEKS:
            raise ValueError(f"horizon_weeks must be 1 to {MAX_HORIZON_WEEKS}")
        t = np.arange(N_WEEKS, N_WEEKS + horizon_weeks)
        fc = forecast_record(self.records[slice_], t)
        verdicts = self.serving[slice_]
        weeks = []
        for i, w in enumerate(t):
            h = int(w - N_WEEKS + 1)
            band = band_of(h)
            served = bool(verdicts[band]["served"])
            numbers = {}
            if served:
                numbers = {
                    "point": float(fc["median"][i]),
                    "lo80": float(fc["lo80"][i]),
                    "hi80": float(fc["hi80"][i]),
                    "lo95": float(fc["lo95"][i]),
                    "hi95": float(fc["hi95"][i]),
                }
            weeks.append(
                ForecastWeek(
                    week_start=week_start(int(w)), horizon=h, band=band, served=served, **numbers
                )
            )
        bands = {w.band for w in weeks}
        return VolumeForecast(
            model_version=self.model_version,
            trained_through=self.trained_through,
            slice=slice_,
            horizon_weeks=horizon_weeks,
            weeks=weeks,
            bands={
                b: BandVerdict(
                    served=bool(verdicts[b]["served"]), shown_error=verdicts[b]["shown_error"]
                )
                for b in ("1-4", "5-13", "14-26")
                if b in bands
            },
            year_end_weeks=[week_start(int(w)) for w in t[year_end_indicator(t) == 1]],
        )


def load_verified(directory: Path, manifest_path: Path) -> Artifact:
    """Read the manifest, verify every listed file, and load the slice records."""
    if not manifest_path.is_file():
        raise ArtifactIntegrityError(f"manifest not found: {manifest_path}")
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    for name in manifest["files"]:
        if not (directory / name).is_file():
            raise ArtifactIntegrityError(f"{name} is missing from {directory}")
    try:
        records = load(directory, manifest)
    except RuntimeError as exc:  # forecast_runtime.load: a hash mismatch
        raise ArtifactIntegrityError(str(exc)) from None
    if manifest.get("serving_rule") != "ADR-071" or "serving" not in manifest:
        raise ArtifactIntegrityError("manifest has no ADR-071 serving table")
    if any(rec["horizon_cap"] != HORIZON_CAP for rec in records.values()):
        raise ArtifactIntegrityError("artifact horizon cap differs from the runtime's")
    last_week = dt.date.fromisoformat(manifest["trained_on"][1])
    return Artifact(
        model_version=hashlib.sha256(raw).hexdigest(),
        trained_through=last_week + dt.timedelta(days=6),
        records=records,
        serving=manifest["serving"]["slices"],
    )
