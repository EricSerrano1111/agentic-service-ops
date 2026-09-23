"""Build the frozen feedback_text corpus (ADR-030, ADR-036, ADR-037, ADR-038).

Pipeline, each stage resumable from its own append-only JSONL file:

    specs -> generate (Flash-Lite) -> automated checks -> judge (Gemma) -> select -> top-up

- Specs: every allowed cell in parameters.py gets its required count (Poisson q99 sizing,
  ADR-038). corpus_id is assigned at spec creation ("fb-000001"), never reassigned, and
  continues sequentially through top-ups. Rejected specs simply never reach the corpus.
- Checks reject money, times, dates, name-like tokens, greetings or sign-offs, a
  "The technician" opener, wrong length, exact duplicates, and near-duplicates across the
  WHOLE corpus (5-gram character Jaccard > 0.6, MinHash LSH candidates then exact check).
- Select (ADR-036 decision 7): a plain comment whose judge label differs from its
  intended label is rejected; sarcastic and implicit comments are kept and their
  disagreement recorded for human review.
- Resilience: server errors retried with backoff (cap 10); requests counted per model per
  Pacific-time day, stopping cleanly at 480 Flash-Lite requests; a daily-quota 429 stops
  cleanly. A rerun resumes where it stopped and never repeats a completed batch.

Prints progress summaries only, never comment text (ADR-030, CLAUDE.md).

Usage:
    python data/generator/build_corpus.py --test-batch     # 60-spec quality check
    python data/generator/build_corpus.py --run            # full corpus (resumable)
    python data/generator/build_corpus.py --status         # no API calls
    python data/generator/build_corpus.py --top-up "positive|implicit|serious|missed_sla"
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import re
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parameters as prm  # noqa: E402

HERE = Path(__file__).resolve().parent
PROMPTS = HERE / "prompts"
GEN_PROMPT_PATH = PROMPTS / "generator_v4.txt"
JUDGE_PROMPT_PATH = PROMPTS / "judge_v4.txt"
CORPUS_DIR = HERE / "corpus"
WORK_DIR = CORPUS_DIR / "work"
TEST_ROOT = HERE / "experiments" / "corpus_test"
COUNTER_PATH = WORK_DIR / "request_counts.json"

GEN_MODEL = "gemini-3.5-flash-lite"
JUDGE_MODEL = "gemma-4-31b-it"
GEN_TEMPERATURE = 1.0
JUDGE_TEMPERATURE = 0.0
THINKING_LEVEL = "minimal"
RESPONSE_MIME_TYPE = "application/json"

BATCH_SIZE = prm.PARAMS.corpus.batch_size.value
MAX_RETRIES = 10
BACKOFF_BASE_S = 4.0
BACKOFF_CAP_S = 120.0
RETRYABLE_CODES = {429, 500, 503}
#: Local stop points, below the free-tier limits (ADR-029: 500 and 14.4K RPD).
DAILY_CAP = {GEN_MODEL: 480, JUDGE_MODEL: 14_000}
QUOTA_TZ = ZoneInfo("America/Los_Angeles")  # Gemini daily quotas reset at Pacific midnight

TOPUP_ROUNDS = 3
TOPUP_INFLATION = 1.5
JUDGE_PASSES = 3
#: A generation batch that parses to zero comments is re-requested, up to this many tries.
EMPTY_PARSE_ATTEMPTS = 3

NEAR_DUP_THRESHOLD = 0.6
SHINGLE_K = 5
NUM_PERM = 128

POSITIVE_INCIDENT_NOTE = "Praise how it was handled without naming what went wrong."
MIXED_SERIOUS_NOTE = "Name the problem and praise how it was handled."
ADMIN_NOTE = (
    "An administrative note is a request or a piece of information, never a dispute or a "
    "correction. Do not use words like wrong, again, still, missing, or incorrect."
)

STAGE_TEST_BATCH = "corpus_test_batch"  # test specs only; not a dataset stage


class StopRun(Exception):
    """Clean stop: a daily cap or daily quota was reached. A rerun resumes."""


# --------------------------------------------------------------------------- jsonl


def append_jsonl(path: Path, row: dict) -> None:
    """Append one line durably: a crash leaves at most one partial final line.

    If a previous crash left a partial line without its newline, terminate it first, or
    this row would be glued onto it and lost along with it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    dangling = False
    if path.exists() and path.stat().st_size:
        with path.open("rb") as f:
            f.seek(-1, os.SEEK_END)
            dangling = f.read(1) != b"\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(("\n" if dangling else "") + json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_jsonl(path: Path) -> list[dict]:
    """Read an append-only stage file, skipping a partial line left by a crash."""
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------- workspace


class Workspace:
    """One run's stage files. The full corpus uses corpus/work/; the test batch its own dir."""

    def __init__(self, root: Path):
        self.root = root
        self.specs = root / "specs.jsonl"
        self.generated = root / "generated.jsonl"
        self.checks = root / "checks.jsonl"
        self.judged = root / "judged.jsonl"

    def load_specs(self) -> list[dict]:
        return read_jsonl(self.specs)

    def generated_batches(self) -> dict[str, dict]:
        return {r["batch"]: r for r in read_jsonl(self.generated)}

    def texts(self) -> dict[str, str | None]:
        out: dict[str, str | None] = {}
        for r in read_jsonl(self.generated):
            for cid in r["corpus_ids"]:
                out[cid] = r["texts"].get(cid)
        return out

    def check_results(self) -> dict[str, dict]:
        return {r["corpus_id"]: r for r in read_jsonl(self.checks)}

    def judge_labels(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for r in read_jsonl(self.judged):
            out.update(r["labels"])
        return out


# --------------------------------------------------------------------------- request cap


class RequestCounter:
    """Requests per model per Pacific-time day, persisted so reruns see today's usage."""

    def __init__(self, path: Path = COUNTER_PATH, caps: dict[str, int] | None = None, today=None):
        self.path = path
        self.caps = caps if caps is not None else DAILY_CAP
        self._today = today or (lambda: datetime.now(QUOTA_TZ).date().isoformat())
        self.data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def used(self, model: str) -> int:
        return self.data.get(self._today(), {}).get(model, 0)

    def take(self, model: str) -> None:
        """Count one request, or raise StopRun if today's cap is reached."""
        cap = self.caps.get(model)
        if cap is not None and self.used(model) >= cap:
            raise StopRun(f"{model}: local daily cap {cap} reached ({self._today()} Pacific)")
        day = self.data.setdefault(self._today(), {})
        day[model] = day.get(model, 0) + 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)


