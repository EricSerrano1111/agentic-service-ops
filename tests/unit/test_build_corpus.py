"""Offline tests for data/generator/build_corpus.py. The API is always mocked."""

import json
import math
import random
import re
import sys
from collections import Counter
from pathlib import Path

import pytest

_GEN = Path(__file__).resolve().parents[2] / "data" / "generator"
sys.path.insert(0, str(_GEN))
import build_corpus as bc  # noqa: E402
import parameters as prm  # noqa: E402

GEN_T = bc.load_prompt(bc.GEN_PROMPT_PATH)
JUDGE_T = bc.load_prompt(bc.JUDGE_PROMPT_PATH)
LINE = re.compile(r"^(\d+)\. sentiment: (\w+);.*?channel: \w+, (\d+)-(\d+) words", re.M)


def _word(rng: random.Random) -> str:
    return "".join(rng.choice("bdfgklmnprstvz") + rng.choice("aeiou") for _ in range(4))


class FakeApi:
    """Answers like the real models: check-passing text, and a fixed judge label."""

    def __init__(self, fail_after: int | None = None, label: str | None = None, counter=None):
        self.fail_after, self.label, self.counter = fail_after, label, counter
        self.calls: list[tuple[str, str]] = []

    def request(self, model: str, prompt: str) -> dict:
        if self.fail_after is not None and len(self.calls) >= self.fail_after:
            raise RuntimeError("simulated crash")
        if self.counter is not None:
            self.counter.take(model)
        self.calls.append((model, prompt))
        if model == bc.GEN_MODEL:
            items = []
            for i, _sentiment, lo, hi in LINE.findall(prompt):
                rng = random.Random(prompt + i)
                n = min(int(hi), int(lo) + 3)
                items.append({"id": int(i), "text": " ".join(_word(rng) for _ in range(n))})
            text = json.dumps(items)
        else:
            body = prompt.split("Comments:", 1)[1]
            n = len(re.findall(r"^\d+\. ", body, re.M))
            text = json.dumps(
                [{"id": i, "label": self.label or "positive"} for i in range(1, n + 1)]
            )
        return {"text": text, "raw": {"fake": True}, "latency_s": 0.0, "retries": {}}


def _ws(tmp_path, specs=None) -> bc.Workspace:
    ws = bc.Workspace(tmp_path / "ws")
    for s in specs if specs is not None else bc.build_test_specs():
        bc.append_jsonl(ws.specs, s)
    return ws


# --------------------------------------------------------------------------- specs


@pytest.fixture(scope="module")
def full_specs():
    return bc.build_full_specs()


def test_spec_counts_per_cell_match_parameters(full_specs):
    required = bc.required_by_cell()
    assert Counter(s["cell"] for s in full_specs) == Counter(required)
    assert len(full_specs) == sum(required.values()) == prm.corpus_summary()["required_comments"]
    for s in full_specs:
        assert prm.is_allowed(s["sentiment"], s["style"], s["context"])


def test_batches_are_shuffled_across_cells(full_specs):
    sizes = Counter(s["batch"] for s in full_specs)
    assert len(sizes) == math.ceil(len(full_specs) / bc.BATCH_SIZE)
    assert max(sizes.values()) == bc.BATCH_SIZE
    first = [s for s in full_specs if s["batch"] == "r0-b0001"]
    assert len({s["cell"] for s in first}) > 5


def test_corpus_id_deterministic_and_sequential(full_specs):
    again = bc.build_full_specs()
    assert again == full_specs
    ids = sorted(s["corpus_id"] for s in full_specs)
    assert ids[0] == "fb-000001" and ids[-1] == f"fb-{len(ids):06d}"
    assert len(set(ids)) == len(ids)


def test_topup_ids_continue_and_are_deterministic(full_specs):
    short = {"neutral|plain|none|repair": 4, "negative|sarcastic|serious|other": 2}
    a = bc.build_topup_specs(full_specs, short, 1)
    b = bc.build_topup_specs(full_specs, short, 1)
    assert a == b
    assert len(a) == math.ceil(4 * 1.5) + math.ceil(2 * 1.5)
    assert min(s["corpus_id"] for s in a) == f"fb-{len(full_specs) + 1:06d}"
    assert all(s["round"] == 1 and s["batch"].startswith("r1-") for s in a)


