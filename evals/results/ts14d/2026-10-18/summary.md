# TS-14-D: credential scan of the repository and the deployed images

*2026-10-18 (S6-S1; owner-decided 2026-10-18; assistant-drafted.)* Runs `05`'s case TS-14-D: "Search the code repository and the built container images for credentials. Expected: none found. Services read credentials from Secret Manager."

**Verdict: Passed.** No real credential in the repository history or in any of the nine deployed images, and every credential the services use comes from Secret Manager. Two Gitleaks hits, both false positives (file digests), are listed below. The case made no model call, no GCP write, no `ops-db` start, no deploy and no code change.

## Scanners

| Tool | Version | Image | Digest |
|---|---|---|---|
| Trivy (secret scanner, `--scanners secret`) | 0.76.0 | `aquasec/trivy:latest` | `sha256:2416d1f74045b57274df1a340eee6b510cacd73c66a6ccb8da092b117eb7d222` |
| Gitleaks (`detect`, full history) | v8.30.1 | `zricethezav/gitleaks:latest` | `sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f` |

Default rules for both; no allowlist, no config file. Gitleaks ran with `--redact`, which hides matched values in the report and does not change what is detected. Docker 29.8.0.

## The nine images

Read from the six Cloud Run services (`gcloud run services describe`, 2026-10-18). Every tag is `9ab7c775964bd0aae491ca72082e95229c994129`. The digest of each tag, read from Artifact Registry, equals the digest the serving revision is pinned to (9 of 9). Registry: `us-central1-docker.pkg.dev/a2a-agentic-service-ops-gcp/agentic-service-ops/`.

| Service / revision | Container | Digest | Trivy secret hits |
|---|---|---|---|
| `ops-forecast` `00003-ndv` | `agent-forecast` | `sha256:68ee3bea52083a5e9691c738a01474f38c4484654f22831b1bbbb2a628d9cbd8` | 0 |
| `ops-forecast` `00003-ndv` | `mcp-volume` | `sha256:dbb731c0096767616805472c82995d52b21e4c7a418e779411a0da95db839e2c` | 0 |
| `ops-gateway` `00002-w57` | `gateway` | `sha256:12b7476e9b35d01218389960e0a452ee0e6ad009d3b1f0279cf97674dda5a7fa` | 0 |
| `ops-orchestrator` `00007-b8z` | `orchestrator` | `sha256:fdc1c232e5b14a1ae53a9505028adea42e61f9ab5bf07ac4d968b410b1dbbeaa` | 0 |
| `ops-qa` `00004-t6m` | `agent-qa` | `sha256:6a0d19c697ae395acf868730e0585d7c49a5f37ae995548433dd7da76d6f463d` | 0 |
| `ops-reporting` `00007-8mm` | `agent-reporting` | `sha256:00367b2bb6cfb6880f0ce4963f0d859130845d0b55910c0e5de6bd6fe23fc379` | 0 |
| `ops-reporting` `00007-8mm` | `mcp-incidents` | `sha256:ec6c07a68fecacaf2f8c571f8f55191a77abeba9d2b517028e1a377310e87276` | 0 |
| `ops-sentiment` `00003-hx4` | `agent-sentiment` | `sha256:1b97b2c6c25ac3bc02d785665370b8581b30420d063cb8b626f46f30aae95e82` | 0 |
| `ops-sentiment` `00003-hx4` | `mcp-feedback` | `sha256:6c529d620c92da27ec5f9d7b88ba86b18e3b160cf35b48cda8aa4ee51febaff6` | 0 |

Each image was addressed by digest, not tag. All nine are Debian 13 / Python 3.12.15 base images running as user `app` (uid 10001).

**How Trivy read them (a deviation to know about).** `docker save` on this machine (Docker 29, containerd image store) produced archives Trivy could not read ("blob ... not found in tar"), and the Docker-socket route failed the same way. Trivy therefore pulled each image from Artifact Registry by digest (`--image-src remote`), authenticated with a short-lived `gcloud auth print-access-token` passed to the scanner container through an environment variable (never on a command line, never written to a file; none of the results contain it). It is the same bytes the digest names. The images were also pulled locally with `docker pull` by digest for the history and config checks below.

## Image history and config (beyond what Trivy reads)

- **`docker history --no-trunc`** (`image-config/*.history.txt`): no `ARG`, no `--build-arg`, no `--mount=type=secret`, and no `COPY` of an `.env`, key or credential file. The application layers are `useradd`, `COPY` of the virtualenv, and (per image) `/app/static`, the sentiment manifest, or `/models/forecast/volume_v2/` plus its manifest, then `ENV PYTHONDONTWRITEBYTECODE PYTHONUNBUFFERED PATH`, `USER app`, `EXPOSE`, `CMD`. The other layers are the `python:3.12` base image.
- **`.Config.Env`** (`image-config/*.env.json`): baked variables are `PATH`, `LANG`, `GPG_KEY`, `PYTHON_VERSION`, `PYTHON_SHA256`, `PYTHONDONTWRITEBYTECODE`, `PYTHONUNBUFFERED`, plus `GATEWAY_STATIC_DIR=/app/static` (gateway) and `MCP_FEEDBACK_SCORING=stored_only` (`mcp-feedback`). `GPG_KEY` is the python.org release-signing key fingerprint set by the official `python` base image, and `PYTHON_SHA256` is the hash of the Python source tarball. Neither is a credential. No baked variable holds a secret.
- No image sets labels.

