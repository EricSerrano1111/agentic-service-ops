"""The UI's source against data dictionary section 6, "Answer display (UI)".

There is no browser in the unit suite, so these read the source files. What they prove: every
user-facing string in rules 1 and 3 to 9 is in the source exactly as the dictionary writes it, the
timer is fed only by the browser's own clock, an example click only fills and focuses the input,
and the export's rules (no inline styles, no new packages, one live region) hold in the source.
What they do not prove: that the page renders as intended. The built export is checked by the
`ui-build` job (Docker build and the `web/tests` helper tests), and the pages by eye
(`docs/screenshots/`).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from api_gateway.app import DEADLINE_MESSAGE, UNKNOWN_UPSTREAM, UPSTREAM_MESSAGES
from api_gateway.interpret import QA_WORDS

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web" / "app"
DICTIONARY = (ROOT / "docs" / "data-dictionary.md").read_text(encoding="utf-8")
SECTION = DICTIONARY.split("### Answer display (UI)", 1)[1].split("### Forecast target", 1)[0]


def source(*parts: str) -> str:
    return (WEB.joinpath(*parts)).read_text(encoding="utf-8")


def rule(number: int) -> str:
    """The text of one numbered rule of section 6."""
    start = SECTION.index(f"**{number}. ")
    following = re.search(r"\n\*\*\d+\. ", SECTION[start + 3 :])
    return SECTION[start : start + 3 + following.start()] if following else SECTION[start:]


# ---------------------------------------------------------------- rules 1, 3, 4, 5


def test_rule_3_words_are_the_gateways_exact_words():
    table = rule(3)
    for status, words in QA_WORDS.items():
        assert f'| `{status}` | "{words}" |' in table


def test_rule_5_messages_are_the_gateways_exact_sentences():
    text = rule(5)
    for _, message in UPSTREAM_MESSAGES.values():
        assert f'"{message}"' in text
    assert f'"{UNKNOWN_UPSTREAM}"' in text
    assert f'"{DEADLINE_MESSAGE}"' in text


def test_the_page_shows_the_labels_of_rules_1_and_4():
    page = source("page.jsx")
    assert "Interpreted as:" in page
    assert "Sent for follow-up. {result.warning}" in page
    # rule 1's order: answer, Interpreted as, verification line, follow-up flag
    order = [page.index(token) for token in ("answer-text", "interpreted", "qa_text", "escalate")]
    assert order == sorted(order)


def test_the_ui_fallback_sentences_are_unchanged():
    page = source("page.jsx")
    for sentence in (
        "An invite link is required. Open the link you were sent to sign in.",
        "The request could not be completed. Please try again.",
        "The service could not be reached. Please try again.",
        "{question.length} of {MAX_QUESTION} characters. Answers can take up to two minutes.",
    ):
        assert sentence in page


# ---------------------------------------------------------------- rule 6


def test_the_notice_is_in_one_component_that_the_layout_puts_on_every_page():
    """Rule 6 (TS-20-E). The built `index.html` carries the same string."""
    text = (
        "Demonstration system: all data here is synthetic, generated for this project, and "
        "describes no real company, customer, technician or operation. The sentiment model was "
        "trained on synthetically written customer feedback, so its results may not reflect how "
        "real customers write."
    )
    component = source("components", "Notice.jsx")
    joined = "".join(re.findall(r'"([^"\n]*)"', component.split("export default")[0]))
    assert text in joined
    assert 'id="synthetic-notice"' in component and 'data-testid="synthetic-notice"' in component
    layout = source("layout.jsx")
    assert layout.count("<Notice />") == 1 and "{children}" in layout
    assert "Notice" not in source("page.jsx")  # shown once, by the layout, never twice
    assert text in SECTION  # the revised notice, as the dictionary now writes it


# ---------------------------------------------------------------- rule 7


def test_the_timer_wording_is_rule_7s():
    timer = (WEB / "lib" / "timer.mjs").read_text(encoding="utf-8")
    for fragment in ("Working… ${", "Answered in ${", "Ended after ${", "toFixed(1)", "Math.floor"):
        assert fragment in timer
    assert '"Working… N s"' in rule(7) and '"Answered in N.N s"' in rule(7)
    assert '"Ended after N.N s"' in rule(7)


def test_the_timer_reads_no_response_field():
    timer = (WEB / "lib" / "timer.mjs").read_text(encoding="utf-8")
    code = re.sub(r"/\*.*?\*/|//.*", "", timer, flags=re.DOTALL)
    assert "import" not in code
    for word in ("result", "body", "response", "res.", "trace", "json", "headers"):
        assert word not in code
    page = source("page.jsx")
    # the only value that reaches the labels is the browser's own clock reading
    assigned = re.findall(r"\bms(?::| =) ([^,;\n]+)", page)
    assert assigned and all(a.strip() == "performance.now() - sentAt.current" for a in assigned)
    assert "workingLabel(elapsed)" in page and "finishedLabel(run.ms," in page
    assert "setElapsed(performance.now() - sentAt.current)" in page


def test_the_timer_sits_outside_the_live_region_and_there_is_one_live_region():
    page = source("page.jsx")
    assert page.count("aria-live") == 1
    assert page.index('data-testid="timer"') < page.index("aria-live")
    others = [p for p in WEB.rglob("*.jsx") if p != WEB / "page.jsx"]
    assert all("aria-live" not in p.read_text(encoding="utf-8") for p in others)


# ---------------------------------------------------------------- rule 9


def _quoted(text: str) -> list[str]:
    return re.findall(r'"([^"]+)"', text)


def test_rule_9_examples_are_in_the_source_exactly():
    text = rule(9)
    examples = (WEB / "lib" / "examples.mjs").read_text(encoding="utf-8")
    questions = [q for q in _quoted(text) if q.endswith("?") or q.startswith("Show examples")]
    assert len(questions) == 7
    for question in questions:
        assert json.dumps(question) in examples or f'"{question}"' in examples
    for caption in ("too open: it asks you to choose", "out of scope: it declines"):
        assert f'"{caption}"' in text and f'"{caption}"' in examples


def test_clicking_an_example_fills_and_focuses_and_never_submits():
    page = source("page.jsx")
    assert re.search(r'<button\s+key=\{item\.q\}\s+type="button"', page)
    body = re.search(r"function fillExample\(text\) \{(.*?)\n  \}", page, re.DOTALL).group(1)
    assert "setQuestion(text)" in body and "inputRef.current?.focus()" in body
    for forbidden in ("submit", "requestSubmit", "postJson", "fetch", "setRun"):
        assert forbidden not in body
    assert "onClick={() => fillExample(item.q)}" in page


# ---------------------------------------------------------------- the pages and the export rules


def test_the_nav_has_three_links_and_no_evaluation_results_yet():
    header = source("components", "SiteHeader.jsx")
    for href, label in (("/", "Ask"), ("/how-it-works/", "How it works"), ("/faq/", "FAQ")):
        assert f'{{ href: "{href}", label: "{label}" }}' in header
    assert "Evaluation results" not in re.sub(r"//.*", "", header)


def test_the_recomputed_line_of_the_first_mockup_is_not_in_the_source():
    everything = "".join(p.read_text(encoding="utf-8") for p in WEB.rglob("*.jsx"))
    assert "QA recomputed" not in everything


# ---------------------------------------------------------------- rule 10 (the answer journey)


def _code(*parts: str) -> str:
    """A source file without its comments."""
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", source(*parts), flags=re.S)


def test_rule_10_button_and_panel_words_are_in_the_source():
    page, panel = source("page.jsx"), source("components", "JourneyPanel.jsx")
    assert "Show the answer journey" in page and "Hide the answer journey" in page
    assert "aria-expanded={showJourney}" in page and 'aria-controls="journey-panel"' in page
    assert 'id="journey-panel"' in panel and "Answer journey" in panel
    where = source("lib", "journey.mjs") + source("components", "ArchitectureDiagram.jsx")
    for words in (
        "Server time",
        "in your browser",
        "Model calls:",
        "Estimated cost:",
        "(list price)",
        "QA figures check:",
        "Interpretation check:",
        "not called",
    ):
        assert words in where, words


def test_the_button_is_shown_only_when_the_response_carries_a_journey():
    page = source("page.jsx")
    assert page.count("hasJourney(run.result)") == 2  # the button and the panel
    assert 'run.status === "done" && hasJourney(run.result)' in page
    assert "export function hasJourney" in source("lib", "journey.mjs")


def test_the_journey_is_drawn_from_journey_fields_only():
    code = _code("components", "JourneyPanel.jsx")
    assert not re.search(r"result\.(answer|headline|interpreted_as|qa_text)", code)
    assert "journey.hops" in code
    # the routed line takes the journey, never the answer text
    assert "routedLine(run.result.journey)" in _code("page.jsx")


def test_bar_positions_come_from_start_and_duration_only():
    lib = _code("lib", "journey.mjs")
    layout = lib.split("export function barLayout", 1)[1].split("\n}\n", 1)[0]
    assert "h.start_ms" in layout and "h.duration_ms" in layout
    for forbidden in ("h.service", "h.step", "h.status", "answer", "question"):
        assert forbidden not in layout, forbidden


def test_the_replay_respects_reduced_motion_and_the_panel_is_not_a_live_region():
    panel = source("components", "JourneyPanel.jsx")
    assert "prefersReducedMotion()" in panel
    assert "if (reduced || replays === 0) return undefined;" in panel
    assert "{!reduced && (" in panel  # no Replay button without motion
    assert "aria-live" not in panel
    assert "prefers-reduced-motion: reduce" in source("lib", "journey.mjs")
    assert ".dg-box { transition: none; }" in source("globals.css")


def test_the_replay_takes_about_a_second_and_a_half():
    assert "REPLAY_TOTAL_MS = 1500" in source("lib", "journey.mjs")


def test_the_faq_has_8_to_10_entries_and_how_it_works_has_its_diagram():
    faq = source("faq", "page.jsx")
    assert 8 <= faq.count("    q: ") <= 10
    how = source("how-it-works", "page.jsx")
    diagram = source("components", "ArchitectureDiagram.jsx")
    assert "<ArchitectureDiagram />" in how and "<ol" in how
    assert 'role="img"' in diagram and "aria-label=" in diagram


def test_no_inline_styles_and_no_new_packages():
    for path in WEB.rglob("*.jsx"):
        assert "style=" not in path.read_text(encoding="utf-8"), path
    package = json.loads((ROOT / "web" / "package.json").read_text(encoding="utf-8"))
    assert set(package["dependencies"]) == {"next", "react", "react-dom"}
    assert "devDependencies" not in package


@pytest.mark.parametrize("token", ["prefers-color-scheme: dark", "prefers-reduced-motion"])
def test_the_stylesheet_has_the_dark_scheme_and_respects_reduced_motion(token):
    assert token in source("globals.css")
