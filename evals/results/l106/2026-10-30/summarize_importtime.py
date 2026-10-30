"""Summarise `python -X importtime` captures.

Usage: python summarize_importtime.py <importtime-dir>

Per container: the total cumulative time of the app/server module (the outermost import line)
for runs 1 to 3; the 10 heaviest direct imports of that module in run 1 ("top-level",
cumulative ms); and the 5 heaviest modules by self time at any depth.
`-X importtime` charges a shared module to whichever importer loads it first, so only the totals
are comparable across containers, not the per-module attribution.

Then: top-level package names (first dotted component, any depth) seen in run 1 of exactly the
two containers `agent-qa` and `mcp-incidents`, and in none of the other seven.
"""

import glob
import os
import re
import sys

PATTERN = re.compile(r"import time:\s+(\d+) \|\s+(\d+) \| (\s*)(\S+)")


def parse(path):
    rows = []
    with open(path, encoding="utf8", errors="replace") as fh:
        for line in fh:
            m = PATTERN.match(line)
            if m:
                rows.append((int(m[1]), int(m[2]), len(m[3]) // 2, m[4]))
    return rows


def main(d):
    names = sorted(
        {os.path.basename(f).rsplit("-importtime", 1)[0] for f in glob.glob(d + "/*.txt")}
    )
    packages, cost = {}, {}
    for c in names:
        totals, rows1, app_name = [], [], ""
        for n in (1, 2, 3):
            rows = parse(f"{d}/{c}-importtime-{n}.txt")
            app = max(rows, key=lambda r: r[1])
            totals.append(app[1] / 1e6)
            if n == 1:
                rows1, app_name = rows, app[3]
        kids = sorted((r for r in rows1 if r[2] == 1), key=lambda r: -r[1])[:10]
        selfs = sorted(rows1, key=lambda r: -r[0])[:5]
        packages[c] = {r[3].split(".")[0] for r in rows1}
        cost[c] = {}
        for _, cum_us, _, name in rows1:
            top = name.split(".")[0]
            cost[c][top] = max(cost[c].get(top, 0), cum_us)
        print(f"{c}: {app_name} total_s run1/2/3 = " + " / ".join(f"{t:.3f}" for t in totals))
        print(
            "  top-level (cumulative ms): " + ", ".join(f"{r[3]} {r[1] / 1000:.0f}" for r in kids)
        )
        print("  top self-time (ms): " + ", ".join(f"{r[3]} {r[0] / 1000:.0f}" for r in selfs))
    pair = {"agent-qa", "mcp-incidents"}
    others = [c for c in names if c not in pair]
    print()
    print("packages by cost (cumulative ms of the heaviest line in the package):")
    print("  in agent-qa and mcp-incidents (>= 50 ms each) but < 5 ms in each of the other seven:")
    hits = [
        k
        for k in cost["agent-qa"]
        if cost["agent-qa"][k] >= 50_000
        and cost["mcp-incidents"].get(k, 0) >= 50_000
        and all(cost[c].get(k, 0) < 5_000 for c in others)
    ]
    for k in sorted(hits):
        qa, inc = cost["agent-qa"][k] / 1000, cost["mcp-incidents"][k] / 1000
        rest_max = max(cost[c].get(k, 0) for c in others) / 1000
        print(f"    {k}: agent-qa {qa:.0f}, mcp-incidents {inc:.0f}, others max {rest_max:.2f}")
    if not hits:
        print("    (none)")
    for who in sorted(pair):
        rest = [c for c in names if c != who]
        only = [k for k in cost[who] if all(k not in packages[c] for c in rest)]
        print(f"  packages present in {who} only: " + (", ".join(sorted(only)) or "(none)"))


if __name__ == "__main__":
    main(sys.argv[1])
