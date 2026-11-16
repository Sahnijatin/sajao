"""Collect about 100 public Indian furniture listings for the per-SKU fidelity gate.

Internal evaluation only (SJ-SCOPE-15): photos are never shipped and never
committed. They are written to a local folder and then uploaded to the private
Modal volume. The repo keeps only the manifest (URLs, dimensions, prices).

    python services/spikes/render-bakeoff/local/fetch_listings.py OUT_DIR

Sources: IKEA India (ikea.com/in) and Wooden Street (woodenstreet.com).
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (evaluation crawler; low rate)"
PAUSE_S = 1.0

# Category -> (IKEA search queries, Wooden Street category slugs, target per source)
PLAN: dict[str, tuple[list[str], list[str], int]] = {
    "sofa": (["3-seat sofa", "2-seat sofa"], ["fabric-sofas", "wooden-sofa"], 9),
    "bed": (["bed frame"], ["all-beds"], 8),
    "almirah": (["wardrobe"], ["almirah", "wardrobes"], 8),
    "table": (
        ["coffee table", "dining table", "side table"],
        ["dining-table-sets", "side-tables", "coffee-tables"],
        9,
    ),
    "chair": (["armchair", "dining chair"], ["arm-chairs", "lounge-chairs"], 9),
    "lamp": (["floor lamp", "table lamp"], ["floor-lamps", "table-lamps"], 7),
}


def get(url: str, timeout: int = 40) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    time.sleep(PAUSE_S)
    return data


def cm(text: str) -> float | None:
    m = re.search(r"([\d.]+)\s*cm", text)
    return float(m.group(1)) if m else None


# ---------- IKEA India ----------


def ikea_search(q: str, n: int = 24) -> list[dict]:
    url = "https://sik.search.blue.cdtapps.com/in/en/search-result-page?" + urllib.parse.urlencode(
        {"q": q, "size": n, "types": "PRODUCT"}
    )
    d = json.loads(get(url))
    return [
        i["product"] for i in d["searchResultPage"]["products"]["main"]["items"] if "product" in i
    ]


def ikea_dims(page: str) -> dict:
    """The product's own measurements list (not packaging, not related products), in cm."""
    m = re.search(r'"measurements":\[(\{"measure".*?)\]', page)
    out: dict[str, float] = {}
    if not m:
        return out
    names = {
        "Width": "width",
        "Depth": "depth",
        "Height": "height",
        "Length": "length",
        "Diameter": "diameter",
        "Shade diameter": "shade_diameter",
        "Max. height": "height",
    }
    for val, unit, name in re.findall(
        r'"measure":"([\d.]+) (cm|mm|m)\b.*?","name":"([^"]+)"', page[m.start() : m.end()]
    ):
        key = names.get(name)
        if key and key not in out:
            out[key] = float(val) * {"cm": 1.0, "mm": 0.1, "m": 100.0}[unit]
    return out


def ikea_gallery(page: str, lifestyle: bool = False) -> list[str]:
    """Product-gallery photos in order: studio shots (`_pe` ids), plus room shots
    (`_ph` ids) when `lifestyle` is set."""
    urls = []
    for m in re.finditer(
        r'aria-label="Select product photo \d+ of \d+[^"]*"[^>]*>.*?<img[^>]*?\ssrc="([^"?]+)',
        page,
        re.S,
    ):
        u = m.group(1)
        if ("_pe" in u or (lifestyle and "_ph" in u)) and u not in urls:
            urls.append(u)
    return [u + "?f=xxl" for u in urls]


def ikea_listings(cat: str, queries: list[str], want: int, need: str = "height") -> list[dict]:
    out, seen_names = [], set()
    for q in queries:
        for p in ikea_search(q):
            if len(out) >= want:
                return out
            name = p.get("name", "")
            if name in seen_names or not p.get("onlineSellable"):
                continue
            try:
                raw = get(p["pipUrl"]).decode("utf-8", "ignore")
                page = html.unescape(raw)
            except Exception as e:
                print("skip", p["pipUrl"], e)
                continue
            dims = ikea_dims(page)
            imgs = ikea_gallery(raw)  # raw: unescaped alt text can contain quotes
            if len(imgs) < (2 if need == "height" else 1) or need not in dims:
                continue
            seen_names.add(name)
            out.append(
                {
                    "id": f"ikea_{p['id']}",
                    "source": "IKEA India",
                    "url": p["pipUrl"],
                    "name": f"{name} {p.get('typeName', '')}".strip(),
                    "category": cat,
                    "price_inr": (p.get("salesPrice") or {}).get("numeral"),
                    "dims_cm": dims,
                    "images": imgs[:6],
                }
            )
            print(cat, out[-1]["id"], out[-1]["name"], dims, len(imgs))
    return out


