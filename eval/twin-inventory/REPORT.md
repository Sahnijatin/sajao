# Inventory-first objects: recall per type on the ARKit rooms

The twin now finds objects inventory first. Two vision models list everything they see in eight keyframes chosen to look all round the room: Gemini 3 Flash on Vertex AI writes the list, and Claude Opus 5.5 lists independently as a cross-check. The lists are merged; each item records which models named it. An open-vocabulary detector then looks for each listed item by name, SAM 2.1 segments it, and the masks are lifted to 3D and fused across frames. Items not placed are retried under other names at a lower threshold, then kept in the twin's inventory with what was tried and why, never dropped. Each object gets a type (furniture, fixture, wall item, textile, decor); built-ins go to the room shell. No model sets a size: sizes come from the fused geometry with error bands.

Scored against hand-made inventories of five ARKitScenes rooms (`hand/`, 131 kinds of thing, 205 items). Recall counts a hand item as found when a listed or placed name matches one of its names (`sajao_workers.inventory_recall`). Tables come from `summarise.py`.

## Listed by the vision models

| Type | Kinds listed | Instance recall |
| --- | --- | --- |
| Furniture | 35 of 39 | 0.75 |
| Fixture | 15 of 24 | 0.61 |
| Wall item | 6 of 6 | 0.76 |
| Textile | 18 of 18 | 0.84 |
| Decor | 25 of 36 | 0.65 |
| Built-in | 6 of 8 | 0.55 |
| **All** | **105 of 131** | **0.71** |

The cross-check pays: in the living room 47331265 only Claude listed the sofa, the rug, the radiator and the display cabinet. Misses are mostly small fixtures (sockets, a subwoofer) and decor.

## Listing recall against the annotated boxes

ARKitScenes annotates 17 classes of furniture and appliances with 3D boxes. Each annotated box the capture saw counts as one real item; listed items of the same class cover them up to their listed count (`listing_recall_by_geometry`). Four rooms have annotations (bedroom 47430034 has none).

| Room | Covered |
| --- | --- |
| Bedroom 47895350 | 8 of 10 |
| Living 41159541 | 7 of 9 |
| Living 41159566 | 6 of 9 |
| Living 47331265 | 9 of 10 |
| **All** | **30 of 38 (0.79)** |

By class: bed 1 of 1, cabinet 5 of 6, chair 7 of 8, shelf 2 of 2, table 6 of 7, TV or monitor 4 of 4, fireplace 1 of 1, sofa 3 of 7, stool 1 of 2.

Gemini alone covers about 27 and Claude alone about 29: the merged list beats either (per-model counts are approximate, since the merge keeps the larger count).

Sofa recall understates the listing: ARKitScenes calls a 0.9 m armchair a sofa, and the models call it an armchair. Pooling seating (chair, sofa, stool) gives 12 of 17: the models undercount seats in three of the four rooms, usually by one or two.

## Placed in 3D, per detector

End to end with objects step version 10 (de-duplication on), on all five rooms. "Kinds" counts hand items with at least one object of a matching name; instance recall counts items, up to the number placed.

| Detector | Kinds placed | Instance recall | Objects per real item | Listed but not placed (flagged) | Cost, five rooms |
| --- | --- | --- | --- | --- | --- |
| Grounding DINO | 79 of 131 | 0.57 | 1.37 (280 for 205) | 44 | Rs 27 |
| YOLOE | 74 of 131 | 0.51 | 1.05 (215 for 205) | 55 | Rs 13 |

An earlier run without de-duplication (version 7) gave Grounding DINO 81 of 131, instance recall 0.60, 2.0 objects per item; and OWLv2 93 of 131, 0.75, but 3.3 objects per item. OWLv2 was not rerun at version 10 (budget).

## De-duplication

Objects step version 10 keeps one object per real thing (`dedupe` in `twin/inventory.py`):

1. Boxes are one thing when they overlap (IoU at least 0.3, or at least 60% of the smaller inside the larger when their volumes are within a factor of about 3: a cushion on a sofa is not the sofa), or when they are the same kind of thing (head noun: armchair and dining chair are both chairs) with centres within 0.3 m at overlapping heights: the back and the seat of one chair. The group pools its views and takes the name most of them gave.
2. The best box of each listed item is never merged into a different kind of thing, so every listed item keeps one object (photo frame and painting stay two).
3. A group seen far less than the best of its name (under 35% of its pooled frames times confidence) and in fewer than 4 frames is dropped: detectors put a common name (book, box) on many things briefly.

A cap on count per listed item was tried and rejected: the vision models undercount, so capping loses real items.

With Grounding DINO, de-duplication takes objects per real item from 1.98 to 1.37 and instance recall from 0.60 to 0.57. The recall lost is names, not things: near-synonyms on one spot (coffee table and dining table on the same table; placemat and table runner) leave one object under one name, and the hand list counts the other name as missing. Placement of annotated big items, which does not depend on names, holds (36 of 38 before, 34 of 38 after, offline on the same boxes).

### The seven dining chairs

In living room 41159541 the hand inventory counts 7 dining chairs. Without de-duplication there were 12 chair objects: chairs seen as separate pieces (back and seat, or once called "armchair"), a stray label on something about a metre up, and a fragment 9 cm wide. Version 9 cut this to 6 and lost two real chairs: one seen only in weak pieces, and a tall chair matching an annotated box but seen in 5 frames. Version 10 pools the pieces of one chair and drops weak groups only when also seen in few frames: **7 dining chair objects, one per chair**, end to end.

## Rough placement of big items

For a launch without the 3D twin: are the big things (bed, sofa, table, chair, cabinet, shelf, TV, fireplace, stool) where the twin says, and about the right size? Each annotated box takes the nearest big object of the same family (seating: chair, sofa, stool; storage: cabinet, shelf; otherwise the class) within half its diagonal, nearest pairs first (`big_item_placement`). Centre error is horizontal; size error compares the longer and shorter footprint sides.

| Detector | Placed | Centre error, median | Centre error, 90% within | Length error, median | Width error, median |
| --- | --- | --- | --- | --- | --- |
| Grounding DINO | 33 of 38 | 8 cm | 19 cm | 12% | 22% |
| YOLOE | 35 of 38 | 9 cm | 32 cm | 13% | 19% |

Footprints come out a little small on average (thin parts such as chair legs and table edges have few depth points). Misses are stools, chairs, small tables and one cabinet. Every size comes from the fused LiDAR geometry with its error band; no model sets one.

## Cost

Version 10, five rooms: Grounding DINO Rs 27, YOLOE Rs 13 (detection and segmentation GPU; the inventory step's two vision-model calls were stored from the earlier run). The earlier runs above cost about Rs 70.
