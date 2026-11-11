# Product catalog and 3D assets

The catalog decides whether the product works. A design is only as accurate as the dimensions on each product, and only as attractive as its 3D model.

Each product needs: width, depth and height; category; style tags; colour; material; price; stock; deliverable pincodes; images; an affiliate deep link; and a 3D model in GLB (Android, web) and USDZ (iOS).

**Where products come from**

- Affiliate network feeds (Cuelinks, EarnKaro) and marketplace programs for breadth.
- Direct deals with furniture and decor brands for depth, better commission and proper data. D2C brands on Shopify are the easiest first partners because their product feeds are structured.
- Paint brands' shade cards for wall colours. Paint is a material on a wall, not a 3D object.

**Getting dimensions right**

- Take structured spec fields first. Where specs are buried in text, a small LLM extracts them once per product in an offline batch.
- Validate with range rules (a 3-seater sofa is 180 to 240 cm wide, 75 to 105 cm deep). Outliers go to a human check.
- Products get a "verified dimensions" flag. Only verified products may be used in tight-fit placements.

**Getting 3D models without a 3D team**

| Priority | Method | Fits | Cost |
| --- | --- | --- | --- |
| 1 | Brand-supplied GLB or USDZ | Partners that already have AR assets | Free |
| 2 | Parametric templates textured with the product photo | Boxy items: wardrobes, shelves, tables, rugs, wall art, curtains, mattresses | Near zero, exact size |
| 3 | AI image-to-3D, then rescale the mesh to the listed dimensions | Sofas, chairs, lamps, decor | About $0.15 to $0.50 per model on hosted tools, or free on your own GPU with open models ([cost guide](https://www.3daistudio.com/3d-generator-ai-comparison-alternatives-guide/how-much-does-ai-3d-model-generation-cost)) |
| 4 | Simple proxy shape with a "shape approximate" tag | Anything that fails quality checks | Free |

Rescaling in method 3 is the key trick: the shape may be approximate, but the outer size is exact, so fit checks stay true. At 3,000 products the one-time generation bill is under $1,500 even in the worst case.

**Keeping it fresh**

Sync price and stock daily, test links for dead ends, and auto-swap out-of-stock items in saved designs with the nearest equivalent. Compute one image and text embedding per product, once, and store it in Postgres with pgvector for style search.
