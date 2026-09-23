"""Prompt v3: final iteration under the stop rule. Fixes v2's two failures — the minimal-neutral
length conflict and the mixed/negative overlap — and tightens the spec rules.

Flash-Lite generates 60 seeded specs (3 batches of 20); Gemma judges every comment from its
text alone. Writes to data/generator/experiments/bakeoff/<YYYY-MM-DD>-v3/.

Still an experiment, not build_corpus.py. Prints summaries only, never comment text.

Usage:
    python data/generator/experiments/prompt_v3_trial.py            # full run
    python data/generator/experiments/prompt_v3_trial.py --dry-run  # specs + prompts, no API
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import model_bakeoff as v0  # noqa: E402 — sibling modules; reuse parser, metrics, retry loop
import prompt_v1_trial as v1  # noqa: E402
import prompt_v2_trial as v2  # noqa: E402

SEED = 20260926
GEN_MODEL = v1.GEN_MODEL
JUDGE_MODEL = v1.JUDGE_MODEL
BATCH_SIZE = 20

NEUTRAL_KINDS = v2.NEUTRAL_KINDS  # minimal 7, administrative 7, status 6
MINIMAL_BAND = (1, 8)  # overrides the channel band for minimal neutrals
OPENINGS = v2.OPENINGS
QUESTION = "question"
POSITIVE_INCIDENT_NOTE = v2.POSITIVE_INCIDENT_NOTE
ADMIN_NOTE = (
    "An administrative note is a request or a piece of information, never a dispute or a "
    "correction. Do not use words like wrong, again, still, missing, or incorrect."
)

# (group, sentiment, style, severity, count). Severity: None, "minor", "serious", or
# "half" = negative distractors, half with incidents (split minor / serious).
SPEC_PLAN = [
    ("neutral", "neutral", "plain", None, 20),
    ("positive_serious", "positive", "plain", "serious", 6),
    ("positive_serious", "positive", "implicit", "serious", 4),
    ("mixed_incident", "mixed", "plain", "minor", 8),
    ("distractor", "positive", "plain", None, 6),
    ("distractor", "positive", "implicit", None, 4),
    ("distractor", "negative", "plain", "half", 2),
    ("distractor", "negative", "implicit", "half", 2),
    ("distractor", "negative", "sarcastic", "half", 4),
    ("distractor", "mixed", "plain", None, 4),
]

REVIEW_QUOTAS = {
    ("neutral", "minimal"): 4,
    ("neutral", "administrative"): 3,
    ("neutral", "status"): 3,
    ("positive_serious", "plain"): 4,
    ("positive_serious", "implicit"): 2,
    ("mixed_incident", "plain"): 4,
    ("distractor", "positive"): 1,
    ("distractor", "negative"): 2,
    ("distractor", "mixed"): 1,
}

PASS_CRITERIA = {
    "judge neutral >= 14/20": ("neutral", 14),
    "judge positive + serious incident >= 7/10": ("positive_serious", 7),
    "judge mixed + minor incident >= 6/8": ("mixed_incident", 6),
}

MIXED_V2 = """\
- mixed: the writer's verdict is divided: at least one aspect is still criticized or
  unresolved, and another is praised."""
MIXED_V3 = """\
- mixed: the writer praises at least one aspect and criticizes at least one other,
  and neither dominates. If the criticism clearly outweighs the praise, the comment
  is negative; if the praise clearly outweighs a minor, resolved gripe, it is positive."""
assert MIXED_V2 in v2.LABEL_DEFINITIONS
LABEL_DEFINITIONS = v2.LABEL_DEFINITIONS.replace(MIXED_V2, MIXED_V3)

INCIDENT_V2 = """\
- If the spec has an incident, the comment should relate to that problem. A serious
  problem can still get a positive or neutral comment if it was handled well."""
INCIDENT_V3 = "- If the spec has an incident, the comment should relate to that problem."
assert INCIDENT_V2 in v2.PROMPT_V2

PROMPT_V3 = v2.PROMPT_V2.replace(v2.LABEL_DEFINITIONS, LABEL_DEFINITIONS).replace(
    INCIDENT_V2, INCIDENT_V3
)
JUDGE_PROMPT_V3 = v2.JUDGE_PROMPT_V2.replace(v2.LABEL_DEFINITIONS, LABEL_DEFINITIONS)


# --------------------------------------------------------------------------- specs


def check_spec_rules(s: dict) -> list[str]:
    """Return every spec rule this spec breaks (empty = valid)."""
    bad = []
    if s["sentiment"] == "neutral" and (s["incident_type"] or s["style"] != "plain"):
        bad.append("neutral must be plain with no incident")
    if s["sentiment"] == "mixed" and (
        s["style"] != "plain" or s["incident_severity"] not in (None, "minor")
    ):
        bad.append("mixed must be plain with no incident or a minor one")
    if s["style"] == "sarcastic" and s["sentiment"] != "negative":
        bad.append("sarcastic is negative only")
    if s["style"] == "implicit" and s["sentiment"] not in ("positive", "negative"):
        bad.append("implicit is positive/negative only")
    if s["opening"] == QUESTION and not (
        s["sentiment"] == "negative" or s["neutral_kind"] == "administrative"
    ):
        bad.append("question opening only for negative or administrative neutral")
    return bad


def build_specs(seed: int = SEED) -> list[dict]:
    rng = random.Random(seed)
    specs: list[dict] = []
    for group, sentiment, style, sev, n in SPEC_PLAN:
        specs += [
            {"group": group, "sentiment": sentiment, "style": style, "_sev": sev} for _ in range(n)
        ]
    rng.shuffle(specs)

    neg_d = [s for s in specs if s["_sev"] == "half"]
    with_inc = rng.sample(neg_d, len(neg_d) // 2)
    for s in neg_d:
        s["_sev"] = None
    for k, s in enumerate(with_inc):
        s["_sev"] = "minor" if k < len(with_inc) // 2 else "serious"

    kinds = [k for k, n in NEUTRAL_KINDS.items() for _ in range(n)]
    rng.shuffle(kinds)
    neutral_iter = iter(kinds)

    no_incident = [i for i, s in enumerate(specs) if s["_sev"] is None]
    service_cycle = v0.SERVICE_TYPES * (len(no_incident) // len(v0.SERVICE_TYPES) + 1)
    service_for = dict(zip(no_incident, service_cycle, strict=False))
    non_question = [o for o in OPENINGS if o != QUESTION]

    out = []
    for i, s in enumerate(specs):
        sev = s["_sev"]
        kind = next(neutral_iter) if s["sentiment"] == "neutral" else None
        channel = rng.choice(list(v0.CHANNEL_BANDS))
        lo, hi = MINIMAL_BAND if kind == "minimal" else v0.CHANNEL_BANDS[channel]
        question_ok = s["sentiment"] == "negative" or kind == "administrative"
        spec = {
            "id": i + 1,
            "group": s["group"],
            "sentiment": s["sentiment"],
            "style": s["style"],
            "neutral_kind": kind,
            "service_type": None if sev else service_for[i],
            "incident_severity": sev,
            "incident_type": rng.choice(list(v0.INCIDENT_PHRASES)) if sev else None,
            "channel": channel,
            "min_words": lo,
            "max_words": hi,
            "writer": rng.choice(v0.WRITERS),
            "focus": rng.choice(v1.FOCUSES),
            "opening": rng.choice(OPENINGS if question_ok else non_question),
        }
        problems = check_spec_rules(spec)
        if problems:
            raise ValueError(f"spec {spec['id']} breaks rules: {problems}")
        out.append(spec)
    return out


def spec_line(s: dict) -> str:
    line = v2.spec_line(s)
    if s["neutral_kind"] == "administrative":
        line += f"; note: {ADMIN_NOTE}"
    return line


def render_prompt(batch: list[dict]) -> str:
    return PROMPT_V3.replace("{numbered spec lines}", "\n".join(spec_line(s) for s in batch))


def render_judge_prompt(items: list[tuple[int, str]]) -> str:
    lines = "\n".join(f"{i}. {' '.join(t.split())}" for i, t in items)
    return JUDGE_PROMPT_V3.replace("{numbered comments}", lines)


# --------------------------------------------------------------------------- review


def select_review_ids(specs: list[dict], available: set[int], seed: int) -> list[int]:
    rng = random.Random(seed)
    chosen = []
    for (group, sub), n in REVIEW_QUOTAS.items():
        pool = [
            s["id"]
            for s in specs
            if s["group"] == group and v2.substratum(s) == sub and s["id"] in available
        ]
        chosen += rng.sample(pool, min(n, len(pool)))
    rng.shuffle(chosen)
    return chosen


def write_review(out: Path, specs: list[dict], comments: dict, judge: dict) -> dict:
    by_id = {s["id"]: s for s in specs}
    ids = select_review_ids(specs, set(comments), SEED + 1)
    cols = [
        "group",
        "intended_sentiment",
        "style",
        "neutral_kind",
        "incident_severity",
        "incident_type",
        "channel",
        "focus",
        "opening",
    ]
    with (
        (out / "review_blind.csv").open("w", newline="", encoding="utf-8") as fb,
        (out / "review_key.csv").open("w", newline="", encoding="utf-8") as fk,
    ):
        wb, wk = csv.writer(fb), csv.writer(fk)
        wb.writerow(
            ["review_id", "text", "my_sentiment", "believable_1to3", "sounds_ai_yn", "notes"]
        )
        wk.writerow(["review_id", "model", "spec_id", *cols, "judge_label"])
        for k, i in enumerate(ids, 1):
            s = {**by_id[i], "intended_sentiment": by_id[i]["sentiment"]}
            wb.writerow([f"R{k:02d}", comments[i], "", "", "", ""])
            wk.writerow([f"R{k:02d}", GEN_MODEL, i, *[s[c] or "" for c in cols], judge.get(i, "")])
    return {"n_rows": len(ids)}


# --------------------------------------------------------------------------- main


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out-date", default=date.today().isoformat())
    args = ap.parse_args()

    specs = build_specs()
    out = v0.OUT_ROOT / f"{args.out_date}-v3"
    out.mkdir(parents=True, exist_ok=True)
    (out / "prompt_v3.txt").write_text(PROMPT_V3, encoding="utf-8")
    (out / "judge_prompt_v3.txt").write_text(JUDGE_PROMPT_V3, encoding="utf-8")
    v0.write_jsonl(out / "specs.jsonl", specs)
    print(f"specs: {len(specs)}, incidents: {sum(bool(s['incident_type']) for s in specs)}")
    if args.dry_run:
        print(f"dry run: wrote {out}")
        return

    import google.genai
    from google.genai import types

    client, gen_config = v0.make_client_and_config()  # same generation settings as v0-v2
    judge_config = types.GenerateContentConfig(
        temperature=v1.JUDGE_TEMPERATURE,
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
        "spec_plan": [
            {"group": g, "sentiment": se, "style": st, "severity": sev, "n": n}
            for g, se, st, sev, n in SPEC_PLAN
        ],
        "neutral_kinds": NEUTRAL_KINDS,
        "minimal_neutral_band_words": list(MINIMAL_BAND),
        "openings": OPENINGS,
        "question_opening_allowed_for": "negative specs and administrative neutral specs",
        "spec_line_notes": {
            "positive with incident": POSITIVE_INCIDENT_NOTE,
            "administrative neutral": ADMIN_NOTE,
        },
        "generation": {
            "model": GEN_MODEL,
            "prompt_version": "v3 (derived from v2 in bakeoff/2026-09-23-v2/prompt_v2.txt)",
            "prompt_delivery": "single user turn, no system_instruction",
            "batch_size": BATCH_SIZE,
            "temperature": v0.TEMPERATURE,
            "response_mime_type": v0.RESPONSE_MIME_TYPE,
            "response_schema": None,
            "thinking_level": v0.THINKING_LEVEL,
        },
        "judge": {
            "model": JUDGE_MODEL,
            "prompt_version": "judge v3 (v2 judge prompt, mixed definition replaced)",
            "input": "comment text only, no spec fields",
            "batch_size": BATCH_SIZE,
            "temperature": v1.JUDGE_TEMPERATURE,
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
    comments, gen_reqs, gen_raw = v1.run_batches(
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
    labels, judge_reqs, judge_raw = v1.run_batches(
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
        out / "judge_labels.jsonl", [{"id": r["id"], "label": labels.get(r["id"])} for r in rows]
    )

    def agr(pred):
        return v1.agreement([(r["sentiment"], labels.get(r["id"])) for r in rows if pred(r)])

    def judged(pred):
        c: dict[str, int] = {}
        for r in rows:
            if pred(r):
                lab = labels.get(r["id"]) or "missing"
                c[lab] = c.get(lab, 0) + 1
        return c

    def is_mixed(r):
        return r["sentiment"] == "mixed"

    groups = {
        "neutral": {
            "all": agr(lambda r: r["group"] == "neutral"),
            "by_kind": {k: agr(lambda r, k=k: r["neutral_kind"] == k) for k in NEUTRAL_KINDS},
            "judged_as": judged(lambda r: r["group"] == "neutral"),
            "judged_as_by_kind": {
                k: judged(lambda r, k=k: r["neutral_kind"] == k) for k in NEUTRAL_KINDS
            },
        },
        "positive_serious": {
            "all": agr(lambda r: r["group"] == "positive_serious"),
            "judged_as": judged(lambda r: r["group"] == "positive_serious"),
        },
        "mixed_incident": {
            "all": agr(lambda r: r["group"] == "mixed_incident"),
            "judged_as": judged(lambda r: r["group"] == "mixed_incident"),
        },
        "mixed_all": {
            "by_incident": {
                "minor_incident": agr(lambda r: is_mixed(r) and bool(r["incident_type"])),
                "no_incident": agr(lambda r: is_mixed(r) and not r["incident_type"]),
            },
            "judged_as": judged(is_mixed),
        },
        "distractor": {
            "all": agr(lambda r: r["group"] == "distractor"),
            "by_sentiment": {
                se: agr(lambda r, se=se: r["group"] == "distractor" and r["sentiment"] == se)
                for se in ("positive", "negative", "mixed")
            },
        },
    }
    openers = v1.opener_metrics([r["text"] for r in rows])
    openers["greeting_or_signoff"] = [r["id"] for r in rows if v2.greeting_or_signoff(r["text"])]
    tm = v0.text_metrics(rows)
    minimal = [r for r in rows if r["neutral_kind"] == "minimal"]
    minimal_ok = sum(MINIMAL_BAND[0] <= len(r["text"].split()) <= MINIMAL_BAND[1] for r in minimal)

    checks = {}
    for name, (group, need) in PASS_CRITERIA.items():
        a = groups[group]["all"]
        checks[name] = {"value": f"{a['agree']}/{a['n']}", "pass": a["agree"] >= need}
    checks["top first word <= 15%"] = {
        "value": f"{openers['top_first_word']['count']}/{openers['n']}",
        "pass": openers["top_first_word"]["share"] <= 0.15,
    }
    checks["top 3-word opener <= 5%"] = {
        "value": f"{openers['top_3word_opener']['count']}/{openers['n']}",
        "pass": openers["top_3word_opener"]["share"] <= 0.05,
    }
    checks["zero 'The technician' starts"] = {
        "value": str(openers["starts_the_technician"]),
        "pass": openers["starts_the_technician"] == 0,
    }
    checks["zero greetings or sign-offs"] = {
        "value": str(len(openers["greeting_or_signoff"])),
        "pass": not openers["greeting_or_signoff"],
    }

    metrics = {
        "pass_criteria": checks,
        "judge_agreement": {"overall": agr(lambda r: True), "groups": groups},
        "openers": openers,
        "minimal_neutral_in_band": {"ok": minimal_ok, "n": len(minimal)},
        "distinct_1": tm["distinct_1"],
        "distinct_2": tm["distinct_2"],
        "near_duplicate_pairs": tm["near_duplicate_pairs"],
        "length_compliance": tm["length_compliance"],
        "mean_words": tm["mean_words"],
        "rule_violations": v1.rule_violations(rows),
        "v0_rule_checks": tm["rule_violations"],
        "generation_requests": v1.request_summary(gen_reqs),
        "judge_requests": v1.request_summary(judge_reqs),
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    review = write_review(out, specs, comments, labels)

    ja = metrics["judge_agreement"]
    print("\n== judge agreement (judge label vs intended)")
    print(f"  overall                {ja['overall']['agree']}/{ja['overall']['n']}")
    for g, d in groups.items():
        head = f"{d['all']['agree']}/{d['all']['n']}" if "all" in d else ""
        print(f"  {g:22} {head:7} judged as {d.get('judged_as', '')}")
        subs = {**d.get("by_kind", {}), **d.get("by_sentiment", {}), **d.get("by_incident", {})}
        for sub, a in subs.items():
            extra = d.get("judged_as_by_kind", {}).get(sub, "")
            print(f"    {sub:20} {a['agree']}/{a['n']}  {extra}")
    print(
        f"\n== text: mean words {tm['mean_words']}, length ok {tm['length_compliance']}, "
        f"minimal in 1-8 band {minimal_ok}/{len(minimal)}, "
        f"distinct-1 {tm['distinct_1']} distinct-2 {tm['distinct_2']}, "
        f"near-dups {len(tm['near_duplicate_pairs'])}, "
        f"violations {metrics['rule_violations']['counts']} {tm['rule_violations']}"
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
    print("\n== PASS/FAIL")
    for name, c in checks.items():
        print(f"  {'PASS' if c['pass'] else 'FAIL'}  {name:45} {c['value']}")
    print(f"\n  review sheet: {review}; wrote {out}")


if __name__ == "__main__":
    main()