def test_spec_field_rules(full_specs):
    for s in full_specs:
        if s["neutral_kind"] == "minimal":
            assert s["focus"] is None and s["opening"] is None
            assert (s["min_words"], s["max_words"]) == (1, 8)
        else:
            assert s["focus"] and s["opening"]
            band = prm.PARAMS.corpus.length_band_by_channel.value[s["channel"]]
            assert (s["min_words"], s["max_words"]) == band
        if s["opening"] == "question":
            assert s["sentiment"] == "negative" or s["neutral_kind"] == "administrative"
        assert (s["sentiment"] == "neutral") == (s["neutral_kind"] is not None)
    assert prm.PARAMS.corpus.length_band_by_channel.value["sms_survey"] == (2, 12)


def test_test_batch_plan():
    specs = bc.build_test_specs()
    assert len(specs) == 60
    groups = Counter(s["group"] for s in specs)
    assert groups == {
        "positive_incident": 15,
        "mixed_serious": 10,
        "minimal_neutral": 10,
        "sms": 10,
        "distractor": 15,
    }
    pos = [s for s in specs if s["group"] == "positive_incident"]
    assert Counter(s["style"] for s in pos) == {"plain": 8, "implicit": 7}
    assert {s["context"] for s in pos} == {"minor", "serious"}
    assert all(s["channel"] == "sms_survey" for s in specs if s["group"] == "sms")
    assert not any(s["channel"] == "sms_survey" for s in specs if s["group"] != "sms")
    assert all(s["context"] == "serious" for s in specs if s["group"] == "mixed_serious")
    assert Counter(s["batch"] for s in specs) == {"t-b0001": 20, "t-b0002": 20, "t-b0003": 20}


def test_spec_line_notes():
    specs = bc.build_test_specs()
    for s in specs:
        line = bc.spec_line(1, s)
        assert "Praise how it was handled" not in line  # removed by ADR-039
        assert (bc.MIXED_SERIOUS_NOTE in line) == (
            s["sentiment"] == "mixed" and s["context"] == "serious"
        )
        if s["incident_type"] == "other":
            assert "a problem with the visit" in line
        if s["neutral_kind"] == "minimal":
            assert "focus:" not in line and "opening:" not in line


def test_prompts_carry_adr036_definitions():
    for t in (GEN_T, JUDGE_T):
        assert (
            "On an incident row, the\n  text praises the handling without naming the failure." in t
        )
        assert "or names a serious problem and praises how it was handled." in t
    assert '"/s"' in GEN_T and "No greetings or sign-offs" in GEN_T
    assert "2-12 words" in GEN_T


# --------------------------------------------------------------------------- checks

SPEC = {"min_words": 1, "max_words": 60}


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        (None, "missing_from_response"),
        ("they charged $300 for the switch swap", "money"),
        ("crew showed up at 9:30 and finished fast", "time"),
        ("booked for March 4 and nobody came", "date"),
        ("came back on 3/14 to finish cabling", "date"),
        ("ordered the parts on the 4th", "date"),
        ("thanks to Dave for sorting the router", "name_like"),
        ("Hi team, the rack install went fine", "greeting_or_signoff"),
        ("rack install went fine. Thanks, Sam", "greeting_or_signoff"),
        ("The technician fixed the access points", "technician_opener"),
    ],
)
def test_checks_catch_each_violation(text, reason):
    assert reason in bc.text_violations(text, SPEC)


def test_length_check():
    spec = {"min_words": 2, "max_words": 12}
    assert bc.text_violations("fine", spec) == ["length"]
    assert bc.text_violations("all good now, switch replaced", spec) == []
    assert "length" in bc.text_violations(" ".join(["word"] * 13), spec)


def test_clean_text_passes():
    text = "Switch swapped quickly. Wi-Fi is stable now and the Ethernet runs look tidy."
    assert bc.text_violations(text, SPEC) == []


