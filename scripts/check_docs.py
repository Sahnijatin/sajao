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

# Repository paths that hold agent configuration are allowed as references.
PATHS = re.compile(r"\.claude/[\w./-]*|\bCLAUDE\.md\b")

# The third-party register must name every vendor the product depends on, including model
# vendors, so legal can review them. Its rows for product dependencies (hosted models and
# libraries) are exempt from the AI tool rule; coding tools never appear as such rows.
REGISTER = "docs/24-third-party-register.md"
DEPENDENCY_ROW = re.compile(r"^\|[^|]*\|\s*(Hosted model|Library)\s*\|")


def main() -> int:
    findings = 0
    for path in TARGETS:
        if not path.is_file():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            scrubbed = PATHS.sub("", line)
            for rule, pattern in RULES:
                if (
                    rule == "no AI tool mentions"
                    and str(path.relative_to(ROOT)) == REGISTER
                    and DEPENDENCY_ROW.match(line)
                ):
                    continue
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
