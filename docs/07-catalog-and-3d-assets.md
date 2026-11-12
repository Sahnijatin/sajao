# Catalog and 3D assets

The catalog decides whether the product works. Products are curated for taste first, then checked for data quality and an app-safe affiliate route. Nothing is listed just because a feed returned it.

## Categories

Lighting (ambient, task, accent), paint and wall finishes, flooring and rugs, curtains and blinds, sofas and seating, beds, tables, storage, wall art, decor, plants and planters.

## How a product gets in

1. **Brand map.** For each category, a list of brands tagged with the [style profiles](14-style-profiles.md) they serve, built from references and research.
2. **Affiliate route check.** For each brand: an affiliate network campaign (Cuelinks, vCommission, EarnKaro and others), the brand's own affiliate program (many Shopify brands run one), or a direct deal with a coupon code or server postback. The route must allow app traffic. No route, no listing.
3. **Ingestion from the brand's own store.** Most D2C brands run on Shopify and publish structured product data. Marketplaces are used only for basics that fill gaps, never for hero pieces.
4. **Extraction.** A small language model pulls dimensions, materials, colours and finish from product pages in an offline batch. Range rules check every number (a 3-seater sofa is 180 to 240 cm wide).
5. **Human approval.** Every product is approved by a person before it goes live, with a style tag and a "verified dimensions" flag. Only verified items may be used in tight spots.
6. **Catalog checker.** A small trained model flags bad photos and suspicious dimensions before review.

Each product carries: dimensions, category, style tags, colour, material, price, stock, deliverable pincodes, images, one or more affiliate links, image and text embeddings, and a 3D model (GLB, plus USDZ for iOS AR later).

## Starting brand candidates (affiliate route to confirm for each)

| Category | Candidates |
| --- | --- |
| Lighting | The Purple Turtles, Ellementry, Pure Home + Living, The Artment, Zwende, The Decor Kart |
| Decor and tableware | Nestasia, Ellementry, Pure Home + Living |
| Furniture | Pepperfry, Urban Ladder, IKEA, WoodenStreet, plus D2C makers found during curation |
| Rugs | Jaipur Rugs and homegrown rug labels found during curation |
| Paint | Asian Paints, Berger, Nerolac shade cards |

The list grows from reference reels and style research. The bar is "would this appear in a room people save".

## Paint, wall finishes and flooring

- **Paint** is a material on a wall, not an object: real shade card colours, sheen and texture (plaster, limewash, matte), shown on her photo through wall masks. A calculator gives litres and cost from true wall area. Painter referrals come later.
- **Wall finishes** such as colour blocks and panels are surface treatments in the design, using the same masks.
- **Flooring** is a material swap on the floor plane: rugs for everyone, peel-and-stick vinyl for renters, tiles and laminate for owners.

## 3D models without a 3D team

| Priority | Method | Fits |
| --- | --- | --- |
| 1 | Brand-supplied GLB or USDZ | Partners with AR assets |
| 2 | Parametric templates textured with product photos | Boxy items: wardrobes, shelves, tables, rugs, frames, curtains, mattresses |
| 3 | Image to 3D with TRELLIS.2 (MIT license) or SAM 3D Objects (SAM license), then rescaled to listed dimensions | Sofas, chairs, lamps, sculptural decor |
| 4 | Simple proxy with a "shape approximate" tag | Anything failing quality checks |

Quality gate for methods 2 and 3: the model is rendered and compared with the product photo by image embedding similarity. Hero pieces (sofas, beds, statement lamps) also get a human check. Small accents (vases, frames, books) may appear only in the photo render as faithful cutouts rather than as 3D meshes.

## Keeping it fresh

Price and stock sync daily, links are tested for dead ends, and out-of-stock items in saved designs are swapped for the nearest equivalent with a notice.