def test_duplicate_index():
    idx = bc.DuplicateIndex()
    idx.add("fb-000001", "the new access points cover the whole warehouse floor now")
    assert idx.find("The new access points  cover the whole warehouse floor now") == (
        "exact_duplicate",
        "fb-000001",
    )
    reason, other = idx.find("the new access points cover the whole warehouse floor now!")
    assert (reason, other) == ("near_duplicate", "fb-000001")
    assert idx.find("billing sorted out after one call, no complaints here") == (None, None)


def test_near_duplicates_checked_across_whole_corpus(tmp_path):
    specs = bc.build_test_specs()[:2]
    specs[0]["batch"], specs[1]["batch"] = "x-b0001", "x-b0002"  # different batches
    for s in specs:
        s["min_words"], s["max_words"] = 1, 60
    ws = _ws(tmp_path, specs)
    same = "router firmware updated and the office network has been steady since"
    for s in specs:
        bc.append_jsonl(
            ws.generated,
            {
                "batch": s["batch"],
                "corpus_ids": [s["corpus_id"]],
                "texts": {s["corpus_id"]: same + "."},
                "at": "2026-01-01",
            },
        )
    bc.stage_checks(ws)
    res = ws.check_results()
    assert res[specs[0]["corpus_id"]]["ok"]
    assert res[specs[1]["corpus_id"]]["reasons"] == ["exact_duplicate"]


# --------------------------------------------------------------------------- select


@pytest.mark.parametrize(
    ("style", "intended", "judge", "status", "disagreement"),
    [
        ("plain", "neutral", "neutral", "accepted", False),
        ("plain", "neutral", "positive", "rejected", True),
        ("plain", "mixed", "negative", "rejected", True),
        ("implicit", "positive", "neutral", "accepted", True),
        ("sarcastic", "negative", "positive", "accepted", True),
        ("sarcastic", "negative", "negative", "accepted", False),
    ],
)
def test_select_policy(style, intended, judge, status, disagreement):
    out = bc.select_policy({"style": style, "sentiment": intended}, judge)
    assert out["status"] == status and out["disagreement"] == disagreement
    if status == "rejected":
        assert out["reason"] == "judge_disagreement"


# --------------------------------------------------------------------------- resume


def _batches_requested(calls):
    return [re.findall(r"^1\. .*$", p, re.M)[0] for m, p in calls if m == bc.GEN_MODEL]


def test_generate_resumes_after_crash_without_repeating(tmp_path):
    ws = _ws(tmp_path)
    first = FakeApi(fail_after=1)
    with pytest.raises(RuntimeError):
        bc.stage_generate(ws, first, GEN_T)
    assert len(ws.generated_batches()) == 1
    with ws.generated.open("a", encoding="utf-8") as f:
        f.write('{"batch": "t-b0002", "corpus_ids": [')  # partial line from the crash
    second = FakeApi()
    bc.stage_generate(ws, second, GEN_T)
    done = [r["batch"] for r in bc.read_jsonl(ws.generated)]
    assert sorted(done) == ["t-b0001", "t-b0002", "t-b0003"]
    assert len(done) == len(set(done))
    assert len(first.calls) + len(second.calls) == 3


def test_judge_resumes_after_crash_without_repeating(tmp_path):
    ws = _ws(tmp_path)
    bc.stage_generate(ws, FakeApi(), GEN_T)
    bc.stage_checks(ws)
    passed = [c for c, r in ws.check_results().items() if r["ok"]]
    with pytest.raises(RuntimeError):
        bc.stage_judge(ws, FakeApi(fail_after=1), JUDGE_T)
    after_crash = set(ws.judge_labels())
    second = FakeApi()
    bc.stage_judge(ws, second, JUDGE_T)
    judged = [c for r in bc.read_jsonl(ws.judged) for c in r["labels"]]
    assert len(judged) == len(set(judged)) == len(passed)
    resent = [c for m, p in second.calls for c in after_crash if c in p]
    assert not resent


def test_checks_resume_is_idempotent(tmp_path):
    ws = _ws(tmp_path)
    bc.stage_generate(ws, FakeApi(), GEN_T)
    assert bc.stage_checks(ws) == 60
    assert bc.stage_checks(ws) == 0


# --------------------------------------------------------------------------- caps