def is_daily_quota_error(message: str) -> bool:
    """A 429 whose quota is per day (free-tier RPD), as opposed to per minute."""
    m = message.lower()
    return "perday" in m or "per_day" in m or "per day" in m or "requestsperday" in m


# --------------------------------------------------------------------------- api


class GeminiApi:
    """Real API. `request(model, prompt)` -> {"text", "raw", "latency_s", "retries"}."""

    def __init__(self, counter: RequestCounter):
        from dotenv import load_dotenv
        from google import genai
        from google.genai import types

        load_dotenv(HERE.parents[1] / ".env")
        key = os.environ.get("GOOGLE_AI_API_KEY")
        if not key:
            raise SystemExit("GOOGLE_AI_API_KEY is not set (see .env.example)")
        self.client = genai.Client(api_key=key)
        self.counter = counter

        def config(temperature: float):
            return types.GenerateContentConfig(
                temperature=temperature,
                response_mime_type=RESPONSE_MIME_TYPE,
                thinking_config=types.ThinkingConfig(thinking_level=THINKING_LEVEL),
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            )

        self.configs = {GEN_MODEL: config(GEN_TEMPERATURE), JUDGE_MODEL: config(JUDGE_TEMPERATURE)}

    def request(self, model: str, prompt: str) -> dict:
        retries: Counter = Counter()
        attempt = 0
        while True:
            self.counter.take(model)
            t0 = time.perf_counter()
            try:
                resp = self.client.models.generate_content(
                    model=model, contents=prompt, config=self.configs[model]
                )
                return {
                    "text": resp.text,
                    "raw": resp.model_dump(mode="json"),
                    "latency_s": round(time.perf_counter() - t0, 2),
                    "retries": dict(retries),
                }
            except Exception as exc:  # SDK raises ClientError/ServerError with .code
                code = getattr(exc, "code", None)
                if code == 429 and is_daily_quota_error(str(exc)):
                    raise StopRun(f"{model}: daily quota exhausted (429)") from exc
                if code not in RETRYABLE_CODES or attempt >= MAX_RETRIES:
                    raise
                retries[str(code)] += 1
                delay = random.uniform(0, min(BACKOFF_CAP_S, BACKOFF_BASE_S * 2**attempt))
                print(f"    {model} {code}; retry {attempt + 1}/{MAX_RETRIES} in {delay:.1f}s")
                time.sleep(delay)
                attempt += 1


# --------------------------------------------------------------------------- specs


def cell_key(sentiment: str, style: str, context: str, detail: str) -> str:
    """No-incident cells end in the service type, incident cells in the incident type."""
    return f"{sentiment}|{style}|{context}|{detail}"


def required_by_cell(params: prm.Parameters = prm.PARAMS) -> dict[str, int]:
    return {
        cell_key(
            c["sentiment"], c["style"], c["context"], c["service_type"] or c["incident_type"]
        ): c["required"]
        for c in prm.expected_cell_counts(params)
    }


def _choice(rng: np.random.Generator, options, p=None):
    options = list(options)
    return options[int(rng.choice(len(options), p=p))]


def draw_spec(
    rng: np.random.Generator,
    key: str,
    corpus_id: str,
    round_no: int,
    *,
    params: prm.Parameters = prm.PARAMS,
    channel: str | None = None,
    neutral_kind: str | None = None,
    channels: dict[str, float] | None = None,
) -> dict:
    """One spec for a cell. Draw order is fixed, so a seed reproduces every field."""
    sentiment, style, context, detail = key.split("|")
    cp = params.corpus
    if not prm.is_allowed(sentiment, style, context):
        raise ValueError(f"cell {key} is forbidden by ADR-036")
    kind = None
    if sentiment == "neutral":
        mix = cp.neutral_kind_mix.value
        drawn = _choice(rng, mix, [mix[k] for k in mix])
        kind = neutral_kind or drawn
    mix = channels or dict(params.feedback.channel_mix.value)
    drawn_channel = _choice(rng, mix, [mix[k] / sum(mix.values()) for k in mix])
    channel = channel or drawn_channel
    lo, hi = (
        cp.minimal_neutral_band.value
        if kind == "minimal"
        else cp.length_band_by_channel.value[channel]
    )
    writer = _choice(rng, cp.writers.value)
    focus = _choice(rng, cp.focuses.value)
    question_ok = sentiment == "negative" or kind == "administrative"
    openings = [o for o in cp.openings.value if question_ok or o != "question"]
    opening = _choice(rng, openings)
    if kind == "minimal":
        focus = opening = None
    return {
        "corpus_id": corpus_id,
        "cell": key,
        "sentiment": sentiment,
        "style": style,
        "hard_case_type": prm.HARD_CASE_BY_STYLE[style],
        "context": context,
        "service_type": detail if context == "none" else None,
        "incident_type": detail if context != "none" else None,
        "neutral_kind": kind,
        "channel": channel,
        "min_words": lo,
        "max_words": hi,
        "writer": writer,
        "focus": focus,
        "opening": opening,
        "round": round_no,
    }


