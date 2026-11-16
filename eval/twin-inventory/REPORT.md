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

## Placed in 3D, per detector

Kinds with at least one object, and instance recall:

| Type | Grounding DINO | OWLv2 |
| --- | --- | --- |
| Furniture | 28 of 39, 0.79 | 30 of 39, 0.84 |
| Fixture | 9 of 24, 0.36 | 14 of 24, 0.57 |
| Wall item | 6 of 6, 0.38 | 6 of 6, 0.86 |
| Textile | 17 of 18, 0.92 | 17 of 18, 0.97 |
| Decor | 15 of 36, 0.39 | 20 of 36, 0.55 |
| Built-in | 6 of 8, 0.64 | 6 of 8, 0.64 |
| **All** | **81 of 131, 0.60** | **93 of 131, 0.75** |

| Detector | Items in the rooms | Objects placed | Per item | Listed but not placed (flagged) |
| --- | --- | --- | --- | --- |
| Grounding DINO | 205 | 406 | 2.0 | 40 |
| OWLv2 | 205 | 670 | 3.3 | 9 |

OWLv2 places more of what was listed, but also places far too many objects: detectors put common names (book, box, chair) on many things, and one thing can be found under two listed names. YOLOE was not run: the Modal workspace reached its spend limit first.

## De-duplication

Objects step version 9 keeps one object per real thing:

1. Boxes that overlap (IoU at least 0.3, or at least 60% of the smaller inside the larger when their volumes are within a factor of about 3) are one thing, whatever their labels. The best-seen box stays, and the group takes the name most of its views gave.
2. The best box of each listed item is never merged away, so every listed item keeps one object.
3. Boxes seen far less than the best box of their label (under 35% of its frames times confidence) are dropped.

A cap on count per listed item was tried and rejected: the vision models undercount, so capping loses real items.

Measured offline on the five Grounding DINO rooms, applying the step's function to their saved boxes. "Covered" counts the ARKitScenes ground-truth boxes the capture saw that still have an object on them (at least 30% of the box), whatever its label:

| | Objects per item | Instance recall | Ground-truth boxes covered |
| --- | --- | --- | --- |
| Before | 1.98 (406 for 205) | 0.60 | 37 of 38 |
| After | 1.26 (259 for 205) | 0.57 | 36 of 38 |

The recall drop is mostly near-synonyms on the same spot (armchair, sofa and dining chair; framed picture and painting; placemat and table runner): the object stays, under the other name. The one ground-truth box lost is a stool covered only by a weakly seen box called "armchair". One kind is genuinely thinner: dining chairs in one room fall from 12 objects to 6 against 7 chairs.

Not yet measured: de-duplication on OWLv2 and YOLOE, and on the step itself end to end (the runs stopped at the spend limit).

## Cost

About Rs 70 for the runs above (GPU for detection and segmentation, and the two vision models), Rs 6 to Rs 13 a room.
