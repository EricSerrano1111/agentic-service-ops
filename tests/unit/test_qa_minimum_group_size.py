"""The small-sample minimum is the data dictionary's 20, in every shipped configuration
(§6 "Answer text" rule 4; ADR-092). QA uses the rule's 20 and never reads the setting, so a
deployment that set another value would make QA fail correct answers; this test is that guard.
"""

from __future__ import annotations

import re
from pathlib import Path

from agent_qa import slots
from agent_reporting.config import Settings

ROOT = Path(__file__).resolve().parents[2]
SHIPPED = [
    ROOT / "docker-compose.yml",
    ROOT / ".env.example",
    *sorted((ROOT / "deploy").rglob("*")),
]
_SETTING = re.compile(r"REPORTING_MIN_GROUP_DENOMINATOR\s*[:=]\s*\$?\{?[A-Z_]*:?-?\"?(\d+)")


def test_the_rules_minimum_is_20_and_the_agents_default_is_the_same():
    assert slots.MIN_CASES == 20
    assert Settings().min_group_denominator == 20


def test_no_shipped_configuration_sets_another_minimum():
    found = {}
    for path in SHIPPED:
        if not path.is_file() or path.suffix in {".png", ".pyc"}:
            continue
        for match in _SETTING.finditer(path.read_text(encoding="utf-8", errors="ignore")):
            found.setdefault(path.name, []).append(int(match.group(1)))
    assert found, "the setting is expected in docker-compose.yml at least"
    assert {n for values in found.values() for n in values} == {20}, found


def test_qa_does_not_read_the_setting():
    qa = (ROOT / "services" / "agent_qa" / "src" / "agent_qa").rglob("*.py")
    assert not any("REPORTING_MIN_GROUP_DENOMINATOR" in p.read_text(encoding="utf-8") for p in qa)