## Repository history

Fresh, non-shallow clone of `origin` at `C:\ts14d\repo`, HEAD `3f342c39782bbed02cde96f65a56d5b798e200d2` (`main`), three remote refs (`main`, `feat/generate`, `HEAD`). Gitleaks scanned **333 commits** (about 22 MB), which is every non-merge commit reachable from any ref (`git rev-list --all --no-merges --count` = 333; the other 73 commits are merges and carry no diff of their own).

**2 hits**, `generic-api-key`, both in `ml/sentiment/artifacts/bert_v1.manifest.json`, commit `ff004c7d4e` (2026-10-01, "ml: bert_v1 export, ADR-066 calibration ..."), lines 23 and 24.

| Hit | Class | Reason |
|---|---|---|
| line 23 (`tokenizer.json` entry) | False positive | A 64-character lowercase-hex value under the key `tokenizer.json` in the manifest's file-digest map: the SHA-256 of a tokenizer file. |
| line 24 (`tokenizer_config.json` entry) | False positive | The same, for `tokenizer_config.json`. |

The manifest is a file-integrity record (the artifact manifest's SHA-256 is the stored predictions' `model_version`, ADR-067); its digests are published by design and verify a file, they do not grant access. The sibling entries on lines 21 and 22 (`label_map.json`, `model.safetensors`) have the same shape and were not flagged, so the rule fired on entropy and key name, not on a credential pattern. The raw report is `gitleaks.json`; it was written with `--redact`, so every `Match` and `Secret` field reads `REDACTED` (checked), and it holds no value.

## Hits by class

| Class | Images (Trivy) | Repository history (Gitleaks) |
|---|---|---|
| Real credential | 0 | 0 |
| Test fixture | 0 | 0 |
| False positive | 0 | 2 (SHA-256 file digests, above) |
| Third-party package content | 0 | 0 |
| **Total** | **0** | **2** |

The raw Trivy reports are `trivy/<container>.json`. They contain no finding (the `Secrets` array is empty or absent in every result), so they hold no matched value; the check for token strings (`ya29.`, `oauth2accesstoken`, `AIza`) over all nine found none.

## Secret Manager use (read-only)

`secretKeyRef` entries per container, read from the live revisions on 2026-10-18 (secret names only; no value was read):

| Container | Env var → Secret Manager secret (`:latest`) |
|---|---|
| `gateway` | `GATEWAY_SESSION_KEY` → `gateway-session-key` |
| `orchestrator` | `GOOGLE_AI_API_KEY` → `gemini-api-key`; `GOOGLE_AI_API_KEY_PAID` → `gemini-api-key-paid` |
| `agent-reporting` | the same two Gemini keys |
| `agent-sentiment` | the same two Gemini keys |
| `agent-forecast` | the same two Gemini keys |
| `agent-qa` | the same two Gemini keys; `DB_ROLE_QA_PASSWORD` → `db-role-qa-password` |
| `mcp-incidents` | `DB_ROLE_REPORTING_PASSWORD` → `db-role-reporting-password` |
| `mcp-feedback` | `DB_ROLE_SENTIMENT_PASSWORD` → `db-role-sentiment-password` |
| `mcp-volume` | `DB_ROLE_FORECAST_PASSWORD` → `db-role-forecast-password` |

**It matches the audit's Appendix A (2026-10-16) exactly**: same six revisions, same containers, same secret mounts, including `agent-qa` holding `DB_ROLE_QA_PASSWORD` by design (ADR-089). The twelve secrets in the project are `db-admin-password`, `db-role-{eval,forecast,generator,qa,reporting,sentiment,train}-password`, `gateway-invites`, `gateway-session-key`, `gemini-api-key`, `gemini-api-key-paid`.

**One addition to Appendix A.** The gateway carries `GATEWAY_INVITES_SECRET` as a *literal* environment variable. Its value is a Secret Manager resource name, not a credential: 45 characters, no leading slash, four `/`-separated segments, the shape `projects/<project number>/secrets/gateway-invites` (the value itself was never printed; `tests/unit/test_deploy_full.py:354` asserts exactly that form, and `services/api_gateway/src/api_gateway/config.py:65-68` documents it as the Secret Manager source). The invite list is read from Secret Manager at runtime. No other container has a literal variable whose name contains `KEY`, `PASS`, `SECRET`, `TOKEN` or `CRED`.

## What this does not show

- It is a pattern and entropy scan. A credential with no recognisable shape would not be found (the same limit as the log scan, L-63).
- It scans the nine images at digests serving on 2026-10-18 and the repository history at `3f342c3`. A later deploy or commit is not covered, and nothing here is automated.
- It is a **secret** scan. It is not a vulnerability (CVE) scan, and `--scanners vuln` was not run.
- GitHub's native secret scanning and push protection are on for the repository (audit, F9); this scan is independent of them.
- The Gemini keys are mounted into the five model-calling containers at run time, so a running container's memory and environment hold them. Image scanning cannot speak to that; the audit's F7 covers it.