def assign_batches(rng: np.random.Generator, specs: list[dict], prefix: str) -> list[dict]:
    """Shuffle across cells, then cut into batches of BATCH_SIZE."""
    order = rng.permutation(len(specs))
    out = []
    for pos, i in enumerate(order):
        s = dict(specs[int(i)])
        s["batch"] = f"{prefix}-b{pos // BATCH_SIZE + 1:04d}"
        out.append(s)
    return out


def format_id(n: int, prefix: str = "fb") -> str:
    return f"{prefix}-{n:06d}"


def next_id_number(specs: list[dict]) -> int:
    return max((int(s["corpus_id"].split("-")[1]) for s in specs), default=0) + 1


def build_full_specs(params: prm.Parameters = prm.PARAMS) -> list[dict]:
    """Round-0 specs: each cell's required count, ids in sorted-cell order, batches shuffled."""
    rng = np.random.default_rng(prm.derive_seed(prm.STAGE_CORPUS_SPECS))
    specs, n = [], 1
    for key, count in sorted(required_by_cell(params).items()):
        for _ in range(count):
            specs.append(draw_spec(rng, key, format_id(n), 0, params=params))
            n += 1
    return assign_batches(rng, specs, "r0")


def build_topup_specs(
    existing: list[dict],
    deficits: dict[str, int],
    round_no: int,
    params: prm.Parameters = prm.PARAMS,
) -> list[dict]:
    """Specs for cells below their required count; ids continue after the highest used."""
    rng = np.random.default_rng(prm.derive_seed(f"{prm.STAGE_CORPUS_SPECS}_topup_{round_no}"))
    n = next_id_number(existing)
    specs = []
    for key in sorted(deficits):
        for _ in range(math.ceil(deficits[key] * TOPUP_INFLATION)):
            specs.append(draw_spec(rng, key, format_id(n), round_no, params=params))
            n += 1
    return assign_batches(rng, specs, f"r{round_no}")


# --------------------------------------------------------------------------- prompts


def load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def prompt_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def spec_line(i: int, s: dict, params: prm.Parameters = prm.PARAMS) -> str:
    if s["incident_type"]:
        phrase = params.corpus.incident_type_phrasing.value[s["incident_type"]]
        context = f"{s['context']} problem: {phrase}"
    else:
        context = f"{s['service_type']} visit"
    parts = [
        f"sentiment: {s['sentiment']}",
        f"style: {s['style']}",
        f"context: {context}",
        f"channel: {s['channel']}, {s['min_words']}-{s['max_words']} words",
        f"writer: {s['writer']}",
    ]
    if s["neutral_kind"]:
        parts.append(f"neutral kind: {s['neutral_kind']}")
    if s["focus"]:
        parts.append(f"focus: {s['focus']}")
    if s["opening"]:
        parts.append(f"opening: {s['opening']}")
    note = None
    if s["sentiment"] == "positive" and s["incident_type"]:
        note = POSITIVE_INCIDENT_NOTE
    elif s["sentiment"] == "mixed" and s["context"] == "serious":
        note = MIXED_SERIOUS_NOTE
    elif s["neutral_kind"] == "administrative":
        note = ADMIN_NOTE
    if note:
        parts.append(f"note: {note}")
    return f"{i}. " + "; ".join(parts)


def render_generator_prompt(template: str, batch: list[dict]) -> str:
    lines = "\n".join(spec_line(i, s) for i, s in enumerate(batch, 1))
    return template.replace("{numbered spec lines}", lines)


def render_judge_prompt(template: str, texts: list[str]) -> str:
    lines = "\n".join(f"{i}. {' '.join(t.split())}" for i, t in enumerate(texts, 1))
    return template.replace("{numbered comments}", lines)


_FENCE = re.compile(r"^\s*```(?:json)?\s*\n?(.*?)\n?\s*```\s*$", re.DOTALL | re.IGNORECASE)


_BARE_KEY = re.compile(r"([{,]\s*)([A-Za-z_]\w*)\s*:")


def _loads_lenient(candidate: str):
    """json.loads, then the outermost [...] slice, then with bare keys quoted.

    Flash-Lite in JSON mode has returned JS-style objects with unquoted keys
    ({ id: 1, text: "..." }); the repair is only tried after strict parsing fails.
    """
    lo, hi = candidate.find("["), candidate.rfind("]")
    sliced = candidate[lo : hi + 1] if 0 <= lo < hi else candidate
    for attempt in (candidate, sliced, _BARE_KEY.sub(r'\1"\2":', sliced)):
        try:
            return json.loads(attempt)
        except json.JSONDecodeError:
            continue
    return None


def parse_array(text: str | None, n: int, field: str) -> dict[int, str]:
    """Parse [{"id": i, field: ...}] into {i: value} for ids 1..n; tolerant of fences."""
    if not text:
        return {}
    candidate = text.strip()
    m = _FENCE.match(candidate)
    if m:
        candidate = m.group(1).strip()
    data = _loads_lenient(candidate)
    if not isinstance(data, list):
        return {}
    out: dict[int, str] = {}
    for item in data:
        if not isinstance(item, dict) or not isinstance(item.get(field), str):
            continue
        try:
            i = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        if 1 <= i <= n and i not in out:
            out[i] = item[field].strip()
    return out


# --------------------------------------------------------------------------- checks

