# Render bake-off (SJ-24)

Which way of rendering a redesign keeps the real products true and still makes people want the room. Product fidelity is a hard gate: the blind vote chooses only among arms that pass it (SJ-SCOPE-24, Decision 69).

## Summary

- **Fidelity gate.** Of 24 checkable product placements, the composites keep the product: A 19, C2 22, C3 19, C3L 19. Guided edit does not: the open model 13, Gemini 6 (on the earlier product set). Guided edit fails on shape: it redraws the product.
- **Eligible arms.** A, C2, C3 and C3L pass the gate. A and C2 render from the 3D twin, which moved to post-launch (SJ-SCOPE-23), so the launchable eligible arms are **C3 and C3L**. C1, B open and B Gemini are shown in the vote for comparison only.
- **Proposed primary arm: C3L** (real hero photo, furniture removed by 2D inpainting, products composited by code, light-only pass), with the C3 base (the same composite with no model pass) as the labelled fallback. The vote between C3 and C3L can still swap the primary; see Decision below.
- **Cost per design.** C3L about Rs 8 to 10 a design (Rs 25 to 28 a room of three designs, including one removal per room). Gemini guided edit about Rs 153 a design in API calls alone.
- **Checkable share by source.** Wooden Street 98%, IKEA India 64% (dimension drawings excluded). Onboard Wooden Street first.

## Arms

| Arm | What it is | Model role |
| --- | --- | --- |
| A | Products rendered by Blender into the room's 3D twin (splat) | None |
| C1 | A plus an image-model lighting pass | Lights, and may redraw |
| C2 | C1 with the product lock: product pixels from A, only smooth light from the pass | Lights only on products |
| C3 | Real hero photo, furniture removed by 2D inpainting, products composited by Blender, lighting pass plus product lock | Removes furniture; lights |
| C3L | C3 where the pass contributes smooth shading only, everywhere, and only brightness on products (no hue) | Removes furniture; lights brightness |
| B open | Guided edit of the hero photo region by region with product reference images (open model) | Places and draws products |
| B Gemini | The same guided edit with Gemini image (Vertex AI) | Places and draws products |

All arms render the same 12 designs (4 rooms, 3 designs each), built only from products whose 3D asset passed the fidelity gate. The ARKit bedroom was dropped: its capture has no frame that shows the design zone.

## Fidelity gate per arm

Thresholds: silhouette at least 0.70, colour difference (CIEDE2000 of the mean, lightness down-weighted) at most 10, DINOv3 embedding similarity at least 0.475. Colour and embedding are scored against held-out listing photos: never the photo the asset was built from, never dimension drawings or detail crops. Shape is scored against the code-made layout at the same camera. A placement is checkable when its listing has a held-out photo and the product is in frame. Rugs are reported as unknown until the flat items check exists (SJ-150).

| Arm | Checkable placements passed | Failures the arm introduced | Eligible |
| --- | --- | --- | --- |
| A | 19 of 24 | 0 | Yes (post-launch: needs the twin) |
| C1 | 19 of 24 | 3 | No |
| C2 | 22 of 24 | 0 | Yes (post-launch: needs the twin) |
| C3 | 19 of 24 | 1 | Yes |
| C3L | 19 of 24 | 1 | Yes |
| B open | 13 of 24 | 9 | No |
| B Gemini (earlier product set) | 6 of 24 | 13 | No, comparison only |

"Introduced" counts placements where A passes and the arm fails. Eligible means at most 1 introduced failure in 24 (5%, the false-pass tolerance the gate is calibrated to). The 5 failures shared by A and the composite arms come from the assets under room light (a white sofa reads darker than its studio photos; one sofa seen almost edge-on), not from the arm.

Per product detail: `results/product_gate_table.md`. The C3 and C3L introduced failure is one coffee table whose brightness the pass raised (colour 11.7 to 12.4; hue unchanged).

Changes made during the run, all applied to every arm they touch:

- Products whose 3D asset failed the gate (SKÅLBODA, BORGEBY, KRAGSTA) and listings that cannot be checked were replaced by gate-passing products. No lamp passed, so no lamp is placed; lamps would appear as 2D cards.
- The C3 and C3L product light was limited to brightness; it had shifted product colour by up to 19 before.
- Arm B removes furniture the same way C3 does (instruction removal); its grey-area clean-up painted new furniture.

## Other automatic checks

