"""L-106 per-start extraction (Appendix A, 2d and 2e). Read-only over a saved C1 file.

    python -I .local/l106/extract_starts.py calib CALIB.json
    python -I .local/l106/extract_starts.py round LOGS.json ROUND STARTS.json [--t1 ISO]

`calib` prints the tally for 18:59:13 to 19:45 on 2026-10-30 and exits 1 if it is not
4 failed ops-reporting, 2 failed ops-qa, 5 passed others.
`round` merges the round's starts into STARTS.json (rows of that round are replaced).
Prints no log text beyond short fields; verbatim evidence goes into the JSON only.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime

SERVICES = {
    "ops-gateway": ["gateway"],
    "ops-orchestrator": ["orchestrator"],
    "ops-reporting": ["agent-reporting", "mcp-incidents"],
    "ops-sentiment": ["agent-sentiment", "mcp-feedback"],
    "ops-forecast": ["agent-forecast", "mcp-volume"],
    "ops-qa": ["agent-qa"],
}
START_RE = re.compile(r"^Starting new instance\. Reason: (\S+)")
OK_RE = re.compile(r'^STARTUP HTTP probe succeeded after (\d+) attempts? for container "([^"]+)"')
FAIL_RE = re.compile(
    r'^STARTUP HTTP probe failed (\d+) times consecutively for container "([^"]+)"'
)
STREAMS = {
    "run.googleapis.com%2Fvarlog%2Fsystem": "system",
    "run.googleapis.com%2Frequests": "requests",
    "run.googleapis.com%2Fstdout": "stdout",
    "run.googleapis.com%2Fstderr": "stderr",
}


def ts(s: str) -> datetime:
    s = s.replace("Z", "")
    if "." in s:
        head, frac = s.split(".")
        s = f"{head}.{frac[:6]}"
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def load(path: str) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        raw = json.load(f)
    out = []
    for e in raw:
        stream = STREAMS.get(e["logName"].rsplit("/", 1)[-1])
        if stream is None:
            continue  # audit entries are not one of the four streams
        e["_stream"] = stream
        e["_t"] = ts(e["timestamp"])
        out.append(e)
    out.sort(key=lambda e: e["_t"])
    return out


def text_of(e: dict) -> str:
    if "textPayload" in e:
        return e["textPayload"]
    jp = e.get("jsonPayload") or {}
    return str(jp.get("msg", json.dumps(jp)))


def kind_of(token: str) -> str:
    if token == "AUTOSCALING":
        return "autoscale"
    if re.search(r"ROLLOUT|DEPLOY|REVISION|TRAFFIC", token):
        return "rollout"
    return f"other:{token}"


def extract(entries: list[dict], rnd: str, window_end: datetime | None) -> list[dict]:
    rows = []
    by_inst: dict[tuple[str, str], list[dict]] = {}
    for e in entries:
        lab = e["resource"]["labels"]
        inst = e.get("labels", {}).get("instanceId")
        if inst:
            by_inst.setdefault((lab["service_name"], inst), []).append(e)
    for (svc, inst), es in by_inst.items():
        starts = [e for e in es if e["_stream"] == "system" and START_RE.match(text_of(e))]
        if not starts:
            continue  # an instance that started before the window: not a start of this round
        st = starts[0]
        t0 = st["_t"]
        token = START_RE.match(text_of(st)).group(1)
        containers: dict[str, dict] = {}
        for e in es:
            c = e.get("labels", {}).get("container_name")
            tx = text_of(e)
            if e["_stream"] in ("stdout", "stderr") and c:
                d = containers.setdefault(c, {})
                if "first_line" not in d:
                    d["first_line"] = {
                        "stream": e["_stream"],
                        "secs_after_start": round((e["_t"] - t0).total_seconds(), 3),
                        "text": tx[:160],
                    }
            if e["_stream"] == "system":
                for rx, res in ((OK_RE, "pass"), (FAIL_RE, "fail")):
                    m = rx.match(tx)
                    if m:
                        d = containers.setdefault(m.group(2), {})
                        d["probe"] = {
                            "result": res,
                            "attempts": int(m.group(1)),
                            "secs_after_start": round((e["_t"] - t0).total_seconds(), 3),
                            "text": tx,
                        }
        expected = SERVICES.get(svc, [])
        results = [containers.get(c, {}).get("probe", {}).get("result") for c in expected]
        if "fail" in [c.get("probe", {}).get("result") for c in containers.values()]:
            verdict = "fail"
        elif all(r == "pass" for r in results) and expected:
            verdict = "pass"
        else:
            verdict = "indeterminate"
        succ = [
            c["probe"] for c in containers.values() if c.get("probe", {}).get("result") == "pass"
        ]
        secs = (
            max((p["secs_after_start"] for p in succ), default=None) if verdict == "pass" else None
        )
        max_att = max((p["attempts"] for p in succ), default=None)
        over60 = bool(verdict == "pass" and ((secs or 0) > 60 or (max_att or 0) > 20))
        # the request that asked for the start: same service, within 1 s before the start line
        req = None
        for e in entries:
            if (
                e["_stream"] == "requests"
                and e["resource"]["labels"]["service_name"] == svc
                and 0.0 <= (t0 - e["_t"]).total_seconds() <= 1.0
                and e.get("labels", {}).get("instanceId") == inst
            ):
                h = e.get("httpRequest", {})
                req = {
                    "ts": e["timestamp"],
                    "status": h.get("status"),
                    "latency": h.get("latency"),
                    "message": e.get("textPayload"),
                    "trace": e.get("trace"),
                }
                break
        row = {
            "round": rnd,
            "service": svc,
            "revision": st["resource"]["labels"].get("revision_name"),
            "instanceId": inst,
            "reason": START_RE.match(text_of(st)).group(0),
            "kind": kind_of(token),
            "start_ts": st["timestamp"],
            "containers": containers,
            "secs_to_probe_success": secs,
            "max_attempts": max_att,
            "over_60s": over60,
            "request": req,
            "question": None,
            "trace": None,
            "verdict": verdict,
        }
        if verdict != "pass" or over60:
            lo, hi = t0.timestamp() - 10, t0.timestamp() + 130
            ev = [
                e
                for e in entries
                if e["resource"]["labels"]["service_name"] == svc
                and lo <= e["_t"].timestamp() <= hi
            ]
            counts = {
                s: sum(1 for e in ev if e["_stream"] == s)
                for s in ("system", "requests", "stdout", "stderr")
            }
            row["evidence"] = {
                "window": "start-10s .. start+130s, all entries of the service",
                "counts": counts,
                "entries": [{k: v for k, v in e.items() if not k.startswith("_")} for e in ev],
                "window_complete": window_end is None or (window_end.timestamp() >= hi),
            }
        rows.append(row)
    rows.sort(key=lambda r: r["start_ts"])
    return rows


def main(argv: list[str]) -> int:
    mode = argv[1]
    if mode == "calib":
        rows = extract(load(argv[2]), "calib", None)
        lo, hi = "2026-10-30T18:59:13", "2026-10-30T19:45:00"
        sel = [r for r in rows if lo <= r["start_ts"][:19] <= hi and r["kind"] == "autoscale"]
        tally = {"failed_reporting": 0, "failed_qa": 0, "passed_other": 0, "other": 0}
        for r in sel:
            if r["verdict"] == "fail" and r["service"] == "ops-reporting":
                tally["failed_reporting"] += 1
            elif r["verdict"] == "fail" and r["service"] == "ops-qa":
                tally["failed_qa"] += 1
            elif r["verdict"] == "pass" and r["service"] not in ("ops-reporting", "ops-qa"):
                tally["passed_other"] += 1
            else:
                tally["other"] += 1
        print("starts in window:", len(sel))
        for r in sel:
            p = [
                (c, v["probe"]["result"], v["probe"]["attempts"])
                for c, v in r["containers"].items()
                if "probe" in v
            ]
            print(
                r["start_ts"][11:23], r["service"], r["revision"][-9:], r["kind"], r["verdict"], p
            )
        print("tally:", tally)
        ok = tally == {"failed_reporting": 4, "failed_qa": 2, "passed_other": 5, "other": 0}
        print("REPRODUCES 10-30:", ok)
        return 0 if ok else 1
    if mode == "round":
        logs, rnd, out = argv[2], argv[3], argv[4]
        end = ts(argv[argv.index("--t1") + 1]) if "--t1" in argv else None
        rows = extract(load(logs), rnd, end)
        try:
            with open(out, encoding="utf-8") as f:
                allrows = json.load(f)
        except FileNotFoundError:
            allrows = []
        allrows = [r for r in allrows if r["round"] != rnd] + rows
        with open(out, "w", encoding="utf-8") as f:  # no byte-order mark
            json.dump(allrows, f, indent=1)
        for r in rows:
            print(
                r["start_ts"][11:23],
                r["service"],
                r["revision"][-9:],
                r["kind"],
                r["verdict"],
                r["secs_to_probe_success"],
                "over60" if r["over_60s"] else "",
            )
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