# ---------- Wooden Street ----------


def ws_next(url: str) -> dict:
    page = get(url).decode("utf-8", "ignore")
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', page, re.S)
    return json.loads(m.group(1)) if m else {}


def ws_dims(s: str) -> dict:
    m = re.search(r'"Dimensions\(cm\)", "value": "([^"]+)"', s) or re.search(
        r"Dimensions \(Cm\):\s*([\d.]+\s*[LWDH](?:\s*x\s*[\d.]+\s*[LWDH])+)", s, re.I
    )
    if not m:
        return {}
    out = {}
    for val, key in re.findall(r"([\d.]+)\s*([LWHD])", m.group(1)):
        out[{"L": "width", "W": "depth", "D": "depth", "H": "height"}[key]] = float(val)
    return out


def ws_images(s: str, lifestyle: bool = False) -> list[str]:
    """Product photos on a Wooden Street page; room shots ("look-") when `lifestyle` is set."""
    imgs: list[str] = []
    for u in re.findall(
        r"https://images\.woodenstreet\.de/image/cache/data/[^\"\\]+?-810x702\.jpg", s
    ):
        low = u.lower()
        if any(k in low for k in ("dimension", "banner", "logo-")) or u in imgs:
            continue
        if "look-" in low and not lifestyle:
            continue
        imgs.append(u)
    return imgs


def ws_listings(cat: str, slugs: list[str], want: int) -> list[dict]:
    out, seen = [], set()
    for slug in slugs:
        try:
            page = get(f"https://www.woodenstreet.com/{slug}").decode("utf-8", "ignore")
        except Exception as e:
            print("skip", slug, e)
            continue
        for prod in dict.fromkeys(re.findall(r"/product/([a-z0-9-]+)", page)):
            if len(out) >= want:
                return out
            stem = re.sub(r"-(honey|walnut|teak|natural|mahogany|white|black)-finish.*$", "", prod)
            if prod in seen or stem in seen:
                continue
            url = f"https://www.woodenstreet.com/product/{prod}"
            try:
                s = json.dumps(ws_next(url))
            except Exception as e:
                print("skip", url, e)
                continue
            dims = ws_dims(s)
            name_m = re.search(r'"name": "([^"]+)"', s)
            price_m = re.search(r'"price": "([\d.]+)"', s)
            imgs = []
            for u in re.findall(
                r"https://images\.woodenstreet\.de/image/cache/data/[^\"\\]+?-810x702\.jpg", s
            ):
                low = u.lower()
                if any(k in low for k in ("dimension", "look-", "banner", "logo-")) or u in imgs:
                    continue
                imgs.append(u)
            if len(imgs) < 2 or "height" not in dims:
                continue
            seen.update({prod, stem})
            out.append(
                {
                    "id": f"ws_{prod[:60]}",
                    "source": "Wooden Street",
                    "url": url,
                    "name": name_m.group(1) if name_m else prod,
                    "category": cat,
                    "price_inr": float(price_m.group(1)) if price_m else None,
                    "dims_cm": dims,
                    "images": imgs[:6],
                }
            )
            print(cat, out[-1]["id"], dims, len(imgs))
    return out


# Design dressing (not part of the fidelity gate): flat items and billboards.
EXTRAS: dict[str, tuple[list[str], int, str]] = {
    "rug": (["rug low pile", "rug flatwoven"], 6, "length"),
    "art": (["picture", "poster"], 6, "height"),
    "plant": (["artificial potted plant"], 4, "height"),
    "cushion": (["cushion cover"], 0, "length"),
}


MAX_IMAGES = 12
GROW_TARGET = 30  # listings per category


def full_gallery(item: dict) -> list[str]:
    """Every product photo on the listing page, studio and room shots."""
    raw = get(item["url"]).decode("utf-8", "ignore")
    if item["source"] == "IKEA India":
        return ikea_gallery(raw, lifestyle=True)
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', raw, re.S)
    return ws_images(json.dumps(json.loads(m.group(1))), lifestyle=True) if m else []


