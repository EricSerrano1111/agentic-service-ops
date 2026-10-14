"""The gateway gives every request a trace id and forwards it (ADR-108)."""

from __future__ import annotations

import re

from gateway_testkit import Kit

HEX32 = re.compile(r"[0-9a-f]{32}")


def test_a_request_without_an_id_gets_one_returned_and_forwarded(tmp_path):
    kit = Kit(tmp_path)
    kit.sign_in()
    r = kit.ask()
    tid = r.headers["X-Trace-Id"]
    assert HEX32.fullmatch(tid)
    assert kit.upstream.requests[-1].headers["X-Trace-Id"] == tid


def test_a_valid_incoming_id_is_kept_end_to_end(tmp_path):
    kit = Kit(tmp_path)
    kit.sign_in()
    tid = "cd" * 16
    r = kit.client.post(
        "/api/ask",
        json={"question": "q"},
        headers={"Origin": "https://testserver", "X-Trace-Id": tid},
    )
    assert r.headers["X-Trace-Id"] == tid
    assert kit.upstream.requests[-1].headers["X-Trace-Id"] == tid


def test_an_invalid_incoming_id_is_replaced_not_forwarded(tmp_path):
    kit = Kit(tmp_path)
    kit.sign_in()
    r = kit.client.post(
        "/api/ask",
        json={"question": "q"},
        headers={"Origin": "https://testserver", "X-Trace-Id": "not-an-id"},
    )
    assert HEX32.fullmatch(r.headers["X-Trace-Id"])
    assert kit.upstream.requests[-1].headers["X-Trace-Id"] == r.headers["X-Trace-Id"]


def test_every_response_carries_an_id_errors_and_unknown_paths_included(tmp_path):
    kit = Kit(tmp_path)
    assert HEX32.fullmatch(kit.client.get("/healthz").headers["X-Trace-Id"])
    assert HEX32.fullmatch(kit.client.get("/no-such-path").headers["X-Trace-Id"])
    assert HEX32.fullmatch(kit.ask().headers["X-Trace-Id"])  # a 401: no session


def test_the_hourly_cap_defaults_to_30_and_the_daily_cap_to_50():
    """ADR-107: raised from 15; the daily cap is unchanged."""
    from api_gateway.config import Settings

    settings = Settings(session_key="k" * 48, public_origin="https://x.test")
    assert settings.asks_per_session_hour == 30
    assert settings.daily_question_cap == 50


def test_the_cloud_definition_and_compose_say_30():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[3]
    cloud = (root / "deploy" / "cloudrun" / "gateway.yaml").read_text("utf-8")
    assert 'GATEWAY_ASKS_PER_SESSION_HOUR\n          value: "30"' in cloud.replace("\r\n", "\n")
    assert "GATEWAY_ASKS_PER_SESSION_HOUR:-30" in (root / "docker-compose.yml").read_text("utf-8")
