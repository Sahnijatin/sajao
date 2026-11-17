"""Check repository docs for writing and hygiene rules.

Scans README.md, ENGINEERING.md and docs/ for em dashes, the British
spelling of license, gendered references to the user, and mentions of
AI coding tools. Vendored skills under .claude/ and CLAUDE.md are not
scanned, and references to their paths are allowed. Exits non-zero on any finding.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = [ROOT / "README.md", ROOT / "ENGINEERING.md", *sorted((ROOT / "docs").rglob("*.md"))]

RULES: list[tuple[str, re.Pattern[str]]] = [
    ("em dash", re.compile("—")),
    ("use 'license'", re.compile(r"\blicence\b", re.IGNORECASE)),
    ("gender-neutral wording", re.compile(r"\b(she|her|hers|herself)\b", re.IGNORECASE)),
    (
        "no AI tool mentions",
        re.compile(r"\b(claude|anthropic|chatgpt|copilot|co-authored-by)\b", re.IGNORECASE),
    ),
]

# Repository paths that hold agent configuration are allowed as references, and so are
# third-party projects whose name contains a flagged word and must be credited by name.
PATHS = re.compile(r"\.claude/[\w./-]*|\bCLAUDE\.md\b|\bbradautomates/claude-video\b")

# Words allowed in one file only. The third-party register lists every model and SDK the
# product uses, for legal review; the product calls a Claude model through the Anthropic
# SDK, so the register must name them. Coding tools stay banned there as everywhere.
ALLOWED_WORDS: dict[str, re.Pattern[str]] = {
    "docs/24-third-party-register.md": re.compile(r"\b(claude|anthropic)\b", re.IGNORECASE),
}


def main() -> int:
    findings = 0
    for path in TARGETS:
        if not path.is_file():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            scrubbed = PATHS.sub("", line)
            allowed = ALLOWED_WORDS.get(path.relative_to(ROOT).as_posix())
            if allowed is not None:
                scrubbed = allowed.sub("", scrubbed)
            for rule, pattern in RULES:
                if pattern.search(scrubbed):
                    findings += 1
                    print(f"{path.relative_to(ROOT)}:{lineno}: {rule}: {line.strip()}")
    if findings:
        print(f"{findings} finding(s)")
        return 1
    print(f"Checked {len(TARGETS)} files: no findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
