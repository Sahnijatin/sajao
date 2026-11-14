# Catalog

We ingest widely and show narrowly: thousands of products come in from feeds, and AI plus a human gate decides which few hundred per style are good enough to appear in a design.

## Sources

| Source | How we get products | Tracking notes |
| --- | --- | --- |
| Flipkart | Official affiliate Product Feed API by category | Deeplinks track inside Flipkart's apps |
| Amazon India | Creators API (replaced PA-API) | Reported to need qualifying sales before access; until then, links added by hand from the Associates dashboard |
| Affiliate networks | Cuelinks, EarnKaro, vCommission, INRDeals deeplink APIs | Per-campaign rules on app traffic must be checked |
| D2C brands | Direct deals: feed or CSV, coupon codes | Coupons survive app switching; best attribution |
| Rental | Furlenco via Cuelinks; other rental platforms by direct outreach | "Rent instead: Rs X/month" shown beside buy prices |

Each source is a row in the Notion "Catalog sources" database with its route, app traffic rule, image permission and status.

## AI curation pipeline (offline, batch)

1. **Extract.** A small language model reads titles and specs into dimensions, material, colour and finish; range rules reject impossible numbers.
2. **Look.** A vision model scores image quality, background and aesthetic fit per style profile; near-duplicates are merged.
3. **Trust.** Rating, review count, return signals, seller quality, delivery coverage.
4. **Fit for rooms.** Dimension confidence; only verified-dimension items may sit in tight spots.
5. **Human gate.** Hero pieces (sofas, beds, rugs, statement lights) approved by a person in the admin review tool; long-tail decor auto-approved above a score threshold and spot-checked.
6. **Embed and index.** Image and text embeddings in pgvector for taste retrieval.

Batch pricing is used for all offline model work.

## Freshness

Daily price, stock and link checks. A design whose item goes out of stock offers the nearest equivalent with a notice. Coverage is reported weekly per style and budget band.

## Paint and flooring

Paint colours and flooring finishes are first-class materials in a `Design`. Paint quantity is estimated in litres from wall area.

## 3D assets

Needed for the 3D view and the render fallback. Hero products get 3D models (from brands where available, otherwise generated from product images and reviewed); long-tail decor uses simple proxies. The 2D plan needs only dimensions.
