"""Prompt v1 rerun on Flash-Lite, plus a trial of Gemma 4 as the sentiment-label judge.

Flash-Lite generates 80 seeded comment specs with prompt v1 (4 batches of 20, same settings as
the v0 bake-off). Gemma then labels every comment from its text alone. Writes everything to
data/generator/experiments/bakeoff/<YYYY-MM-DD>-v1/.

Still an experiment, not build_corpus.py. Prints summaries only, never comment text.

Usage:
    python data/generator/experiments/prompt_v1_trial.py            # full run
    python data/generator/experiments/prompt_v1_trial.py --dry-run  # specs + prompts, no API
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import model_bakeoff as v0  # noqa: E402 — sibling module; reuses parser, metrics, retry loop

SEED = 20260924
GEN_MODEL = "gemini-3.5-flash-lite"
JUDGE_MODEL = "gemma-4-31b-it"
JUDGE_TEMPERATURE = 0.0
BATCH_SIZE = 20
SENTIMENTS = ["positive", "neutral", "negative", "mixed"]
STYLES = ["plain", "implicit", "sarcastic"]

FOCUSES = [
    "timeliness",
    "communication beforehand",
    "the fix itself",
    "professionalism",
    "cleanup",
    "scheduling",
    "how things run now",
    "billing",
]
OPENINGS = [
    "outcome first",
    "problem first",
    "time reference",
    "writer's situation",
    "sentence fragment",
    "question",
    "addressed to the company",
]
# Neutral specs never get these: a neutral reaction to them reads as implausible.
NEUTRAL_EXCLUDED_INCIDENTS = {"technician_conduct", "equipment_damage"}

# (style, sentiment) -> count. 80 total.
SPEC_MIX = {
    ("plain", "neutral"): 10,
    ("implicit", "neutral"): 10,
    ("implicit", "positive"): 8,
    ("implicit", "negative"): 7,
    ("sarcastic", "negative"): 12,
    ("sarcastic", "mixed"): 3,
    ("plain", "positive"): 12,
    ("plain", "negative"): 10,
    ("plain", "mixed"): 8,
}
N_NEUTRAL_MINOR = 8  # of the 20 neutral specs
N_SERIOUS_POSITIVE = 8  # "handled well" cases; neutral may not take serious incidents here
N_OTHER_INCIDENTS = 16  # from the remaining non-neutral specs: 8 serious, 8 minor
# Totals: 32 incidents (40%), 16 serious / 16 minor.

# Blind review: 40 of 80, weighted toward the cells this run is testing.
REVIEW_QUOTAS = {
    ("plain", "neutral"): 5,
    ("implicit", "neutral"): 5,
    ("implicit", "positive"): 4,
    ("implicit", "negative"): 4,
    ("sarcastic", "negative"): 6,
    ("sarcastic", "mixed"): 2,
    ("plain", "positive"): 5,
    ("plain", "negative"): 5,
    ("plain", "mixed"): 4,
}

PROMPT_V1 = """\
You are writing realistic post-visit survey comments from customers of a field service
company that sends technicians to install, repair, maintain, inspect, and upgrade
business network and hardware equipment (switches, routers, access points, cabling,
servers, security cameras, UPS units).

Write one comment per spec. Each spec gives the sentiment the writer means, a style,
the visit context, the channel and length, and who is writing.

Definitions:
- mixed: clearly praises one concrete thing and clearly criticizes another; neither dominates.
- neutral: The writer reports what happened, or is indifferent, without judging the
  visit. A smooth visit described approvingly is positive, not neutral. A problem
  mentioned with any annoyance is negative or mixed. Neutral comments about a problem
  state it matter-of-factly.
- sarcastic: Deadpan or understated, not effusive: the wording is mildly approving or
  matter-of-fact, and a concrete detail shows the real meaning. Avoid exaggerated praise
  (thrilled, amazing, love that).
- implicit: the sentiment is real but carried by facts or understatement rather than
  sentiment words. A careful reader should still reach the stated sentiment. A careful
  reader must reach the stated sentiment with confidence. If two careful readers could
  reasonably disagree, the comment is wrong.
- If the spec has an incident, the comment should relate to that problem. A serious
  problem can still get a positive or neutral comment if it was handled well.

Rules:
- Write like real customers: vary openings, sentence length, punctuation, and formality.
  SMS comments are short and may skip capitalization. No two comments may start the
  same way.
- Start each comment as its spec's opening says. Never start with 'The technician'.
- No personal names, company names, dates, times, prices, or ticket numbers.
- Do not mention the survey or a rating.
- Output only JSON: an array of {"id": <spec id>, "text": "<comment>"}, one per spec,
  in spec order.