MONEY = re.compile(r"[$€£]\s?\d|\b\d+(?:\.\d+)?\s?(?:dollars|bucks|usd)\b", re.IGNORECASE)
TIME = re.compile(r"\b\d{1,2}:\d{2}\b|\b\d{1,2}\s?(?:a\.?m\.?|p\.?m\.?)(?!\w)", re.IGNORECASE)
_MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"
DATE = re.compile(
    rf"\b(?:{_MONTHS})\s+\d{{1,2}}\b|\b\d{{1,2}}/\d{{1,2}}(?:/\d{{2,4}})?\b"
    r"|\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?\b"
    r"|\b\d{1,2}(?:st|nd|rd|th)\b",
    re.IGNORECASE,
)
#: Titlecase word not at the start of the text or of a sentence/clause.
NAME_LIKE = re.compile(r"(?<![.!?:;]\s)(?<![.!?:;])(?<!^)(?<!\n)\b[A-Z][a-z]+\b")
NAME_ALLOW = {"Wi", "Fi", "Ethernet", "Internet", "PoE"}
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
TECHNICIAN_OPENER = re.compile(r"^\W*the\s+technician\b", re.IGNORECASE)

CHECK_ORDER = (
    "missing_from_response",
    "money",
    "time",
    "date",
    "name_like",
    "greeting_or_signoff",
    "technician_opener",
    "length",
    "exact_duplicate",
    "near_duplicate",
)


def text_violations(text: str | None, spec: dict) -> list[str]:
    """Per-comment checks, in CHECK_ORDER. Duplicate checks need the corpus index."""
    if not text:
        return ["missing_from_response"]
    out = []
    if MONEY.search(text):
        out.append("money")
    if TIME.search(text):
        out.append("time")
    if DATE.search(text):
        out.append("date")
    if any(m not in NAME_ALLOW for m in NAME_LIKE.findall(text)):
        out.append("name_like")
    if GREETING.search(text) or SIGN_OFF.search(text.strip()):
        out.append("greeting_or_signoff")
    if TECHNICIAN_OPENER.search(text):
        out.append("technician_opener")
    if not spec["min_words"] <= len(text.split()) <= spec["max_words"]:
        out.append("length")
    return out


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def shingles(text: str, k: int = SHINGLE_K) -> set[str]:
    t = normalize(text)
    return {t[i : i + k] for i in range(max(len(t) - k + 1, 1))}


class DuplicateIndex:
    """Corpus-wide exact and near-duplicate index (MinHash LSH, then exact Jaccard)."""

    def __init__(self):
        from datasketch import MinHash, MinHashLSH

        self._minhash = MinHash
        self.lsh = MinHashLSH(threshold=NEAR_DUP_THRESHOLD, num_perm=NUM_PERM)
        self.exact: dict[str, str] = {}
        self.sh: dict[str, set[str]] = {}

    def _mh(self, sh: set[str]):
        m = self._minhash(num_perm=NUM_PERM)
        for s in sh:
            m.update(s.encode("utf-8"))
        return m

    def find(self, text: str) -> tuple[str | None, str | None]:
        """(reason, other corpus_id) if `text` duplicates something indexed."""
        norm = normalize(text)
        if norm in self.exact:
            return "exact_duplicate", self.exact[norm]
        sh = shingles(text)
        for other in self.lsh.query(self._mh(sh)):
            inter = len(sh & self.sh[other])
            if inter / len(sh | self.sh[other]) > NEAR_DUP_THRESHOLD:
                return "near_duplicate", other
        return None, None

    def add(self, corpus_id: str, text: str) -> None:
        sh = shingles(text)
        self.exact[normalize(text)] = corpus_id
        self.sh[corpus_id] = sh
        self.lsh.insert(corpus_id, self._mh(sh))


# --------------------------------------------------------------------------- stages


def _now() -> str:
    return datetime.now(QUOTA_TZ).isoformat(timespec="seconds")


def stage_generate(ws: Workspace, api, template: str) -> int:
    """Generate every batch not yet in generated.jsonl. Returns batches completed now."""
    specs = ws.load_specs()
    done = ws.generated_batches()
    by_batch: dict[str, list[dict]] = defaultdict(list)
    for s in specs:
        by_batch[s["batch"]].append(s)
    pending = [b for b in sorted(by_batch) if b not in done]
    completed = 0
    for n, b in enumerate(pending, 1):
        batch = sorted(by_batch[b], key=lambda s: s["corpus_id"])
        prompt = render_generator_prompt(template, batch)
        for attempt in range(1, EMPTY_PARSE_ATTEMPTS + 1):
            res = api.request(GEN_MODEL, prompt)
            parsed = parse_array(res["text"], len(batch), "text")
            if parsed:
                break
            print(f"  generate {b}: unparseable response (attempt {attempt})")
        texts = {s["corpus_id"]: parsed.get(i) for i, s in enumerate(batch, 1)}
        append_jsonl(
            ws.generated,
            {
                "batch": b,
                "corpus_ids": [s["corpus_id"] for s in batch],
                "texts": {k: v for k, v in texts.items() if v},
                "model": GEN_MODEL,
                "at": _now(),
                "latency_s": res.get("latency_s"),
                "retries": res.get("retries", {}),
                "attempts": attempt,
                "raw": res.get("raw"),
            },
        )
        completed += 1
        got = sum(1 for v in texts.values() if v)
        print(f"  generate {b}: {got}/{len(batch)} texts ({n}/{len(pending)} pending batches)")
    return completed


def stage_checks(ws: Workspace) -> int:
    """Check every generated comment not yet in checks.jsonl, against the whole corpus."""
    specs = {s["corpus_id"]: s for s in ws.load_specs()}
    texts = ws.texts()
    results = ws.check_results()
    index = DuplicateIndex()
    for cid, r in results.items():  # rebuild from everything that already passed
        if r["ok"]:
            index.add(cid, texts[cid])
    new = 0
    for cid in [c for c in texts if c not in results]:
        text = texts[cid]
        reasons = text_violations(text, specs[cid])
        other = None
        if not reasons:
            dup, other = index.find(text)
            if dup:
                reasons.append(dup)
        ok = not reasons
        if ok:
            index.add(cid, text)
        append_jsonl(
            ws.checks,
            {"corpus_id": cid, "ok": ok, "reasons": reasons, "duplicate_of": other},
        )
        new += 1
    return new


