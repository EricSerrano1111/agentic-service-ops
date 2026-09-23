"""Model bake-off for the feedback_text corpus (ADR-030 open item: Gemma 4 vs Flash-Lite).

Sends the same 100 seeded comment specs, in 5 batches of 20, to each candidate model and
writes raw responses, parsed comments, automatic metrics, and a blind human-review sheet to
data/generator/experiments/bakeoff/<YYYY-MM-DD>/.

This is an experiment, not build_corpus.py: nothing here feeds generate.py.

Prints progress and summaries only, never comment text (ADR-030, CLAUDE.md).

Usage:
    python data/generator/experiments/model_bakeoff.py            # full run
    python data/generator/experiments/model_bakeoff.py --dry-run  # specs + prompt only, no API
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import sys
import time
from collections import Counter
from datetime import date
from itertools import combinations
from pathlib import Path

SEED = 20260923
BATCH_SIZE = 20
MODELS = ["gemma-4-31b-it", "gemini-3.5-flash-lite"]
TEMPERATURE = 1.0
THINKING_LEVEL = "minimal"
RESPONSE_MIME_TYPE = "application/json"
MAX_RETRIES = 5
BACKOFF_BASE_S = 4.0
BACKOFF_CAP_S = 60.0
RETRYABLE_CODES = {429, 500, 503}

OUT_ROOT = Path(__file__).resolve().parent / "bakeoff"

SERVICE_TYPES = ["install", "repair", "maintenance", "inspection", "upgrade"]
WRITERS = ["site contact", "office manager", "IT manager", "facilities lead"]
CHANNEL_BANDS = {
    "email_survey": (15, 60),
    "sms_survey": (5, 20),
    "phone_followup": (10, 40),
    "portal": (15, 60),
}
INCIDENT_PHRASES = {
    "missed_sla": "technician arrived late",
    "wrong_dispatch_info": "technician was sent with wrong information or parts",
    "repeat_visit_required": "needed a second visit",
    "technician_conduct": "a problem with the technician's conduct",
    "equipment_damage": "equipment was damaged",
    "billing_dispute": "a billing problem",
}
# (style, sentiment) -> count. 40 plain, 30 sarcastic, 30 implicit.
SPEC_MIX = {
    ("plain", "positive"): 10,
    ("plain", "neutral"): 10,
    ("plain", "negative"): 10,
    ("plain", "mixed"): 10,
    ("sarcastic", "negative"): 24,
    ("sarcastic", "mixed"): 6,
    ("implicit", "positive"): 10,
    ("implicit", "neutral"): 10,
    ("implicit", "negative"): 10,
}
N_INCIDENTS = 40
N_SERIOUS_POS_NEU = 10  # prompt asks for >= 8 serious incidents on positive/neutral specs

# Blind-review quotas per model: (style, sentiment) -> n. Same spec ids for both models.
REVIEW_QUOTAS = {
    ("sarcastic", "negative"): 4,
    ("sarcastic", "mixed"): 2,
    ("implicit", "positive"): 2,
    ("implicit", "neutral"): 2,
    ("implicit", "negative"): 2,
    ("plain", "positive"): 2,
    ("plain", "neutral"): 2,
    ("plain", "negative"): 2,
    ("plain", "mixed"): 2,
}

# Automatic rule checks — cheap proxies for the prompt's "Rules" and sarcasm bans.
BANNED_SARCASM = re.compile(r"/s\b|\boh,? great\b|\bwow,? just wow\b", re.IGNORECASE)
MENTIONS_SURVEY = re.compile(r"\b(survey|rating|rate (?:this|you|us))\b", re.IGNORECASE)
PRICE_OR_TIME = re.compile(r"\$\s?\d|\b\d{1,2}:\d{2}\b|\b\d{1,2}\s?(?:am|pm)\b", re.IGNORECASE)

PROMPT_V0 = """\
You are writing realistic post-visit survey comments from customers of a field service
company that sends technicians to install, repair, maintain, inspect, and upgrade
business network and hardware equipment (switches, routers, access points, cabling,
servers, security cameras, UPS units).

