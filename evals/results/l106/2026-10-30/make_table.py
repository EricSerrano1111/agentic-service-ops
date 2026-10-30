"""Build summary.md from images.csv, importtime/, startup_warm.csv and startup_cold.csv."""

import csv
import re
import statistics as st
import sys
from pathlib import Path

d = Path(sys.argv[1])
pat = re.compile(r"import time:\s+(\d+) \|\s+(\d+) \| (\s*)(\S+)")
CONTAINERS = [
    "orchestrator",
    "agent-reporting",
    "mcp-incidents",
    "agent-qa",
    "agent-forecast",
    "mcp-volume",
    "gateway",
    "agent-sentiment",
    "mcp-feedback",
]
HEAD = (
    "| container | image MB | .venv files | import s (median of 3 / run 1) "
    "| T_log s (median / max) | T_listen s (median / max) | cold_cache T_listen s "
    "| heaviest direct import (ms, run 1) |"
)


def imports(c, n):
    rows = []
    with open(
        d / "importtime" / f"{c}-importtime-{n}.txt", encoding="utf8", errors="replace"
    ) as fh:
        for line in fh:
            m = pat.match(line)
            if m:
                rows.append((int(m[2]), len(m[3]) // 2, m[4]))
    return rows


def read_csv(name):
    with open(d / name, newline="") as fh:
        return list(csv.DictReader(fh))


imgs = {r["container"]: r for r in read_csv("images.csv")}
warm, cold = read_csv("startup_warm.csv"), read_csv("startup_cold.csv")
out = [HEAD, "|---|---|---|---|---|---|---|---|"]
for c in CONTAINERS:
    tot = [max(r[0] for r in imports(c, n)) / 1e6 for n in (1, 2, 3)]
    kid = max((r for r in imports(c, 1) if r[1] == 1), key=lambda r: r[0])
    w = [r for r in warm if r["container"] == c]
    tl = [float(r["t_log_s"]) for r in w]
    ts = [float(r["t_listen_s"]) for r in w]
    cc = next(r["t_listen_s"] for r in cold if r["container"] == c)
    size = int(imgs[c]["image_bytes"]) / 1e6
    out.append(
        f"| {c} | {size:.0f} | {imgs[c]['venv_files']} | {st.median(tot):.2f} / {tot[0]:.2f} "
        f"| {st.median(tl):.2f} / {max(tl):.2f} | {st.median(ts):.2f} / {max(ts):.2f} | {cc} "
        f"| {kid[2]} {kid[0] / 1000:.0f} |"
    )
(d / "summary.md").write_text("\n".join(out) + "\n")
print("\n".join(out))
