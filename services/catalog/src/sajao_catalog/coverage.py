"""Coverage of the catalog: category by style by budget band."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from sajao_catalog.model import CatalogEntry

STYLES = (
    "modern_indian",
    "warm_luxe",
    "japandi",
    "warm_maximalist",
    "eclectic_retro",
    "minimal_wabi_sabi",
)
BANDS = ("value", "mid", "premium")


def counts(entries: Iterable[CatalogEntry]) -> Counter[tuple[str, str, str]]:
    c: Counter[tuple[str, str, str]] = Counter()
    for e in entries:
        tags = e.product.get("style_tags")
        for style in tags if isinstance(tags, list) else []:
            c[(str(e.product["category"]), str(style), e.budget_band)] += 1
    return c


def table(entries: list[CatalogEntry], placeable_only: bool = False) -> str:
    """Markdown: one row per category, one column per style, cells 'value/mid/premium'."""
    rows = [e for e in entries if not placeable_only or e.gate.result == "pass"]
    c = counts(rows)
    cats = sorted({k[0] for k in c} | {str(e.product["category"]) for e in rows})
    head = "| Category | Products | " + " | ".join(STYLES) + " |"
    sep = "| --- | --- | " + " | ".join("---" for _ in STYLES) + " |"
    lines = [head, sep]
    for cat in cats:
        n = sum(1 for e in rows if e.product["category"] == cat)
        cells = ["/".join(str(c[(cat, s, b)]) for b in BANDS) for s in STYLES]
        lines.append(f"| {cat} | {n} | " + " | ".join(cells) + " |")
    return "\n".join(lines)
