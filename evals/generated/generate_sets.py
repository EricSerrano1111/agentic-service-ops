"""Fill the brief, generate with an independent model, filter, select (ADR-094).

    python evals/generated/generate_sets.py fill       # DB read as app_eval, no model call
    python evals/generated/generate_sets.py generate   # paid calls, at most 15 via packages/llm
    python evals/generated/generate_sets.py filter     # pool.jsonl + removed.jsonl
    python evals/generated/generate_sets.py select     # sets/*.draft.jsonl, reserve, skim.csv

Prints counts, hashes and costs only, never item text (ADR-030, ADR-094). `generate` is
resumable: finished categories are skipped and `provenance.json` is written after every call.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import dataclasses
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

SEED = 20261012
MODEL = "gemini-3.8-flash"
BRIEF = HERE / "brief_v2.md"
FILLED = HERE / "brief_v2.filled.md"
RAW = HERE / "raw"
PROVENANCE = HERE / "provenance.json"
AS_OF_DEFAULT = dt.date(2026, 8, 30)

REQUEST_BUDGET = 16  # 1 models.list (direct SDK, 2026-10-11) + 11 generation + 4 margin
MODELS_LIST_REQUESTS = 1
CLIENT_CAP = REQUEST_BUDGET - MODELS_LIST_REQUESTS
SPEND_CAP_USD = 2.00
PROJECTION_STOP_USD = 1.50
MAX_RETRIES = 4

POOL: dict[str, int] = {
    "clear_reporting": 25,
    "clear_sentiment": 20,
    "clear_forecast": 20,
    "underspecified": 20,
    "ambiguous": 30,
    "multi_domain": 20,
    "out_of_scope": 15,
    "near_miss": 25,
    "technician": 15,
    "filtered": 20,
    "unsupported_in_area": 15,
}

#: Explicit allowlist of existing evaluation inputs for the duplicate check. Never a glob of
#: evals/, and never evals/golden/ or evals/results/ (results files hold golden question text).
EXISTING_SETS = (
    "evals/routing/seed_v1.jsonl",
    "evals/routing/seed_v2.jsonl",
    "evals/routing/routing_v1.jsonl",
    "evals/routing/routing_v2.jsonl",
    "evals/routing/fr03_fresh_v1.jsonl",
    "evals/qa_interp/pairs_v1.jsonl",
    "evals/reporting_parse/parse_v3.jsonl",
    "evals/reporting_parse/parse_v4.jsonl",
    "evals/forecast_parse/parse_v1.jsonl",
    "evals/sentiment_parse/parse_v1.jsonl",
    "evals/qa_faults/catalogue_v1.yaml",
)
SHINGLE_K = 5
NEAR_DUP_THRESHOLD = 0.6


def _sibling(name: str):
    mod_name = f"evalgen_{name}"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


schema = _sibling("schema")
periods = _sibling("periods")
mapping = _sibling("mapping")


# ------------------------------------------------------------------------------ helpers


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def rank(key: str) -> str:
    """The only source of randomness: ordering by this digest, ascending (plan.md)."""
    return hashlib.sha256(f"{SEED}|{key}".encode()).hexdigest()


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def connect_eval():
    import psycopg

    load_env()
    e = os.environ
    return psycopg.connect(
        host=e["POSTGRES_HOST"],
        port=e["POSTGRES_PORT"],
        dbname=e["POSTGRES_DB"],
        user=e["DB_ROLE_EVAL_USER"],
        password=e["DB_ROLE_EVAL_PASSWORD"],
    )


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def write_json(path: Path, obj: Any) -> None:
    write_text(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    write_text(
        path, "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)
    )


# ------------------------------------------------------------------------------ fill


def as_of_date() -> dt.date:
    load_env()
    raw = (os.environ.get("REPORTING_AS_OF_DATE") or "").strip()
    return dt.date.fromisoformat(raw) if raw else AS_OF_DEFAULT


def fill() -> dict:
    from schemas import DATASET_WINDOW_END, DATASET_WINDOW_START

    load_env()
    with connect_eval() as conn:
        accounts = conn.execute("SELECT account_id, account_name FROM accounts").fetchall()
        techs = conn.execute("SELECT technician_id, full_name FROM technicians").fetchall()
    acc = sorted(accounts, key=lambda r: rank(f"account:{r[0]}"))[:12]
    tec = sorted(techs, key=lambda r: rank(f"technician:{r[0]}"))[:8]
    values = {
        "{DATA_START}": DATASET_WINDOW_START.isoformat(),
        "{DATA_END}": DATASET_WINDOW_END.isoformat(),
        "{AS_OF_DATE}": as_of_date().isoformat(),
        "{ACCOUNT_NAMES}": ", ".join(r[1] for r in acc),
        "{TECHNICIAN_NAMES}": ", ".join(r[1] for r in tec),
    }
    text = BRIEF.read_text(encoding="utf-8")
    for key, value in values.items():
        assert text.count(key) == 1, key
        text = text.replace(key, value)
    assert "{" not in text.split("## Output")[0], "unfilled placeholder"
    write_text(FILLED, text)
    info = {
        "brief_sha256": sha256_file(BRIEF),
        "filled_brief_sha256": sha256_file(FILLED),
        "data_start": values["{DATA_START}"],
        "data_end": values["{DATA_END}"],
        "as_of_date": values["{AS_OF_DATE}"],
        "accounts_shown": len(acc),
        "technicians_shown": len(tec),
    }
    print(json.dumps(info, indent=2))
    return info


# ------------------------------------------------------------------------------ generate


def _load_provenance() -> dict:
    if PROVENANCE.exists():
        return json.loads(PROVENANCE.read_text(encoding="utf-8"))
    return {
        "model": MODEL,
        "seed": SEED,
        "created": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "settings": {},
        "hashes": {},
        "calls": [
            {
                "kind": "models.list",
                "date": "2026-10-11",
                "requests": MODELS_LIST_REQUESTS,
                "via": "google-genai SDK directly, not packages/llm",
                "cost_usd": 0.0,
                "outcome": "ok",
            }
        ],
    }


def _used_requests(prov: dict) -> int:
    return sum(c.get("requests", 0) for c in prov["calls"])


def _generation_calls(prov: dict) -> list[dict]:
    return [c for c in prov["calls"] if c.get("kind") == "generate"]


class RecordingTransport:
    """Wraps the real transport to keep each response's usage split (thinking vs visible)."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.usages: list[dict] = []

    async def generate(self, **kwargs):
        response = await self._inner.generate(**kwargs)
        u = getattr(response, "usage_metadata", None)
        self.usages.append(
            {
                "prompt_tokens": getattr(u, "prompt_token_count", None) or 0,
                "visible_output_tokens": getattr(u, "candidates_token_count", None) or 0,
                "thinking_tokens": getattr(u, "thoughts_token_count", None) or 0,
            }
        )
        return response


