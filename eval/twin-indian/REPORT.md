# Indian home objects: YOLOE, Grounding DINO and OWLv2

The twin's detector is now prompted with a pinned list of Indian home object names next to the general list (`sajao_workers.models`). This benchmark asks how well each candidate detector finds those objects. It is a first look: the hand-checked Indian-object eval set from real scans (SJ-130) does not exist yet, so this uses openly licensed web photos. Every number comes from `results.json`; the photos and their licenses are listed in `photos.json`.

## Setup

- **Classes added:** almirah, diwan, puja unit, geyser, air cooler, water purifier, shoe rack, dressing table, ceiling fan, tube light, jhoola, air conditioner, tv unit, floor seating, gas stove. Some are prompted with a plainer description (for example "steel almirah cupboard"); detections come back under the class name.
- **Photos:** Openverse search (Wikimedia Commons and Flickr), 207 downloaded, 58 kept after a hand check that the photo clearly shows the class. Most search hits were wrong. Water purifier had no usable photo; diwan, geyser and jhoola have one each, so their numbers mean little.
- **Detectors:** each with the full vocabulary (30 general plus 15 Indian names) and its production score threshold (YOLOE 0.25, Grounding DINO 0.30, OWLv2 0.20). YOLOE was also run at 0.10.
- **Scores (per photo):** found if the detector reports the photo's class (exact) or a class in the same group (group, for example almirah reported as wardrobe). Wrong Indian class: the photo also got another Indian class. False alarms: share of 80 frames from two US homes (ARKitScenes) in which the detector reports a class that cannot be there (almirah, diwan, puja unit, geyser, air cooler, jhoola, floor seating).
- **Furniture check:** the full objects step on the ARKitScenes living room (120 frames, LiDAR), scored against its 3D boxes as before.

## Results

| Detector | Found, exact class | Found, same group | Wrong Indian class | False alarms in US homes | GPU time, 58 photos plus 80 frames |
| --- | --- | --- | --- | --- | --- |
| YOLOE (0.25) | 9% | 29% | 14% | 8% | 34 s |
| YOLOE (0.10) | 21% | 52% | 21% | 25% | 3 s (warm) |
| Grounding DINO | 48% | 78% | 47% | 36% | 34 s |
| **OWLv2** | **83%** | **90%** | 24% | 26% | 39 s |

Per class, exact (photos found of photos):

| Class | Photos | YOLOE | Grounding DINO | OWLv2 |
| --- | --- | --- | --- | --- |
| Air conditioner | 10 | 2 | 10 | 10 |
| Ceiling fan | 10 | 1 | 10 | 9 |
| Shoe rack | 10 | 0 | 0 | 10 |
| TV unit | 7 | 0 | 3 | 6 |
| Dressing table | 5 | 0 | 0 | 4 |
| Air cooler | 4 | 1 | 0 | 3 |
| Almirah | 3 | 0 | 0 | 0 |
| Puja unit, tube light, floor seating | 2 each | 1 of 6 | 5 of 6 | 5 of 6 |
| Diwan, geyser, jhoola | 1 each | 0 of 3 | 0 of 3 | 1 of 3 |

Furniture check (ARKitScenes living room, objects step):

| Primary detector | Objects | Recall, right class (IoU 0.25) | Precision | Median centre error |
| --- | --- | --- | --- | --- |
| YOLOE | 30 | 60% | 33% | 13 cm |
| OWLv2 | 66 | 60% | 19% | 15 cm |

## Findings

- **YOLOE misses most Indian objects.** Its text prompts for unfamiliar names score below its threshold; lowering the threshold to 0.10 lifts recall only to 21% and triples false alarms.
- **OWLv2 finds them best** (83% exact) with fewer wrong Indian labels than Grounding DINO. Most of its false alarms are "floor seating" on rugs and cushions (19 of 80 frames); without that class its false-alarm rate is about 3%.
- **On ordinary furniture OWLv2 matches YOLOE's recall** but reports twice as many objects, so precision drops. Some extra objects are unannotated real items; some are duplicates.
- **Almirah is not found by any detector** on these three photos; it is reported as a wardrobe or cabinet at best (group match).

## Recommendation

OWLv2 (Apache 2.0) as the primary detector, YOLOE dropped from the chain or kept as a fallback, once two checks pass: a higher OWLv2 threshold or per-class thresholds that bring furniture precision back to YOLOE's level, and the same comparison on the first golden rooms. This also removes the AGPL question on YOLOE. The switch is one setting (`SAJAO_DETECTORS=owlv2,grounding-dino`). Until then YOLOE stays the default, as the task specifies.

## Limits

- Web photos, not scans: objects are large and centred, lighting is better than in a phone video, and the set is small (58 photos, 13 classes). The SJ-130 eval set replaces this.
- Image-level scores only: boxes were not hand-drawn, so a detection anywhere in the photo counts.
- Some photos are licensed for non-commercial use only; they are used for internal evaluation and are never trained on or redistributed.

## Cost

About 0.1 USD of GPU time on Modal (L40S) for the benchmark runs and the two furniture checks.
