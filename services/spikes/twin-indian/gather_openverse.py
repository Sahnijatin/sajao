"""Openly licensed photos per Indian-home class via Openverse (internal eval only).

Searches Openverse (which indexes Wikimedia Commons, Flickr and other open
sources) with a few phrases per class, keeps up to MAX_PER_CLASS results with
their license, creator and source URL, and downloads Openverse's thumbnail of
each. The lead then hand-checks which photos really show the class.

    uv run python services/spikes/twin-indian/gather_openverse.py OUT_DIR
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import requests

API = "https://api.openverse.org/v1/images/"
UA = {"User-Agent": "detector-benchmark/0.1"}
MAX_PER_CLASS = 16
QUERIES = {
    "almirah": ["almirah", "steel almirah", "almirah bedroom"],
    "diwan": ["diwan furniture", "diwan bed", "divan daybed india"],
    "puja unit": ["puja room home", "home mandir", "household shrine india"],
    "geyser": ["geyser bathroom", "water heater bathroom wall"],
    "air cooler": ["air cooler", "desert cooler"],
    "water purifier": ["water purifier", "ro water purifier"],
    "shoe rack": ["shoe rack", "shoe cabinet"],
    "dressing table": ["dressing table", "dressing table mirror"],
    "ceiling fan": ["ceiling fan", "ceiling fan room"],
    "tube light": ["tube light", "fluorescent tube light"],
    "jhoola": ["jhoola", "jhula swing", "indoor swing"],
    "air conditioner": ["split air conditioner", "split ac indoor unit"],
    "tv unit": ["tv unit", "tv cabinet living room"],
    "floor seating": ["floor seating", "floor cushions seating"],
}


def get(url: str, **kwargs: Any) -> requests.Response:
    for attempt in range(6):
        r = requests.get(url, headers=UA, timeout=60, **kwargs)
        if r.status_code != 429 and r.status_code < 500:
            r.raise_for_status()
            return r
        time.sleep(float(r.headers.get("Retry-After") or 0) or 5 * 2**attempt)
    r.raise_for_status()
    return r


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for cls, queries in QUERIES.items():
        seen: set[str] = set()
        kept = 0
        for q in queries:
            results = get(API, params={"q": q, "page_size": 20}).json()["results"]
            for r in results:
                if kept >= MAX_PER_CLASS or r["id"] in seen:
                    continue
                seen.add(r["id"])
                try:
                    data = get(r["thumbnail"]).content
                except requests.RequestException:
                    continue
                name = f"{cls.replace(' ', '_')}_{kept:02d}.jpg"
                (out / name).write_bytes(data)
                manifest.append(
                    {
                        "file": name,
                        "class": cls,
                        "title": r.get("title"),
                        "license": f"{r.get('license')} {r.get('license_version') or ''}".strip(),
                        "creator": r.get("creator"),
                        "source": r.get("source"),
                        "landing_url": r.get("foreign_landing_url"),
                    }
                )
                kept += 1
                time.sleep(0.3)
            time.sleep(1.0)
        print(cls, kept, flush=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
