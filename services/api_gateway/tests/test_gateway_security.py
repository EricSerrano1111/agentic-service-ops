"""Headers and the CSP, limits, logging, the invite store and the admin tool (ADR-097)."""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from api_gateway import csp
from api_gateway.app import create_app
from api_gateway.config import GatewayConfigError, Settings
from api_gateway.invites import (
    CACHE_TTL_S,
    FileInviteStore,
    SecretManagerInviteStore,
    dump_document,
    find_by_token,
    new_invite,
)
from api_gateway.upstream import IdTokenProvider, Orchestrator
from fastapi.testclient import TestClient
from gateway_testkit import KEY, NOW, ORIGIN, Kit, Upstream

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
def kit(tmp_path) -> Kit:
    return Kit(tmp_path)


# ---------------------------------------------------------------- the export and the CSP

EXPORT_HTML = """<!DOCTYPE html><html><head><title>t</title>
<script src="/_next/static/chunks/main.js" async></script>
<script>self.__next_f=self.__next_f||[];self.__next_f.push([0])</script>
<script>self.__next_f.push([1,"hello"])</script>
</head><body><div id="root">hi</div><script type="application/json">{"a":1}</script></body></html>
"""


@pytest.fixture
def export(tmp_path) -> Path:
    out = tmp_path / "out"
    (out / "_next").mkdir(parents=True)
    (out / "index.html").write_text(EXPORT_HTML, encoding="utf-8")
    (out / "404.html").write_text(EXPORT_HTML, encoding="utf-8")
    return out


def static_kit(tmp_path, export: Path) -> Kit:
    csp.main(["csp", str(export)])  # the image build step
    return Kit(tmp_path, static_dir=export)


def test_the_policy_has_no_unsafe_inline_and_the_required_directives(tmp_path, export):
    kit = static_kit(tmp_path, export)
    policy = kit.client.get("/").headers["content-security-policy"]
    assert "unsafe-inline" not in policy and "unsafe-eval" not in policy
    for directive in (
        "default-src 'self'",
        "frame-ancestors 'none'",
        "object-src 'none'",
        "base-uri 'self'",
    ):
        assert directive in policy


def test_the_policy_hashes_match_the_inline_scripts_actually_in_the_export(tmp_path, export):
    kit = static_kit(tmp_path, export)
    policy = kit.client.get("/").headers["content-security-policy"]
    html = (export / "index.html").read_text(encoding="utf-8")
    inline = [
        body
        for attrs, body in re.findall(r"<script\b([^>]*)>(.*?)</script>", html, re.S)
        if "src=" not in attrs and body.strip()
    ]
    assert len(inline) == 3  # two executable scripts and the JSON data block
    for body in inline:
        assert csp.sha256_source(body) in policy
    # and nothing else is allowed: exactly those hashes
    assert set(re.findall(r"'sha256-[^']+'", policy)) == {csp.sha256_source(b) for b in inline}


def test_a_hash_is_the_base64_sha256_of_the_exact_script_text():
    # Known vector: sha256("") is 47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=
    assert csp.sha256_source("") == "'sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU='"


def test_an_export_without_its_hashes_is_never_served(tmp_path, export):
    with pytest.raises(FileNotFoundError):
        Kit(tmp_path, static_dir=export)


def test_an_export_with_inline_style_attributes_fails_the_build_check(tmp_path, export):
    (export / "index.html").write_text(
        EXPORT_HTML.replace('<div id="root">', '<div style="color:red" id="root">'),
        encoding="utf-8",
    )
    assert csp.main(["csp", str(export)]) == 1
    with pytest.raises(RuntimeError):
        csp.load_policy(export)


def test_the_real_export_if_built_matches_its_hashes():
    real = REPO / "web" / "out"
    if not (real / "index.html").exists():
        pytest.skip("no built UI export in this checkout (built in the image / by the smoke)")
    scan = csp.scan(real)
    assert scan["inline_style_attributes"] == 0
    assert scan["script_hashes"], "a Next.js export has inline scripts"


