# sajao-catalog

One ingest path for every product source: hand-curated development products today, affiliate and brand feeds later. An adapter turns a source's data into `Listing`s; the ingest validates each against the `Product` contract and upserts it into the catalog.

```
uv run sajao-catalog ingest --adapter curated --input data/development/curated.json --out data/development/catalog.jsonl
uv run sajao-catalog coverage --catalog data/development/catalog.jsonl [--placeable]
```

- **Truth.** Dimensions, price and stock come from the listing and a live check of its page, never from a model. Listing dimensions are `estimated` (unverified retailer data) with a 2 cm band, and the entry records where on the page they came from.
- **Permission.** A product enters the contract only with image permission and a permitted route. Until a source grants both, the entry stays at stage `development`, its product carries `image_use_permitted: false`, and `flags` says why (engineering rule 9). Nothing is written as permitted that is not.
- **Fidelity.** Each entry stores its fidelity gate result: `pass`, `fail` or `unverifiable`. Only `pass` products are placed as exact products in designs.
- **Flat items.** Rugs and wall art are rejected until the flat items check exists (SJ-150).
- **Idempotent.** The product id is derived from source and SKU; re-ingesting replaces the entry.
- **Photos** stay on the private Modal volume `sajao-catalog`; entries hold their paths, never the files.

Feeds add a module under `adapters/` and register it in `ADAPTERS`.
