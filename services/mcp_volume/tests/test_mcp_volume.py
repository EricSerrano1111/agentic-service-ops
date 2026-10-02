"""Offline tests for the volume MCP server (ADR-072). Assembled, not observed.

A hand-built artifact (six slices, a hand-written serving table) stands in for `volume_v2`,
so this runs in CI where `models/` is absent; the history query is faked. Two checks also
run against the real artifact when it is present locally.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from forecast_runtime import N_WEEKS, forecast_record
from mcp import Client
from mcp_volume.artifact import ArtifactIntegrityError, load_verified
from mcp_volume.config import Settings
from mcp_volume.server import FORECAST, HISTORY, Backend, create_app, create_server
from schemas import FORECAST_SLICES, HORIZON_BANDS, HistoryWeek, VolumeHistory
from starlette.testclient import TestClient

pytestmark = pytest.mark.anyio
SETTINGS = Settings(db_host="unused", db_port=5432, db_name="unused", db_user="unused")
REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_DIR = REPO_ROOT / "models" / "forecast" / "volume_v2"
REAL_MANIFEST = REPO_ROOT / "ml" / "forecast" / "artifacts" / "volume_v2.manifest.json"

#: The hand-written serving table: total everywhere, install 5-13 only, nothing else.
SERVED = {("total", b) for b in HORIZON_BANDS} | {("install", "5-13")}


@pytest.fixture
def anyio_backend():
    return "asyncio"


def build_artifact(tmp_path: Path) -> Path:
    files = {}
    for i, name in enumerate(FORECAST_SLICES):
        rec = {
            "slice": name,
            "k": 1,
            "year_end": True,
            "params": [4.0 + 0.1 * i, 0.001, -0.15, 0.2, 0.1],
            "scale": 0.1,
            "xtwx_inv": (np.eye(5) * 1e-3).tolist(),
            "last_t": N_WEEKS - 1,
            "horizon_cap": 26,
        }
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(rec), encoding="utf-8")
        files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {
        "trained_on": ["2023-09-04", "2026-08-24"],
        "files": files,
        "serving_rule": "ADR-071",
        "serving": {
            "slices": {
                s: {
                    b: {"served": (s, b) in SERVED, "shown_error": 10.0 + j}
                    for j, b in enumerate(HORIZON_BANDS)
                }
                for s in FORECAST_SLICES
            }
        },
    }
    path = tmp_path / "volume_test.manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


@pytest.fixture
def artifact(tmp_path):
    return load_verified(tmp_path, build_artifact(tmp_path))


def fake_history(slice_: str, weeks: int) -> VolumeHistory:
    return VolumeHistory(
        slice=slice_,
        weeks=[
            HistoryWeek(
                week_start=dt.date(2026, 8, 24) - dt.timedelta(weeks=weeks - 1 - i), count=i
            )
            for i in range(weeks)
        ],
    )


def backend(artifact) -> Backend:
    return Backend(artifact=artifact, history=fake_history, ready=lambda: None)


# --------------------------------------------------------------------------- served-only numbers


async def test_no_numbers_ever_for_an_unserved_slice_band(artifact):
    async with Client(create_server(SETTINGS, backend(artifact))) as client:
        for s in FORECAST_SLICES:
            r = (
                await client.call_tool(FORECAST, {"slice": s, "horizon_weeks": 26})
            ).structured_content
            for w in r["weeks"]:
                numbers = [w.get(k) for k in ("point", "lo80", "hi80", "lo95", "hi95")]
                if (s, w["band"]) in SERVED:
                    assert w["served"] and all(n is not None for n in numbers)
                else:
                    assert not w["served"] and all(n is None for n in numbers), (s, w)
            assert {b: v["served"] for b, v in r["bands"].items()} == {
                b: (s, b) in SERVED for b in HORIZON_BANDS
            }


async def test_forecast_numbers_equal_the_runtime_path_exactly(artifact):
    async with Client(create_server(SETTINGS, backend(artifact))) as client:
        r = (
            await client.call_tool(FORECAST, {"slice": "total", "horizon_weeks": 26})
        ).structured_content
    expected = forecast_record(artifact.records["total"], np.arange(N_WEEKS, N_WEEKS + 26))
    for i, w in enumerate(r["weeks"]):
        assert w["point"] == float(expected["median"][i])
        assert (w["lo80"], w["hi80"]) == (float(expected["lo80"][i]), float(expected["hi80"][i]))
        assert (w["lo95"], w["hi95"]) == (float(expected["lo95"][i]), float(expected["hi95"][i]))
    assert r["weeks"][0]["week_start"] == "2026-08-31" and r["trained_through"] == "2026-08-30"
    assert r["year_end_weeks"] == ["2026-12-21", "2026-12-28"]


async def test_bands_listed_are_those_within_the_horizon(artifact):
    async with Client(create_server(SETTINGS, backend(artifact))) as client:
        r = (
            await client.call_tool(FORECAST, {"slice": "install", "horizon_weeks": 10})
        ).structured_content
    assert list(r["bands"]) == ["1-4", "5-13"]
    assert [w["served"] for w in r["weeks"]] == [False] * 4 + [True] * 6
    assert r["bands"]["1-4"]["shown_error"] == 10.0 and r["year_end_weeks"] == []


# --------------------------------------------------------------------------- validation


@pytest.mark.parametrize("bad", [0, 27, -1, True, 2.5, "5"])
async def test_horizon_outside_1_to_26_is_rejected(artifact, bad):
    async with Client(create_server(SETTINGS, backend(artifact))) as client:
        r = await client.call_tool(FORECAST, {"slice": "total", "horizon_weeks": bad})
    assert r.is_error


@pytest.mark.parametrize("bad", [0, 53])
async def test_history_weeks_outside_1_to_52_is_rejected(artifact, bad):
    async with Client(create_server(SETTINGS, backend(artifact))) as client:
        r = await client.call_tool(HISTORY, {"slice": "total", "weeks": bad})
    assert r.is_error and "weeks must be an integer from 1 to 52" in r.content[0].text


async def test_unknown_slice_is_rejected(artifact):
    async with Client(create_server(SETTINGS, backend(artifact))) as client:
        r = await client.call_tool(FORECAST, {"slice": "region", "horizon_weeks": 4})
    assert r.is_error


async def test_only_the_two_read_tools_are_exposed(artifact):
    async with Client(create_server(SETTINGS, backend(artifact))) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == {FORECAST, HISTORY}
    assert set(tools[FORECAST].input_schema["properties"]) == {"slice", "horizon_weeks"}
    assert set(tools[HISTORY].input_schema["properties"]) == {"slice", "weeks"}


async def test_history_passes_through(artifact):
    async with Client(create_server(SETTINGS, backend(artifact))) as client:
        r = (await client.call_tool(HISTORY, {"slice": "repair", "weeks": 3})).structured_content
    assert [w["week_start"] for w in r["weeks"]] == ["2026-08-10", "2026-08-17", "2026-08-24"]


def test_healthz(artifact):
    with TestClient(create_app(SETTINGS, backend(artifact))) as client:
        r = client.get("/healthz", headers={"host": "localhost:8103"})
    assert r.status_code == 200 and r.json()["model_version"] == artifact.model_version


# --------------------------------------------------------------------------- start-up


def test_refuses_to_start_on_an_altered_file(tmp_path):
    manifest = build_artifact(tmp_path)
    (tmp_path / "total.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ArtifactIntegrityError, match="does not match"):
        load_verified(tmp_path, manifest)


def test_refuses_to_start_on_a_missing_file_or_no_serving_table(tmp_path):
    manifest = build_artifact(tmp_path)
    (tmp_path / "repair.json").unlink()
    with pytest.raises(ArtifactIntegrityError, match="repair.json is missing"):
        load_verified(tmp_path, manifest)
    other = tmp_path / "other"
    other.mkdir()
    m2 = build_artifact(other)
    data = json.loads(m2.read_text())
    data.pop("serving_rule")
    m2.write_text(json.dumps(data))
    with pytest.raises(ArtifactIntegrityError, match="serving table"):
        load_verified(other, m2)


# --------------------------------------------------------------------------- the real artifact


@pytest.mark.skipif(not REAL_DIR.exists(), reason="volume_v2 artifact not present (gitignored)")
async def test_real_artifact_serves_numbers_only_where_the_manifest_says():
    real = load_verified(REAL_DIR, REAL_MANIFEST)
    manifest = json.loads(REAL_MANIFEST.read_text(encoding="utf-8"))
    async with Client(create_server(SETTINGS, backend(real))) as client:
        for s in FORECAST_SLICES:
            r = (
                await client.call_tool(FORECAST, {"slice": s, "horizon_weeks": 26})
            ).structured_content
            expected = forecast_record(real.records[s], np.arange(N_WEEKS, N_WEEKS + 26))
            for i, w in enumerate(r["weeks"]):
                if manifest["serving"]["slices"][s][w["band"]]["served"]:
                    assert w["point"] == float(expected["median"][i])
                else:
                    assert w["point"] is None and w["lo95"] is None
    assert real.model_version == hashlib.sha256(REAL_MANIFEST.read_bytes()).hexdigest()


@pytest.mark.skipif(not REAL_DIR.exists(), reason="volume_v2 artifact not present (gitignored)")
def test_real_artifact_matches_the_committed_production_forecast():
    """The ml/forecast export wrote production_forecast.json from the same records."""
    real = load_verified(REAL_DIR, REAL_MANIFEST)
    prod = json.loads(
        (
            REPO_ROOT / "evals/results/forecast/2026-10-02_volume_v2/production_forecast.json"
        ).read_text(encoding="utf-8")
    )
    for s in FORECAST_SLICES:
        f = real.forecast(s, 26)
        rows = prod["forecast"][s]
        for w, row in zip(f.weeks, rows, strict=True):
            if w.served:
                assert round(w.point, 4) == row["median"] and round(w.hi80, 4) == row["hi80"]
