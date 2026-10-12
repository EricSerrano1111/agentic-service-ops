"""The Sprint 5 evaluation freeze (ADR-103): every prompt file, the default router, the
shipped interpretation prompt, the mode flags and the models are what the freeze recorded.

If this fails, the frozen evaluation state changed. Only changes that alter no answer and no
`qa_status` are allowed after the freeze (the Next.js pin, the trace ID, logging, UI copy
outside section 6's answer rules; ADR-103). Any other change invalidates Prompt X's runs and
needs a new ADR; then the runs are repeated and `evals/freeze_s5.json` is re-recorded.
"""

from __future__ import annotations

import glob
import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FROZEN = json.loads((ROOT / "evals" / "freeze_s5.json").read_text("utf-8"))
HOW = (
    "The frozen evaluation state changed (ADR-103, evals/freeze_s5.json). Only changes that alter "
    "no answer and no qa_status may follow the freeze; anything else invalidates Prompt X's runs "
    "and needs a new ADR."
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_every_prompt_file_hash_is_the_frozen_one():
    current = {
        Path(p).as_posix(): sha256(ROOT / p)
        for p in sorted(glob.glob("services/*/prompts/*.md", root_dir=ROOT))
    }
    frozen = FROZEN["prompts_sha256"]
    assert set(current) == set(frozen), f"{HOW} Prompt files added or removed."
    for name, digest in frozen.items():
        assert current[name] == digest, f"{HOW} Changed: {name}"


def test_the_default_router_and_interpretation_prompt_are_the_frozen_ones():
    sys.path.insert(0, str(ROOT / "services" / "orchestrator" / "src"))
    sys.path.insert(0, str(ROOT / "services" / "agent_qa" / "src"))
    from agent_qa import interpretation
    from orchestrator import routing

    assert FROZEN["default_router"] == routing.PROMPT_NAME, HOW
    assert FROZEN["shipped_interpretation_prompt"] == interpretation.PROMPT_NAME, HOW


def test_the_mode_flags_are_the_frozen_ones():
    from agent_qa import config

    assert config.Settings.interp_mode == FROZEN["flags"]["QA_INTERP_MODE"], HOW
    assert config.Settings.forecast_recompute is (FROZEN["flags"]["QA_FORECAST_RECOMPUTE"] == "on")
    qa = (ROOT / "deploy" / "cloudrun" / "qa.yaml").read_text("utf-8")
    assert re.search(r"QA_INTERP_MODE\s*\n\s*value: advisory", qa), HOW
    assert re.search(r"QA_FORECAST_RECOMPUTE\s*\n\s*value: \"on\"", qa), HOW
    sentiment = (ROOT / "deploy" / "cloudrun" / "sentiment.yaml").read_text("utf-8")
    scoring = FROZEN["flags"]["MCP_FEEDBACK_SCORING_deploy"]
    assert re.search(rf"MCP_FEEDBACK_SCORING\s*\n\s*value: {scoring}", sentiment), HOW


@pytest.mark.parametrize("role", ["orchestrator", "specialist", "qa"])
def test_the_runtime_models_and_thinking_levels_are_the_frozen_ones(role):
    env = (ROOT / ".env.example").read_text("utf-8")
    model = re.search(rf"^GEMINI_MODEL_{role.upper()}=(.*)$", env, re.M).group(1).strip()
    assert model == FROZEN["models"][role]["model"], HOW
    level = re.search(rf"^LLM_THINKING_LEVEL_{role.upper()}=(.*)$", env, re.M).group(1).strip()
    assert level == "", f"{HOW} (a blank level means the model's lowest, `minimal`)"


def test_the_retry_cap_and_as_of_date_are_the_frozen_ones():
    sys.path.insert(0, str(ROOT / "services" / "orchestrator" / "src"))
    from orchestrator import config

    caps = FROZEN["thresholds_and_caps"]
    assert config.Settings.max_qa_retry_attempts == caps["MAX_QA_RETRY_ATTEMPTS"], HOW
    assert str(config.Settings.as_of) == caps["as_of_date"], HOW
    assert config.Settings.route_timeout_s == caps["route_timeout_s"], HOW
    assert config.Settings.qa_a2a_timeout_s == caps["qa_a2a_timeout_s"], HOW
