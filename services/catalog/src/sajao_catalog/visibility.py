"""Which catalog products a build may show (Decision SJ-DEC-84).

A development product keeps `image_use_permitted: false` and its flags. Development and
closed-test builds may show it; the store release never does (engineering rule 9 stands
for the public release). The setting is off unless a build turns it on.
"""

from __future__ import annotations

import os

from sajao_catalog.model import CatalogEntry

ENV = "SAJAO_SHOW_FLAGGED_PRODUCTS"


def flagged_allowed(environ: dict[str, str] | None = None) -> bool:
    value = (environ if environ is not None else os.environ).get(ENV, "")
    return value.strip().lower() in {"1", "true", "yes"}


def may_show(entry: CatalogEntry, *, allow_flagged: bool) -> bool:
    """Live products always; development products only where the build allows them."""
    if entry.stage == "live":
        return entry.product.get("image_use_permitted") is True
    return allow_flagged
