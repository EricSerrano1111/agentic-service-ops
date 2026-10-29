"""Build web/data/results.json: the figures on the /results/ page, each read from a committed file.

Data dictionary section 6, rule 11. Every figure carries its source path, the source's SHA-256,
a locator and the evaluation report section that cites it. Nothing here touches the network, a
database or a model, and the output is deterministic (sorted keys, LF line endings).

    python scripts/build_results_data.py            # rewrite web/data/results.json
    python scripts/build_results_data.py --check    # exit 1 if the committed file is stale

A SHA-256 is taken over the file with CRLF turned into LF, so a Windows and a Linux checkout
agree. For the three living documents that gain entries all the time, it is taken over the quoted
line instead (rule 11), so an unrelated entry does not break the build.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "data" / "results.json"
REPORT = "docs/evaluation-report.md"
LIVING = {"docs/decisions-log.md", "docs/sprint-log.md", "docs/production-grade-audit.md"}

ROUTING = "evals/results/routing_heldout_v1/2026-10-13/score.json"
GOLDEN = "evals/results/golden_v2/2026-10-13/score.json"
OWNER_REVIEW = "evals/results/sprint5_x/golden_owner_review.csv"
QA_M1 = "evals/results/qa_faults/2026-10-10/report.md"
QA_M2 = "evals/results/qa_faults/2026-10-10-m2/report.md"
BERT = "evals/results/sentiment/2026-10-01_bert_v1/bert_v1.test.metrics.json"
TFIDF = "evals/results/sentiment/2026-10-01_baselines/tfidf_logreg.test.metrics.json"
HOLDOUT = "evals/results/forecast/2026-10-02_holdout/holdout.json"
MANIFEST = "ml/forecast/artifacts/volume_v2.manifest.json"
LEDGER = "evals/results/sprint5_x_ledger.json"
DECISIONS = "docs/decisions-log.md"
AUDIT = "docs/production-grade-audit.md"
SPRINT_LOG = "docs/sprint-log.md"

FR03_ROW = "| **Both** | **ambiguous recognised** | **10 of 15** | **0 of 15** |"
NO_GO = (
    "**P2: no-go. The attempt has failed and FR-03 is unmet, with no further attempt (ADR-113).**"
)
QA_M1_QUOTE = "219/223 = 98.2% (95% Wilson 95.5-99.3%)"
QA_M2_QUOTE = "223/223 = 100.0% (95% Wilson 98.3-100.0%)"
AUDIT_QUOTE = "so 11 of 12 boxes are ticked"
GCP_QUOTE = "**GCP cost from 2026-10-01 to 10-28 is $8.79,**"
HOLDOUT_MODEL = "/models/loglinear_robust_v2/total/model/overall/mape"  # `volume_v2` (ADR-070)
HOLDOUT_NAIVE = "/models/loglinear_robust_v2/total/baseline/overall/mape"


# ---------------------------------------------------------------------------- reading files


def read_text(path: str) -> str:
    return (ROOT / path).read_bytes().decode("utf-8").replace("\r\n", "\n")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def pointer(document, ptr: str):
    """RFC 6901 for the subset used here: `/a/0/b`."""
    node = document
    for part in ptr.lstrip("/").split("/"):
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def quoted_line(text: str, quote: str) -> str:
    lines = [line for line in text.split("\n") if quote in line]
    if len(lines) != 1:
        raise ValueError(f"expected exactly one line containing {quote!r}, found {len(lines)}")
    return lines[0]


def served_count(manifest: dict) -> tuple[int, int]:
    bands = [band for sl in manifest["serving"]["slices"].values() for band in sl.values()]
    return sum(1 for b in bands if b["served"]), len(bands)


def owner_count(path: str) -> tuple[int, int]:
    rows = list(csv.DictReader(io.StringIO(read_text(path))))
    return sum(1 for r in rows if r["owner_pass"] == "Y"), len(rows)


# ---------------------------------------------------------------------------- entries


def figure(
    group, label, text, section, source, locator, located, number=None, of=None, report_text=None
):
    """One entry. `located` is what the locator finds in `source`; the tests find it again.

    `report_text` is how the report prints the figure when that differs from `text`."""
    body = read_text(source)
    if source in LIVING:
        hashed, digest = "line", sha256(quoted_line(body, locator["quote"]))
    else:
        hashed, digest = "file", sha256(body)
    entry = {
        "group": group,
        "label": label,
        "text": text,
        "report_section": section,
        "source": source,
        "sha256": digest,
        "hashed": hashed,
        "locator": locator,
        "located": located,
    }
    if number is not None:
        entry["number"] = number
    if of is not None:
        entry["of"] = of
    if report_text is not None:
        entry["report_text"] = report_text
    return entry


def json_figure(group, label, text, section, source, pointers, number=None, of=None):
    document = json.loads(read_text(source))
    located = [pointer(document, p) for p in pointers]
    locator = {"kind": "json_pointer", "pointers": pointers}
    return figure(group, label, text(located), section, source, locator, located, number, of)


def build_figures() -> dict[str, dict]:
    figs: dict[str, dict] = {}
    route = json.loads(read_text(ROUTING))

    # -- routing (report 4.1): the three runs, then the diagnostics
    for i in range(3):
        n, c = route["runs"][i]["n"], route["runs"][i]["correct"]
        figs[f"routing_heldout_run{i + 1}"] = json_figure(
            "routing_heldout",
            f"Held-out routing, run {i + 1}",
            lambda v: f"{v[0]} of {v[1]}",
            "4.1",
            ROUTING,
            [f"/runs/{i}/correct", f"/runs/{i}/n"],
            number=c,
            of=n,
        )
    figs["routing_heldout_without_ambiguous"] = json_figure(
        "routing_heldout",
        "Without the ambiguous items",
        lambda v: f"{v[0]} of {v[1]}",
        "4.1",
        ROUTING,
        ["/runs/0/correct_without_ambiguous", "/runs/0/n_without_ambiguous"],
        number=route["runs"][0]["correct_without_ambiguous"],
        of=route["runs"][0]["n_without_ambiguous"],
    )
    figs["routing_heldout_ambiguous_not_flagged"] = json_figure(
        "routing_heldout",
        "Ambiguous questions not flagged",
        lambda v: f"{v[0]} item-runs",
        "4.1",
        ROUTING,
        ["/taxonomy/ambiguous not flagged"],
        number=route["taxonomy"]["ambiguous not flagged"],
    )
    figs["routing_heldout_out_of_scope_accepted"] = json_figure(
        "routing_heldout",
        "Out-of-scope questions accepted",
        lambda v: f"{v[0]} item-runs",
        "4.1",
        ROUTING,
        ["/taxonomy/out-of-scope accepted"],
        number=route["taxonomy"]["out-of-scope accepted"],
    )

    # -- golden (report 4.2)
    golden = json.loads(read_text(GOLDEN))
    figs["golden_mechanical"] = json_figure(
        "golden",
        "Golden set, mechanical rules",
        lambda v: f"{v[0]} of {v[1]}",
        "4.2",
        GOLDEN,
        ["/passed", "/n_scored"],
        number=golden["passed"],
        of=golden["n_scored"],
    )
    yes, rows = owner_count(OWNER_REVIEW)
    figs["golden_owner"] = figure(
        "golden",
        "Golden set, owner's judgement",
        f"{yes} of {rows}",
        "4.2",
        OWNER_REVIEW,
        {"kind": "csv_count", "column": "owner_pass", "equals": "Y"},
        [yes, rows],
        yes,
        rows,
    )

    # -- QA fault catch rate (report 4.3)
    for key, source, quote, label in (
        ("m1", QA_M1, QA_M1_QUOTE, "QA fault cases caught, first measurement"),
        ("m2", QA_M2, QA_M2_QUOTE, "QA fault cases caught, after fixes"),
    ):
        caught, total, rate = re.search(r"(\d+)/(\d+) = ([\d.]+)%", quote).groups()
        locator = {"kind": "markdown_line", "quote": quote}
        figs[f"qa_faults_{key}"] = figure(
            "qa_faults",
            label,
            f"{caught} of {total}",
            "4.3",
            source,
            locator,
            [int(caught), int(total)],
            int(caught),
            int(total),
        )
        if key == "m1":
            figs["qa_faults_m1_rate"] = figure(
                "qa_faults",
                "First measurement, as a rate",
                f"{rate}%",
                "4.3",
                source,
                locator,
                [rate],
                float(rate),
            )

    # -- sentiment (report 4.5)
    for key, source, label in (
        ("bert", BERT, "BERT (`bert_v1`)"),
        ("tfidf", TFIDF, "TF-IDF + logistic regression"),
    ):
        value = json.loads(read_text(source))["macro_f1"]
        figs[f"sentiment_{key}"] = json_figure(
            "sentiment",
            f"{label}, macro-F1",
            lambda v: f"{v[0]:.4f}",
            "4.5",
            source,
            ["/macro_f1"],
            number=value,
        )

    # -- forecast (report 4.4)
    holdout = json.loads(read_text(HOLDOUT))
    for key, ptr, label in (
        ("volume_v2", HOLDOUT_MODEL, "`volume_v2`, holdout MAPE"),
        ("seasonal_naive", HOLDOUT_NAIVE, "Seasonal naive, holdout MAPE"),
    ):
        figs[f"forecast_holdout_{key}"] = json_figure(
            "forecast_holdout",
            label,
            lambda v: f"{v[0]:.2f}%",
            "4.4",
            HOLDOUT,
            [ptr],
            number=round(pointer(holdout, ptr), 2),
        )
    served, bands = served_count(json.loads(read_text(MANIFEST)))
    figs["forecast_served"] = figure(
        "forecast_served",
        "Slice-bands served",
        f"{served} of {bands}",
        "4.4",
        MANIFEST,
        {"kind": "json_count", "container": "/serving/slices", "field": "served", "equals": True},
        [served, bands],
        served,
        bands,
    )

    # -- FR-03 (report 6)
    fr03_locator = {"kind": "markdown_line", "quote": FR03_ROW}
    (v6, v6_of), (v3, v3_of) = (
        (int(a), int(b)) for a, b in re.findall(r"\*\*(\d+) of (\d+)\*\*", FR03_ROW)
    )
    for key, label, got, of in (
        ("route_v6", "`route_v6`, ambiguous recognised", v6, v6_of),
        ("route_v3", "`route_v3`, ambiguous recognised", v3, v3_of),
    ):
        figs[f"fr03_{key}"] = figure(
            "fr03",
            label,
            f"{got} of {of}",
            "6",
            DECISIONS,
            fr03_locator,
            [v6, v6_of, v3, v3_of],
            got,
            of,
        )
    figs["fr03_third_attempt"] = figure(
        "fr03",
        "FR-03's third attempt (ADR-114)",
        "no-go",
        "6",
        DECISIONS,
        {"kind": "markdown_line", "quote": NO_GO},
        ["no-go"],
    )

    # -- production-grade status (report 8)
    ticked, items = re.search(r"(\d+) of (\d+) boxes", AUDIT_QUOTE).groups()
    figs["production_grade"] = figure(
        "production_grade",
        "Checklist items ticked",
        f"{ticked} of {items}",
        "8",
        AUDIT,
        {"kind": "markdown_line", "quote": AUDIT_QUOTE},
        [int(ticked), int(items)],
        int(ticked),
        int(items),
        report_text="11 of the 12",
    )

    # -- cost (report 4.7)
    ledger = json.loads(read_text(LEDGER))
    figs["cost_heldout"] = json_figure(
        "cost",
        "Held-out routing and golden run, list price",
        lambda v: f"${v[0]}",
        "4.7",
        LEDGER,
        ["/cost_usd_known"],
        number=ledger["cost_usd_known"],
    )
    figs["cost_heldout_requests"] = json_figure(
        "cost",
        "Requests in that run",
        lambda v: f"{v[0]} requests",
        "4.7",
        LEDGER,
        ["/requests"],
        number=ledger["requests"],
    )
    figs["cost_gcp"] = figure(
        "cost",
        "GCP cost, 2026-10-01 to 2026-10-28",
        "$8.79",
        "4.7",
        SPRINT_LOG,
        {"kind": "markdown_line", "quote": GCP_QUOTE},
        ["8.79"],
    )
    return figs


def build() -> str:
    document = {
        "report": REPORT,
        "note": "Generated by scripts/build_results_data.py (data dictionary section 6, rule 11).",
        "figures": build_figures(),
    }
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    text = build()
    if argv[1:] == ["--check"]:
        current = OUT.read_bytes().decode("utf-8").replace("\r\n", "\n") if OUT.exists() else ""
        if current != text:
            print(f"{OUT.relative_to(ROOT)} is stale: run scripts/build_results_data.py")
            return 1
        print("results.json is current")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(text.encode("utf-8"))
    print(f"wrote {OUT.relative_to(ROOT)}: {len(json.loads(text)['figures'])} figures")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
