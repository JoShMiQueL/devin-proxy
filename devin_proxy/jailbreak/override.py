"""System override file handling: resolution order + mtime hot-reload.

Resolution order (first existing file wins):
1. ``DEVIN_PROXY_SYSTEM_FILE`` env var.
2. ``~/.devin-proxy/<name>`` — user data dir.
3. ``<package>/prompts/<name>`` — the shipped default inside the installed
   package (works both from an editable checkout and a wheel install).
"""
from __future__ import annotations

import os
from pathlib import Path

NAMES = ("override-compact.txt", "override.txt", "system_override.txt")

#: bundled language variants under devin_proxy/prompts/
BUNDLED = {
    "en": "override-compact.txt",
    "english": "override-compact.txt",
    "es": "override-compact-es.txt",
    "spanish": "override-compact-es.txt",
}


def _package_prompts() -> Path:
    # devin_proxy/jailbreak/override.py -> devin_proxy/prompts
    return Path(__file__).resolve().parent.parent / "prompts"


def resolve_system_file(setting: str | None = None) -> Path:
    """Resolve DEVIN_PROXY_SYSTEM_FILE / Settings.system_file to a Path.

    A bundled language name ("es", "spanish", "en", "english") maps to the
    shipped variant inside the package; anything else is a filesystem path.
    """
    raw = setting if setting is not None else os.environ.get(
        "DEVIN_PROXY_SYSTEM_FILE")
    if raw:
        if str(raw).strip().lower() in BUNDLED:
            return _package_prompts() / BUNDLED[str(raw).strip().lower()]
        return Path(raw)
    home_dir = Path.home() / ".devin-proxy"
    for base in (home_dir, _package_prompts()):
        for name in NAMES:
            p = base / name
            if p.exists():
                return p
    return home_dir / NAMES[0]


def default_system_file() -> Path:
    return resolve_system_file()


class OverridePrompt:
    """Reads the override file; returns "" when it does not exist."""

    def __init__(self, path=None):
        if isinstance(path, str):
            path = resolve_system_file(path)
        self.path = path or default_system_file()
        self._mtime: float | None = None
        self._text = ""

    def load(self) -> str:
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            return ""
        if mtime != self._mtime:
            try:
                self._text = self.path.read_text(encoding="utf-8", errors="replace")
                self._mtime = mtime
            except OSError:
                return ""
        return self._text

    def __len__(self) -> int:
        return len(self._text)