def test_daily_cap_stops_cleanly_and_resumes_next_day(tmp_path):
    day = {"d": "2026-09-24"}
    path = tmp_path / "counts.json"
    counter = bc.RequestCounter(path, caps={bc.GEN_MODEL: 2}, today=lambda: day["d"])
    ws = _ws(tmp_path)
    stopped = bc.run_pipeline(
        ws, FakeApi(counter=counter), gen_template=GEN_T, judge_template=JUDGE_T
    )
    assert stopped and "cap" in stopped
    assert len(ws.generated_batches()) == 2
    assert bc.RequestCounter(path, caps={}, today=lambda: day["d"]).used(bc.GEN_MODEL) == 2
    day["d"] = "2026-09-25"
    counter2 = bc.RequestCounter(path, caps={bc.GEN_MODEL: 2}, today=lambda: day["d"])
    api = FakeApi(counter=counter2)
    assert bc.run_pipeline(ws, api, gen_template=GEN_T, judge_template=JUDGE_T) is None
    assert len(ws.generated_batches()) == 3
    assert sum(1 for m, _ in api.calls if m == bc.GEN_MODEL) == 1


@pytest.mark.parametrize(
    ("message", "daily"),
    [
        ("429 RESOURCE_EXHAUSTED quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier", True),
        ("You exceeded your current quota: requests per day", True),
        ("429 RESOURCE_EXHAUSTED quotaId: GenerateRequestsPerMinutePerProjectPerModel", False),
    ],
)
def test_daily_quota_error_detection(message, daily):
    assert bc.is_daily_quota_error(message) is daily


def test_daily_quota_429_stops_without_retry_loop(tmp_path):
    class Err(Exception):
        code = 429

    class Models:
        calls = 0

        def generate_content(self, **_):
            Models.calls += 1
            raise Err("RESOURCE_EXHAUSTED GenerateRequestsPerDayPerProjectPerModel")

    api = _api_with(Models(), tmp_path)
    with pytest.raises(bc.StopRun, match="daily quota"):
        api.request(bc.GEN_MODEL, "prompt")
    assert Models.calls == 1


# --------------------------------------------------------------------------- outputs


def test_outputs_match_schema(tmp_path):
    ws = _ws(tmp_path)
    bc.run_pipeline(ws, FakeApi(label="positive"), gen_template=GEN_T, judge_template=JUDGE_T)
    out = tmp_path / "out"
    out.mkdir()
    required = dict(Counter(s["cell"] for s in ws.load_specs()))
    prov = bc.finalize(ws, out, required, complete=True)
    accepted = bc.read_jsonl(out / "feedback_text.jsonl")
    rejected = bc.read_jsonl(out / "rejected.jsonl")
    assert accepted and rejected
    for row in accepted:
        assert set(row) == set(bc.OUTPUT_FIELDS)
        assert row["hard_case_type"] == prm.HARD_CASE_BY_STYLE[row["style"]]
        assert row["model"] == bc.GEN_MODEL and row["judge_model"] == bc.JUDGE_MODEL
        if row["style"] == "plain":
            assert row["judge_label"] == row["intended_sentiment"]
    for row in rejected:
        assert set(row) == {"corpus_id", "text", "reason"}
    assert {r["reason"] for r in rejected} == {"judge_disagreement"}
    assert len(accepted) + len(rejected) == 60
    for key in (
        "models",
        "settings",
        "versions",
        "prompts",
        "master_seed",
        "run_dates",
        "cells",
        "rejections_by_reason",
        "hard_case_judge_disagreements",
    ):
        assert key in prov
    assert prov["settings"]["near_duplicate"]["scope"] == "whole corpus"
    assert set(prov["prompts"]) == {"generator_v4.txt", "judge_v4.txt"}
    assert json.loads((out / "provenance.json").read_text())["accepted"] == len(accepted)


def test_select_and_deficits(tmp_path):
    ws = _ws(tmp_path)
    bc.run_pipeline(ws, FakeApi(label="negative"), gen_template=GEN_T, judge_template=JUDGE_T)
    specs = ws.load_specs()
    status = bc.select(ws)
    counts = bc.cell_counts(specs, status)
    required = {s["cell"]: 1 for s in specs}
    short = bc.deficits(required, counts)
    # Plain non-negative cells lose everything to the judge; hard cases are kept.
    for s in specs:
        if s["style"] == "plain" and s["sentiment"] != "negative":
            assert status[s["corpus_id"]]["status"] == "rejected"
            assert s["cell"] in short
        if s["style"] != "plain":
            assert status[s["corpus_id"]]["status"] == "accepted"


