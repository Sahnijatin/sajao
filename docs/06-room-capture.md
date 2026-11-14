# Room understanding

You share 3 to 8 photos or a 10 to 30 second video; the server builds a Room Profile with a confidence on every number. Tape values are optional and turn "Estimated" into "Verified".

## Capture on the phone

Works on any Android or iPhone. Translucent glass guides over the camera (level line, "step back", "include a corner", "turn on lights"), a coverage ring, and sharpness and blur checks running on the device without AI. Gallery upload is allowed. ARKit or ARCore poses are attached when the phone has them, but never required. Compass headings are averaged during capture for Vastu. Uploads are compressed on the phone and resumable in the background.

## Server pipeline

1. **Frame selection.** Best 8 to 20 frames by sharpness and coverage.
2. **Geometry.** Multi-view reconstruction (MapAnything Apache 2.0 release or the VGGT commercial checkpoint) when there are several views; single-image metric geometry (MoGe-2) for one photo. Output: camera poses, point cloud, floor and wall planes.
3. **Layout.** Walls, floor polygon, ceiling, doors and windows fitted from planes plus a layout model; SAM 3 masks for walls, floor, windows and existing furniture; a vision-language model names items and reads light direction.
4. **Scale, cross-checked from independent anchors.** The geometry model's metric estimate; standard Indian door height (about 2.0 to 2.1 m); switchboard height; ceiling height priors (2.7 to 3.1 m in typical flats); the vitrified tile grid (600 or 800 mm tiles, so counting tiles measures the floor). Anchors that agree tighten the band; disagreement widens it and triggers a request for one tape value.
5. **Room Profile.** A JSON scene graph where every dimension carries a value, a source (measured, estimated, user-confirmed) and an error band.

Single-image models can shrink far-away geometry, which is why scale is cross-checked from anchors rather than trusted from one model.

## Confirm, never draw

The Room Profile card shows the plan drawn over your photo. You can drag a door, mark each existing item keep, replace or remove, and add tape values. Each value snaps in with a haptic tick and re-fits the whole room.

## Upload safety and privacy

Non-room or explicit images are rejected by a classifier. Faces and personal photos are blurred before storage. Raw video is deleted after processing.
