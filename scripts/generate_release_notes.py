#!/usr/bin/env python3
"""Generate release notes from CHANGELOG.md for GitHub releases."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def generate_notes(tag: str, version: str, output_path: str = "release_notes.md") -> str:
    changelog_path = Path("CHANGELOG.md")
    notes = ""

    if changelog_path.exists():
        content = changelog_path.read_text(encoding="utf-8")
        pattern = rf"(## \[{re.escape(version)}\].*?)(?=\n## \[|\Z)"
        match = re.search(pattern, content, re.DOTALL)
        if match:
            notes = match.group(1).strip()
        else:
            match_first = re.search(
                r"(## \[[0-9]+\.[0-9]+\.[0-9]+\].*?)(?=\n## \[|\Z)", content, re.DOTALL
            )
            notes = match_first.group(1).strip() if match_first else f"### Synap Release {version}"
    else:
        notes = f"### Synap Release {version}"

    body = (
        f"# Synap Release {tag}\n\n"
        f"{notes}\n\n"
        "---\n\n"
        "## Installation & Quickstart\n\n"
        "```bash\n"
        f"pip install synap-git=={version}\n"
        "```\n\n"
        "Verify your installation:\n"
        "```bash\n"
        "synap --version\n"
        "synap --help\n"
        "synap init .\n"
        "synap doctor .\n"
        "```\n"
    )

    Path(output_path).write_text(body, encoding="utf-8")
    return body


def main() -> None:
    tag = sys.argv[1] if len(sys.argv) > 1 else "v2.6.0"
    version = sys.argv[2] if len(sys.argv) > 2 else tag.lstrip("v")
    output_path = sys.argv[3] if len(sys.argv) > 3 else "release_notes.md"
    generate_notes(tag, version, output_path)
    print(f"Generated {output_path} for {tag} ({version})")


if __name__ == "__main__":
    main()