# --------------------------------------------------------------------------- parsing


def test_parse_repairs_unquoted_keys():
    # The shape Flash-Lite returned for one test batch: JS-style objects, bare keys.
    text = (
        '[\n  {\n    id: 1,\n    text: "switch swapped, all good: no issues"\n  },\n'
        '  {id: 2, text: "fine"}\n]'
    )
    assert bc.parse_array(text, 2, "text") == {1: "switch swapped, all good: no issues", 2: "fine"}


def test_parse_valid_and_fenced():
    assert bc.parse_array('[{"id": 1, "label": "mixed"}]', 1, "label") == {1: "mixed"}
    assert bc.parse_array('```json\n[{"id": 1, "label": "x"}]\n```', 1, "label") == {1: "x"}
    assert bc.parse_array("not json", 1, "label") == {}


def test_unparseable_generation_batch_is_retried(tmp_path):
    ws = _ws(tmp_path, bc.build_test_specs()[:20])

    class Flaky(FakeApi):
        def request(self, model, prompt):
            if not self.calls:
                self.calls.append((model, prompt))
                return {"text": "garbage", "raw": None, "latency_s": 0, "retries": {}}
            return super().request(model, prompt)

    bc.stage_generate(ws, Flaky(), GEN_T)
    (row,) = bc.read_jsonl(ws.generated)
    assert row["attempts"] == 2 and len(row["texts"]) == 20


def test_append_terminates_a_dangling_partial_line(tmp_path):
    path = tmp_path / "x.jsonl"
    path.write_text('{"a": 1}\n{"b": ', encoding="utf-8")
    bc.append_jsonl(path, {"c": 3})
    assert bc.read_jsonl(path) == [{"a": 1}, {"c": 3}]


def test_status_reports_new_sizing(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(bc, "COUNTER_PATH", tmp_path / "c.json")
    required = bc.required_by_cell()
    bc.print_status(bc.Workspace(tmp_path / "ws"), required)
    out = capsys.readouterr().out
    total = sum(required.values())
    assert f"cells: {len(required)} ({total} comments required" in out
    assert not any(k.startswith("positive|") and "|none|" not in k for k in required)


# --------------------------------------------------------------------------- pacing


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, d):
        self.t += d


def test_pacer_rpm():
    clock = FakeClock()
    pacer = bc.Pacer({"m": {"rpm": 12}}, clock=clock, sleep=clock.sleep)
    for _ in range(12):
        assert pacer.wait("m", 1) == 0
        pacer.record("m", 1)
    assert pacer.wait("m", 1) == pytest.approx(60.0)  # the 13th waits out the window


def test_pacer_tpm_uses_reported_tokens():
    clock = FakeClock()
    pacer = bc.Pacer({"m": {"tpm": 12_000}}, clock=clock, sleep=clock.sleep)
    pacer.record("m", 5_000)
    pacer.correct_last("m", 11_500)  # the API reported more than estimated
    assert pacer.wait("m", 1_000) > 0
    clock.t = 0.0
    pacer2 = bc.Pacer({"m": {"tpm": 12_000}}, clock=clock, sleep=clock.sleep)
    pacer2.record("m", 5_000)
    assert pacer2.wait("m", 1_000) == 0


def test_pacing_limits_match_today_request():
    assert bc.PACING[bc.GEN_MODEL] == {"rpm": 12}
    assert bc.PACING[bc.JUDGE_MODEL] == {"tpm": 12_000}


