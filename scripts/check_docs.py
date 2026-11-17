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
PATHS = re.compile(
    r"\.claude/[\w./-]*|\bCLAUDE\.md\b|\bbradautomates/claude-video\b"
    # Hosted models and their SDK are credited by name in the third-party register.
    r"|Claude Opus 5\.5 \(claude-opus-5-5\) on the Claude API"
    r"|anthropic 2\.8\.0|anthropics/anthropic-sdk-python|anthropic\.com/legal/commercial-terms"
    r"|Anthropic Commercial Terms of Service|sent to Anthropic"
)


def main() -> int:
    findings = 0
    for path in TARGETS:
        if not path.is_file():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            scrubbed = PATHS.sub("", line)
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
