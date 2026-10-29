"""The extra UI pages (/how-it-works/, /faq/) are served by the same static mount as the main page,
under the same access rule: public files, with the API behind the session (ADR-097, ADR-117)."""

from __future__ import annotations

from pathlib import Path

import pytest
from api_gateway import csp
from gateway_testkit import JSON_HEADERS, Kit

PAGE = """<!DOCTYPE html><html><head><title>t</title>
<script>self.__next_f=self.__next_f||[];self.__next_f.push([0])</script>
</head><body>{name}</body></html>
"""
PAGES = {
    "index.html": "ask",
    "how-it-works/index.html": "how",
    "faq/index.html": "faq",
    "results/index.html": "results",
}


@pytest.fixture
def export(tmp_path) -> Path:
    out = tmp_path / "out"
    for name, body in PAGES.items():
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(PAGE.format(name=body), encoding="utf-8")
    (out / "404.html").write_text(PAGE.format(name="404"), encoding="utf-8")
    return out


@pytest.fixture
def kit(tmp_path, export) -> Kit:
    csp.main(["csp", str(export)])  # the image build step
    return Kit(tmp_path, static_dir=export)


@pytest.mark.parametrize("path", ["/", "/how-it-works/", "/faq/", "/results/"])
def test_each_page_is_served_without_a_session_with_the_same_policy(kit, path):
    r = kit.client.get(path)
    assert r.status_code == 200
    assert (
        r.headers["content-security-policy"]
        == kit.client.get("/").headers["content-security-policy"]
    )
    assert "script-src 'self' 'sha256-" in r.headers["content-security-policy"]


def test_the_pages_are_static_files_and_the_api_stays_behind_the_session(kit):
    assert kit.client.get("/api/session").status_code == 401
    assert "<body>how</body>" in kit.client.get("/how-it-works/").text
    assert "<body>faq</body>" in kit.client.get("/faq/").text
    assert "<body>results</body>" in kit.client.get("/results/").text
    kit.sign_in()
    assert kit.client.get("/api/session").status_code == 200
    assert kit.client.get("/faq/").status_code == 200  # the same file signed in or out
    assert kit.client.get("/results/").status_code == 200


def test_a_path_without_the_trailing_slash_redirects_to_the_page(kit):
    for page in ("how-it-works", "faq", "results"):
        r = kit.client.get(f"/{page}", follow_redirects=False)
        assert r.status_code == 307
        assert r.headers["location"] == f"/{page}/"  # path only: never a scheme (L-105)


def test_the_redirect_keeps_the_query_string_and_is_never_absolute(kit):
    r = kit.client.get("/faq?a=1&b=two", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/faq/?a=1&b=two"
    for path in ("/faq", "/how-it-works", "/faq?x=y"):
        location = kit.client.get(path, follow_redirects=False).headers["location"]
        assert location.startswith("/") and not location.startswith("//")
        assert "://" not in location


def test_the_gateway_still_runs_with_proxy_headers_off(monkeypatch):
    from api_gateway import __main__ as entry

    seen = {}
    monkeypatch.setattr(entry.uvicorn, "run", lambda app, **kw: seen.update(kw))
    monkeypatch.setattr(entry, "build_app", lambda: (None, type("S", (), {"port": 1})()))
    monkeypatch.setattr(entry, "configure_logging", lambda *a: None)
    assert entry.main(["serve"]) == 0
    assert seen["proxy_headers"] is False  # the forwarded-for rule is applied in code


@pytest.mark.parametrize("path", ["/", "/faq/", "/how-it-works/", "/results/"])
def test_html_pages_are_revalidated_on_every_load(kit, path):
    r = kit.client.get(path)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"
    assert r.headers["etag"] and r.headers["last-modified"]


def test_hashed_next_files_are_immutable_and_other_static_files_revalidate(kit, export):
    chunk = export / "_next" / "static" / "chunks" / "app-abc123.js"
    chunk.parent.mkdir(parents=True)
    chunk.write_text("console.log(1)", encoding="utf-8")
    (export / "favicon.ico").write_bytes(b"\x00\x00")
    r = kit.client.get("/_next/static/chunks/app-abc123.js")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert r.headers["etag"] and r.headers["last-modified"]
    assert kit.client.get("/favicon.ico").headers["cache-control"] == "no-cache"
    # A conditional request is answered 304 and keeps the same policy.
    again = kit.client.get(
        "/_next/static/chunks/app-abc123.js", headers={"If-None-Match": r.headers["etag"]}
    )
    assert again.status_code == 304
    assert again.headers["cache-control"] == "public, max-age=31536000, immutable"
    # A missing hashed file is the 404 page, which must not be cached as immutable.
    missing = kit.client.get("/_next/static/chunks/gone.js")
    assert missing.status_code == 404 and missing.headers["cache-control"] == "no-cache"


def test_api_session_and_health_routes_keep_their_own_headers(kit):
    assert kit.client.get("/api/session").headers["cache-control"] == "no-store"  # 401 error
    kit.sign_in()
    assert kit.client.get("/api/session").headers["cache-control"] == "no-store"
    ask = kit.client.post("/api/ask", json={"question": ""}, headers=JSON_HEADERS)
    assert ask.status_code == 422 and ask.headers["cache-control"] == "no-store"
    health = kit.client.get("/health")
    assert health.status_code == 200 and "cache-control" not in health.headers
    assert "cache-control" not in kit.client.get("/healthz").headers


def test_an_unknown_path_is_a_404_carrying_the_export_page_and_the_policy(kit):
    r = kit.client.get("/no-such-page/")
    assert r.status_code == 404 and "<body>404</body>" in r.text
    assert "script-src" in r.headers["content-security-policy"]


def test_the_real_export_if_built_has_the_pages_and_no_inline_styles():
    real = Path(__file__).resolve().parents[3] / "web" / "out"
    if not (real / "how-it-works" / "index.html").exists():
        pytest.skip("no built UI export in this checkout (built in the image)")
    assert (real / "faq" / "index.html").exists()
    assert csp.scan(real)["inline_style_attributes"] == 0
