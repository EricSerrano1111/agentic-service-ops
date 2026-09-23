"""Prompt v2: targeted rerun on the cells v1 got wrong (neutral, positive + serious incident,
mixed + incident), with operational label definitions shared by generator and judge.

Flash-Lite generates 60 seeded specs (3 batches of 20); Gemma judges every comment from its
text alone. Writes to data/generator/experiments/bakeoff/<YYYY-MM-DD>-v2/.

Still an experiment, not build_corpus.py. Prints summaries only, never comment text.

Usage:
    python data/generator/experiments/prompt_v2_trial.py            # full run
    python data/generator/experiments/prompt_v2_trial.py --dry-run  # specs + prompts, no API
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import model_bakeoff as v0  # noqa: E402 — sibling modules; reuse parser, metrics, retry loop
import prompt_v1_trial as v1  # noqa: E402

SEED = 20260925
GEN_MODEL = v1.GEN_MODEL
JUDGE_MODEL = v1.JUDGE_MODEL
BATCH_SIZE = 20

OPENINGS = ["outcome first", "problem first", "time reference", "sentence fragment", "question"]
NEUTRAL_KINDS = {"minimal": 7, "administrative": 7, "status": 6}
POSITIVE_INCIDENT_NOTE = (
    "Mention the problem briefly and without blame. Make the recovery and the writer's "
    "satisfaction the point. No lingering complaint."
)

# Spec groups. Each entry: (group, sentiment, style, incident severity or None, count).
# "split" = mixed target, 4 minor / 4 serious; "half" = negative distractors, half with incidents.
SPEC_PLAN = [
    ("neutral", "neutral", "plain", None, 20),
    ("positive_serious", "positive", "plain", "serious", 6),
    ("positive_serious", "positive", "implicit", "serious", 4),
    ("mixed_incident", "mixed", "plain", "split", 6),
    ("mixed_incident", "mixed", "sarcastic", "split", 2),
    ("distractor", "positive", "plain", None, 6),
    ("distractor", "positive", "implicit", None, 4),
    ("distractor", "negative", "plain", "half", 4),
    ("distractor", "negative", "implicit", "half", 2),
    ("distractor", "negative", "sarcastic", "half", 2),
    ("distractor", "mixed", "plain", None, 4),
]
TARGET_GROUPS = ["neutral", "positive_serious", "mixed_incident"]

# Blind review: 24 rows, (group, sub-stratum) -> n. Sub-stratum is the neutral kind, the
# style for the two incident targets, and the sentiment for distractors.
REVIEW_QUOTAS = {
    ("neutral", "minimal"): 4,
    ("neutral", "administrative"): 3,
    ("neutral", "status"): 3,
    ("positive_serious", "plain"): 4,
    ("positive_serious", "implicit"): 2,
    ("mixed_incident", "plain"): 3,
    ("mixed_incident", "sarcastic"): 1,
    ("distractor", "positive"): 1,
    ("distractor", "negative"): 2,
    ("distractor", "mixed"): 1,
}

PASS_CRITERIA = {
    "judge neutral >= 14/20": ("neutral", 14),
    "judge positive + serious incident >= 7/10": ("positive_serious", 7),
    "judge mixed + incident >= 6/8": ("mixed_incident", 6),
}

LABEL_DEFINITIONS = """\
- positive: the writer's overall verdict is satisfied. A problem may be mentioned if
  it was resolved and the writer ends satisfied.
- negative: the writer's overall verdict is dissatisfied.
- mixed: the writer's verdict is divided: at least one aspect is still criticized or
  unresolved, and another is praised.
