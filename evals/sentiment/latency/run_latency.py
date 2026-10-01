"""Host side of the BERT latency proxy (ADR-065). Results are labelled PROXY throughout.

    python -m evals.sentiment.latency.run_latency [--out-date YYYY-MM-DD] [--skip-build]
        [--large-repeats N]

`--skip-build` reuses the built image; `bench.py` is bind-mounted from the repo either
way. `--large-repeats N` sets the repeats for the full-window and last-12-months slices
only (default 3; neither is a gate slice); every other slice keeps 3. Each slice's repeat
count is recorded in the results.

1. Slice sizes, read as `app_eval`: how many comments each realistic question covers.
2. Train-split texts, read as `app_train` (test is never fetched), exported to a temp
   folder that is mounted read-only into the container.
3. Builds the throwaway image: exactly the uv.lock versions of the `bert` extra
   (`requirements.txt`, exported from the lock with hashes and committed beside this file)
   and the pinned model files from the local Hugging Face cache. Never pushed.
4. For each configuration (1 CPU / 2 GiB, 2 CPUs / 4 GiB), with `--network none`:
   cold start three times (host clock, `docker run` to the first prediction), then one
   warm run that measures throughput at batch sizes 16/32/64 and each slice three times
   at the best batch size, while `docker stats` is polled for peak memory.
5. Writes `evals/results/sentiment/<date>_latency_proxy/`, marking each slice against
   ADR-065's budget: warm at most 30 s on the gate slices, cold start at most 20 s.

Real model compute in a CPU-limited local container, not Cloud Run (L-28): proxy, not
observed. Stops with an error on an out-of-memory kill at 4 GiB (the one stop rule).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from datetime import date
from pathlib import Path

from ml.sentiment import config, data

HERE = Path(__file__).resolve().parent
IMAGE = "service-ops-latency-proxy:local"
CONFIGS = ({"cpus": 1, "memory": "2g"}, {"cpus": 2, "memory": "4g"})
COLD_REPEATS = 3
SLICE_REPEATS = 3
#: The two slices too large to repeat cheaply at 1 CPU; --large-repeats applies to these
#: only (default 3). Neither is a gate slice. Every result records its repeat count.
LARGE_SLICES = ("full_window", "last_12_months")
WARM_BUDGET_S = 30.0
COLD_BUDGET_S = 20.0
GATE_SLICES = ("largest_account_quarter", "largest_region_quarter")

_SLICE_SQL = """
WITH f AS (
    SELECT (f.submitted_at AT TIME ZONE 'UTC') AS ts, r.account_id, l.region
    FROM service_feedback f
    JOIN service_requests r USING (request_id)
    JOIN locations l ON l.location_id = r.location_id
),
aq AS (SELECT count(*) AS n FROM f GROUP BY account_id, date_trunc('quarter', ts)),
rq AS (SELECT count(*) AS n FROM f GROUP BY region, date_trunc('quarter', ts))
SELECT
    (SELECT count(*) FROM f),
    (SELECT count(*) FROM f WHERE ts >= '2025-08-31' AND ts < '2026-08-31'),
    (SELECT max(n) FROM (SELECT count(*) AS n FROM f GROUP BY date_trunc('quarter', ts)) q),
    (SELECT max(n) FROM (SELECT count(*) AS n FROM f GROUP BY date_trunc('month', ts)) m),
    (SELECT max(n) FROM aq),
    (SELECT percentile_disc(0.5) WITHIN GROUP (ORDER BY n) FROM aq),
    (SELECT max(n) FROM rq)
