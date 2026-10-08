"""Resolve ${NAME} placeholders in a Cloud Run service definition and write v2 API JSON.

Cloud Build substitutions apply only to cloudbuild.yaml steps, not to files those steps read,
so the definitions are rendered here. Every ${NAME} is replaced from the environment, and the
render fails (exit 1) if a placeholder has no value or one is still present afterwards.

    python deploy/render.py deploy/cloudrun/reporting.yaml rendered/reporting.json

Needs PyYAML (the build step installs it). The YAML is parsed first, so comments may mention
placeholders freely; only values are rendered.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class UnresolvedPlaceholder(Exception):
    """A placeholder had no value, or one remained after rendering."""


def render_value(value: Any, env: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        missing = sorted({m for m in PLACEHOLDER.findall(value) if not env.get(m)})
        if missing:
            raise UnresolvedPlaceholder(f"no value for: {', '.join(missing)}")
        out = PLACEHOLDER.sub(lambda m: env[m.group(1)], value)
        if "${" in out:  # malformed, or a value that itself contains a placeholder
            raise UnresolvedPlaceholder(f"a placeholder remains in {out!r}")
        return out
    if isinstance(value, list):
        return [render_value(v, env) for v in value]
    if isinstance(value, dict):
        return {k: render_value(v, env) for k, v in value.items()}
    return value


def render_file(source: Path, env: Mapping[str, str]) -> dict:
    return render_value(yaml.safe_load(source.read_text(encoding="utf-8")), env)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: render.py SOURCE.yaml OUTPUT.json", file=sys.stderr)
        return 2
    try:
        document = render_file(Path(argv[1]), os.environ)
    except UnresolvedPlaceholder as exc:
        print(f"render failed: {argv[1]}: {exc}", file=sys.stderr)
        return 1
    out = Path(argv[2])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, indent=2), encoding="utf-8")
    print(f"rendered {argv[1]} -> {argv[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