def _api_with(models, tmp_path, caps=None, tier="free", paid_max=1000):
    api = object.__new__(bc.GeminiApi)
    client = type("C", (), {"models": models})()
    api.clients = {bc.GEN_MODEL: client, bc.JUDGE_MODEL: client}
    api.tiers = {bc.GEN_MODEL: tier, bc.JUDGE_MODEL: "free"}
    api.counter = bc.RequestCounter(tmp_path / "c.json", caps=caps or {}, today=lambda: "d")
    clock = FakeClock()
    api.pacer = bc.Pacer({}, clock=clock, sleep=clock.sleep)
    api.configs = {bc.GEN_MODEL: None, bc.JUDGE_MODEL: None}
    api.paid_max_requests, api.paid_requests = paid_max, 0
    api.paid_log = tmp_path / "paid.jsonl"
    return api


def test_per_minute_429_backs_off_and_continues(tmp_path, monkeypatch):
    class Err(Exception):
        code = 429

    class Resp:
        text = "[]"
        usage_metadata = None

        def model_dump(self, mode):
            return {}

    class Models:
        calls = 0

        def generate_content(self, **_):
            Models.calls += 1
            if Models.calls == 1:
                raise Err("RESOURCE_EXHAUSTED GenerateRequestsPerMinutePerProjectPerModel")
            return Resp()

    slept = []
    monkeypatch.setattr(bc.time, "sleep", slept.append)
    out = _api_with(Models(), tmp_path).request(bc.GEN_MODEL, "p")
    assert out["retries"] == {"429": 1} and Models.calls == 2
    assert slept and slept[0] >= bc.PER_MINUTE_429_MIN_WAIT_S


def test_gen_cap_flag_overrides_todays_cap(tmp_path, monkeypatch):
    seen = {}

    class NoApi:
        def __init__(self, counter, pacer=None, **_):
            seen["caps"] = counter.caps

    monkeypatch.setattr(bc, "GeminiApi", NoApi)
    monkeypatch.setattr(bc, "run_full", lambda ws, api: None)
    monkeypatch.setattr(bc, "COUNTER_PATH", tmp_path / "c.json")
    bc.main(["--run", "--gen-cap", "440"])
    assert seen["caps"][bc.GEN_MODEL] == 440
    assert bc.DAILY_CAP[bc.GEN_MODEL] == 480  # the default is untouched


def test_persistent_server_errors_stop_cleanly(tmp_path, monkeypatch):
    class Err(Exception):
        code = 503

    class Models:
        calls = 0

        def generate_content(self, **_):
            Models.calls += 1
            raise Err("503 UNAVAILABLE high demand")

    monkeypatch.setattr(bc.time, "sleep", lambda _: None)
    with pytest.raises(bc.StopRun, match="persisted through"):
        _api_with(Models(), tmp_path).request(bc.GEN_MODEL, "p")
    assert Models.calls == bc.MAX_RETRIES + 1


def test_non_retryable_errors_still_raise(tmp_path):
    class Err(Exception):
        code = 400

    class Models:
        def generate_content(self, **_):
            raise Err("400 INVALID_ARGUMENT")

    with pytest.raises(Err):
        _api_with(Models(), tmp_path).request(bc.GEN_MODEL, "p")


# --------------------------------------------------------------------------- weekday exemption


@pytest.mark.parametrize(
    "text",
    [
        "installed tuesday, we'll see Monday if it holds",
        "tech came back Wed to finish the rack",
        "fine, see you next Fri",
    ],
)
def test_weekday_names_are_allowed(text):
    assert "date" not in bc.text_violations(text, SPEC)


def _generated(ws, rows):
    for batch, cid, text in rows:
        bc.append_jsonl(
            ws.generated,
            {
                "batch": batch,
                "corpus_ids": [cid],
                "texts": {cid: text},
                "at": "2026-09-23T00:00:00-07:00",
            },
        )