def _raw_path(category: str, attempt: int | None) -> Path:
    return RAW / (f"{category}.json" if attempt is None else f"{category}.attempt{attempt}.json")


def _category_done(category: str) -> bool:
    return _raw_path(category, None).exists() or any(
        c.get("kind") == "generate" and c["category"] == category and c["outcome"] == "ok"
        for c in _load_provenance()["calls"]
    )


def _is_array_of_objects(text: str) -> bool:
    try:
        data = json.loads(text)
    except ValueError:
        return False
    return isinstance(data, list) and all(isinstance(x, dict) for x in data)


async def generate() -> int:
    from llm import LLMClient, LLMError, LLMOutputInvalid, LLMSettings
    from pydantic import RootModel

    if not FILLED.exists():
        print("run `fill` first", file=sys.stderr)
        return 2
    prov = _load_provenance()
    remaining = CLIENT_CAP - sum(c.get("requests", 0) for c in prov["calls"][1:])
    if remaining <= 0:
        print("request budget exhausted", file=sys.stderr)
        return 2

    load_env()
    os.environ.update(
        {
            "LLM_MODE": "paid",
            "LLM_MAX_REQUESTS": str(remaining),
            "LLM_MAX_SPEND_USD": f"{SPEND_CAP_USD:.2f}",
            "LLM_REQUEST_TIMEOUT_S": "300",
            "GEMINI_MODEL_SPECIALIST": MODEL,
        }
    )
    os.environ.pop("LLM_THINKING_LEVEL_SPECIALIST", None)
    settings = dataclasses.replace(LLMSettings.from_env("specialist"), temperature=None)
    from llm.transport import GeminiTransport

    recorder = RecordingTransport(GeminiTransport(settings))
    client = LLMClient(settings, transport=recorder)
    level = client.thinking_level_for(MODEL)
    price = client.prices[MODEL]
    prov["settings"] = {
        "mode": settings.mode,
        "thinking_level_sent": level,
        "temperature": "not sent (the model's default)",
        "request_timeout_s": settings.request_timeout_s,
        "client_request_cap": remaining,
        "spend_cap_usd": SPEND_CAP_USD,
        "input_per_m": price.input_per_m,
        "output_per_m": price.output_per_m,
        "price_source": price.source,
        "price_as_of": price.as_of.isoformat(),
        "output": "JSON array via response_json_schema (array of objects), no per-item validation",
    }
    prov["hashes"] = {
        "brief_sha256": sha256_file(BRIEF),
        "filled_brief_sha256": sha256_file(FILLED),
        "schema_json_sha256": sha256_file(HERE / "schema.json"),
    }
    filled = FILLED.read_text(encoding="utf-8")
    Array = RootModel[list[dict[str, Any]]]  # noqa: N806

    retries_used = sum(1 for c in _generation_calls(prov) if c["attempt"] > 1)
    done_calls = len(_generation_calls(prov))
    write_json(PROVENANCE, prov)

    for category, count in POOL.items():
        if _category_done(category):
            continue
        for attempt in (1, 2):
            if attempt == 2:
                if retries_used >= MAX_RETRIES:
                    print("stop: a fifth retry would be needed", file=sys.stderr)
                    return 3
                retries_used += 1
            prompt = f"{filled}\nWrite {count} questions in the category {category}."
            req0, cost0 = client.totals.requests, client.totals.cost_usd
            in0, out0 = client.totals.input_tokens, client.totals.output_tokens
            use0 = len(recorder.usages)
            began = time.perf_counter()
            text, outcome, error = None, "ok", None
            try:
                result = await client.generate(prompt, response_model=Array, trace_id=None)
                text = result.text
            except LLMOutputInvalid as exc:
                text, outcome, error = exc.raw_text, "LLMOutputInvalid", "not a JSON array"
            except LLMError as exc:
                outcome, error = type(exc).__name__, str(exc)[:200]
            record = {
                "kind": "generate",
                "category": category,
                "count_requested": count,
                "attempt": attempt,
                "requests": client.totals.requests - req0,
                "input_tokens": client.totals.input_tokens - in0,
                "output_tokens": client.totals.output_tokens - out0,
                "usage_detail": recorder.usages[use0:],
                "cost_usd": round(client.totals.cost_usd - cost0, 6),
                "latency_s": round(time.perf_counter() - began, 3),
                "outcome": outcome,
            }
            if error:
                record["error"] = error
            if record["requests"] > 1:
                record["hidden_retries"] = record["requests"] - 1
            if text is not None and outcome in ("ok", "LLMOutputInvalid"):
                path = _raw_path(category, None if (attempt == 1 and outcome == "ok") else attempt)
                write_text(path, text)
                record["raw_file"] = path.name
                record["raw_sha256"] = sha256_bytes(text.encode("utf-8"))
                record["array_of_objects"] = _is_array_of_objects(text)
            prov["calls"].append(record)
            prov["spent_usd"] = round(sum(c.get("cost_usd", 0) for c in prov["calls"]), 6)
            write_json(PROVENANCE, prov)  # after every call (the resume rule re-reads this)
            gen = _generation_calls(prov)
            print(
                f"{category} attempt {attempt}: {outcome}, requests {record['requests']}, "
                f"out {record['output_tokens']}, ${record['cost_usd']:.4f}, "
                f"total ${prov['spent_usd']:.4f}, requests used {_used_requests(prov)}"
            )
            if record.get("hidden_retries"):
                print(f"note: {record['hidden_retries']} hidden retry(ies) spent margin")
            if outcome == "ok":
                if len(gen) == 3 and done_calls < 3:
                    mean = sum(c["cost_usd"] for c in gen) / len(gen)
                    projected = mean * len(POOL)
                    print(f"projection after 3 calls: ${projected:.2f} over {len(POOL)} calls")
                    if projected > PROJECTION_STOP_USD:
                        print("stop: projection over $1.50", file=sys.stderr)
                        return 4
                break
            if outcome != "LLMOutputInvalid":
                print(f"stop: {outcome}", file=sys.stderr)
                return 5
            if attempt == 2:
                print(f"stop: second attempt for {category} also failed to parse", file=sys.stderr)
                return 6
    print(f"done: {_used_requests(prov)} of {REQUEST_BUDGET} requests, ${prov['spent_usd']:.4f}")
    return 0


