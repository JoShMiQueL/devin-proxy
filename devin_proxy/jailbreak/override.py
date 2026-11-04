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


def _package_prompts() -> Path:
    # devin_proxy/jailbreak/override.py -> devin_proxy/prompts
    return Path(__file__).resolve().parent.parent / "prompts"


def default_system_file() -> Path:
    env = os.environ.get("DEVIN_PROXY_SYSTEM_FILE")
    if env:
        return Path(env)
    home_dir = Path.home() / ".devin-proxy"
    for base in (home_dir, _package_prompts()):
        for name in NAMES:
            p = base / name
            if p.exists():
                return p
    return home_dir / NAMES[0]


class OverridePrompt:
    """Reads the override file; returns "" when it does not exist."""

    def __init__(self, path: Path | None = None):
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
