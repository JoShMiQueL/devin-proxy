"""Live fingerprint of the installed Devin CLI.

The backend checks the client version/channel we send in the request
metadata. Hardcoding it means every `devin` CLI self-update silently drifts
our fingerprint. Instead we ask the CLI itself — `devin version` — and fall
back to the bundled constant only when no CLI is found.
"""
from __future__ import annotations

import re
import shutil
import subprocess

FALLBACK_VERSION = "3000.11.234"
FALLBACK_CHANNEL = "chisel"

_ver_re = re.compile(r"(\d+\.\d+\.\d+)")


def cli_version() -> str:
    """Version of the `devin` binary on PATH ("" when absent/unparseable)."""
    exe = shutil.which("devin")
    if not exe:
        return ""
    try:
        out = subprocess.run([exe, "version"], capture_output=True,
                             text=True, timeout=10)
        m = _ver_re.search(out.stdout + out.stderr)
        return m.group(1) if m else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def fingerprint() -> tuple[str, str]:
    """(version, channel) the proxy will present to the backend."""
    return cli_version() or FALLBACK_VERSION, FALLBACK_CHANNEL