# ------------------------------------------------------------------------------ filter


def normalise_exact(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.lower())


def shingles(text: str) -> set[str]:
    t = re.sub(r"\s+", " ", text.lower()).strip()
    return {t[i : i + SHINGLE_K] for i in range(max(len(t) - SHINGLE_K + 1, 1))}


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def _collect_questions(obj: Any, out: list[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "question" and isinstance(v, str):
                out.append(v)
            else:
                _collect_questions(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_questions(v, out)


def existing_questions() -> list[str]:
    out: list[str] = []
    for rel in EXISTING_SETS:
        path = ROOT / rel
        if not path.exists():
            continue
        if path.suffix == ".jsonl":
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    _collect_questions(json.loads(line), out)
        else:
            import yaml

            _collect_questions(yaml.safe_load(path.read_text(encoding="utf-8")), out)
    return out


BREAKDOWNS_NOT_OFFERED = {
    "reporting": {"month", "quarter"},
    "sentiment": {"account", "work_type", "technician", "incident_type", "severity"},
    "forecast": {
        "account",
        "region",
        "technician",
        "incident_type",
        "severity",
        "month",
        "quarter",
    },
}


def has_unsupported_element(intent: dict) -> bool:
    return (
        intent.get("measure") == "other"
        or intent.get("region") == "unsupported"
        or intent.get("breakdown") in BREAKDOWNS_NOT_OFFERED.get(intent.get("area"), set())
    )


def label_problem(item: Any, requested: str) -> str | None:
    """A reason if the item's labels contradict the brief's rules, else None."""
    if item.category != requested:
        return "category_mismatch"
    fixed = mapping.CATEGORY_ROUTE[item.category]
    if fixed is not None and item.expected_route != fixed:
        return "route_contradicts_category"
    if item.intent is not None and item.intent.area != item.expected_route:
        return "area_contradicts_route"
    if item.category == "unsupported_in_area" and not has_unsupported_element(
        item.intent.model_dump(mode="json")
    ):
        return "no_unsupported_element"
    return None


def load_raw_items() -> list[tuple[str, int, Any]]:
    """(requested category, index, raw element): the first attempt that parsed as an array."""
    out = []
    for category in POOL:
        paths = [_raw_path(category, None)] + [_raw_path(category, n) for n in (1, 2, 3)]
        for path in paths:
            if path.exists() and _is_array_of_objects(path.read_text(encoding="utf-8")):
                data = json.loads(path.read_text(encoding="utf-8"))
                out += [(category, i, el) for i, el in enumerate(data)]
                break
    return out


def eligibility(item: Any, as_of: dt.date) -> tuple[bool, list[str]]:
    reasons = []
    intent = item.intent
    if intent is None:
        return False, ["no_intent"]
    if intent.measure is None:
        reasons.append("no_measure")
    elif intent.measure == "other":
        reasons.append("measure_other")
    if item.category == "unsupported_in_area":
        reasons.append("unsupported_in_area")
    ok, why = periods.check_item_period(intent.model_dump(mode="json"), as_of)
    if not ok:
        reasons.append(f"date_check: {why}")
    return not reasons, reasons


def filter_pool() -> dict:
    as_of = as_of_date()
    kept: list[dict] = []
    removed: list[dict] = []
    stats: dict[str, dict[str, int]] = {c: {} for c in POOL}
    generated: dict[str, int] = dict.fromkeys(POOL, 0)

    def remove(cat: str, reason: str, raw: Any, detail: str = "") -> None:
        removed.append({"category": cat, "reason": reason, "detail": detail, "item": raw})
        stats[cat][reason] = stats[cat].get(reason, 0) + 1

    candidates = []
    for cat, _idx, raw in load_raw_items():
        generated[cat] += 1
        try:
            item = schema.Item.model_validate(raw)
        except ValueError as exc:
            remove(cat, "schema", raw, f"{type(exc).__name__}")
            continue
        problem = label_problem(item, cat)
        if problem:
            remove(cat, problem, raw)
            continue
        uid = f"{item.category}/{item.id}"
        candidates.append((rank(f"item:{uid}"), uid, cat, item, raw))
    candidates.sort(key=lambda c: c[0])

    existing = existing_questions()
    ex_exact = {normalise_exact(q) for q in existing}
    ex_sh = [shingles(q) for q in existing]
    seen_exact: dict[str, str] = {}
    seen_sh: list[tuple[str, set[str]]] = []
    seen_uids: set[str] = set()
    for _, uid, cat, item, raw in candidates:
        if uid in seen_uids:
            remove(cat, "duplicate_id", raw)
            continue
        norm = normalise_exact(item.question)
        if norm in ex_exact or norm in seen_exact:
            remove(cat, "exact_duplicate", raw, "existing set" if norm in ex_exact else "pool")
            continue
        sh = shingles(item.question)
        if any(jaccard(sh, o) > NEAR_DUP_THRESHOLD for o in ex_sh):
            remove(cat, "near_duplicate", raw, "existing set")
            continue
        if any(jaccard(sh, o) > NEAR_DUP_THRESHOLD for _, o in seen_sh):
            remove(cat, "near_duplicate", raw, "pool")
            continue
        seen_uids.add(uid)
        seen_exact[norm] = uid
        seen_sh.append((uid, sh))
        eligible, reasons = eligibility(item, as_of)
        kept.append(
            {
                "uid": uid,
                "rank": rank(f"item:{uid}"),
                "category": item.category,
                "area": item.intent.area if item.intent else item.expected_route,
                "brief_route": item.expected_route,
                "system_route": mapping.system_route(item.expected_route),
                "interp_eligible": eligible,
                "ineligible_reasons": reasons,
                "item": json.loads(item.model_dump_json()),
            }
        )
    kept.sort(key=lambda r: r["rank"])
    write_jsonl(HERE / "filtered" / "pool.jsonl", kept)
    write_jsonl(HERE / "filtered" / "removed.jsonl", removed)
    summary = {
        c: {
            "generated": generated[c],
            "removed": stats[c],
            "kept": sum(1 for k in kept if k["category"] == c),
        }
        for c in POOL
    }
    print(json.dumps(summary, indent=2))
    print("existing questions checked against:", len(existing))
    return summary


# ------------------------------------------------------------------------------ select

SET_SIZES = {
    "interp_fresh_v1": 24,
    "fr03_fresh_v2": 16,
    "routing_heldout_v1": 50,
    "parse_filters_v1": 12,
}
CLEAR = mapping.CLEAR_CATEGORIES
INTERP_CATEGORIES = (*CLEAR, "underspecified", "filtered", "technician")


def _load_pool() -> list[dict]:
    path = HERE / "filtered" / "pool.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def select_sets(pool: list[dict]) -> tuple[dict[str, list[dict]], list[dict], dict]:
    used: set[str] = set()
    sets: dict[str, list[dict]] = {name: [] for name in SET_SIZES}
    notes: dict[str, Any] = {}

    def take(name: str, n: int, pred, label: str = "") -> int:
        got = 0
        for r in pool:  # `pool` is sorted by rank
            if got >= n:
                break
            if r["uid"] in used or not pred(r):
                continue
            used.add(r["uid"])
            sets[name].append({**r, "set": name, "stratum": label})
            got += 1
        return got

    def elig(r: dict) -> bool:
        return r["interp_eligible"] and r["category"] in INTERP_CATEGORIES

    # interp_fresh_v1: narrowest eligibility first.
    n = "interp_fresh_v1"
    rep = lambda r: elig(r) and r["area"] == "reporting"  # noqa: E731
    got_unsup = take(
        n,
        1,
        lambda r: (
            rep(r)
            and r["category"] == "filtered"
            and r["item"]["intent"]["region"] == "unsupported"
        ),
        "reporting/filtered/unsupported_region",
    )
    take(n, 2 - got_unsup, lambda r: rep(r) and r["category"] == "filtered", "reporting/filtered")
    take(n, 2, lambda r: rep(r) and r["category"] == "technician", "reporting/technician")
    take(n, 10 - len(sets[n]), rep, "reporting")
    take(n, 7, lambda r: elig(r) and r["area"] == "sentiment", "sentiment")
    take(n, 7, lambda r: elig(r) and r["area"] == "forecast", "forecast")
    notes["interp_unsupported_region_eligible"] = bool(got_unsup)

    n = "fr03_fresh_v2"
    take(n, 8, lambda r: r["category"] == "ambiguous", "ambiguous")
    take(n, 4, lambda r: r["category"] == "underspecified", "underspecified")
    take(n, 2, lambda r: r["category"] in CLEAR, "clear")
    take(n, 2, lambda r: r["category"] == "multi_domain", "multi_domain")

    n = "routing_heldout_v1"
    for cat in CLEAR:
        take(n, 5, lambda r, cat=cat: r["category"] == cat, f"clear/{cat}")
    for cat, k in (
        ("underspecified", 6),
        ("ambiguous", 7),
        ("multi_domain", 6),
        ("out_of_scope", 5),
        ("near_miss", 5),
        ("technician", 2),
        ("filtered", 2),
        ("unsupported_in_area", 2),
    ):
        take(n, k, lambda r, cat=cat: r["category"] == cat, cat)

    take("parse_filters_v1", 12, lambda r: r["category"] == "filtered", "filtered")

    reserve = [{**r, "set": "reserve", "stratum": ""} for r in pool if r["uid"] not in used]
    return sets, reserve, notes


def select() -> dict:
    pool = _load_pool()
    sets, reserve, notes = select_sets(pool)
    for name, rows in sets.items():
        write_jsonl(HERE / "sets" / f"{name}.draft.jsonl", rows)
    write_jsonl(HERE / "sets" / "reserve.jsonl", reserve)

    amb_res = [r for r in reserve if r["category"] == "ambiguous"][:6]
    und_res = [r for r in reserve if r["category"] == "underspecified"][:2]
    skim_rows = []
    for name, rows in sets.items():
        for r in rows:
            if r["category"] == "ambiguous" or name == "fr03_fresh_v2":
                skim_rows.append(r)
    skim_rows += amb_res + und_res
    path = HERE / "skim" / "skim.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(
            [
                "id",
                "set",
                "category",
                "question",
                "expected_route",
                "candidate_areas",
                "rationale",
                "owner_agree",
                "owner_note",
            ]
        )
        for r in skim_rows:
            it = r["item"]
            w.writerow(
                [
                    r["uid"],
                    r["set"],
                    r["category"],
                    it["question"],
                    it["expected_route"],
                    "|".join(it["candidate_areas"]),
                    it["rationale"],
                    "",
                    "",
                ]
            )
    summary = {
        "sets": {
            name: {
                "size": len(rows),
                "target": SET_SIZES[name],
                "by_category": {
                    c: sum(1 for r in rows if r["category"] == c)
                    for c in sorted({r["category"] for r in rows})
                },
            }
            for name, rows in sets.items()
        },
        "reserve": len(reserve),
        "skim_rows": len(skim_rows),
        "interp_eligible_in_pool": sum(1 for r in pool if r["interp_eligible"]),
        "interp_date_check_ineligible": sum(
            1
            for r in pool
            if any(x.startswith("date_check") for x in r["ineligible_reasons"])
            and r["category"] in INTERP_CATEGORIES
        ),
        **notes,
    }
    print(json.dumps(summary, indent=2))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["fill", "generate", "filter", "select"])
    args = ap.parse_args()
    if args.stage == "fill":
        fill()
    elif args.stage == "generate":
        return asyncio.run(generate())
    elif args.stage == "filter":
        filter_pool()
    else:
        select()
    return 0


if __name__ == "__main__":
    sys.exit(main())
