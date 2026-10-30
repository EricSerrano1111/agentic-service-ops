# L-106 offline startup measurement, 2026-10-30

Local Docker only: no GCP calls, no model calls, `ops-db` stayed stopped. Measurement only; no source
file changed. Built from `9a92a22` with the Dockerfiles and targets in `deploy/cloudbuild.yaml`
(`mcp-feedback` uses `--target stored`), tagged `l106/<container>:local`.

## Machine

Intel Core i7-6700HQ @ 2.60 GHz (4 cores, 8 threads), 15.9 GB RAM, Windows 10 Home 10.0.19045.
Docker Desktop, engine 29.8.0 (WSL2 VM: 8 CPUs, 5.8 GiB, overlayfs). Every measured container ran with
`--cpus 1 --memory 512m` (Cloud Run's size). Postgres is the compose one (`postgres:16`, bind-mounted `./pgdata`).

## Method

| Step | What | Files |
|---|---|---|
| 1 | image size (`docker image inspect`), file count under `/app/.venv` | `images.csv` |
| 2 | `python -X importtime -c "import <module>"` in a fresh container, 3 runs each, `--entrypoint python` | `importtime/`, `importtime-summary.txt`, `summarize_importtime.py` |
| 3 | the real entrypoint, fresh container per run, 3 runs; `measure_startup.py` | `startup_warm.csv`, `logs/*-warm-*.log` (last 4 KB of each) |
| 4 | one run per container after `docker desktop restart` (done to drop the VM's file cache; not verified directly, but the roughly 2x slower runs are consistent with it; images and build cache kept) | `startup_cold.csv`, `logs/*-cold_cache-1.log` |
| 5 | `make_table.py` | `summary.md` |

Modules imported: `agent_qa.app`, `mcp_incidents.server`, `mcp_feedback.server`, `mcp_volume.server`,
`agent_reporting.app`, `agent_sentiment.app`, `agent_forecast.app`, `orchestrator.app`, `api_gateway.app`.
"Total import time" is the cumulative time of that module, the outermost line of the importtime output.
"Top-level import" means a direct import of that module (one indent down), cumulative.

**Timing.** The clock starts when `docker run -d` returns the container ID. One loop targets 0.25 s: `docker logs`
(until non-empty), then an HTTP GET on the published host port with a 1 s timeout, until 200 or 120 s.
`t_log_s` is the first non-empty `docker logs`; `t_listen_s` is the first HTTP response of any status;
`first_status` is that status; `t_200_s` is the first 200. In practice the loop turns about every 0.3 to 0.4 s, since each
`docker logs` call takes tens of milliseconds, so values are good to roughly 0.3 s and biased slightly high.
The first log line is uvicorn's "Started server process", so T_log is the point just before the port is open, by construction.

## Deviations from `docker-compose.yml` (all recorded)

- Compose's resolved environment was used for each service (`docker compose config`), but every container got
  `--cpus 1 --memory 512m`, including `mcp-feedback` (compose gives it 2 GiB; deploy gives it 512 Mi).
- `mcp-feedback`: `MCP_FEEDBACK_SCORING=stored_only` added and `MODELS_DIR` dropped, because the `stored` image has
  no model and no `./models` mount (as in `deploy/cloudrun/sentiment.yaml`).
- `gateway`: `GATEWAY_SESSION_KEY` is a harmless dummy (compose leaves it empty and the gateway then refuses to start).
  `./.local/gateway` is mounted read-only as compose does.
- Agents' MCP servers (`mcp-incidents`, `mcp-feedback`, `mcp-volume`) were started once, before the agents, under
  their compose hostnames on the compose network, so an agent's `/readyz` could return 200. Those dependency
  containers sat idle (not measured) while the agent rows ran. The orchestrator ran with no agents behind it
  (its probe is `/healthz`, plain liveness). `agent-qa` needs only Postgres.
- Published ports (`127.0.0.1:1xxxx`) were used to probe, so the Docker Desktop port proxy is in the path.
- LLM mode: compose's `free`. Start-up makes no model call and none was made.

## Limits

- **A local Docker run is not Cloud Run.** Cloud Run reads the image over the network onto a fresh machine, has its
  own sandbox (gVisor), CPU throttling, other containers in the same instance, Cloud SQL's socket and Secret Manager
  at start-up. None of that is present here. Local numbers say what the code costs on one warm machine,
  not what the platform adds.
- The file cache differs. Warm rows have the image's files in the Docker VM's page cache. The `importtime` runs
  followed the `.venv` file counts, which touch directory metadata but not file contents, so run 1 may be
  slightly colder than runs 2 and 3.
- `cold_cache` is **one run per container, taken in a fixed order** (`mcp-incidents` first). All nine images share
  the `python:3.12-slim` base layer, so once the first container has read it, the later ones read part of their
  image from a warm cache. The order confounds the comparison between containers; the cold rows say how much
  slower the first read is, not which image is slowest. A VM restart does not clear the Windows host's cache.
- The clock starts when `docker run -d` *returns*, so container create and start are excluded from T_log and
  T_listen (per the spec). Cloud Run's "Starting new instance" to first log line includes the equivalent.
- Three warm runs per container: enough to see the order of magnitude, not a distribution.
- The CPU is a 2016 laptop part, with Docker on WSL2; the absolute numbers are not Cloud Run's.
- Secrets: the env files holding compose's resolved values are in the ignored `.local/l106/env/`; none are committed
  and none of the logs contain credentials (searched for `password`, `api_key`, `postgres://`).