def test_recheck_reinstates_weekday_only_rejections(tmp_path):
    specs = bc.build_test_specs()[:4]
    for i, s in enumerate(specs):
        s.update(batch=f"x-b{i}", min_words=1, max_words=60)
    ws = _ws(tmp_path, specs)
    a, b, c, d = (s["corpus_id"] for s in specs)
    kept = "router firmware updated and the office network has been steady since"
    _generated(
        ws,
        [
            ("x-b0", a, "switch swapped out on tuesday and the ports all light up now"),
            ("x-b1", b, "booked for March 4 and nobody showed up at all"),
            ("x-b2", c, kept),
            ("x-b3", d, kept + " monday"),  # weekday was hiding a near-duplicate
        ],
    )
    for cid, ok, reasons in (
        (a, False, ["date"]),
        (b, False, ["date", "name_like"]),
        (c, True, []),
        (d, False, ["date"]),
    ):
        bc.append_jsonl(
            ws.checks, {"corpus_id": cid, "ok": ok, "reasons": reasons, "duplicate_of": None}
        )
    out = bc.recheck_date_rejections(ws)
    assert out == {"reinstated": 1, "unchanged": 1, "rejected_other": 1}
    res = ws.check_results()
    assert res[a]["ok"] and res[a]["recheck"] == bc.WEEKDAY_RECHECK
    assert res[b]["reasons"] == ["date", "name_like"]
    assert res[d]["reasons"] == ["near_duplicate"]
    assert bc.recheck_date_rejections(ws) == {"unchanged": 1}  # idempotent
    # A reinstated comment goes to the judge like any new one.
    api = FakeApi()
    bc.stage_judge(ws, api, JUDGE_T)
    assert a in ws.judge_labels()


# --------------------------------------------------------------------------- retired specs


def test_retired_minimal_specs_are_never_generated(tmp_path):
    specs = bc.build_test_specs()
    ws = _ws(tmp_path, specs)
    minimal = {s["corpus_id"] for s in specs if s["neutral_kind"] == "minimal"}
    assert len(minimal) == 10
    first_batch = sorted({s["batch"] for s in specs})[0]
    bc.append_jsonl(
        ws.generated,
        {
            "batch": first_batch,
            "corpus_ids": [s["corpus_id"] for s in specs if s["batch"] == first_batch],
            "texts": {},
            "at": "2026-09-23T00:00:00-07:00",
        },
    )
    generated_minimal = {
        s["corpus_id"] for s in specs if s["batch"] == first_batch and s["corpus_id"] in minimal
    }
    n = bc.retire_ungenerated_minimal(ws)
    assert n == len(minimal - generated_minimal) > 0
    assert bc.retire_ungenerated_minimal(ws) == 0  # idempotent
    api = FakeApi()
    bc.stage_generate(ws, api, GEN_T)
    retired = set(ws.retired_ids())
    sent = {c for r in bc.read_jsonl(ws.generated) for c in r["corpus_ids"]}
    assert not retired & sent
    status = bc.select(ws)
    assert all(status[c]["status"] == "retired" for c in retired)
    counts = bc.cell_counts(ws.load_specs(), status)
    assert sum(c["specs"] for c in counts.values()) == len(specs) - len(retired)


def test_new_kind_mix_applies_to_new_specs():
    mix = prm.PARAMS.corpus.neutral_kind_mix.value
    assert dict(mix) == {"minimal": 0.15, "administrative": 0.50, "status": 0.35}
    assert "435" in prm.PARAMS.corpus.neutral_kind_mix.note


# --------------------------------------------------------------------------- paid tier


class _Resp:
    text = "[]"

    class usage_metadata:  # noqa: N801
        prompt_token_count = 1500
        candidates_token_count = 800
        thoughts_token_count = 0
        total_token_count = 2300

    def model_dump(self, mode):
        return {}


class _OkModels:
    def generate_content(self, **_):
        return _Resp()


def test_paid_session_cap_stops_cleanly(tmp_path):
    api = _api_with(_OkModels(), tmp_path, tier="paid", paid_max=2)
    api.request(bc.GEN_MODEL, "p")
    api.request(bc.GEN_MODEL, "p")
    with pytest.raises(bc.StopRun, match="paid session cap 2"):
        api.request(bc.GEN_MODEL, "p")
    api.request(bc.JUDGE_MODEL, "p")  # the free-tier judge is not capped by it
    assert api.counter.used(bc.GEN_MODEL + "@paid") == 2
    assert api.counter.used(bc.GEN_MODEL) == 0  # paid never eats the free count