def test_the_page_source_carries_the_synthetic_data_notice_on_every_screen():
    """Data dictionary section 6, rule 6 (TS-20-E). The built export is not available in unit
    tests, so this checks the source files; the built `index.html` carries the same string. The
    notice is one component, placed once by the root layout, so every page and state shows it."""
    notice = (REPO / "web" / "app" / "components" / "Notice.jsx").read_text(encoding="utf-8")
    layout = (REPO / "web" / "app" / "layout.jsx").read_text(encoding="utf-8")
    text = (
        "Demonstration system: all data here is synthetic, generated for this project, and "
        "describes no real company, customer, technician or operation. The sentiment model was "
        "trained on synthetically written customer feedback, so its results may not reflect how "
        "real customers write."
    )
    joined = "".join(re.findall(r'"([^"\n]*)"', notice.split("export default")[0]))
    assert text in joined
    assert layout.count("<Notice />") == 1 and "{children}" in layout
    assert 'id="synthetic-notice"' in notice and 'data-testid="synthetic-notice"' in notice


def test_static_files_are_public_and_never_shadow_the_api(tmp_path, export):
    kit = static_kit(tmp_path, export)
    assert kit.client.get("/").status_code == 200
    assert kit.client.get("/api/session").status_code == 401
    assert kit.client.get("/healthz").json() == {"status": "ok"}
    # The public probe: Cloud Run's front end reserves /healthz on the service URL (ADR-097 note).
    r = kit.client.get("/health")
    assert (r.status_code, r.json()) == (200, {"status": "ok"})


def test_security_headers_are_on_every_kind_of_response(tmp_path, export):
    kit = static_kit(tmp_path, export)
    kit.sign_in()
    responses = [
        kit.client.get("/"),
        kit.client.get("/healthz"),
        kit.client.get("/api/session"),
        kit.ask(),
        kit.client.get("/nothing-here"),
        kit.client.post("/api/ask", content=b"x", headers={"Origin": "https://evil.example"}),
    ]
    for r in responses:
        assert r.headers["referrer-policy"] == "no-referrer"
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["strict-transport-security"].startswith("max-age=")
        assert "default-src 'self'" in r.headers["content-security-policy"]
    api = kit.client.get("/api/session")
    assert api.headers["cache-control"] == "no-store"


# ---------------------------------------------------------------- limits


def test_the_per_session_hourly_limit_triggers_and_resets(tmp_path):
    kit = Kit(tmp_path, asks_per_session_hour=3)
    kit.sign_in()
    for _ in range(3):
        assert kit.ask().status_code == 200
    r = kit.ask()
    assert r.status_code == 429 and r.json()["error"] == "session_limit"
    assert len(kit.upstream.requests) == 3  # the refused question reached no model
    kit.clock.t += 3601
    assert kit.ask().status_code == 200


def test_re_exchanging_does_not_reset_the_session_limit(tmp_path):
    kit = Kit(tmp_path, asks_per_session_hour=2)
    kit.sign_in()
    kit.ask(), kit.ask()
    kit.client.cookies.clear()
    kit.sign_in()
    assert kit.ask().status_code == 429


def test_the_global_daily_cap_triggers_with_a_clear_message_and_resets_at_pacific_midnight(
    tmp_path,
):
    kit = Kit(tmp_path, daily_question_cap=2, asks_per_session_hour=99)
    # 23:30 Pacific on 2026-10-12 is 06:30 UTC on the 13th.
    kit.clock.t = dt.datetime(2026, 10, 13, 6, 30, tzinfo=dt.UTC).timestamp()
    kit.store.save(
        [
            kit.invite.__class__(
                kit.invite.id, "g", kit.invite.token_sha256, NOW, NOW + dt.timedelta(days=30)
            )
        ]
    )
    kit.sign_in()
    assert kit.ask().status_code == 200
    assert kit.ask().status_code == 200
    r = kit.ask()
    assert r.status_code == 429 and r.json()["error"] == "daily_limit"
    assert "Daily limit reached" in r.json()["detail"]
    assert len(kit.upstream.requests) == 2
    kit.clock.t += 3600  # 00:30 Pacific on the 13th: a new day
    kit.client.cookies.clear()
    kit.sign_in()
    assert kit.ask().status_code == 200


