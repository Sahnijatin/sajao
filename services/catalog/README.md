# sajao-catalog

One ingest path for every product source: hand-curated development products today, affiliate and brand feeds later. An adapter turns a source's data into `Listing`s; the ingest validates each against the `Product` contract and upserts it into the catalog.

```
uv run sajao-catalog ingest --adapter curated --input data/development/curated.json --out data/development/catalog.jsonl
uv run sajao-catalog coverage --catalog data/development/catalog.jsonl [--placeable]
```

- **Truth.** Dimensions, price and stock come from the listing and a live check of its page, never from a model. Listing dimensions are `estimated` (unverified retailer data) with a 2 cm band, and the entry records where on the page they came from.
- **Permission.** A product is live only with image permission and a permitted route. Until a source grants both, the entry stays at stage `development`, its product carries `image_use_permitted: false` and `catalog_stage: development`, and `flags` says why (engineering rule 9). Nothing is written as permitted that is not.
- **Fidelity.** Each entry stores its fidelity gate result: `pass`, `fail` or `unverifiable`. Only `pass` products are placed as exact products in designs.
- **Flat items.** Rugs and wall art are rejected until the flat items check exists (SJ-150).
- **Idempotent.** The product id is derived from source and SKU; re-ingesting replaces the entry.
- **Photos** stay on the private Modal volume `sajao-catalog`; entries hold their paths, never the files.

Feeds add a module under `adapters/` and register it in `ADAPTERS`.

## Showing flagged products

Development products keep `image_use_permitted: false` and their flags. Whether a build may show them is one setting (Decision SJ-DEC-84): `SAJAO_SHOW_FLAGGED_PRODUCTS` on the server and `EXPO_PUBLIC_SHOW_FLAGGED_PRODUCTS` in the app, set to `1` in the `development`, `preview` and `closed-test` EAS profiles and absent from `production`, the store release. `sajao_catalog.visibility.may_show` applies it: live products always, development products only where the setting is on.

## Fidelity gate

A product is placed as itself only when its 3D asset matches its listing photos. The gate is our own code: a numpy point rasterizer (`gate/raster.py`), a camera search (`gate/search.py`), the scores (`gate/metrics.py`) and the rule (`gate/gate.py`). No third-party renderer. Two models run on one GPU container through Modal: BiRefNet (MIT) cuts the product out of each photo, DINOv3 embeds images.

```
sajao-catalog gate PRODUCT_FOLDER
```

The folder holds `product.json` (`category`, `dims_cm`, `main`: the photo the asset was built from), `photos/` (the listing photos, named by index) and `asset.glb`. The command writes `gate.json`: `pass`, `fail` or `unverifiable`, with every photo's use and every view's scores.

1. **Photos.** Each cut-out is classified (`gate/views.py`): dimension drawings, crops that run off the frame, photos with other furniture and tiny cut-outs are not checks. A held-out photo that DINOv3 finds unlike the main photo shows a part or a scene, not the product, and is not a check either. The main photo is never a check: the asset was built from it.
2. **Asset.** Code scales the asset to the listing size and, when it has no texture, colours it from the main photo.
3. **Views.** For each check photo, the camera is found by search and the asset is scored there: shape (silhouette agreement with a 2% tolerance), colour (CIEDE2000 of the mean colours, lightness weighted half) and look (DINOv3 similarity).
4. **Rule.** Every check photo must pass all three; colour is skipped on photos of a lamp switched on. No check photo means `unverifiable`, never a pass.

The shape threshold is calibrated so that another product's asset of the same category passes at most 5% of the time (`gate.calibrate`).

Launch admission uses one rule for every category (shape 0.70, colour 10, look 0.475); that is `result` in `gate.json`. A held-out bed photo is styled with bedding the asset does not have, so even the right bed scores lower on look. Beds get look 0.35 for development and closed-test builds only (`gate.DEVELOPMENT`): 0 of 51 wrong-bed pairs pass there. That verdict is `development_result` in `gate.json` and never admits a product to the launch catalog.

### Beds and lamps

`data/development/gate_beds_lamps.json` holds the run on the bake-off's 17 beds and 26 lamps (TripoSG assets), with three wrong-product pairs per product for calibration:

| | Pass | Fail | Unverifiable | Wrong pairs passing |
| --- | --- | --- | --- | --- |
| Beds | 3 (1 at the approved look threshold) | 14 | 0 | 0 of 51 |
| Lamps | 3 | 14 | 9 | 2 of 51 |

Why the rest fail:

- **Beds: look.** The listing's other photos show the bed made up with a duvet and pillows, or a different side, while the asset is the bare bed from the main photo. Shape agrees (0.85 to 0.98 on most views); look does not.
- **Beds: colour.** Wood finishes (honey, walnut, teak) differ by 11 to 17 between studio photos of the same bed, so one warm photo fails colour.
- **Lamps: no main photo.** Six floor lamps were shot only in rooms, so no asset could be built; three more have no other photo of the whole lamp. All nine are unverifiable.
- **Lamps: thin parts.** Work lamps, arcs and pendants (HÅRTE, PILSKOTT, KRUX, BRUNBÅGE, ZEBRASÄV) come out of the image-to-3D model with the wrong arms or cords, and their shape fails.
- **Lamps: glass and lit shades.** Glass and switched-on photos change look and colour; colour is now skipped on lit photos, look is not.