Specs:
{numbered spec lines}
"""

JUDGE_PROMPT = """\
You are labeling post-visit comments from customers of a field service company that sends
technicians to install, repair, maintain, inspect, and upgrade business network and
hardware equipment.

For each comment, label the writer's intended overall sentiment: exactly one of positive,
neutral, negative, or mixed.

Definitions:
- positive: the writer is satisfied overall with the visit or how it was handled.
- negative: the writer is dissatisfied overall with the visit or how it was handled.
- neutral: The writer reports what happened, or is indifferent, without judging the
  visit. A smooth visit described approvingly is positive, not neutral. A problem
  mentioned with any annoyance is negative or mixed. Neutral comments about a problem
  state it matter-of-factly.
- mixed: clearly praises one concrete thing and clearly criticizes another; neither dominates.

Output only JSON: an array of {"id": <comment id>, "label": "<label>"}, one per comment,
in comment order.

Comments:
{numbered comments}
"""

# Rule-violation heuristics. Name-like = Titlecase word not at a sentence start.
MONEY = re.compile(r"[$€£]\s?\d|\b\d+(?:\.\d+)?\s?(?:dollars|bucks|usd)\b", re.IGNORECASE)
TIME = re.compile(r"\b\d{1,2}:\d{2}\b|\b\d{1,2}\s?(?:a\.?m\.?|p\.?m\.?)(?!\w)", re.IGNORECASE)
MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"
DATE = re.compile(
    rf"\b(?:{MONTHS})\s+\d{{1,2}}\b|\b\d{{1,2}}/\d{{1,2}}(?:/\d{{2,4}})?\b"
    r"|\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"
    r"|\b\d{1,2}(?:st|nd|rd|th)\b",
    re.IGNORECASE,
)
NAME_LIKE = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-z]{1,}\b")
NAME_ALLOW = {"Wi", "Fi", "Ethernet", "PoE"}


# --------------------------------------------------------------------------- specs


def build_specs(seed: int = SEED) -> list[dict]:
    rng = random.Random(seed)
    specs = [{"style": st, "sentiment": se} for (st, se), n in SPEC_MIX.items() for _ in range(n)]
    rng.shuffle(specs)

    idx = {se: [i for i, s in enumerate(specs) if s["sentiment"] == se] for se in SENTIMENTS}
    severity: dict[int, str] = {}
    severity.update({i: "minor" for i in rng.sample(idx["neutral"], N_NEUTRAL_MINOR)})
    severity.update({i: "serious" for i in rng.sample(idx["positive"], N_SERIOUS_POSITIVE)})
    rest = [i for i, s in enumerate(specs) if s["sentiment"] != "neutral" and i not in severity]
    more = rng.sample(rest, N_OTHER_INCIDENTS)
    half = N_OTHER_INCIDENTS // 2
    severity.update({i: ("serious" if k < half else "minor") for k, i in enumerate(more)})

    no_incident = [i for i in range(len(specs)) if i not in severity]
    service_cycle = v0.SERVICE_TYPES * (len(no_incident) // len(v0.SERVICE_TYPES) + 1)
    service_for = dict(zip(no_incident, service_cycle, strict=False))

    all_types = list(v0.INCIDENT_PHRASES)
    neutral_types = [t for t in all_types if t not in NEUTRAL_EXCLUDED_INCIDENTS]
    out = []
    for i, s in enumerate(specs):
        if i in severity:
            pool = neutral_types if s["sentiment"] == "neutral" else all_types
            inc_sev, inc_type, service = severity[i], rng.choice(pool), None
        else:
            inc_sev, inc_type, service = None, None, service_for[i]
        channel = rng.choice(list(v0.CHANNEL_BANDS))
        lo, hi = v0.CHANNEL_BANDS[channel]
        out.append(
            {
                "id": i + 1,
                "sentiment": s["sentiment"],
                "style": s["style"],
                "service_type": service,
                "incident_severity": inc_sev,
                "incident_type": inc_type,
                "channel": channel,
                "min_words": lo,
                "max_words": hi,
                "writer": rng.choice(v0.WRITERS),
                "focus": rng.choice(FOCUSES),
                "opening": rng.choice(OPENINGS),
            }
        )
    return out


def spec_line(s: dict) -> str:
    return f"{v0.spec_line(s)}; focus: {s['focus']}; opening: {s['opening']}"


def render_prompt(batch: list[dict]) -> str:
    return PROMPT_V1.replace("{numbered spec lines}", "\n".join(spec_line(s) for s in batch))


def render_judge_prompt(items: list[tuple[int, str]]) -> str:
    lines = "\n".join(f"{i}. {' '.join(t.split())}" for i, t in items)
    return JUDGE_PROMPT.replace("{numbered comments}", lines)


# --------------------------------------------------------------------------- metrics


def agreement(pairs: list[tuple[str, str | None]]) -> dict:
    n = len(pairs)
    a = sum(intended == got for intended, got in pairs)
    return {"agree": a, "n": n, "rate": round(a / n, 3) if n else None}


def opener_metrics(texts: list[str]) -> dict:
    toks = [v0.tokens(t) for t in texts]
    first = Counter(t[0] for t in toks if t)
    three = Counter(" ".join(t[:3]) for t in toks if len(t) >= 3)
    n = len(texts)
    (fw, fwc), (o3, o3c) = first.most_common(1)[0], three.most_common(1)[0]
    return {
        "n": n,
        "top_first_word": {"word": fw, "count": fwc, "share": round(fwc / n, 3)},
        "top_3word_opener": {"opener": o3, "count": o3c, "share": round(o3c / n, 3)},
        "distinct_first_words": len(first),
        "starts_the_technician": sum(t[:2] == ["the", "technician"] for t in toks),
    }


def rule_violations(rows: list[dict]) -> dict:
    out: dict = {"money": [], "time": [], "date": [], "name_like": []}
    for r in rows:
        t = r["text"]
        if MONEY.search(t):
            out["money"].append(r["id"])
        if TIME.search(t):
            out["time"].append(r["id"])
        if DATE.search(t):
            out["date"].append(r["id"])
        names = [m for m in NAME_LIKE.findall(t) if m not in NAME_ALLOW]
        if names:
            out["name_like"].append({"id": r["id"], "tokens": names})
    counts = {k: len(v) for k, v in out.items()}
    return {"counts": counts, "spec_ids": out}


# --------------------------------------------------------------------------- run


def run_batches(client, model, config, prompts, expected, field, label):
    """Sequential requests; returns (parsed values by id, request records, raw rows)."""
    values, requests, raw = {}, [], []
    for b, (prompt, ids) in enumerate(zip(prompts, expected, strict=True), 1):
        res = v0.call_model(client, model, prompt, config)
        resp = res["response"]
        usage = resp.usage_metadata if resp is not None else None
        parsed = v0.parse_response(resp.text if resp is not None else None, ids, field=field)
        req = {
            "batch": b,
            "latency_s": res["latency_s"],
            "retries": res["retries"],
            "error": res["error"],
            "input_tokens": getattr(usage, "prompt_token_count", None),
            "output_tokens": getattr(usage, "candidates_token_count", None),
            "thought_tokens": getattr(usage, "thoughts_token_count", None),
            "parse_ok": parsed["ok"],
            "n_parsed": len(parsed["comments"]),
            "missing_ids": parsed["missing_ids"],
            "extra_ids": parsed["extra_ids"],
            "duplicate_ids": parsed["duplicate_ids"],
        }
        requests.append(req)
        raw.append(
            {
                "batch": b,
                "ids": ids,
                "latency_s": res["latency_s"],
                "retries": res["retries"],
                "error": res["error"],
                "response": resp.model_dump(mode="json") if resp else None,
            }
        )
        values.update(parsed["comments"])
        print(
            f"  {label} batch {b}/{len(prompts)}: {len(parsed['comments'])}/{len(ids)}, "
            f"in={req['input_tokens']} out={req['output_tokens']} "
            f"{req['latency_s']}s retries={req['retries']}"
        )
    return values, requests, raw


def request_summary(requests: list[dict]) -> dict:
    retries = Counter()
    for r in requests:
        retries.update(r["retries"])
    ok = [r for r in requests if not r["error"]]
    return {
        "requests": len(requests),
        "failed_requests": len(requests) - len(ok),
        "parse_failures": sum(not r["parse_ok"] for r in requests),
        "count_mismatch_batches": sum(
            1 for r in requests if r["missing_ids"] or r["extra_ids"] or r["duplicate_ids"]
        ),
        "retries_429": retries.get("429", 0),
        "retries_5xx": retries.get("500", 0) + retries.get("503", 0),
        "input_tokens_total": sum(r["input_tokens"] or 0 for r in requests),
        "output_tokens_total": sum(r["output_tokens"] or 0 for r in requests),
        "mean_latency_s": round(sum(r["latency_s"] for r in ok) / len(ok), 2) if ok else None,
        "per_request": requests,
    }


def write_review(out: Path, specs: list[dict], comments: dict, judge: dict) -> dict:
    by_id = {s["id"]: s for s in specs}
    ids = v0.select_review_ids(specs, set(comments), seed=SEED + 1, quotas=REVIEW_QUOTAS)
    random.Random(SEED + 2).shuffle(ids)
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
                "focus",
                "opening",
                "judge_label",
            ]
        )
        for k, i in enumerate(ids, 1):
            rid, s = f"R{k:02d}", by_id[i]
            wb.writerow([rid, comments[i], "", "", "", ""])
            wk.writerow(
                [
                    rid,
                    GEN_MODEL,
                    i,
                    s["sentiment"],
                    s["style"],
                    s["incident_severity"] or "",
                    s["incident_type"] or "",
                    s["channel"],
                    s["focus"],
                    s["opening"],
                    judge.get(i, ""),
                ]
            )
    return {"n_rows": len(ids), "incident_specs": sum(bool(by_id[i]["incident_type"]) for i in ids)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out-date", default=date.today().isoformat())
    args = ap.parse_args()

    specs = build_specs()
    out = v0.OUT_ROOT / f"{args.out_date}-v1"
    out.mkdir(parents=True, exist_ok=True)
    (out / "prompt_v1.txt").write_text(PROMPT_V1, encoding="utf-8")
    (out / "judge_prompt.txt").write_text(JUDGE_PROMPT, encoding="utf-8")
    v0.write_jsonl(out / "specs.jsonl", specs)
    print(f"specs: {len(specs)}, incidents: {sum(bool(s['incident_type']) for s in specs)}")
    if args.dry_run:
        print(f"dry run: wrote {out}")
        return

    import google.genai
    from google.genai import types

    client, gen_config = v0.make_client_and_config()  # identical to the v0 run
    judge_config = types.GenerateContentConfig(
        temperature=JUDGE_TEMPERATURE,
        response_mime_type=v0.RESPONSE_MIME_TYPE,
        thinking_config=types.ThinkingConfig(thinking_level=v0.THINKING_LEVEL),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    settings = {
        "run_date": args.out_date,
        "sdk": f"google-genai {google.genai.__version__}",
        "python": sys.version.split()[0],
        "seed": SEED,
        "n_specs": len(specs),
        "spec_mix": {f"{st}/{se}": n for (st, se), n in SPEC_MIX.items()},
        "incident_rules": {
            "neutral_minor": N_NEUTRAL_MINOR,
            "serious_on_positive": N_SERIOUS_POSITIVE,
            "other_incidents": f"{N_OTHER_INCIDENTS} non-neutral, half serious",
            "neutral_excluded_types": sorted(NEUTRAL_EXCLUDED_INCIDENTS),
        },
        "generation": {
            "model": GEN_MODEL,
            "prompt_version": "v1 (derived from v0 in bakeoff/2026-09-23/prompt.txt)",
            "prompt_delivery": "single user turn, no system_instruction",
            "batch_size": BATCH_SIZE,
            "temperature": v0.TEMPERATURE,
            "response_mime_type": v0.RESPONSE_MIME_TYPE,
            "response_schema": None,
            "thinking_level": v0.THINKING_LEVEL,
        },
        "judge": {
            "model": JUDGE_MODEL,
            "input": "comment text only, no spec fields",
            "batch_size": BATCH_SIZE,
            "temperature": JUDGE_TEMPERATURE,
            "response_mime_type": v0.RESPONSE_MIME_TYPE,
            "response_schema": None,
            "thinking_level": v0.THINKING_LEVEL,
        },
        "retry_policy": {
            "retry_on": sorted(v0.RETRYABLE_CODES),
            "max_retries": v0.MAX_RETRIES,
            "backoff": f"full jitter, uniform(0, min({v0.BACKOFF_CAP_S}, "
            f"{v0.BACKOFF_BASE_S}*2^n)) s",
        },
        "requests": "sequential; all generation batches, then all judge batches",
    }
    (out / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")

    print(f"\n== generate ({GEN_MODEL})")
    spec_batches = v0.batches(specs, BATCH_SIZE)
    comments, gen_reqs, gen_raw = run_batches(
        client,
        GEN_MODEL,
        gen_config,
        [render_prompt(b) for b in spec_batches],
        [[s["id"] for s in b] for b in spec_batches],
        "text",
        "gen",
    )
    rows = [{**s, "text": comments[s["id"]]} for s in specs if s["id"] in comments]
    v0.write_jsonl(out / f"raw_{GEN_MODEL}.jsonl", gen_raw)
    v0.write_jsonl(out / f"comments_{GEN_MODEL}.jsonl", rows)

    print(f"\n== judge ({JUDGE_MODEL})")
    items = [(r["id"], r["text"]) for r in rows]
    item_batches = [items[i : i + BATCH_SIZE] for i in range(0, len(items), BATCH_SIZE)]
    labels, judge_reqs, judge_raw = run_batches(
        client,
        JUDGE_MODEL,
        judge_config,
        [render_judge_prompt(b) for b in item_batches],
        [[i for i, _ in b] for b in item_batches],
        "label",
        "judge",
    )
    labels = {k: v.lower() for k, v in labels.items()}
    v0.write_jsonl(out / f"raw_judge_{JUDGE_MODEL}.jsonl", judge_raw)
    v0.write_jsonl(
        out / "judge_labels.jsonl",
        [{"id": r["id"], "label": labels.get(r["id"])} for r in rows],
    )

    pairs = [(r, labels.get(r["id"])) for r in rows]
    confusion = {se: dict.fromkeys([*SENTIMENTS, "invalid_or_missing"], 0) for se in SENTIMENTS}
    for r, got in pairs:
        confusion[r["sentiment"]][got if got in SENTIMENTS else "invalid_or_missing"] += 1

    def agr(pred):
        return agreement([(r["sentiment"], got) for r, got in pairs if pred(r)])

    tm = v0.text_metrics(rows)
    metrics = {
        "judge_agreement": {
            "overall": agr(lambda r: True),
            "by_sentiment": {se: agr(lambda r, se=se: r["sentiment"] == se) for se in SENTIMENTS},
            "by_style": {st: agr(lambda r, st=st: r["style"] == st) for st in STYLES},
            "by_incident": {
                "incident": agr(lambda r: bool(r["incident_type"])),
                "no_incident": agr(lambda r: not r["incident_type"]),
            },
            "confusion_intended_by_judged": confusion,
        },
        "openers": opener_metrics([r["text"] for r in rows]),
        "distinct_1": tm["distinct_1"],
        "distinct_2": tm["distinct_2"],
        "near_duplicate_pairs": tm["near_duplicate_pairs"],
        "length_compliance": tm["length_compliance"],
        "mean_words": tm["mean_words"],
        "rule_violations": rule_violations(rows),
        "v0_rule_checks": tm["rule_violations"],
        "generation_requests": request_summary(gen_reqs),
        "judge_requests": request_summary(judge_reqs),
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    review = write_review(out, specs, comments, labels)

    ja = metrics["judge_agreement"]
    print("\n== judge agreement (judge label vs intended)")
    print(f"  overall      {ja['overall']['agree']}/{ja['overall']['n']}")
    for grp in ("by_sentiment", "by_style", "by_incident"):
        for k, a in ja[grp].items():
            print(f"  {k:12} {a['agree']}/{a['n']}")
    print("  confusion (rows intended, cols judged: pos neu neg mix other)")
    for se, row in confusion.items():
        print(f"    {se:9} " + " ".join(f"{v:3}" for v in row.values()))
    op = metrics["openers"]
    print("\n== openers")
    print(
        f"  top first word share {op['top_first_word']['share']:.0%} "
        f"({op['top_first_word']['count']}/{op['n']}), "
        f"top 3-word opener share {op['top_3word_opener']['share']:.0%} "
        f"({op['top_3word_opener']['count']}/{op['n']}), "
        f"distinct first words {op['distinct_first_words']}, "
        f"'The technician' starts {op['starts_the_technician']}"
    )
    print(
        f"  distinct-1 {tm['distinct_1']} distinct-2 {tm['distinct_2']}, "
        f"near-dups {len(tm['near_duplicate_pairs'])}, "
        f"rule violations {metrics['rule_violations']['counts']}"
    )
    print("\n== errors")
    for name in ("generation_requests", "judge_requests"):
        rs = metrics[name]
        print(
            f"  {name}: failed {rs['failed_requests']}/{rs['requests']}, "
            f"parse failures {rs['parse_failures']}, mismatches {rs['count_mismatch_batches']}, "
            f"429s {rs['retries_429']}, 5xx {rs['retries_5xx']}, "
            f"tokens in/out {rs['input_tokens_total']}/{rs['output_tokens_total']}, "
            f"mean latency {rs['mean_latency_s']}s"
        )
    print(f"\n  review sheet: {review}; wrote {out}")


if __name__ == "__main__":
    main()