"""
SLICE_NAMES = (
    "full_window",
    "last_12_months",
    "largest_quarter",
    "largest_month",
    "largest_account_quarter",
    "median_account_quarter",
    "largest_region_quarter",
)


def slice_sizes() -> dict[str, int]:
    """Comment counts per slice, as `app_eval`. Calendar periods in UTC; the 12 months are
    2025-08-31 to 2026-08-30 inclusive; the median is over non-empty account-quarters."""
    with data.connect("app_eval") as conn:
        row = conn.execute(_SLICE_SQL).fetchone()
    return dict(zip(SLICE_NAMES, (int(x) for x in row), strict=True))


def export_requirements() -> Path:
    req = subprocess.run(
        [
            "uv", "export", "--frozen", "--no-emit-project", "--no-emit-workspace",
            "--extra", "bert", "--no-dev", "--format", "requirements-txt",
        ],
        cwd=data.ROOT, capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    path = HERE / "requirements.txt"
    path.write_text(req, encoding="utf-8", newline="\n")
    return path


def build(work: Path) -> None:
    from huggingface_hub import snapshot_download

    ctx = work / "context"
    (ctx / "model").mkdir(parents=True)
    src = Path(
        snapshot_download(
            config.MODEL_ID,
            revision=config.REVISION,
            allow_patterns=list(config.MODEL_FILES),
            local_files_only=True,
        )
    )
    for name in config.MODEL_FILES:
        shutil.copyfile(src / name, ctx / "model" / name)
    for name in ("Dockerfile", "bench.py"):
        shutil.copyfile(HERE / name, ctx / name)
    shutil.copyfile(export_requirements(), ctx / "requirements.txt")
    subprocess.run(["docker", "build", "-t", IMAGE, str(ctx)], check=True)


def _run_args(cfg: dict, work: Path, name: str) -> list[str]:
    return [
        "docker", "run", "--name", name, "--network", "none",
        f"--cpus={cfg['cpus']}", f"--memory={cfg['memory']}",
        f"--memory-swap={cfg['memory']}",  # no swap: an overrun is an OOM kill, not a slowdown
        "--mount", f"type=bind,source={work / 'data'},target=/data,readonly",
        # The repo's bench.py, not the copy baked into the image, so --skip-build always
        # runs the committed script.
        "--mount", f"type=bind,source={HERE / 'bench.py'},target=/app/bench.py,readonly",
        IMAGE, "python", "bench.py",
    ]  # fmt: skip


def _oom(name: str) -> bool:
    out = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.OOMKilled}} {{.State.ExitCode}}", name],
        capture_output=True, text=True,
    ).stdout.split()  # fmt: skip
    return bool(out) and (out[0] == "true" or out[1] == "137")


def _rm(name: str) -> None:
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def cold_start(cfg: dict, work: Path, k: int) -> dict:
    name = f"latency-cold-{cfg['cpus']}-{k}"
    _rm(name)
    t0 = time.perf_counter()
    proc = subprocess.Popen(
        [*_run_args(cfg, work, name), "cold", "--threads", str(cfg["cpus"])],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )  # fmt: skip
    first = None
    lines = []
    for line in proc.stdout:
        if line.startswith("FIRST_PREDICTION") and first is None:
            first = time.perf_counter() - t0
        lines.append(line)
    proc.wait()
    oom = _oom(name)
    _rm(name)
    if first is None:
        raise SystemExit(f"cold start produced no prediction (OOM: {oom}): {''.join(lines)}")
    return {"host_s": round(first, 3), **json.loads(lines[-1])}


def _parse_mem(text: str) -> float:
    m = re.match(r"([\d.]+)\s*([KMG]i?B)", text)
    if not m:
        return 0.0
    scale = {"KiB": 1 / 1024, "MiB": 1, "GiB": 1024, "KB": 1 / 1000, "MB": 1, "GB": 1000}
    return float(m.group(1)) * scale[m.group(2)]


def warm(cfg: dict, work: Path, slice_plan: dict[str, list[int]]) -> dict:
    name = f"latency-warm-{cfg['cpus']}"
    _rm(name)
    peak = {"mib": 0.0}
    done = threading.Event()

    def poll() -> None:
        while not done.is_set():
            out = subprocess.run(
                ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", name],
                capture_output=True, text=True,
            ).stdout  # fmt: skip
            peak["mib"] = max(peak["mib"], _parse_mem(out.strip()))

    proc = subprocess.Popen(
        [*_run_args(cfg, work, name), "warm", "--threads", str(cfg["cpus"]),
         "--slices", json.dumps(slice_plan)],
        stdout=subprocess.PIPE, text=True,
    )  # fmt: skip
    poller = threading.Thread(target=poll, daemon=True)
    poller.start()
    out, _ = proc.communicate()
    done.set()
    poller.join(timeout=10)
    oom = _oom(name)
    _rm(name)
    if oom or proc.returncode != 0:
        raise SystemExit(
            f"warm run failed at {cfg} (OOM: {oom}, exit {proc.returncode}). "
            "An OOM at 4 GiB is the stop rule (ADR-065 latency proxy)."
        )
    result = json.loads(out.strip().splitlines()[-1])
    result["docker_stats_peak_mib"] = round(peak["mib"], 1)
    return result


def verdicts(cold: list[dict], warm_result: dict) -> dict:
    cold_median = statistics.median(c["host_s"] for c in cold)
    out = {
        "cold_start": {
            "median_s": round(cold_median, 3),
            "max_s": max(c["host_s"] for c in cold),
            "budget_s": COLD_BUDGET_S,
            "pass": cold_median <= COLD_BUDGET_S
            and max(c["host_s"] for c in cold) <= COLD_BUDGET_S,
        },
        "slices": {},
    }
    for slice_name, s in warm_result["slices"].items():
        gate = slice_name in GATE_SLICES
        out["slices"][slice_name] = {
            "size": s["size"],
            "repeats": s["repeats"],
            "median_s": s["median_s"],
            "max_s": s["max_s"],
            "gate": gate,
            "within_30s": s["max_s"] <= WARM_BUDGET_S,
            "verdict": ("PASS" if s["max_s"] <= WARM_BUDGET_S else "FAIL")
            if gate
            else "reported (not the gate)",
        }
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out-date", default=date.today().isoformat())
    ap.add_argument("--skip-build", action="store_true")
    ap.add_argument(
        "--large-repeats",
        type=int,
        default=SLICE_REPEATS,
        help=f"repeats for {', '.join(LARGE_SLICES)} only (default {SLICE_REPEATS}); "
        f"every other slice keeps {SLICE_REPEATS}",
    )
    args = ap.parse_args(argv)
    out_dir = data.ROOT / "evals" / "results" / "sentiment" / f"{args.out_date}_latency_proxy"

    if args.large_repeats < 1:
        raise SystemExit("--large-repeats must be at least 1")
    slices = slice_sizes()
    slice_plan = {
        name: [size, args.large_repeats if name in LARGE_SLICES else SLICE_REPEATS]
        for name, size in slices.items()
    }
    print("slice sizes (app_eval):", slices, flush=True)
    print("repeats per slice:", {k: v[1] for k, v in slice_plan.items()}, flush=True)
    with tempfile.TemporaryDirectory(prefix="latency_proxy_") as tmp:
        work = Path(tmp)
        (work / "data").mkdir()
        texts = [r.feedback_text for r in data.load_training_rows(("train",))]
        (work / "data" / "texts.json").write_text(json.dumps(texts), encoding="utf-8")
        print(f"{len(texts)} train texts exported (app_train)", flush=True)
        if not args.skip_build:
            build(work)

        results = []
        for cfg in CONFIGS:
            cold = [cold_start(cfg, work, k) for k in range(COLD_REPEATS)]
            print(f"{cfg} cold: {[c['host_s'] for c in cold]}", flush=True)
            w = warm(cfg, work, slice_plan)
            print(f"{cfg} warm done; peak {w['docker_stats_peak_mib']} MiB", flush=True)
            results.append(
                {"config": cfg, "cold_runs": cold, "warm": w, "budget": verdicts(cold, w)}
            )

    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "label": "PROXY: real model compute in a CPU-limited local container, not Cloud Run",
        "adr": "ADR-065",
        "model": {"id": config.MODEL_ID, "revision": config.REVISION, "head": "random 4-class"},
        "max_length": config.MAX_LENGTH,
        "padding": "longest in batch",
        "image": IMAGE,
        "network": "none",
        "slice_sizes": slices,
        "slice_repeats": {k: v[1] for k, v in slice_plan.items()},
        "cold_start_repeats": COLD_REPEATS,
        "gate_slices": list(GATE_SLICES),
        "budget": {"warm_gate_max_s": WARM_BUDGET_S, "cold_start_max_s": COLD_BUDGET_S},
        "results": results,
    }
    (out_dir / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_dir / 'results.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