def stage_judge(ws: Workspace, api, template: str) -> int:
    """Label every check-passed comment not yet judged. Retries ids the model skipped."""
    texts = ws.texts()
    total = 0
    for _ in range(JUDGE_PASSES):
        labels = ws.judge_labels()
        pending = sorted(
            cid for cid, r in ws.check_results().items() if r["ok"] and cid not in labels
        )
        if not pending:
            break
        for start in range(0, len(pending), BATCH_SIZE):
            ids = pending[start : start + BATCH_SIZE]
            res = api.request(JUDGE_MODEL, render_judge_prompt(template, [texts[c] for c in ids]))
            parsed = parse_array(res["text"], len(ids), "label")
            got = {ids[i - 1]: v.lower() for i, v in parsed.items()}
            append_jsonl(
                ws.judged,
                {
                    "corpus_ids": ids,
                    "labels": got,
                    "model": JUDGE_MODEL,
                    "at": _now(),
                    "latency_s": res.get("latency_s"),
                    "retries": res.get("retries", {}),
                    "raw": res.get("raw"),
                },
            )
            total += len(got)
            print(f"  judge: {len(got)}/{len(ids)} labeled")
    return total


def select(ws: Workspace) -> dict[str, dict]:
    """Status of every spec: accepted, rejected (with reason), or pending."""
    specs = ws.load_specs()
    generated = set()
    for r in read_jsonl(ws.generated):
        generated.update(r["corpus_ids"])
    checks = ws.check_results()
    labels = ws.judge_labels()
    out = {}
    for s in specs:
        cid = s["corpus_id"]
        st = {
            "status": "pending_generation",
            "reason": None,
            "judge": labels.get(cid),
            "disagreement": False,
        }
        if cid in generated:
            c = checks.get(cid)
            if c is None:
                st["status"] = "pending_checks"
            elif not c["ok"]:
                st.update(status="rejected", reason=c["reasons"][0])
            elif cid not in labels:
                st["status"] = "pending_judge"
            else:
                st.update(select_policy(s, labels[cid]))
        out[cid] = st
    return out


def select_policy(spec: dict, judge_label: str) -> dict:
    """ADR-036 decision 7: plain must match the judge; hard cases never rejected by it."""
    agree = judge_label == spec["sentiment"]
    if spec["style"] == "plain":
        if agree:
            return {"status": "accepted", "reason": None, "disagreement": False}
        return {"status": "rejected", "reason": "judge_disagreement", "disagreement": True}
    return {"status": "accepted", "reason": None, "disagreement": not agree}


def cell_counts(specs: list[dict], status: dict[str, dict]) -> dict[str, Counter]:
    out: dict[str, Counter] = defaultdict(Counter)
    for s in specs:
        st = status[s["corpus_id"]]["status"]
        out[s["cell"]]["specs"] += 1
        out[s["cell"]][st if st in ("accepted", "rejected") else "pending"] += 1
    return out


def deficits(required: dict[str, int], counts: dict[str, Counter]) -> dict[str, int]:
    """Cells whose accepted + still-pending comments fall short of their requirement."""
    out = {}
    for key, need in required.items():
        c = counts.get(key, Counter())
        short = need - c["accepted"] - c["pending"]
        if short > 0:
            out[key] = short
    return out


# --------------------------------------------------------------------------- outputs

OUTPUT_FIELDS = (
    "corpus_id",
    "text",
    "intended_sentiment",
    "style",
    "hard_case_type",
    "cell",
    "context",
    "service_type",
    "incident_type",
    "focus",
    "opening",
    "channel",
    "min_words",
    "max_words",
    "writer",
    "neutral_kind",
    "judge_label",
    "judge_disagreement",
    "model",
    "judge_model",
)


