"""Versioned prompt files.

A prompt lives in a service's `prompts/` folder as `<name>_v<N>.md`. The file name is
its version, and a short content hash catches an edit made without bumping the version.
Both are logged with every call that uses the prompt, so a routing or parsing result can
always be traced to the exact prompt text that produced it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

PLACEHOLDER_OPEN, PLACEHOLDER_CLOSE = "{{", "}}"


@dataclass(frozen=True)
class Prompt:
    version: str  # the file stem, e.g. "route_v1"
    sha: str  # first 12 hex characters of the content's SHA-256
    text: str

    @classmethod
    def from_path(cls, path: Path) -> Prompt:
        text = path.read_text(encoding="utf-8")
        return cls(path.stem, hashlib.sha256(text.encode()).hexdigest()[:12], text)

    def render(self, **values: str) -> str:
        """Fill `{{name}}` placeholders. Every placeholder must be given, and no other."""
        out = self.text
        for name, value in values.items():
            token = f"{PLACEHOLDER_OPEN}{name}{PLACEHOLDER_CLOSE}"
            if token not in out:
                raise KeyError(f"{self.version} has no placeholder {token}")
            out = out.replace(token, value)
        if PLACEHOLDER_OPEN in out:
            start = out.index(PLACEHOLDER_OPEN)
            raise KeyError(f"{self.version} left unfilled: {out[start : start + 30]!r}")
        return out


def load_prompt(package: str, name: str, source_file: str) -> Prompt:
    """Load `prompts/<name>.md` for a service.

    Installed images carry the folder inside the package (hatch `force-include`). An
    editable install runs from the source tree, where the folder sits next to `src/`:
    `source_file` is the calling module's `__file__`, used to find it there.
    """
    packaged = files(package) / "prompts" / f"{name}.md"
    if packaged.is_file():
        return Prompt.from_path(Path(str(packaged)))
    source = Path(source_file).resolve().parents[2] / "prompts" / f"{name}.md"
    if source.is_file():
        return Prompt.from_path(source)
    raise FileNotFoundError(f"prompt {name}.md not found in {package} or {source.parent}")
