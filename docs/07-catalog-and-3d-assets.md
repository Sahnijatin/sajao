# Catalog and 3D assets

The catalog is the real bottleneck, so it is its own workstream that starts now, in parallel with phase 0. Products are curated for taste first, then checked for data quality, an app-safe affiliate route and permission to use their images.

## Categories

Lighting (ambient, task, accent), paint and wall finishes, flooring and rugs, curtains and blinds, sofas and seating, beds, tables, storage, wall art, decor, plants and planters.

## v1 size

A few hundred approved items across both room types and the six style profiles, deep enough that every profile can fill every slot. Breadth grows after launch.

## How a product gets in

1. **Brand map.** Brands per category tagged with the [style profiles](14-style-profiles.md) they serve.
2. **Route and permission.** An affiliate network campaign, the brand's own affiliate program, or a direct deal, whose terms allow app traffic and cover use of product images and data. Recorded in the permissions log. No route or no permission, no listing.
3. **Product data.** From the brand's feed or store under those terms. Marketplaces fill gaps for basics only.
4. **Extraction.** A language model pulls dimensions, materials, colours and finish in an offline batch; range rules check every number.
5. **Human approval.** Every product is approved by a person with a style tag and a "verified dimensions" flag. Only verified items may sit in tight spots.

Each product carries: dimensions, category, style tags, colour, material, price, stock, deliverable pincodes, images, affiliate routes and coupon code where available, embeddings, and a 3D model.

## Starting brand candidates (route and permission to confirm)

| Category | Candidates |
| --- | --- |
| Lighting | The Purple Turtles, Ellementry, Pure Home + Living, The Artment, Zwende, The Decor Kart |
| Decor and tableware | Nestasia, Ellementry, Pure Home + Living |
| Furniture | Pepperfry, Urban Ladder, IKEA, WoodenStreet, plus D2C makers found during curation |
| Rugs | Jaipur Rugs and homegrown rug labels found during curation |
| Paint | Asian Paints, Berger, Nerolac shade cards |

## Paint, wall finishes and flooring

- **Paint** is a material on a wall: shade card colour, sheen and texture, shown on her photo through wall masks, with litres and cost from measured wall area.
- **Wall finishes** such as colour blocks and panels use the same masks.
- **Flooring** is a material swap on the floor plane: rugs for everyone, peel-and-stick vinyl for renters, tiles and laminate for owners.

## 3D models

| Priority | Method | Fits |
| --- | --- | --- |
| 1 | Brand-supplied GLB or USDZ | Partners with AR assets |
| 2 | Parametric templates textured with product photos | Boxy items |
| 3 | Image to 3D with TRELLIS.2 (MIT) or SAM 3D Objects (SAM license), rescaled to listed dimensions | Sofas, chairs, lamps, sculptural decor |
| 4 | Simple proxy with a "shape approximate" tag | Anything failing checks |

Every generated model is rendered and reviewed against the product photo; hero pieces always get a human check.

## Keeping it fresh

Daily price and stock sync, link checks, and nearest-equivalent swaps in saved designs with a notice.
