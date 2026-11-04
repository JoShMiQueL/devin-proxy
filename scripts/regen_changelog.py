#!/usr/bin/env python3
"""Backfill: regenerate every tag's CHANGELOG section in the new format."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import changelog as cl


def main() -> None:
    all_tags = cl.tags()          # newest first
    out = [cl.HEADER.rstrip(), ""]
    for i, tag in enumerate(all_tags):
        prev = all_tags[i + 1] if i + 1 < len(all_tags) else None
        rng = f"{prev}..{tag}" if prev else tag
        items = cl.commits(rng)
        date = subprocess.run(
            ["git", "log", "-1", "--format=%cs", tag],
            capture_output=True, text=True).stdout.strip()
        out.append(cl.section(tag, items, date))
    Path("CHANGELOG.md").write_text("\n".join(out), encoding="utf-8")
    print("regenerated:", ", ".join(all_tags))


if __name__ == "__main__":
    main()