def test_paid_cap_stops_pipeline_cleanly(tmp_path):
    ws = _ws(tmp_path)

    class Capped(FakeApi):
        def __init__(self):
            super().__init__()
            self.paid = 0

        def request(self, model, prompt):
            if model == bc.GEN_MODEL:
                if self.paid >= 1:
                    raise bc.StopRun("paid session cap 1 reached")
                self.paid += 1
            return super().request(model, prompt)

    stopped = bc.run_pipeline(ws, Capped(), gen_template=GEN_T, judge_template=JUDGE_T)
    assert "paid session cap" in stopped
    assert len(ws.generated_batches()) == 1


def test_paid_requests_logged_with_cost(tmp_path):
    api = _api_with(_OkModels(), tmp_path, tier="paid")
    out = api.request(bc.GEN_MODEL, "p")
    assert out["tier"] == "paid" and out["usage"] == {"input": 1500, "output": 800}
    (row,) = bc.read_jsonl(api.paid_log)
    assert row["input_tokens"] == 1500 and row["output_tokens"] == 800
    assert row["cost_usd"] == pytest.approx(1500 * 0.30 / 1e6 + 800 * 2.50 / 1e6)
    s = bc.paid_summary(api.paid_log)
    assert s["requests"] == 1 and s["estimated_cost_usd"] == pytest.approx(0.00245, abs=1e-6)
    assert bc.request_cost(1_000_000, 0) == pytest.approx(0.30)
    assert bc.request_cost(0, 1_000_000) == pytest.approx(2.50)
    free = _api_with(_OkModels(), tmp_path / "f", tier="free")
    assert free.request(bc.GEN_MODEL, "p")["tier"] == "free"
    assert not (tmp_path / "f" / "paid.jsonl").exists()


def test_correct_key_per_model(tmp_path, monkeypatch, capsys):
    import google.genai as genai

    made = []

    class FakeClient:
        def __init__(self, api_key):
            made.append(api_key)
            self.api_key = api_key

    monkeypatch.setattr(genai, "Client", FakeClient)
    monkeypatch.setenv("GOOGLE_AI_API_KEY", "free-key-123")
    monkeypatch.setenv("GOOGLE_AI_API_KEY_PAID", "paid-key-456")
    counter = bc.RequestCounter(tmp_path / "c.json", caps={}, today=lambda: "d")
    paid = bc.GeminiApi(counter, paid=True)
    assert paid.clients[bc.GEN_MODEL].api_key == "paid-key-456"
    assert paid.clients[bc.JUDGE_MODEL].api_key == "free-key-123"
    assert paid.pacer.limits[bc.GEN_MODEL] == {"rpm": bc.PAID_RPM}
    free = bc.GeminiApi(counter)
    assert free.clients[bc.GEN_MODEL].api_key == "free-key-123"
    assert free.pacer.limits[bc.GEN_MODEL] == {"rpm": 12}
    out = capsys.readouterr()
    assert "123" not in out.out + out.err and "456" not in out.out + out.err


def test_paid_flag_needs_its_key(tmp_path, monkeypatch):
    import google.genai as genai

    monkeypatch.setattr(genai, "Client", lambda api_key: object())
    monkeypatch.setenv("GOOGLE_AI_API_KEY", "free")
    monkeypatch.setenv("GOOGLE_AI_API_KEY_PAID", "")
    with pytest.raises(SystemExit, match="GOOGLE_AI_API_KEY_PAID is not set"):
        bc.GeminiApi(bc.RequestCounter(tmp_path / "c.json", caps={}), paid=True)


def test_capitalised_weekday_no_longer_trips_name_check(tmp_path):
    text = "switch swapped Tuesday and the ports all light up now"
    assert bc.text_violations(text, SPEC) == []
    assert "name_like" in bc.text_violations("thanks to Velcro for the cable ties", SPEC)
    specs = bc.build_test_specs()[:1]
    specs[0].update(batch="x-b0", min_words=1, max_words=60)
    ws = _ws(tmp_path, specs)
    cid = specs[0]["corpus_id"]
    _generated(ws, [("x-b0", cid, text)])
    bc.append_jsonl(
        ws.checks,
        {"corpus_id": cid, "ok": False, "reasons": ["date", "name_like"], "duplicate_of": None},
    )
    assert bc.recheck_date_rejections(ws) == {"reinstated": 1}
    assert ws.check_results()[cid]["ok"]