def grow(out_dir: Path) -> None:
    """Add every product photo to each listing (existing images keep their index),
    then top each category up to GROW_TARGET listings."""
    path = out_dir / "listings.json"
    listings = json.loads(path.read_text())
    for item in listings:
        try:
            extra = [u for u in full_gallery(item) if u not in item["images"]]
        except Exception as e:
            print("gallery skip", item["id"], e)
            continue
        item["images"] = (item["images"] + extra)[: max(MAX_IMAGES, len(item["images"]))]
        d = out_dir / item["id"]
        d.mkdir(exist_ok=True)
        for i, u in enumerate(item["images"]):
            if not (d / f"{i}.jpg").exists():
                try:
                    (d / f"{i}.jpg").write_bytes(get(u))
                except Exception as e:
                    print("image skip", u, e)
        path.write_text(json.dumps(listings, indent=1))
    print("galleries done", flush=True)
    have = {x["id"] for x in listings}
    names = {x["name"] for x in listings}
    queries = {
        **{c: q for c, (q, _, _) in PLAN.items()},
        "tv_unit": ["TV bench", "TV storage combination"],
        "shelf": ["bookcase", "shelving unit", "wall shelf"],
    }
    slugs = {**WS_MORE, "tv_unit": ["tv-units"], "shelf": ["bookshelves", "wall-shelves"]}
    for cat in [*PLAN, "tv_unit", "shelf"]:
        need = GROW_TARGET - sum(1 for x in listings if x["category"] == cat)
        if need <= 0:
            continue
        cand = [x for x in ws_listings(cat, slugs[cat], need // 2 + 10) if x["id"] not in have]
        cand += [
            x
            for x in ikea_listings(cat, queries[cat] + [cat], need + 10)
            if x["id"] not in have and x["name"] not in names
        ]
        new = cand[:need]
        for item in new:
            item["images"] = full_gallery(item)[:MAX_IMAGES] or item["images"]
            d = out_dir / item["id"]
            d.mkdir(exist_ok=True)
            for i, u in enumerate(item["images"]):
                try:
                    (d / f"{i}.jpg").write_bytes(get(u))
                except Exception as e:
                    print("image skip", u, e)
        listings += new
        have |= {x["id"] for x in new}
        names |= {x["name"] for x in new}
        path.write_text(json.dumps(listings, indent=1))
        print(cat, "added", len(new), flush=True)


WS_MORE = {
    "sofa": [
        "fabric-sofas",
        "wooden-sofa",
        "sofa-sets",
        "blue-sofas",
        "brown-sofas",
        "3-1-1-sofa-set",
    ],
    "bed": ["all-beds", "king-size-beds", "queen-size-beds"],
    "almirah": ["almirah", "wardrobes"],
    "table": ["coffee-tables", "bedside-tables", "dining-table-sets", "side-tables"],
    "chair": ["arm-chairs", "lounge-chairs"],
    "lamp": ["lamps", "floor-lamps", "table-lamps"],
}


def topup(out_dir: Path) -> None:
    """Bring Wooden Street up to its per-category target, appending to listings.json."""
    path = out_dir / "listings.json"
    listings = json.loads(path.read_text())
    have = {x["id"] for x in listings}
    for cat, (_, _, n) in PLAN.items():
        ws = [x for x in listings if x["category"] == cat and x["source"] == "Wooden Street"]
        need = n - len(ws)
        if need <= 0:
            continue
        new = [x for x in ws_listings(cat, WS_MORE[cat], n + 12) if x["id"] not in have][:need]
        for item in new:
            d = out_dir / item["id"]
            d.mkdir(exist_ok=True)
            for i, u in enumerate(item["images"]):
                try:
                    (d / f"{i}.jpg").write_bytes(get(u))
                except Exception as e:
                    print("image skip", u, e)
        listings += new
        have |= {x["id"] for x in new}
        path.write_text(json.dumps(listings, indent=1))
        print(cat, "added", len(new))


def main(out_dir: Path, extras: bool = False) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    listings: list[dict] = []
    if extras:
        for cat, (queries, n, need) in EXTRAS.items():
            if n:
                listings += ikea_listings(cat, queries, n, need=need)
    else:
        for cat, (queries, slugs, n) in PLAN.items():
            listings += ikea_listings(cat, queries, n)
            listings += ws_listings(cat, slugs, n)
    for item in listings:
        d = out_dir / item["id"]
        d.mkdir(exist_ok=True)
        for i, u in enumerate(item["images"]):
            f = d / f"{i}.jpg"
            if not f.exists():
                try:
                    f.write_bytes(get(u))
                except Exception as e:
                    print("image skip", u, e)
    (out_dir / "listings.json").write_text(json.dumps(listings, indent=1))
    by = {}
    for x in listings:
        by.setdefault((x["category"], x["source"]), 0)
        by[(x["category"], x["source"])] += 1
    print(len(listings), by)


if __name__ == "__main__":
    if "--grow" in sys.argv:
        grow(Path(sys.argv[1]))
    elif "--topup" in sys.argv:
        topup(Path(sys.argv[1]))
    else:
        main(Path(sys.argv[1]), extras="--extras" in sys.argv)