Write one comment per spec. Each spec gives the sentiment the writer means, a style,
the visit context, the channel and length, and who is writing.

Definitions:
- mixed: clearly praises one concrete thing and clearly criticizes another; neither dominates.
- neutral: factual or indifferent; no real praise or complaint.
- sarcastic: the wording sounds positive, but the writer means the stated sentiment. The
  real meaning must be recoverable from a concrete detail (a count, a delay, a repeat
  visit). Do not signal sarcasm with "/s", "Oh great", "Wow, just wow", scare quotes,
  or exclamation-heavy openings.
- implicit: the sentiment is real but carried by facts or understatement rather than
  sentiment words. A careful reader should still reach the stated sentiment.
- If the spec has an incident, the comment should relate to that problem. A serious
  problem can still get a positive or neutral comment if it was handled well.

Rules:
- Write like real customers: vary openings, sentence length, punctuation, and formality.
  SMS comments are short and may skip capitalization. No two comments may start the
  same way.
- No personal names, company names, dates, times, prices, or ticket numbers.
- Do not mention the survey or a rating.
- Output only JSON: an array of {"id": <spec id>, "text": "<comment>"}, one per spec,
  in spec order.

Specs:
{numbered spec lines}
"""


# --------------------------------------------------------------------------- specs


def build_specs(seed: int = SEED) -> list[dict]:
    """Deterministic 100-spec set. Order is shuffled so every batch mixes styles."""
    rng = random.Random(seed)
    specs = [
        {"style": style, "sentiment": sentiment}
        for (style, sentiment), n in SPEC_MIX.items()
        for _ in range(n)
    ]
    rng.shuffle(specs)

    # Incidents: 10 serious on positive/neutral specs first (the "handled well" cases),
    # then 30 more drawn from the rest; 20 serious / 20 minor overall.
    pos_neu = [i for i, s in enumerate(specs) if s["sentiment"] in ("positive", "neutral")]
    serious_pn = set(rng.sample(pos_neu, N_SERIOUS_POS_NEU))
    others = [i for i in range(len(specs)) if i not in serious_pn]
    more = rng.sample(others, N_INCIDENTS - N_SERIOUS_POS_NEU)
    n_serious_more = N_INCIDENTS // 2 - N_SERIOUS_POS_NEU
    severity = {i: "serious" for i in serious_pn}
    severity.update({i: ("serious" if k < n_serious_more else "minor") for k, i in enumerate(more)})

    no_incident = [i for i in range(len(specs)) if i not in severity]
    service_cycle = SERVICE_TYPES * (len(no_incident) // len(SERVICE_TYPES) + 1)
    service_for = dict(zip(no_incident, service_cycle, strict=False))

    incident_types = list(INCIDENT_PHRASES)
    for i, s in enumerate(specs):
        s["id"] = i + 1
        if i in severity:
            s["incident_severity"] = severity[i]
            s["incident_type"] = rng.choice(incident_types)
            s["service_type"] = None
        else:
            s["incident_severity"] = None
            s["incident_type"] = None
            s["service_type"] = service_for[i]
        s["channel"] = rng.choice(list(CHANNEL_BANDS))
        s["min_words"], s["max_words"] = CHANNEL_BANDS[s["channel"]]
        s["writer"] = rng.choice(WRITERS)
    return [
        {
            k: s[k]
            for k in (
                "id",
                "sentiment",
                "style",
                "service_type",
                "incident_severity",
                "incident_type",
                "channel",
                "min_words",
                "max_words",
                "writer",
            )
        }
        for s in specs
    ]


def spec_line(s: dict) -> str:
    if s["incident_type"]:
        context = f"{s['incident_severity']} problem: {INCIDENT_PHRASES[s['incident_type']]}"
    else:
        context = f"{s['service_type']} visit"
    return (
        f"{s['id']}. sentiment: {s['sentiment']}; style: {s['style']}; context: {context}; "
        f"channel: {s['channel']}, {s['min_words']}-{s['max_words']} words; "
        f"writer: {s['writer']}"
    )


def render_prompt(batch: list[dict]) -> str:
    return PROMPT_V0.replace("{numbered spec lines}", "\n".join(spec_line(s) for s in batch))


def batches(specs: list[dict], size: int = BATCH_SIZE) -> list[list[dict]]:
    return [specs[i : i + size] for i in range(0, len(specs), size)]


# --------------------------------------------------------------------------- parsing

_FENCE = re.compile(r"^\s*```(?:json)?\s*\n?(.*?)\n?\s*```\s*$", re.DOTALL | re.IGNORECASE)


def parse_response(text: str | None, expected_ids: list[int]) -> dict:
    """Parse a batch response into {id: text} and report mismatches against the specs.

    Accepts bare JSON, fenced JSON, or JSON embedded in prose (first '[' to last ']').
    Never raises: a failure is reported as ok=False so metrics can count it.
    """
    result = {
        "ok": False,
        "comments": {},
        "missing_ids": list(expected_ids),
        "extra_ids": [],
        "duplicate_ids": [],
        "error": None,
    }
    if not text:
        result["error"] = "empty response"
        return result
    candidate = text.strip()
    m = _FENCE.match(candidate)
    if m:
        candidate = m.group(1).strip()
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        lo, hi = candidate.find("["), candidate.rfind("]")
        try:
            data = json.loads(candidate[lo : hi + 1]) if 0 <= lo < hi else None
        except json.JSONDecodeError:
            data = None
    if not isinstance(data, list):
        result["error"] = "no JSON array found"
        return result

    comments: dict[int, str] = {}
    seen: Counter = Counter()
    for item in data:
        if not isinstance(item, dict) or "text" not in item:
            continue
        try:
            cid = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        seen[cid] += 1
        if cid not in comments and isinstance(item["text"], str):
            comments[cid] = item["text"].strip()
    expected = set(expected_ids)
    result.update(
        ok=True,
        comments={k: v for k, v in comments.items() if k in expected},
        missing_ids=sorted(expected - comments.keys()),
        extra_ids=sorted(comments.keys() - expected),
        duplicate_ids=sorted(k for k, n in seen.items() if n > 1),
    )
    return result


# --------------------------------------------------------------------------- metrics

_WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")


def tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def shingles(text: str, k: int = 5) -> set[str]:
    t = re.sub(r"\s+", " ", text.lower()).strip()
    return {t[i : i + k] for i in range(max(len(t) - k + 1, 1))}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def text_metrics(rows: list[dict]) -> dict:
    """Metrics over parsed comment rows (each row = spec fields + 'text')."""
    unigrams, bigrams = [], []
    openers: Counter = Counter()
    first_words: Counter = Counter()
    in_band = 0
    band_by_channel: dict[str, list[int]] = {}
    violations = Counter()
    for r in rows:
        toks = tokens(r["text"])
        unigrams += toks
        bigrams += list(zip(toks, toks[1:], strict=False))
        if len(toks) >= 3:
            openers[" ".join(toks[:3])] += 1
        if toks:
            first_words[toks[0]] += 1
        n_words = len(r["text"].split())
        ok = r["min_words"] <= n_words <= r["max_words"]
        in_band += ok
        band_by_channel.setdefault(r["channel"], [0, 0])
        band_by_channel[r["channel"]][0] += ok
        band_by_channel[r["channel"]][1] += 1
        violations["banned_sarcasm_marker"] += bool(BANNED_SARCASM.search(r["text"]))
        violations["mentions_survey_or_rating"] += bool(MENTIONS_SURVEY.search(r["text"]))
        violations["price_or_clock_time"] += bool(PRICE_OR_TIME.search(r["text"]))
        violations["exclamation_opening"] += bool(re.match(r"^[^.?!]{0,40}!", r["text"]))

    sh = {r["id"]: shingles(r["text"]) for r in rows}
    near_dups = [
        {"id_a": a, "id_b": b, "jaccard": round(j, 3)}
        for a, b in combinations(sorted(sh), 2)
        if (j := jaccard(sh[a], sh[b])) > 0.6
    ]
    n = len(rows)
    return {
        "n_comments": n,
        "length_compliance": round(in_band / n, 3) if n else None,
        "length_compliance_by_channel": {
            ch: {"in_band": v[0], "n": v[1], "rate": round(v[0] / v[1], 3)}
            for ch, v in sorted(band_by_channel.items())
        },
        "mean_words": round(sum(len(r["text"].split()) for r in rows) / n, 1) if n else None,
        "distinct_1": round(len(set(unigrams)) / len(unigrams), 4) if unigrams else None,
        "distinct_2": round(len(set(bigrams)) / len(bigrams), 4) if bigrams else None,
        "top_repeated_3word_openers": [
            {"opener": o, "count": c} for o, c in openers.most_common(10) if c > 1
        ],
        "distinct_first_words": len(first_words),
        "top_first_words": [
            {"word": w, "count": c} for w, c in first_words.most_common(5) if c > 1
        ],
        "near_duplicate_pairs": near_dups,
        "rule_violations": dict(violations),
    }


# --------------------------------------------------------------------------- API


def _status_code(exc: Exception) -> int | None:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    return code if isinstance(code, int) else None


def call_model(client, model: str, prompt: str, config) -> dict:
    """One request with exponential backoff + full jitter on 429/500/503."""
    retries = Counter()
    attempt = 0
    while True:
        t0 = time.perf_counter()
        try:
            resp = client.models.generate_content(model=model, contents=prompt, config=config)
            return {
                "response": resp,
                "latency_s": round(time.perf_counter() - t0, 2),
                "retries": dict(retries),
                "error": None,
            }
        except Exception as exc:  # SDK raises ClientError/ServerError with .code
            code = _status_code(exc)
            if code not in RETRYABLE_CODES or attempt >= MAX_RETRIES:
                return {
                    "response": None,
                    "latency_s": round(time.perf_counter() - t0, 2),
                    "retries": dict(retries),
                    "error": f"{type(exc).__name__} {code}",
                }
            retries[str(code)] += 1
            delay = random.uniform(0, min(BACKOFF_CAP_S, BACKOFF_BASE_S * 2**attempt))
            print(f"    {code}; retry {attempt + 1}/{MAX_RETRIES} in {delay:.1f}s")
            time.sleep(delay)
            attempt += 1


def make_client_and_config():
    from dotenv import load_dotenv
    from google import genai
    from google.genai import types

    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    key = os.environ.get("GOOGLE_AI_API_KEY")
    if not key:
        sys.exit("GOOGLE_AI_API_KEY is not set (see .env.example)")
    config = types.GenerateContentConfig(
        temperature=TEMPERATURE,
        response_mime_type=RESPONSE_MIME_TYPE,
        thinking_config=types.ThinkingConfig(thinking_level=THINKING_LEVEL),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    return genai.Client(api_key=key), config


# --------------------------------------------------------------------------- review sheet


def select_review_ids(specs: list[dict], available: set[int], seed: int = SEED) -> list[int]:
    """Stratified spec ids for blind review; within each stratum alternate incident/none."""
    rng = random.Random(seed + 1)
    chosen = []
    for (style, sentiment), n in REVIEW_QUOTAS.items():
        pool = [
            s
            for s in specs
            if s["style"] == style and s["sentiment"] == sentiment and s["id"] in available
        ]
        inc = [s["id"] for s in pool if s["incident_type"]]
        clean = [s["id"] for s in pool if not s["incident_type"]]
        rng.shuffle(inc)
        rng.shuffle(clean)
        picks = []
        while len(picks) < n and (inc or clean):
            src = inc if (len(picks) % 2 == 0 and inc) or not clean else clean
            picks.append(src.pop())
        chosen += picks
    return chosen


def write_review(out: Path, specs: list[dict], comments: dict[str, dict[int, str]]) -> dict:
    by_id = {s["id"]: s for s in specs}
    available = set.intersection(*(set(c) for c in comments.values()))
    ids = select_review_ids(specs, available)
    rows = [(m, i) for m in comments for i in ids]
    random.Random(SEED + 2).shuffle(rows)
    with (
        (out / "review_blind.csv").open("w", newline="", encoding="utf-8") as fb,
        (out / "review_key.csv").open("w", newline="", encoding="utf-8") as fk,
    ):
        wb, wk = csv.writer(fb), csv.writer(fk)
        wb.writerow(
            ["review_id", "text", "my_sentiment", "believable_1to3", "sounds_ai_yn", "notes"]
        )
        wk.writerow(
            [
                "review_id",
                "model",
                "spec_id",
                "intended_sentiment",
                "style",
                "incident_severity",
                "incident_type",
                "channel",
            ]
        )
        for k, (m, i) in enumerate(rows, 1):
            rid = f"R{k:02d}"
            s = by_id[i]
            wb.writerow([rid, comments[m][i], "", "", "", ""])
            wk.writerow(
                [
                    rid,
                    m,
                    i,
                    s["sentiment"],
                    s["style"],
                    s["incident_severity"] or "",
                    s["incident_type"] or "",
                    s["channel"],
                ]
            )
    return {
        "n_rows": len(rows),
        "per_model": len(ids),
        "incident_specs": sum(1 for i in ids if by_id[i]["incident_type"]),
    }


# --------------------------------------------------------------------------- main


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="write specs + prompt, no API calls")
    ap.add_argument("--out-date", default=date.today().isoformat())
    args = ap.parse_args()

    specs = build_specs()
    out = OUT_ROOT / args.out_date
    out.mkdir(parents=True, exist_ok=True)
    (out / "prompt.txt").write_text(PROMPT_V0, encoding="utf-8")
    write_jsonl(out / "specs.jsonl", specs)
    mix = Counter((s["style"], s["sentiment"]) for s in specs)
    n_inc = sum(1 for s in specs if s["incident_type"])
    print(f"specs: {len(specs)} ({len(mix)} style/sentiment cells), incidents: {n_inc}")
    if args.dry_run:
        prompt_words = len(render_prompt(batches(specs)[0]).split())
        print(f"dry run: batch-1 prompt ~{prompt_words} words; wrote {out}")
        return

    import google.genai

    client, config = make_client_and_config()
    settings = {
        "run_date": args.out_date,
        "models": MODELS,
        "sdk": f"google-genai {google.genai.__version__}",
        "python": sys.version.split()[0],
        "seed": SEED,
        "n_specs": len(specs),
        "batch_size": BATCH_SIZE,
        "prompt_version": "v0",
        "prompt_delivery": "single user turn (no system_instruction), identical for both models",
        "generation_config": {
            "temperature": TEMPERATURE,
            "response_mime_type": RESPONSE_MIME_TYPE,
            "response_schema": None,
            "thinking_config": {"thinking_level": THINKING_LEVEL},
            "automatic_function_calling": "disabled",
            "other params": "API defaults (top_p, top_k, max_output_tokens unset)",
        },
        "retry_policy": {
            "retry_on": sorted(RETRYABLE_CODES),
            "max_retries": MAX_RETRIES,
            "backoff": f"full jitter, uniform(0, min({BACKOFF_CAP_S}, {BACKOFF_BASE_S}*2^n)) s",
        },
        "requests": "sequential; model by model, batch order 1-5",
        "feature_probe_2026_09_23": {
            "gemma-4-31b-it": {
                "system_instruction": "supported",
                "response_mime_type_json": "supported",
                "response_schema": "unverified: 1 success, 4 x HTTP 500 on probe",
                "thinking_default": "on (~90-700 thought tokens per probe call)",
                "thinking_level": "'minimal' (no thought tokens) and 'high' accepted; "
                "'low' -> 400 not supported",
                "thinking_budget": "400 not supported",
                "reliability": "frequent transient 500/503 on probe calls",
            },
            "gemini-3.5-flash-lite": {
                "system_instruction": "supported",
                "response_mime_type_json": "supported",
                "response_schema": "supported",
                "thinking_default": "no thought tokens observed at default (3 probe prompts) "
                "- behaves as 'minimal'; set explicitly anyway",
                "thinking_level": "minimal/low/medium/high accepted",
                "thinking_budget": "0 -> 400 invalid argument",
            },
            "fairness_note": "both features used are supported by both models; schema omitted "
            "because it could not be verified on Gemma. Parser tolerates "
            "fenced/embedded JSON for both.",
        },
    }
    (out / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")

    metrics: dict = {}
    all_comments: dict[str, dict[int, str]] = {}
    for model in MODELS:
        print(f"\n== {model}")
        raw_rows, comment_rows, requests = [], [], []
        comments: dict[int, str] = {}
        batch_results = []
        for b, batch in enumerate(batches(specs), 1):
            ids = [s["id"] for s in batch]
            res = call_model(client, model, render_prompt(batch), config)
            resp = res["response"]
            usage = resp.usage_metadata if resp is not None else None
            req = {
                "batch": b,
                "latency_s": res["latency_s"],
                "retries": res["retries"],
                "error": res["error"],
                "input_tokens": getattr(usage, "prompt_token_count", None),
                "output_tokens": getattr(usage, "candidates_token_count", None),
                "thought_tokens": getattr(usage, "thoughts_token_count", None),
                "finish_reason": (
                    str(resp.candidates[0].finish_reason)
                    if resp is not None and resp.candidates
                    else None
                ),
            }
            parsed = parse_response(resp.text if resp is not None else None, ids)
            req.update(
                parse_ok=parsed["ok"],
                n_parsed=len(parsed["comments"]),
                missing_ids=parsed["missing_ids"],
                extra_ids=parsed["extra_ids"],
                duplicate_ids=parsed["duplicate_ids"],
                parse_error=parsed["error"],
            )
            requests.append(req)
            raw_rows.append(
                {
                    "batch": b,
                    "spec_ids": ids,
                    **{k: req[k] for k in ("latency_s", "retries", "error")},
                    "response": resp.model_dump(mode="json") if resp else None,
                }
            )
            comments.update(parsed["comments"])
            batch_results.append(parsed)
            print(
                f"  batch {b}/5: {'ok' if parsed['ok'] else 'FAIL'} "
                f"{len(parsed['comments'])}/{len(ids)} comments, "
                f"in={req['input_tokens']} out={req['output_tokens']} "
                f"think={req['thought_tokens']} {req['latency_s']}s retries={req['retries']}"
            )

        for s in specs:
            if s["id"] in comments:
                comment_rows.append({**s, "text": comments[s["id"]]})
        write_jsonl(out / f"raw_{model}.jsonl", raw_rows)
        write_jsonl(out / f"comments_{model}.jsonl", comment_rows)
        all_comments[model] = comments

        retry_totals = Counter()
        for r in requests:
            retry_totals.update(r["retries"])
        metrics[model] = {
            "parse_success_rate": sum(p["ok"] for p in batch_results) / len(batch_results),
            "comments_returned": len(comments),
            "comments_expected": len(specs),
            "count_mismatch_batches": sum(
                1 for r in requests if r["missing_ids"] or r["extra_ids"] or r["duplicate_ids"]
            ),
            "retries_429": retry_totals.get("429", 0),
            "retries_5xx": retry_totals.get("500", 0) + retry_totals.get("503", 0),
            "failed_requests": sum(1 for r in requests if r["error"]),
            **text_metrics(comment_rows),
            "requests": requests,
        }

    review = write_review(out, specs, all_comments)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    print("\n== summary")
    for model, m in metrics.items():
        lat = [r["latency_s"] for r in m["requests"] if not r["error"]]
        mean_lat = f"{sum(lat) / len(lat):.1f}s" if lat else "n/a"
        print(
            f"  {model}: parse {m['parse_success_rate']:.0%}, "
            f"{m['comments_returned']}/{m['comments_expected']} comments, "
            f"mismatch batches {m['count_mismatch_batches']}, "
            f"length ok {m['length_compliance']}, d1 {m['distinct_1']} d2 {m['distinct_2']}, "
            f"repeated openers {len(m['top_repeated_3word_openers'])}, "
            f"near-dups {len(m['near_duplicate_pairs'])}, "
            f"429s {m['retries_429']} 5xx {m['retries_5xx']}, "
            f"mean latency {mean_lat}"
        )
    print(f"  review sheet: {review}")
    print(f"  wrote {out}")


if __name__ == "__main__":
    main()
