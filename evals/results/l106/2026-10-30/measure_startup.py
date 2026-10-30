"""L-106 offline startup measurement: time from `docker run -d` returning to first log line
(T_log) and to the startup-probe path answering (T_listen), for the nine l106/<name>:local images.

Usage (repo root, Docker running, `docker compose up -d postgres` healthy):
    python measure_startup.py --label warm --runs 3 --out startup.csv
    python measure_startup.py --label cold_cache --runs 1 --out startup_cold.csv

Env comes from `docker compose config` (resolved from .env; secrets are written only to an
ignored scratch dir, never printed). Each run is a fresh container, --cpus 1 --memory 512m.
Dependencies an agent needs (MCP servers) are started once, before the agents, on the compose
network under their compose hostnames, so an agent's /readyz can return 200. Polling: one
loop every 0.25 s target (docker logs, then the HTTP probe with a 1 s timeout), to 120 s.
Deviations from compose are listed in README.md.
"""

import argparse
import csv
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

CPU, MEM, TIMEOUT_S, TICK = "1", "512m", 120.0, 0.25
SCRATCH = Path(".local/l106/env")
# (image, compose service, container port, probe path, host port)
SERVICES = [
    ("mcp-incidents", "mcp_incidents", 8101, "/readyz", 18101),
    ("mcp-feedback", "mcp_feedback", 8102, "/readyz", 18102),
    ("mcp-volume", "mcp_volume", 8103, "/readyz", 18103),
    ("agent-reporting", "agent_reporting", 8001, "/readyz", 18001),
    ("agent-sentiment", "agent_sentiment", 8002, "/readyz", 18002),
    ("agent-forecast", "agent_forecast", 8003, "/readyz", 18003),
    ("agent-qa", "agent_qa", 8004, "/readyz", 18004),
    ("orchestrator", "orchestrator", 8000, "/healthz", 18000),
    ("gateway", "gateway", 8080, "/healthz", 18080),
]
MCP_FOR_AGENT = {
    "agent-reporting": "mcp-incidents",
    "agent-sentiment": "mcp-feedback",
    "agent-forecast": "mcp-volume",
}
# Values compose does not give, or that differ because the image is the deploy one (see README).
OVERRIDES = {
    "gateway": {"GATEWAY_SESSION_KEY": "l106-dummy-session-key-" + "0" * 40},
    "mcp-feedback": {"MCP_FEEDBACK_SCORING": "stored_only"},
}
DROP = {"mcp-feedback": {"MODELS_DIR"}}


def sh(*args, check=True):
    return subprocess.run(args, capture_output=True, text=True, check=check).stdout


def compose_env():
    cfg = json.loads(sh("docker", "compose", "config", "--format", "json"))
    return cfg["services"], cfg.get("networks", {})


def network_name():
    names = [
        n
        for n in sh("docker", "network", "ls", "--format", "{{.Name}}").split()
        if n.endswith("_default")
    ]
    return next(n for n in names if "agentic" in n)


def env_file(image, svc, services):
    env = dict(services[svc].get("environment", {}))
    for k in DROP.get(image, ()):
        env.pop(k, None)
    env.update(OVERRIDES.get(image, {}))
    SCRATCH.mkdir(parents=True, exist_ok=True)
    path = SCRATCH / f"{image}.env"
    path.write_text("".join(f"{k}={v}\n" for k, v in env.items() if v is not None))
    return path


def run_args(image, svc, port, host_port, net, services, name, alias=None):
    a = [
        "docker",
        "run",
        "-d",
        "--name",
        name,
        "--cpus",
        CPU,
        "--memory",
        MEM,
        "--network",
        net,
        "--env-file",
        str(env_file(image, svc, services)),
        "-p",
        f"127.0.0.1:{host_port}:{port}",
    ]
    if alias:
        a += ["--network-alias", alias]
    if image == "gateway":
        a += ["-v", f"{Path('.local/gateway').resolve()}:/run/gateway:ro"]
    return a + [f"l106/{image}:local"]


def fmt(v):
    return "" if v is None else f"{v:.2f}"


def probe(host_port, path):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{host_port}{path}", timeout=1) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return None


def measure(image, svc, port, path, host_port, net, services, label, n, logdir):
    name = f"l106-{image}-{n}"
    sh("docker", "rm", "-f", name, check=False)
    cid = sh(*run_args(image, svc, port, host_port, net, services, name)).strip()
    t0 = time.perf_counter()
    t_log = t_listen = t_200 = first = outcome = None
    while True:
        tick = time.perf_counter()
        el = tick - t0
        if el > TIMEOUT_S:
            outcome = "timeout_120s"
            break
        if t_log is None and sh("docker", "logs", cid, check=False).strip():
            t_log = time.perf_counter() - t0
        st = probe(host_port, path)
        if st is not None and t_listen is None:
            t_listen, first = time.perf_counter() - t0, st
        if st == 200:
            t_200, outcome = time.perf_counter() - t0, "ok"
            break
        if t_listen is not None and t_listen and time.perf_counter() - t0 > t_listen + 10:
            outcome = f"stayed_{st}"
            break
        if (
            int(el * 4) % 8 == 0
            and sh("docker", "inspect", "-f", "{{.State.Running}}", cid, check=False).strip()
            != "true"
        ):
            outcome = "exited"
            break
        time.sleep(max(0.0, TICK - (time.perf_counter() - tick)))
    logs = subprocess.run(["docker", "logs", cid], capture_output=True, text=True).stdout
    (logdir / f"{image}-{label}-{n}.log").write_text(logs[-4000:])
    mem = sh("docker", "inspect", "-f", "{{.State.OOMKilled}}", cid, check=False).strip()
    sh("docker", "rm", "-f", cid, check=False)
    return [image, label, n, fmt(t_log), fmt(t_listen), first or "", fmt(t_200), outcome, mem]


def start_dep(image, services, net):
    spec = next(s for s in SERVICES if s[0] == image)
    _, svc, port, path, host_port = spec
    name = f"l106-dep-{image}"
    sh("docker", "rm", "-f", name, check=False)
    sh(*run_args(image, svc, port, host_port + 1000, net, services, name, alias=svc))
    for _ in range(240):
        if probe(host_port + 1000, path) == 200:
            return name
        time.sleep(0.5)
    raise SystemExit(f"dependency {image} never ready")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="warm")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()
    out = Path(args.out)
    logdir = out.parent / "logs"
    logdir.mkdir(exist_ok=True)
    services, _ = compose_env()
    net = network_name()
    rows, deps = [], {}
    for image, svc, port, path, host_port in SERVICES:
        if args.only and image not in args.only:
            continue
        need = MCP_FOR_AGENT.get(image)
        if need and need not in deps:
            deps[need] = start_dep(need, services, net)
        for n in range(1, args.runs + 1):
            row = measure(image, svc, port, path, host_port, net, services, args.label, n, logdir)
            print(*row, flush=True)
            rows.append(row)
    for d in deps.values():
        sh("docker", "rm", "-f", d, check=False)
    new = not out.exists()
    with out.open("a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(
                [
                    "container",
                    "label",
                    "run",
                    "t_log_s",
                    "t_listen_s",
                    "first_status",
                    "t_200_s",
                    "outcome",
                    "oom_killed",
                ]
            )
        w.writerows(rows)


if __name__ == "__main__":
    main()