- neutral: the comment is one of these three kinds, and nothing else:
  (a) minimal or indifferent ("fine", "it's done", "no comments");
  (b) administrative or off-topic (where to send the invoice, a question about the
      next visit, a note for the office);
  (c) status without a verdict: the outcome is not known yet ("installed, we'll see
      Monday if it holds").
  A visit described as having gone well or having worked is positive, however flatly
  it is worded."""

PROMPT_V2 = f"""\
You are writing realistic post-visit survey comments from customers of a field service
company that sends technicians to install, repair, maintain, inspect, and upgrade
business network and hardware equipment (switches, routers, access points, cabling,
servers, security cameras, UPS units).

Write one comment per spec. Each spec gives the sentiment the writer means, a style,
the visit context, the channel and length, and who is writing.

Definitions:
{LABEL_DEFINITIONS}
- sarcastic: Deadpan or understated, not effusive: the wording is mildly approving or
  matter-of-fact, and a concrete detail shows the real meaning. Avoid exaggerated praise
  (thrilled, amazing, love that). Do not signal sarcasm with "/s", "Oh great",
  "Wow, just wow", scare quotes, or exclamation-heavy openings.
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
- No greetings or sign-offs (e.g. 'To whom it may concern', 'Hi team', 'Thanks, …').
  Most real comments are one or two plain, unpolished sentences.
- No personal names, company names, dates, times, prices, or ticket numbers.
- Do not mention the survey or a rating.
- Output only JSON: an array of {{"id": <spec id>, "text": "<comment>"}}, one per spec,
  in spec order.

Specs:
{{numbered spec lines}}
"""

JUDGE_PROMPT_V2 = f"""\
You are labeling post-visit comments from customers of a field service company that sends
technicians to install, repair, maintain, inspect, and upgrade business network and
hardware equipment.

For each comment, label the writer's intended overall sentiment: exactly one of positive,
neutral, negative, or mixed.

Definitions:
{LABEL_DEFINITIONS}

Output only JSON: an array of {{"id": <comment id>, "label": "<label>"}}, one per comment,
in comment order.

Comments:
{{numbered comments}}
"""

GREETING = re.compile(
    r"^\W*(?:hi|hello|hey|dear|greetings|good (?:morning|afternoon|evening)"
    r"|to whom it may concern|to (?:the|your|our) (?:team|company|crew|office)|team\s*[,:])\b",
    re.IGNORECASE,
)
SIGN_OFF = re.compile(
    r"(?:^|[.!?]\s+)(?:thanks|thank you|many thanks|regards|best regards|kind regards"
    r"|cheers|sincerely)(?:[,!.]?\s+\w+)?[.!]?\s*$",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- specs


def build_specs(seed: int = SEED) -> list[dict]:
    rng = random.Random(seed)
    specs: list[dict] = []
    for group, sentiment, style, sev, n in SPEC_PLAN:
        specs += [
            {"group": group, "sentiment": sentiment, "style": style, "_sev": sev} for _ in range(n)
        ]
    rng.shuffle(specs)

    # Resolve severities: mixed target 4 minor / 4 serious; negative distractors half with
    # incidents (2 minor / 2 serious).
    mixed_t = [s for s in specs if s["_sev"] == "split"]
    for k, s in enumerate(rng.sample(mixed_t, len(mixed_t))):
        s["_sev"] = "minor" if k < len(mixed_t) // 2 else "serious"
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

    out = []
    for i, s in enumerate(specs):
        sev = s["_sev"]
        channel = rng.choice(list(v0.CHANNEL_BANDS))
        lo, hi = v0.CHANNEL_BANDS[channel]
        out.append(
            {
                "id": i + 1,
                "group": s["group"],
                "sentiment": s["sentiment"],
                "style": s["style"],
                "neutral_kind": next(neutral_iter) if s["sentiment"] == "neutral" else None,
                "service_type": None if sev else service_for[i],
                "incident_severity": sev,
                "incident_type": rng.choice(list(v0.INCIDENT_PHRASES)) if sev else None,
                "channel": channel,
                "min_words": lo,
                "max_words": hi,
                "writer": rng.choice(v0.WRITERS),
                "focus": rng.choice(v1.FOCUSES),
                "opening": rng.choice(OPENINGS),
            }
        )
    return out


def spec_line(s: dict) -> str:
    line = v0.spec_line(s)
    if s["neutral_kind"]:
        line += f"; neutral kind: {s['neutral_kind']}"
    line += f"; focus: {s['focus']}; opening: {s['opening']}"
    if s["sentiment"] == "positive" and s["incident_type"]:
        line += f"; note: {POSITIVE_INCIDENT_NOTE}"
    return line


def render_prompt(batch: list[dict]) -> str:
    return PROMPT_V2.replace("{numbered spec lines}", "\n".join(spec_line(s) for s in batch))


def render_judge_prompt(items: list[tuple[int, str]]) -> str:
    lines = "\n".join(f"{i}. {' '.join(t.split())}" for i, t in items)
    return JUDGE_PROMPT_V2.replace("{numbered comments}", lines)


def substratum(s: dict) -> str:
    if s["group"] == "neutral":
        return s["neutral_kind"]
    if s["group"] == "distractor":
        return s["sentiment"]
    return s["style"]


def greeting_or_signoff(text: str) -> bool:
    return bool(GREETING.search(text) or SIGN_OFF.search(text.strip()))


# --------------------------------------------------------------------------- review


def select_review_ids(specs: list[dict], available: set[int], seed: int) -> list[int]:
    rng = random.Random(seed)
    chosen = []
    for (group, sub), n in REVIEW_QUOTAS.items():
        pool = [
            s["id"]
            for s in specs
            if s["group"] == group and substratum(s) == sub and s["id"] in available
        ]
        chosen += rng.sample(pool, min(n, len(pool)))
    rng.shuffle(chosen)
    return chosen


def write_review(out: Path, specs: list[dict], comments: dict, judge: dict) -> dict:
    by_id = {s["id"]: s for s in specs}
    ids = select_review_ids(specs, set(comments), SEED + 1)
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
                "group",
                "intended_sentiment",
                "style",
                "neutral_kind",
                "incident_severity",
                "incident_type",
                "channel",
                "focus",
                "opening",
                "judge_label",
            ]
        )
        for k, i in enumerate(ids, 1):
            s = by_id[i]
            wb.writerow([f"R{k:02d}", comments[i], "", "", "", ""])
            wk.writerow(
                [
                    f"R{k:02d}",
                    GEN_MODEL,
                    i,
                    s["group"],
                    s["sentiment"],
                    s["style"],
                    s["neutral_kind"] or "",
                    s["incident_severity"] or "",
                    s["incident_type"] or "",
                    s["channel"],
                    s["focus"],
                    s["opening"],
                    judge.get(i, ""),
                ]
            )
    return {"n_rows": len(ids)}


# --------------------------------------------------------------------------- main


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out-date", default=date.today().isoformat())
    args = ap.parse_args()

    specs = build_specs()
    out = v0.OUT_ROOT / f"{args.out_date}-v2"
    out.mkdir(parents=True, exist_ok=True)
    (out / "prompt_v2.txt").write_text(PROMPT_V2, encoding="utf-8")
    (out / "judge_prompt_v2.txt").write_text(JUDGE_PROMPT_V2, encoding="utf-8")
    v0.write_jsonl(out / "specs.jsonl", specs)
    print(f"specs: {len(specs)}, incidents: {sum(bool(s['incident_type']) for s in specs)}")
    if args.dry_run:
        print(f"dry run: wrote {out}")
        return

    import google.genai
    from google.genai import types

    client, gen_config = v0.make_client_and_config()  # same generation settings as v0/v1
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
        "openings": OPENINGS,
        "positive_incident_note": "appended to the spec line of positive specs with an incident",
        "generation": {
            "model": GEN_MODEL,
            "prompt_version": "v2 (derived from v1 in bakeoff/2026-09-23-v1/prompt_v1.txt)",
            "prompt_delivery": "single user turn, no system_instruction",
            "batch_size": BATCH_SIZE,
            "temperature": v0.TEMPERATURE,
            "response_mime_type": v0.RESPONSE_MIME_TYPE,
            "response_schema": None,
            "thinking_level": v0.THINKING_LEVEL,
        },
        "judge": {
            "model": JUDGE_MODEL,
            "prompt_version": "judge v2 (v1 judge prompt, definitions replaced)",
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
        c = {}
        for r in rows:
            if pred(r):
                lab = labels.get(r["id"]) or "missing"
                c[lab] = c.get(lab, 0) + 1
        return c

    groups = {
        "neutral": {
            "all": agr(lambda r: r["group"] == "neutral"),
            "by_kind": {k: agr(lambda r, k=k: r["neutral_kind"] == k) for k in NEUTRAL_KINDS},
            "judged_as": judged(lambda r: r["group"] == "neutral"),
        },
        "positive_serious": {
            "all": agr(lambda r: r["group"] == "positive_serious"),
            "judged_as": judged(lambda r: r["group"] == "positive_serious"),
        },
        "mixed_incident": {
            "all": agr(lambda r: r["group"] == "mixed_incident"),
            "judged_as": judged(lambda r: r["group"] == "mixed_incident"),
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
    openers["greeting_or_signoff"] = [r["id"] for r in rows if greeting_or_signoff(r["text"])]
    tm = v0.text_metrics(rows)

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
        print(f"  {g:22} {d['all']['agree']}/{d['all']['n']}   judged as {d.get('judged_as', '')}")
        for sub, a in {**d.get("by_kind", {}), **d.get("by_sentiment", {})}.items():
            print(f"    {sub:20} {a['agree']}/{a['n']}")
    print(
        f"\n== text: mean words {tm['mean_words']}, length ok {tm['length_compliance']}, "
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