| Arm | Items placed exactly (strict position check) | Nothing invented | Aesthetic (1 to 10) |
| --- | --- | --- | --- |
| A | 38 of 38 (reference) | 12 of 12 | 4.2 |
| C1 | 0 of 38 | 4 of 12 | 7.6 |
| C2 | 10 of 38 | 4 of 12 | 7.3 |
| C3 | 20 of 38 | 7 of 12 | 7.1 |
| C3L | 36 of 38 | 12 of 12 | 6.6 |
| B open | 1 of 38 | 9 of 12 | 7.1 |

C3L adds nothing to the room and keeps products where code put them, at an aesthetic score close to the model-heavy arms.

## Votes

Blind page: one link, mobile, random order, 1 to 5 on "I want this room", no branding. 12 designs, 7 versions each; each voter sees 6 designs (42 photos). Study `s2` uses the final renders; its key is `voting/key_s2.json` (Gemini images marked comparison only). Codes from the earlier study `s1` decode against `voting/key_s1.json`.

No votes yet at the time of writing. Votes are analysed among eligible arms only (C3 against C3L for launch; A and C2 for the post-launch record), with C1, B open and B Gemini reported for comparison:

```
python eval/render-bakeoff/votes.py codes.txt
```

## C3 removal

Furniture is removed by type only (furniture, rugs, decor; never fixtures, built-ins, windows, curtains or radiators): the twin's labels choose the candidates, and a photo detector protects anything it sees as a fixture. The edit model is asked to remove the named types from the real photo; only its changes near the twin's mask are accepted, so it cannot repaint the rest of the room. The hero fill is carried to 3 other keyframes through the floor and wall planes; views edited on their own invent a different room (agreement with the hero 12 to 13 dB, against 14 to 18 dB carried over).

Open risks: where furniture hid a wall the model invents structure (a built-in unit, a radiator), which no check catches yet; carried-over views are patchy where reprojected texture meets fresh fill. The vote uses hero views only.

## Cost per design

Marginal GPU time at Modal list rates plus API calls, median warm times over the 12 designs, Rs 95 to the dollar. Cold starts are a fixed cost.

| Arm | Per design | Per room (3 designs) |
| --- | --- | --- |
| C3, C3L | Rs 8 to 10 | Rs 25 to 28 (one removal Rs 19 to 23, then Rs 2 a design) |
| A, C2 (twin) | Rs 1.4 to 1.9 | Rs 4 to 6, plus twin capture and training (not counted) |
| B open | Rs 11 | Rs 34 |
| B Gemini | about Rs 153 in API calls (141 calls, Rs 1,832 for 12 designs) | about Rs 460 |

The design engine, the hero-view choice and storage are not included. C3L sits inside the Rs 30 to 40 a room target with room for them.

## Product gate and catalog sources

The per-product gate on 111 sofas, tables, chairs and lamps with TripoSG assets (DINOv3, every held-out photo must pass):

| Category | Pass | Fail | Unverifiable |
| --- | --- | --- | --- |
| Chair | 12 | 11 | 5 |
| Table | 8 | 17 | 5 |
| Sofa | 5 | 10 | 12 |
| Lamp | 0 | 12 | 14 |

Checkable share (at least two real product photos: one to build from, one to check against), 211 listings:

| Source | Listings | Studio photos only | With room shots, drawings excluded |
| --- | --- | --- | --- |
| Wooden Street | 55 | 84% | 98% |
| IKEA India | 156 | 21% | 64% |

144 dimension drawings (139 from IKEA) had been counted as photos and are now excluded by a pixel test. The test separates drawings from the darkest real photo by a small margin; it should be checked on new sources.

## Spend

Modal: USD 22.16 billed for the bake-off apps, with about USD 2 to 3 of the last re-render still to bill. Vertex AI (Gemini arm): Rs 1,832. Both are logged in Notion Spends. TRELLIS.2 was not run this round.

## Decision proposed

Primary render arm for launch: **C3L**. Labelled fallback: the C3 base (no model pass). Guided edit (B) is not used to place products; Gemini stays a comparison. If the vote between C3 and C3L, with at least 10 voters, favours C3 by more than 0.3 points, C3 becomes primary; both pass the gate.

## What is in this folder

- `REPORT.md`: this report.
- `results/`: gate tables and JSON (product gate per arm, asset gate, checks, costs, verifiability, drawing views).
- `voting/`: the page source and the keys.

The evaluation harness that produced these results stays on the unmerged PR 59 branch as evidence; it is not product code.
