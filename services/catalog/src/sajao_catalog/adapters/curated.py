"""Hand-curated development products: a JSON list of listings checked by a person."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from sajao_catalog.model import Listing


def listings(path: Path) -> Iterator[Listing]:
    for raw in json.loads(path.read_text()):
        yield Listing.model_validate(raw)
