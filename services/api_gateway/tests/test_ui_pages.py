"""The extra UI pages (/how-it-works/, /faq/) are served by the same static mount as the main page,
under the same access rule: public files, with the API behind the session (ADR-097, ADR-117)."""

from __future__ import annotations

from pathlib import Path

import pytest
from api_gateway import csp
from gateway_testkit import Kit

PAGE = """<!DOCTYPE html><html><head><title>t</title>
<script>self.__next_f=self.__next_f||[];self.__next_f.push([0])</script>
</head><body>{name}</body></html>
"""
PAGES = {"index.html": "ask", "how-it-works/index.html": "how", "faq/index.html": "faq"}


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


@pytest.mark.parametrize("path", ["/", "/how-it-works/", "/faq/"])
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
    kit.sign_in()
    assert kit.client.get("/api/session").status_code == 200
    assert kit.client.get("/faq/").status_code == 200  # the same file signed in or out


def test_a_path_without_the_trailing_slash_redirects_to_the_page(kit):
    for page in ("how-it-works", "faq"):
        r = kit.client.get(f"/{page}", follow_redirects=False)
        assert r.status_code == 307
        assert r.headers["location"].endswith(f"/{page}/")


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
