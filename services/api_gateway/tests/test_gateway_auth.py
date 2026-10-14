"""Exchange, session, exposure, CSRF and input rules (ADR-097)."""

from __future__ import annotations

import datetime as dt

import pytest
from api_gateway.invites import Invite, hash_token
from api_gateway.session import COOKIE_NAME, MAX_SESSION_S
from gateway_testkit import JSON_HEADERS, ORIGIN, Kit, dumps, raw_post, registered_routes
from starlette.routing import Mount


@pytest.fixture
def kit(tmp_path) -> Kit:
    return Kit(tmp_path)


# ---------------------------------------------------------------- exchange


def test_a_valid_token_sets_the_session_cookie_with_every_flag(kit):
    r = kit.exchange()
    assert r.status_code == 200 and r.json() == {"signed_in": True}
    header = r.headers["set-cookie"]
    assert header.startswith(f"{COOKIE_NAME}=")
    flags = {part.strip().lower() for part in header.split(";")[1:]}
    assert "secure" in flags and "httponly" in flags
    assert "samesite=strict" in flags and "path=/" in flags
    assert not any(f.startswith("domain=") for f in flags)  # __Host- forbids a Domain
    # The token itself is never in the cookie or the body.
    assert kit.token not in header and kit.token not in r.text


def test_the_session_lasts_the_earlier_of_the_invite_and_twelve_hours(kit):
    r = kit.exchange()
    assert f"Max-Age={MAX_SESSION_S}" in r.headers["set-cookie"]
    now = kit.clock.now()
    soon = Invite(
        "inv2", "short", hash_token("short-token-xyz"), now, now + dt.timedelta(minutes=30)
    )
    kit.store.save([kit.invite, soon])
    r = kit.exchange("short-token-xyz")
    assert "Max-Age=1800" in r.headers["set-cookie"]


@pytest.mark.parametrize(
    "token",
    ["", "x", "not-a-real-token", "a" * 300, " ", "tok-" + "a" * 39],
    ids=["empty", "short", "unknown", "overlong", "blank", "near-miss"],
)
def test_every_bad_token_gets_the_same_generic_failure(kit, token):
    reference = kit.exchange("definitely-wrong")
    r = kit.exchange(token)
    assert r.status_code == 401
    assert (r.status_code, r.json()) == (reference.status_code, reference.json())
    assert "set-cookie" not in r.headers


def test_an_expired_token_is_indistinguishable_from_an_unknown_one(kit):
    now = kit.clock.now()
    expired = Invite(
        "inv3",
        "old",
        hash_token("old-token-abcdefgh"),
        now - dt.timedelta(days=9),
        now - dt.timedelta(days=1),
    )
    kit.store.save([kit.invite, expired])
    unknown = kit.exchange("unknown-token-abcdef")
    r = kit.exchange("old-token-abcdefgh")
    assert (r.status_code, r.json()) == (unknown.status_code, unknown.json())
    assert "set-cookie" not in r.headers


@pytest.mark.parametrize(
    "content",
    [b"", b"not json", b"[]", b'{"token": 5}', b'{"token": "x", "extra": 1}', b"{}"],
    ids=["empty", "text", "array", "wrong-type", "unknown-field", "no-token"],
)
def test_a_malformed_exchange_body_gets_the_same_generic_failure(kit, content):
    expected = kit.exchange("nope-nope-nope")
    r = raw_post(kit.client, "/auth/exchange", content)
    assert (r.status_code, r.json()) == (expected.status_code, expected.json())


def test_the_exchange_limit_triggers_at_the_eleventh_attempt_in_a_minute(kit):
    for _ in range(10):
        assert kit.exchange("wrong-wrong-wrong").status_code == 401
    r = kit.exchange()  # even a valid token: the limit is on the address
    assert r.status_code == 429 and "set-cookie" not in r.headers
    kit.clock.t += 61
    assert kit.exchange().status_code == 200


def test_the_limit_keys_on_the_forwarded_for_entry_counted_from_the_right(kit):
    # The leftmost entry is client-controlled; the one Cloud Run appends is the last.
    def attempt(forwarded: str):
        return kit.client.post(
            "/auth/exchange",
            json={"token": "bad-bad-bad-b"},
            headers={"Origin": ORIGIN, "X-Forwarded-For": forwarded},
        )

    for i in range(10):
        assert attempt(f"10.0.0.{i}, 203.0.113.7").status_code == 401
    assert attempt("10.9.9.9, 203.0.113.7").status_code == 429
    assert attempt("10.9.9.9, 203.0.113.8").status_code == 401


# ---------------------------------------------------------------- session


