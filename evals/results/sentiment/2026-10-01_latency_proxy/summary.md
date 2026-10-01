# BERT latency proxy, 2026-10-01 (ADR-065)

**Every figure here is PROXY:** real `bert-base-uncased` compute (pinned revision
`86b5e093…`, random 4-class head, `max_length` 64, padding to the longest comment in the
batch) in a CPU-limited local Docker container with `--network none`. It is not Cloud Run
(L-28). Fine-tuning changes the weights, not the compute, so the trained model costs the
same. Host: Intel i7-6700HQ (4 cores / 8 threads), Docker Desktop on WSL2. Raw data:
`results.json`. Harness: `evals/sentiment/latency/`. Run by Eric from his own terminal with
`--skip-build --large-repeats 1`.

**Repeats:** cold start 3 runs per configuration; throughput 3 runs per batch size; every
slice 3 runs, **except `full_window` and `last_12_months`, which ran once each**
(`--large-repeats 1`, to fit the run into about an hour on this machine). Neither is a gate
slice. For those two, median and maximum are the single run.

## Slice sizes (comments, read as `app_eval`)

| Slice | Comments | Gate? |
|---|---:|---|
| Full window (2023-09-04 to 2026-08-30) | 7,521 | no |
| Last 12 months (2025-08-31 to 2026-08-30) | 2,666 | no |
| Largest calendar quarter | 736 | no |
| Largest calendar month | 287 | no |
| Largest account × quarter | 107 | **yes** |
| Median account × quarter | 9 | no |
| Largest region × quarter | 225 | **yes** |

## Cold start (container start to first prediction; budget 20 s)

| Config | Runs (s) | Median | Max | Verdict |
|---|---|---:|---:|---|
| 1 CPU / 2 GiB | 13.09, 13.12, 13.41 | 13.12 | 13.41 | PASS |
| 2 CPU / 4 GiB | 13.10, 12.87, 13.02 | 13.02 | 13.10 | PASS |

About 12.3 s of each is inside Python (imports plus model load); the rest is container start.

## Warm throughput (comments/s, median of 3; min in brackets)

| Config | Batch 16 | Batch 32 | Batch 64 |
|---|---:|---:|---:|
| 1 CPU | **10.74** (10.72) | 9.65 (9.60) | 9.16 (9.10) |
| 2 CPU | **17.45** (17.26) | 16.22 (16.13) | 14.98 (14.45) |

Batch 16 is best at both, so slices ran at batch 16.

## Warm slice latency at batch 16 (budget 30 s on the gate slices)

| Slice | Repeats | 1 CPU median / max (s) | 2 CPU median / max (s) | Verdict |
|---|---:|---|---|---|
| Full window (7,521) | **1** | 669.2 / 669.2 | 409.9 / 409.9 | reported, not the gate (over 30 s) |
| Last 12 months (2,666) | **1** | 239.0 / 239.0 | 147.7 / 147.7 | reported, not the gate (over 30 s) |
| Largest quarter (736) | 3 | 65.3 / 65.4 | 40.0 / 40.2 | reported, not the gate (**over 30 s**) |
| Largest month (287) | 3 | 25.8 / 26.2 | 15.5 / 15.8 | reported, not the gate |
| Largest account × quarter (107) | 3 | 9.8 / 10.0 | 6.0 / 6.1 | **PASS** |
| Median account × quarter (9) | 3 | 0.76 / 0.77 | 0.49 / 0.50 | reported, not the gate |
| Largest region × quarter (225) | 3 | 20.2 / 20.7 | 12.3 / 12.3 | **PASS** |

## Peak memory

| Config | `docker stats` peak (sampled) | cgroup `memory.peak` |
|---|---:|---:|
| 1 CPU / 2 GiB | 444.8 MiB | 491.8 MiB |
| 2 CPU / 4 GiB | 480.2 MiB | 486.0 MiB |

No out-of-memory kill. Under 0.5 GiB at both, so 2 GiB has ample headroom.

## Reading (no decision taken here)

- Both ADR-065 gates pass at both configurations, and cold start passes with about 7 s to
  spare.
- With two revision cycles (ADR-055) re-running inference, the 1 CPU worst gate slice
  costs 3 × 20.7 s plus a 13.4 s cold start, about 75 s before any LLM call; at 2 CPUs,
  about 50 s. Reusing a request's inference across revisions (ADR-065 context) removes
  most of that.
- A company-wide quarter (736 comments, e.g. "sentiment last quarter") is not a gate slice
  under ADR-065 but takes 65 s at 1 CPU and 40 s at 2 CPUs, over the 30 s budget at both.
  It is a plausible question, so whether it belongs in the gate is a decision for Eric.
