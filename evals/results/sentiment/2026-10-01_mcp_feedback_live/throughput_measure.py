"""Real-container throughput for ADR-067's cap (observed). Run inside the mcp_feedback image:

    docker compose run --rm --no-deps -v <this folder>:/bench:ro mcp_feedback \
        python /bench/throughput_measure.py

Pure inference through the service's own `BertClassifier` (tokenise, forward pass,
calibrated softmax); no database writes. Texts: the 300 oldest comments of 2025 Q4, the set
the step-3 on-demand call scored, read as app_sentiment. One untimed warm-up pass, then
batch 8 and batch 16 interleaved, 3 repeats each.
"""

import datetime as dt
import json
import statistics
import time
from pathlib import Path

import torch
from mcp_feedback.artifact import load_verified
from mcp_feedback.classifier import BertClassifier, container_cpus
from mcp_feedback.config import Settings
from mcp_feedback.store import _f, make_engine
from sqlalchemy import select

s = Settings.from_env()
art = load_verified(s.models_dir, s.manifest_path)
lo = dt.datetime(2025, 10, 1, tzinfo=dt.UTC)
hi = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
q = (
    select(_f.c.feedback_text)
    .where(_f.c.submitted_at >= lo, _f.c.submitted_at < hi, _f.c.feedback_text.is_not(None))
    .order_by(_f.c.submitted_at, _f.c.feedback_id)
    .limit(300)
)
with make_engine(s).connect() as conn:
    texts = [r[0] for r in conn.execute(q)]

clf = BertClassifier(art, 16)
t = time.perf_counter()
clf.predict(texts)  # loads the model and warms up; not counted
warmup_s = time.perf_counter() - t

runs: dict[int, list[float]] = {8: [], 16: []}
for _ in range(3):
    for bs in (8, 16):
        clf.batch_size = bs
        t = time.perf_counter()
        clf.predict(texts)
        runs[bs].append(time.perf_counter() - t)

result = {
    "evidence": "observed",
    "image": "agentic-service-ops-mcp_feedback (commit 338e9b8 code)",
    "cgroup_cpu_max": Path("/sys/fs/cgroup/cpu.max").read_text().strip(),
    "cgroup_memory_max": Path("/sys/fs/cgroup/memory.max").read_text().strip(),
    "container_cpus": container_cpus(),
    "torch": torch.__version__,
    "torch_threads": torch.get_num_threads(),
    "n_texts": len(texts),
    "texts": "300 oldest comments submitted in 2025 Q4 (UTC)",
    "warmup_incl_model_load_s": round(warmup_s, 2),
    "load_seconds": clf.load_seconds,
    "batches": {
        str(bs): {
            "seconds": [round(x, 2) for x in xs],
            "median_s": round(statistics.median(xs), 2),
            "max_s": round(max(xs), 2),
            "median_per_s": round(len(texts) / statistics.median(xs), 2),
            "slowest_per_s": round(len(texts) / max(xs), 2),
        }
        for bs, xs in runs.items()
    },
}
print(json.dumps(result, indent=1), flush=True)