# ---------------------------------------------------------------- logging


class _Records(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def caplog_gateway():
    """Capture on the gateway loggers themselves: another test's `configure_logging` can leave
    the root logger (and so pytest's caplog) without the records."""
    handler = _Records()
    loggers = [logging.getLogger(n) for n in ("gateway", "gateway.upstream")]
    saved = [(lg.level, lg.propagate, lg.disabled) for lg in loggers]
    for lg in loggers:
        lg.addHandler(handler)
        lg.setLevel(logging.DEBUG)
        lg.disabled = False  # a dictConfig elsewhere can leave existing loggers disabled
    yield handler
    for lg, (level, propagate, disabled) in zip(loggers, saved, strict=True):
        lg.removeHandler(handler)
        lg.setLevel(level)
        lg.propagate = propagate
        lg.disabled = disabled


def test_no_token_cookie_or_hash_reaches_the_logs(kit, caplog_gateway):
    kit.exchange("wrong-token-should-not-be-logged")
    cookie = kit.sign_in()
    kit.ask("What was SLA compliance in the Northeast last month?")
    kit.ask("x" * 600)  # refused
    text = "\n".join(
        r.getMessage() + " " + json.dumps(r.__dict__, default=str) for r in caplog_gateway.records
    )
    assert "exchange ok" in text and kit.invite.id in text  # the id is logged
    for secret in (
        kit.token,
        "wrong-token-should-not-be-logged",
        cookie,
        cookie.split(".")[0],
        kit.invite.token_sha256,
        KEY,
    ):
        assert secret not in text


# ---------------------------------------------------------------- the invite store


def test_find_by_token_is_exact_and_ignores_expired(tmp_path):
    invite, token = new_invite("g", 1, NOW)
    assert find_by_token([invite], token, NOW) == invite
    assert find_by_token([invite], token + "x", NOW) is None
    assert find_by_token([invite], token, NOW + dt.timedelta(days=2)) is None
    assert find_by_token([invite], 5, NOW) is None  # type: ignore[arg-type]


def test_a_token_is_43_urlsafe_characters_and_only_its_hash_is_stored(tmp_path):
    invite, token = new_invite("g", 1, NOW)
    assert len(token) == 43 and re.fullmatch(r"[A-Za-z0-9_-]+", token)
    document = dump_document([invite])
    assert token not in document and invite.token_sha256 in document


class FakeSecret:
    def __init__(self, text: str) -> None:
        self.text, self.reads, self.fail = text, 0, False

    def __call__(self) -> str:
        self.reads += 1
        if self.fail:
            raise RuntimeError("secret manager down")
        return self.text


def test_the_secret_manager_store_caches_for_at_most_sixty_seconds():
    invite, _ = new_invite("g", 1, NOW)
    fake = FakeSecret(dump_document([invite]))
    t = [0.0]
    store = SecretManagerInviteStore(fake, ttl_s=9999, clock=lambda: t[0])  # clamped to 60
    assert [i.id for i in store.invites()] == [invite.id]
    store.invites()
    assert fake.reads == 1
    fake.text = dump_document([])  # revoked
    t[0] = CACHE_TTL_S - 1
    assert len(store.invites()) == 1  # still cached
    t[0] = CACHE_TTL_S + 1
    assert store.invites() == []  # revocation took effect within 60 seconds
    assert fake.reads == 2


def test_the_secret_manager_store_keeps_the_last_copy_through_a_blip_and_fails_closed():
    invite, _ = new_invite("g", 1, NOW)
    fake = FakeSecret(dump_document([invite]))
    t = [0.0]
    store = SecretManagerInviteStore(fake, clock=lambda: t[0])
    store.invites()
    fake.fail = True
    t[0] = 100.0
    assert [i.id for i in store.invites()] == [invite.id]
    never = SecretManagerInviteStore(FakeSecret("{}"), clock=lambda: 0.0)
    broken = FakeSecret("")
    broken.fail = True
    assert SecretManagerInviteStore(broken, clock=lambda: 0.0).invites() == []
    assert never.invites() == []


def test_a_malformed_record_is_skipped_not_fatal(tmp_path):
    good, _ = new_invite("g", 1, NOW)
    path = tmp_path / "i.json"
    doc = json.loads(dump_document([good]))
    doc["invites"].append({"id": "broken"})
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert [i.id for i in FileInviteStore(path).invites()] == [good.id]


def test_a_missing_store_file_means_no_invites(tmp_path):
    assert FileInviteStore(tmp_path / "absent.json").invites() == []


# ---------------------------------------------------------------- the admin tool


def run_tool(file: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO / "scripts" / "invites.py"), "--file", str(file), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_the_admin_tool_creates_lists_without_hashes_and_revokes(tmp_path):
    file = tmp_path / "state" / "invites.json"
    made = run_tool(
        file, "create", "--label", "grader one", "--days", "14", "--base-url", "https://gw.example"
    )
    assert made.returncode == 0, made.stderr
    link = re.search(r"https://gw\.example/#invite=([A-Za-z0-9_-]{43})", made.stdout)
    assert link, made.stdout
    token = link.group(1)
    stored = file.read_text(encoding="utf-8")
    assert token not in stored  # only the hash is kept

    listed = run_tool(file, "list")
    assert listed.returncode == 0
    assert "grader one" in listed.stdout and "1 invite(s)" in listed.stdout
    digest = json.loads(stored)["invites"][0]["token_sha256"]
    assert digest not in listed.stdout and token not in listed.stdout

    invite_id = json.loads(stored)["invites"][0]["id"]
    assert run_tool(file, "revoke", "--id", "nope").returncode == 1
    assert run_tool(file, "revoke", "--id", invite_id).returncode == 0
    assert FileInviteStore(file).invites() == []
    assert "0 invite(s)" in run_tool(file, "list").stdout


def test_an_invite_made_by_the_tool_signs_in(tmp_path):
    file = tmp_path / "invites.json"
    made = run_tool(file, "create", "--label", "g", "--days", "1", "--base-url", ORIGIN)
    token = re.search(r"#invite=([A-Za-z0-9_-]+)", made.stdout).group(1)
    settings = Settings(session_key=KEY, public_origin=ORIGIN)
    upstream = Upstream()
    orchestrator = Orchestrator(
        settings.orchestrator_url, 5.0, transport=httpx.MockTransport(upstream.handler)
    )
    client = TestClient(create_app(settings, FileInviteStore(file), orchestrator), base_url=ORIGIN)
    r = client.post("/auth/exchange", json={"token": token}, headers={"Origin": ORIGIN})
    assert r.status_code == 200


# ---------------------------------------------------------------- configuration and upstream auth


def test_a_short_session_key_or_no_store_refuses_to_start(monkeypatch):
    monkeypatch.setenv("GATEWAY_SESSION_KEY", "short")
    monkeypatch.setenv("GATEWAY_INVITES_FILE", "x.json")
    with pytest.raises(GatewayConfigError):
        Settings.from_env()
    monkeypatch.setenv("GATEWAY_SESSION_KEY", "k" * 40)
    monkeypatch.delenv("GATEWAY_INVITES_FILE")
    monkeypatch.delenv("GATEWAY_INVITES_SECRET", raising=False)
    with pytest.raises(GatewayConfigError):
        Settings.from_env()


def test_the_orchestrator_call_carries_an_id_token_when_configured():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization"))
        return httpx.Response(200, json={"answer": "a"})

    tokens = IdTokenProvider("https://orch.run.app", fetch=lambda aud: f"idtoken-for-{aud}")
    o = Orchestrator(
        "https://orch.run.app", 5.0, tokens=tokens, transport=httpx.MockTransport(handler)
    )
    import asyncio

    status, _ = asyncio.run(o.ask("q"))
    assert status == 200
    assert seen == ["Bearer idtoken-for-https://orch.run.app"]


def test_the_upstream_timeout_is_just_over_the_request_deadline():
    assert 120 < Settings(session_key=KEY, public_origin=ORIGIN).upstream_timeout_s <= 130