def test_no_cookie_a_tampered_cookie_and_an_expired_cookie_get_401(kit):
    assert kit.client.get("/api/session").status_code == 401
    value = kit.sign_in()
    assert kit.client.get("/api/session").status_code == 200
    kit.client.cookies.clear()
    body, mac = value.split(".")
    flipped = mac[:-1] + ("A" if mac[-1] != "A" else "B")
    for bad in (f"{body}.{flipped}", f"{body}x.{mac}", "garbage", ""):
        kit.client.cookies.set(COOKIE_NAME, bad)
        r = kit.client.get("/api/session")
        assert r.status_code == 401 and r.json() == {"error": "sign_in_required"}
    kit.client.cookies.clear()
    kit.client.cookies.set(COOKIE_NAME, value)
    kit.clock.t += MAX_SESSION_S + 1
    assert kit.client.get("/api/session").status_code == 401


def test_a_revoked_invite_gets_401_on_the_next_request(kit):
    kit.sign_in()
    assert kit.ask().status_code == 200
    kit.store.save([])  # revoke: the file store is read on every call (no cache to wait out)
    r = kit.ask()
    assert r.status_code == 401 and len(kit.upstream.requests) == 1


def test_an_invite_that_expires_ends_its_sessions(kit):
    kit.sign_in()
    kit.clock.t = kit.invite.expires_at.timestamp() + 1
    assert kit.client.get("/api/session").status_code == 401


def test_logout_clears_the_cookie(kit):
    kit.sign_in()
    r = kit.client.post("/auth/logout", headers=JSON_HEADERS, json={})
    assert r.status_code == 200
    assert "max-age=0" in r.headers["set-cookie"].lower()
    assert kit.client.get("/api/session").status_code == 401


# ---------------------------------------------------------------- exposure


def test_every_registered_api_route_is_401_without_a_session(kit):
    api = [(p, m) for p, m in registered_routes(kit.app) if p.startswith("/api/")]
    assert {p for p, _ in api} >= {"/api/session", "/api/ask"}
    for path, methods in api:
        for method in methods - {"HEAD", "OPTIONS"}:
            r = kit.client.request(method, path)
            assert r.status_code == 401, (method, path)
            assert r.json() == {"error": "sign_in_required"}


def test_the_only_non_api_routes_are_the_documented_public_ones(kit):
    public = {p for p, _ in registered_routes(kit.app) if not p.startswith("/api/")}
    assert public == {"/health", "/healthz", "/auth/exchange", "/auth/logout"}
    assert not any(isinstance(r, Mount) for r in kit.app.routes)  # no static dir in this kit


def test_the_unauthenticated_api_error_has_no_detail(kit):
    r = kit.client.post("/api/ask", json={"question": "hi"}, headers={"Origin": ORIGIN})
    assert r.status_code == 401 and set(r.json()) == {"error"}


# ---------------------------------------------------------------- CSRF


def test_a_wrong_or_missing_origin_is_rejected_and_nothing_is_sent_upstream(kit):
    kit.sign_in()
    for headers in ({"Origin": "https://evil.example"}, {}):
        r = kit.client.post("/api/ask", json={"question": "hi"}, headers=headers)
        assert r.status_code == 403
    assert not kit.upstream.requests
    r = kit.client.post(
        "/auth/exchange", json={"token": kit.token}, headers={"Origin": "https://evil.example"}
    )
    assert r.status_code == 403 and "set-cookie" not in r.headers


def test_a_non_json_content_type_is_rejected(kit):
    kit.sign_in()
    for ctype in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data"):
        r = kit.client.post(
            "/api/ask",
            content=dumps({"question": "hi"}),
            headers={"Origin": ORIGIN, "Content-Type": ctype},
        )
        assert r.status_code == 403
    assert not kit.upstream.requests


# ---------------------------------------------------------------- input


@pytest.mark.parametrize(
    ("content", "status"),
    [
        (dumps({"question": "x" * 501}), 422),
        (dumps({"question": ""}), 422),
        (dumps({"question": "   \n  "}), 422),
        (dumps({"question": "ok", "extra": 1}), 422),
        (dumps({"question": 7}), 422),
        (dumps(["question"]), 422),
        (dumps({}), 422),
        (b"{not json", 400),
        (dumps({"question": "y" * 5000}), 413),
    ],
    ids=[
        "over-500",
        "empty",
        "blank",
        "unknown-field",
        "wrong-type",
        "array",
        "missing",
        "malformed",
        "over-4kb",
    ],
)
def test_bad_input_gets_a_4xx_with_no_internal_detail(kit, content, status):
    kit.sign_in()
    r = raw_post(kit.client, "/api/ask", content)
    assert r.status_code == status
    assert set(r.json()) <= {"error", "detail"}
    text = r.text.lower()
    assert "traceback" not in text and "pydantic" not in text and "input" not in text
    assert "xxxxx" not in text and "yyyyy" not in text  # the input is never echoed
    assert not kit.upstream.requests


def test_a_question_is_trimmed_and_500_characters_is_accepted(kit):
    kit.sign_in()
    r = kit.ask("  " + "q" * 500 + "  ")
    assert r.status_code == 200
    sent = kit.upstream.requests[0].read()
    assert b"q" * 500 in sent and b" q" not in sent.replace(b'": "', b"")