def finalize(ws: Workspace, out_dir: Path, required: dict[str, int], *, complete: bool) -> dict:
    """Write feedback_text.jsonl, rejected.jsonl and provenance.json from the stage files."""
    specs = ws.load_specs()
    texts = ws.texts()
    status = select(ws)
    accepted, rejected = [], []
    for s in sorted(specs, key=lambda s: s["corpus_id"]):
        st = status[s["corpus_id"]]
        if st["status"] == "accepted":
            accepted.append(
                {
                    "corpus_id": s["corpus_id"],
                    "text": texts[s["corpus_id"]],
                    "intended_sentiment": s["sentiment"],
                    **{k: s[k] for k in OUTPUT_FIELDS if k in s},
                    "judge_label": st["judge"],
                    "judge_disagreement": st["disagreement"],
                    "model": GEN_MODEL,
                    "judge_model": JUDGE_MODEL,
                }
            )
        elif st["status"] == "rejected":
            rejected.append(
                {
                    "corpus_id": s["corpus_id"],
                    "text": texts.get(s["corpus_id"]),
                    "reason": st["reason"],
                }
            )
    write_jsonl(out_dir / "feedback_text.jsonl", accepted)
    write_jsonl(out_dir / "rejected.jsonl", rejected)

    counts = cell_counts(specs, status)
    hard_disagree = Counter(
        s["style"]
        for s in specs
        if s["style"] != "plain" and status[s["corpus_id"]]["disagreement"]
    )
    dates = sorted({r["at"][:10] for r in read_jsonl(ws.generated) + read_jsonl(ws.judged)})
    provenance = {
        "complete": complete,
        "models": {"generator": GEN_MODEL, "judge": JUDGE_MODEL},
        "settings": {
            "generator": {
                "temperature": GEN_TEMPERATURE,
                "thinking_level": THINKING_LEVEL,
                "response_mime_type": RESPONSE_MIME_TYPE,
                "batch_size": BATCH_SIZE,
            },
            "judge": {
                "temperature": JUDGE_TEMPERATURE,
                "thinking_level": THINKING_LEVEL,
                "response_mime_type": RESPONSE_MIME_TYPE,
                "batch_size": BATCH_SIZE,
                "input": "comment text only",
            },
            "near_duplicate": {
                "scope": "whole corpus",
                "shingle_chars": SHINGLE_K,
                "jaccard_gt": NEAR_DUP_THRESHOLD,
                "minhash_num_perm": NUM_PERM,
            },
            "retries": {"max": MAX_RETRIES, "on": sorted(RETRYABLE_CODES)},
            "daily_cap": DAILY_CAP,
            "topup": {"rounds": TOPUP_ROUNDS, "inflation": TOPUP_INFLATION},
        },
        "versions": _versions(),
        "prompts": {
            "generator_v4.txt": prompt_sha256(GEN_PROMPT_PATH),
            "judge_v4.txt": prompt_sha256(JUDGE_PROMPT_PATH),
        },
        "master_seed": prm.MASTER_SEED,
        "run_dates": dates,
        "cells": {
            key: {
                "required": required.get(key, 0),
                "generated": c["specs"] - c["pending"],
                "accepted": c["accepted"],
                "rejected": c["rejected"],
                "pending": c["pending"],
            }
            for key, c in sorted(counts.items())
        },
        "rejections_by_reason": dict(Counter(r["reason"] for r in rejected).most_common()),
        "hard_case_judge_disagreements": dict(hard_disagree),
        "accepted": len(accepted),
        "rejected": len(rejected),
    }
    (out_dir / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    return provenance


def _versions() -> dict:
    import importlib.metadata as md

    out = {"python": sys.version.split()[0], "numpy": np.__version__}
    for pkg in ("google-genai", "datasketch"):
        try:
            out[pkg] = md.version(pkg)
        except md.PackageNotFoundError:
            out[pkg] = None
    return out


# --------------------------------------------------------------------------- runs


def run_pipeline(ws: Workspace, api, *, gen_template: str, judge_template: str) -> str | None:
    """generate -> checks -> judge. Returns the stop reason if a cap stopped generation."""
    stopped = None
    try:
        stage_generate(ws, api, gen_template)
    except StopRun as exc:
        stopped = str(exc)
        print(f"  stopped generation: {stopped}")
    stage_checks(ws)
    try:
        stage_judge(ws, api, judge_template)
    except StopRun as exc:
        stopped = stopped or str(exc)
        print(f"  stopped judging: {exc}")
    return stopped


def run_full(ws: Workspace, api, params: prm.Parameters = prm.PARAMS) -> dict:
    gen_t, judge_t = load_prompt(GEN_PROMPT_PATH), load_prompt(JUDGE_PROMPT_PATH)
    required = required_by_cell(params)
    if not ws.load_specs():
        for s in build_full_specs(params):
            append_jsonl(ws.specs, s)
        print(f"specs: {sum(required.values())} across {len(required)} cells")
    while True:
        stopped = run_pipeline(ws, api, gen_template=gen_t, judge_template=judge_t)
        specs = ws.load_specs()
        short = deficits(required, cell_counts(specs, select(ws)))
        round_no = max(s["round"] for s in specs)
        if stopped or not short or round_no >= TOPUP_ROUNDS:
            break
        new = build_topup_specs(specs, short, round_no + 1, params)
        for s in new:
            append_jsonl(ws.specs, s)
        print(f"top-up round {round_no + 1}: {len(new)} specs for {len(short)} short cells")
    prov = finalize(ws, CORPUS_DIR, required, complete=not stopped and not short)
    print_status(ws, required)
    if stopped:
        print(f"stopped cleanly ({stopped}); rerun --run to resume")
    elif short:
        print(f"{len(short)} cells still short after {TOPUP_ROUNDS} top-up rounds:")
        for key, n in sorted(short.items()):
            print(f"  {key}: short {n}")
    return prov


def run_topup(ws: Workspace, api, key: str, n: int | None, params: prm.Parameters = prm.PARAMS):
    required = required_by_cell(params)
    if key not in required:
        raise SystemExit(f"unknown or forbidden cell: {key}")
    specs = ws.load_specs()
    short = deficits(required, cell_counts(specs, select(ws))).get(key, 0)
    count = n or math.ceil(short * TOPUP_INFLATION)
    if count <= 0:
        print(f"{key} is not short; pass --n to add specs anyway")
        return
    round_no = max((s["round"] for s in specs), default=0) + 1
    rng = np.random.default_rng(prm.derive_seed(f"{prm.STAGE_CORPUS_SPECS}_manual_{round_no}"))
    first = next_id_number(specs)
    new = [draw_spec(rng, key, format_id(first + i), round_no, params=params) for i in range(count)]
    for s in assign_batches(rng, new, f"r{round_no}"):
        append_jsonl(ws.specs, s)
    print(f"manual top-up round {round_no}: {count} specs for {key}")
    stopped = run_pipeline(
        ws,
        api,
        gen_template=load_prompt(GEN_PROMPT_PATH),
        judge_template=load_prompt(JUDGE_PROMPT_PATH),
    )
    finalize(ws, CORPUS_DIR, required, complete=False)
    print_status(ws, required)
    if stopped:
        print(f"stopped cleanly ({stopped}); rerun to resume")


def print_status(ws: Workspace, required: dict[str, int]) -> None:
    specs = ws.load_specs()
    status = select(ws)
    by = Counter(v["status"] for v in status.values())
    reasons = Counter(v["reason"] for v in status.values() if v["status"] == "rejected")
    counts = cell_counts(specs, status)
    short = deficits(required, counts)
    counter = RequestCounter()
    print(f"specs {len(specs)}; " + ", ".join(f"{k} {v}" for k, v in sorted(by.items())))
    if reasons:
        print("  rejections: " + ", ".join(f"{k} {v}" for k, v in reasons.most_common()))
    print(f"  cells: {len(required)} required, {len(short)} short")
    print(
        f"  requests today (Pacific): {GEN_MODEL} {counter.used(GEN_MODEL)}/"
        f"{DAILY_CAP[GEN_MODEL]}, {JUDGE_MODEL} {counter.used(JUDGE_MODEL)}/"
        f"{DAILY_CAP[JUDGE_MODEL]}"
    )


# --------------------------------------------------------------------------- test batch

#: (group, sentiment, style, context, forced channel or None, neutral kind or None, count)
TEST_PLAN: tuple[tuple, ...] = (
    ("positive_incident", "positive", "plain", "minor", None, None, 4),
    ("positive_incident", "positive", "plain", "serious", None, None, 4),
    ("positive_incident", "positive", "implicit", "minor", None, None, 3),
    ("positive_incident", "positive", "implicit", "serious", None, None, 4),
    ("mixed_serious", "mixed", "plain", "serious", None, None, 10),
    ("minimal_neutral", "neutral", "plain", "none", None, "minimal", 10),
    ("sms", "positive", "plain", "none", "sms_survey", None, 1),
    ("sms", "positive", "implicit", "none", "sms_survey", None, 1),
    ("sms", "positive", "plain", "minor", "sms_survey", None, 1),
    ("sms", "neutral", "plain", "none", "sms_survey", "administrative", 1),
    ("sms", "neutral", "plain", "none", "sms_survey", "status", 1),
    ("sms", "negative", "plain", "none", "sms_survey", None, 1),
    ("sms", "negative", "implicit", "minor", "sms_survey", None, 1),
    ("sms", "negative", "sarcastic", "none", "sms_survey", None, 1),
    ("sms", "negative", "plain", "serious", "sms_survey", None, 1),
    ("sms", "mixed", "plain", "none", "sms_survey", None, 1),
    ("distractor", "positive", "plain", "none", None, None, 2),
    ("distractor", "positive", "implicit", "none", None, None, 2),
    ("distractor", "neutral", "plain", "none", None, "administrative", 2),
    ("distractor", "neutral", "plain", "none", None, "status", 2),
    ("distractor", "negative", "plain", "none", None, None, 1),
    ("distractor", "negative", "plain", "minor", None, None, 1),
    ("distractor", "negative", "implicit", "serious", None, None, 1),
    ("distractor", "negative", "sarcastic", "none", None, None, 1),
    ("distractor", "negative", "sarcastic", "minor", None, None, 1),
    ("distractor", "mixed", "plain", "none", None, None, 1),
    ("distractor", "mixed", "plain", "minor", None, None, 1),
)

#: Keywords that suggest a comment names its incident (heuristic for ADR-036's positive rule).
INCIDENT_KEYWORDS = {
    "missed_sla": ("late", "delay", "behind schedule", "waited", "waiting", "arrived after"),
    "wrong_dispatch_info": ("wrong", "incorrect", "missing part", "parts", "information"),
    "repeat_visit_required": (
        "second visit",
        "second trip",
        "return",
        "came back",
        "again",
        "follow-up",
        "follow up",
        "another visit",
    ),
    "technician_conduct": (
        "conduct",
        "rude",
        "attitude",
        "behavior",
        "behaviour",
        "unprofessional",
    ),
    "equipment_damage": ("damage", "dent", "crack", "scratch", "broke"),
    "billing_dispute": ("bill", "invoice", "charge"),
    "other": ("problem", "issue", "hiccup"),
}


def build_test_specs(params: prm.Parameters = prm.PARAMS) -> list[dict]:
    """The 60-spec quality batch (ids t-000001..). Non-SMS groups never draw SMS."""
    rng = np.random.default_rng(prm.derive_seed(STAGE_TEST_BATCH))
    non_sms = {k: v for k, v in params.feedback.channel_mix.value.items() if k != "sms_survey"}
    specs, n = [], 1
    for group, se, st, ctx, channel, kind, count in TEST_PLAN:
        for _ in range(count):
            if ctx == "none":
                detail = _choice(rng, prm.SERVICE_TYPES)
            else:
                detail = _choice(rng, prm.INCIDENT_TYPES)
            s = draw_spec(
                rng,
                cell_key(se, st, ctx, detail),
                format_id(n, "t"),
                0,
                params=params,
                channel=channel,
                neutral_kind=kind,
                channels=None if channel else non_sms,
            )
            s["group"] = group
            specs.append(s)
            n += 1
    return assign_batches(rng, specs, "t")


def names_incident(text: str, incident_type: str) -> bool:
    t = text.lower()
    return any(k in t for k in INCIDENT_KEYWORDS[incident_type])


def test_batch_report(ws: Workspace) -> dict:
    specs = ws.load_specs()
    texts = ws.texts()
    status = select(ws)
    checks = ws.check_results()
    groups: dict[str, Counter] = defaultdict(Counter)
    for s in specs:
        st = status[s["corpus_id"]]
        g = groups[s["group"]]
        g["specs"] += 1
        g[st["status"]] += 1
        if st["judge"]:
            g["judged"] += 1
            g["judge_agrees"] += st["judge"] == s["sentiment"]
    reasons = Counter(r["reasons"][0] for r in checks.values() if not r["ok"])
    missing = sum(1 for s in specs if not texts.get(s["corpus_id"]))
    pos_inc = [s for s in specs if s["group"] == "positive_incident" and texts.get(s["corpus_id"])]
    mentions = [
        s["corpus_id"] for s in pos_inc if names_incident(texts[s["corpus_id"]], s["incident_type"])
    ]
    return {
        "judge_agreement_by_group": {
            g: {
                "agree": c["judge_agrees"],
                "judged": c["judged"],
                "specs": c["specs"],
                "accepted": c["accepted"],
                "rejected": c["rejected"],
            }
            for g, c in sorted(groups.items())
        },
        "check_rejections_by_reason": dict(reasons.most_common()),
        "missing_from_response": missing,
        "positive_incident_names_problem_HEURISTIC": {
            "count": len(mentions),
            "of": len(pos_inc),
            "corpus_ids": mentions,
            "note": "keyword match on the incident phrasing; a heuristic, not a judgment",
        },
        "judge_disagreement_by_style": dict(
            Counter(
                s["style"]
                for s in specs
                if status[s["corpus_id"]]["judge"]
                and status[s["corpus_id"]]["judge"] != s["sentiment"]
            )
        ),
    }


REVIEW_QUOTAS = (
    ("positive_incident", "implicit", 7),
    ("positive_incident", "plain", 5),
    ("mixed_serious", None, 6),
    ("minimal_neutral", None, 5),
    ("sms", None, 3),
    ("distractor", None, 4),
)


def write_test_review(ws: Workspace, out: Path) -> int:
    """30 blind rows (all implicit positive-incident comments included), plus the key."""
    specs = ws.load_specs()
    texts = ws.texts()
    status = select(ws)
    checks = ws.check_results()
    rng = random.Random(prm.MASTER_SEED)
    eligible = [
        s for s in specs if texts.get(s["corpus_id"]) and checks.get(s["corpus_id"], {}).get("ok")
    ]
    chosen: list[dict] = []
    for group, style, n in REVIEW_QUOTAS:
        pool = [
            s
            for s in eligible
            if s["group"] == group and (style is None or s["style"] == style) and s not in chosen
        ]
        rng.shuffle(pool)
        chosen += pool[:n]
    rest = [s for s in eligible if s not in chosen]
    rng.shuffle(rest)
    chosen += rest[: max(0, 30 - len(chosen))]
    rng.shuffle(chosen)
    with (
        (out / "review_blind.csv").open("w", newline="", encoding="utf-8") as fb,
        (out / "review_key.csv").open("w", newline="", encoding="utf-8") as fk,
    ):
        wb, wk = csv.writer(fb), csv.writer(fk)
        wb.writerow(
            [
                "review_id",
                "text",
                "my_sentiment",
                "believable_1to3",
                "sounds_ai_yn",
                "names_failure_yn",
                "notes",
            ]
        )
        wk.writerow(
            [
                "review_id",
                "model",
                "spec_id",
                "corpus_id",
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
                "selected",
                "names_problem_heuristic",
            ]
        )
        for k, s in enumerate(chosen, 1):
            rid, cid = f"R{k:02d}", s["corpus_id"]
            st = status[cid]
            wb.writerow([rid, texts[cid], "", "", "", "", ""])
            wk.writerow(
                [
                    rid,
                    GEN_MODEL,
                    int(cid.split("-")[1]),
                    cid,
                    s["group"],
                    s["sentiment"],
                    s["style"],
                    s["neutral_kind"] or "",
                    s["context"] if s["incident_type"] else "",
                    s["incident_type"] or "",
                    s["channel"],
                    s["focus"] or "",
                    s["opening"] or "",
                    st["judge"] or "",
                    st["status"] if st["status"] != "rejected" else f"rejected:{st['reason']}",
                    ""
                    if not s["incident_type"]
                    else ("y" if names_incident(texts[cid], s["incident_type"]) else "n"),
                ]
            )
    return len(chosen)


def run_test_batch(out: Path, api) -> dict:
    ws = Workspace(out)
    if not ws.load_specs():
        for s in build_test_specs():
            append_jsonl(ws.specs, s)
    stopped = run_pipeline(
        ws,
        api,
        gen_template=load_prompt(GEN_PROMPT_PATH),
        judge_template=load_prompt(JUDGE_PROMPT_PATH),
    )
    required = Counter(s["cell"] for s in ws.load_specs())
    finalize(ws, out, dict(required), complete=not stopped)
    report = test_batch_report(ws)
    report["review_rows"] = write_test_review(ws, out)
    report["stopped"] = stopped
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def print_test_report(report: dict) -> None:
    print("\n== test batch: judge agreement by group (judge label vs intended)")
    for g, c in report["judge_agreement_by_group"].items():
        print(
            f"  {g:18} judge {c['agree']}/{c['judged']}   accepted {c['accepted']}/"
            f"{c['specs']}, rejected {c['rejected']}"
        )
    print(f"  judge disagreements by style: {report['judge_disagreement_by_style']}")
    print("\n== automated check rejections by reason")
    print(f"  {report['check_rejections_by_reason'] or 'none'}")
    h = report["positive_incident_names_problem_HEURISTIC"]
    print(
        f"\n== positive-with-incident comments naming the problem (HEURISTIC keyword match): "
        f"{h['count']}/{h['of']}"
    )
    print(f"\n  review sheet rows: {report['review_rows']}; stopped: {report['stopped']}")


# --------------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--test-batch", action="store_true")
    g.add_argument("--run", action="store_true")
    g.add_argument("--status", action="store_true")
    g.add_argument("--top-up", metavar="CELL_KEY")
    ap.add_argument("--n", type=int, help="specs to add with --top-up")
    ap.add_argument("--out-date", default=datetime.now(QUOTA_TZ).date().isoformat())
    args = ap.parse_args(argv)

    prm.validate_parameters()
    ws = Workspace(WORK_DIR)
    if args.status:
        print_status(ws, required_by_cell())
        return 0
    api = GeminiApi(RequestCounter())
    if args.test_batch:
        report = run_test_batch(TEST_ROOT / args.out_date, api)
        print_test_report(report)
    elif args.run:
        run_full(ws, api)
    else:
        run_topup(ws, api, args.top_up, args.n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
