"""The Content-Security-Policy and its inline-script hashes (ADR-097).

A Next.js static export puts inline `<script>` elements in each page. They are allowed by the
SHA-256 of their exact text, never by `'unsafe-inline'`. `python -m api_gateway.csp <export
dir>` writes `csp-hashes.json` next to the export at image build time; the gateway reads it at
start-up and refuses to serve an export without it. Inline style attributes cannot be hashed
without `'unsafe-hashes'`, so the build check reports any (`inline_style_attributes`).
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import sys
from pathlib import Path

HASHES_FILE = "csp-hashes.json"
_INLINE_SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.DOTALL | re.IGNORECASE)
_STYLE_ELEMENT = re.compile(r"<style\b[^>]*>(.*?)</style>", re.DOTALL | re.IGNORECASE)
_STYLE_ATTR = re.compile(r"<[a-z][^>]*\sstyle\s*=", re.IGNORECASE)


def sha256_source(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return "'sha256-" + base64.b64encode(digest).decode("ascii") + "'"


def scan(export_dir: Path) -> dict:
    """Hashes of every inline script and style element in the export's HTML files, and the
    count of inline style attributes (which must be zero)."""
    scripts: set[str] = set()
    styles: set[str] = set()
    attrs = 0
    for page in sorted(Path(export_dir).rglob("*.html")):
        html = page.read_text(encoding="utf-8")
        for attributes, body in _INLINE_SCRIPT.findall(html):
            if "src=" not in attributes.lower() and body.strip():
                scripts.add(sha256_source(body))
        for body in _STYLE_ELEMENT.findall(html):
            if body.strip():
                styles.add(sha256_source(body))
        attrs += len(_STYLE_ATTR.findall(html))
    return {
        "script_hashes": sorted(scripts),
        "style_hashes": sorted(styles),
        "inline_style_attributes": attrs,
    }


def build_policy(script_hashes: list[str], style_hashes: list[str] | None = None) -> str:
    scripts = " ".join(["'self'", *script_hashes])
    styles = " ".join(["'self'", *(style_hashes or [])])
    return "; ".join(
        [
            "default-src 'self'",
            f"script-src {scripts}",
            f"style-src {styles}",
            "frame-ancestors 'none'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
    )


def load_policy(export_dir: Path) -> str:
    """The policy for a built export; raises if the hashes file is missing or the export has
    inline style attributes (the page would be broken or the policy unsafe)."""
    data = json.loads((Path(export_dir) / HASHES_FILE).read_text(encoding="utf-8"))
    if data.get("inline_style_attributes"):
        raise RuntimeError("the export has inline style attributes, which the policy forbids")
    return build_policy(data["script_hashes"], data.get("style_hashes", []))


def main(argv: list[str]) -> int:
    export_dir = Path(argv[1])
    result = scan(export_dir)
    (export_dir / HASHES_FILE).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        f"csp: {len(result['script_hashes'])} inline script hash(es), "
        f"{len(result['style_hashes'])} style hash(es), "
        f"{result['inline_style_attributes']} inline style attribute(s)"
    )
    return 1 if result["inline_style_attributes"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
