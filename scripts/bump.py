#!/usr/bin/env python3
"""Release bumper: edit __version__ + pyproject, regen CHANGELOG, commit+tag.

    bump.py                # suggest + confirm
    bump.py patch|minor|major
    bump.py X.Y.Z          # explicit
    bump.py --dry          # preview only
    bump.py minor --push   # also push commit + tag (starts release.yml)
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INIT = ROOT / "devin_proxy" / "__init__.py"
TOML = ROOT / "pyproject.toml"


def run(*args: str, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), cwd=ROOT, capture_output=True,
                          text=True, check=check)


def cur_version() -> str:
    m = re.search(r'__version__ = "([^"]+)"', INIT.read_text(encoding="utf-8"))
    if not m:
        raise RuntimeError("__version__ not found in __init__.py")
    return m.group(1)


def bump(v: str, kind: str) -> str:
    major, minor, patch = (int(x) for x in v.split("."))
    if kind == "major":
        return f"{major + 1}.0.0"
    if kind == "minor":
        return f"{major}.{minor + 1}.0"
    if kind == "patch":
        return f"{major}.{minor}.{patch + 1}"
    return kind  # explicit version


def set_version(v: str) -> None:
    INIT.write_text(
        re.sub(r'__version__ = "[^"]+"', f'__version__ = "{v}"',
               INIT.read_text(encoding="utf-8")),
        encoding="utf-8")
    TOML.write_text(
        re.sub(r'(?m)^version = "[^"]+"', f'version = "{v}"',
               TOML.read_text(encoding="utf-8"), count=1),
        encoding="utf-8")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    dry = "--dry" in flags
    push = "--push" in flags

    sug = run("python", "scripts/changelog.py", "suggest").stdout.strip()
    cur = cur_version()
    print(f"current {cur}, suggested bump: {sug}")

    kind = args[0] if args else sug
    new = bump(cur, kind)
    if new == cur:
        print("version unchanged, aborting", file=sys.stderr)
        sys.exit(1)
    tag = f"v{new}"
    print(f"-> {tag}")

    if dry:
        run("python", "scripts/changelog.py", "changelog", "--tag", tag)
        print("(dry: CHANGELOG.md rewritten, no commit/tag)")
        return

    set_version(new)
    run("python", "scripts/changelog.py", "changelog", "--tag", tag)
    run("git", "add", str(INIT), str(TOML), "CHANGELOG.md")
    run("git", "-c", "user.name=JoShMiQueL",
        "-c", "user.email=joshmiquel.cs@gmail.com",
        "commit", "-m", f"release: {new}")
    run("git", "tag", tag)
    print(f"committed + tagged {tag}")

    if push:
        # HEAD:master works both locally (on master) and in CI (detached HEAD)
        run("git", "push", "origin", "HEAD:master")
        run("git", "push", "origin", tag)
        print("pushed — release.yml will build + publish")

    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as f:
            f.write(f"version={new}\ntag={tag}\n")


if __name__ == "__main__":
    main()
