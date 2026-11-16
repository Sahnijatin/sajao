# Space understanding

You share 3 to 8 photos or a 10 to 30 second video; the server builds a Space Profile with a confidence on every number. Tape values are optional and turn "Estimated" into "Verified".

## Capture on the phone

You scan whatever you want redone: a whole room, a corner, a balcony or any area. There is no room-type picker.

**Live scan mesh.** While you pan, a frame processor finds real feature points in the camera frames on the phone (no AI, no server cost). They are triangulated and drawn with Skia as a glowing mesh that spreads over what has been mapped. Phones with ARKit or ARCore also use their detected planes. Low-tier phones draw dots and edges instead. The mesh is feedback only: nothing from it is stored or used for dimensions.

**Guardrails.** Live chips watch light, speed and shake, phone level, and mirrors and glare. When one fails the scan pauses softly with a fix ("A little more light") and keeps everything mapped so far; you can also scan anyway. Never a hard error.

Works on any Android or iPhone. Translucent glass guides over the camera (level line, "step back", "include a corner", "turn on lights"), a coverage ring, and sharpness and blur checks running on the device without AI. Gallery upload is allowed. ARKit or ARCore poses are attached when the phone has them, but never required. Compass headings are averaged during capture for Vastu. Uploads are compressed on the phone and resumable in the background.

## Capture package

An AR scan records one package for the twin (schema: `Capture.package`). The phone captures; the server understands.

- **Keyframes.** Up to 120 full-resolution JPEGs, the sharpest per direction (30 degree yaw sectors, three pitch bands). The native view saves a candidate only when it is clearly sharper than the best for its direction; the app's recorder decides which are kept and the rest are deleted at once. Images are stored in sensor orientation.
- **Pose and intrinsics per keyframe.** ARKit or ARCore camera pose in the AR world frame (metres, gravity aligned, y up): position and a unit quaternion (x, y, z, w), with the camera's +X right, +Y up and -Z forward relative to the stored image. Intrinsics (fx, fy, cx, cy) are in the stored image's pixels.
- **Depth** where the phone has it (LiDAR scene depth; the ARCore depth API): one file, format SJDEPTH1, little endian: magic `SJDEPTH1`, `uint32` count, then per keyframe `uint16` id length, the keyframe id (`k1`, `k2`, ...), `uint32` width, `uint32` height, `uint16` millimetres per pixel (0 means no reading), `uint8` confidence per pixel (0 to 255). Each depth image is aligned to its keyframe; scale the keyframe's intrinsics by the width ratio. Reader: `sajao_workers.capture_depth`.
- **Planes** as JSON (`sajao-planes-1`): type, ARKit class where available, a column-major 4 by 4 transform, extent and the polygon in the plane's x and z.
- **LiDAR scene mesh** as binary PLY in the AR world frame with ARKit's surface class per face.
- **Live detections** with world points, and a **sensor log** of AR poses (JSON lines, at most five a second).

The package works without AR (keyframes and video, no poses). Depth, planes and mesh are measurements from the phone's sensors; nothing in the package is set by a generative model, and tape still decides fit. Keyframes follow the same upload safety path as photos.

## Server pipeline

1. **Frame selection.** Best 8 to 20 frames by sharpness and coverage.
2. **Geometry.** Multi-view reconstruction (MapAnything Apache 2.0 release or the VGGT commercial checkpoint) when there are several views; single-image metric geometry (MoGe-2) for one photo. Output: camera poses, point cloud, floor and wall planes.
3. **Layout.** Walls, floor polygon, ceiling, doors and windows fitted from planes plus a layout model; SAM 3 masks for walls, floor, windows and existing furniture; a vision-language model names items and reads light direction.
4. **Scale, cross-checked from independent anchors.** The geometry model's metric estimate; standard Indian door height (about 2.0 to 2.1 m); switchboard height; ceiling height priors (2.7 to 3.1 m in typical flats); the vitrified tile grid (600 or 800 mm tiles, so counting tiles measures the floor). Anchors that agree tighten the band; disagreement widens it and triggers a request for one tape value.
5. **Space type and extent.** The pipeline detects what was scanned (living room, bedroom, balcony or other) and how much (a whole room or part of one). Both are shown to you and can be changed.
6. **Space Profile.** A JSON scene graph where every dimension carries a value, a source (measured, estimated, user-confirmed) and an error band.

Single-image models can shrink far-away geometry, which is why scale is cross-checked from anchors rather than trusted from one model.

## Confirm, never draw

The Space Profile card shows what we found (the space type and size, with a Change action) and the plan drawn over your photo. You choose what to redo, "All of it" or "Just a part" by drawing around a corner or wall. You can drag a door, mark each existing item keep, replace or remove, and add tape values. Each value snaps in with a haptic tick and re-fits the whole room.

## Upload safety and privacy

Non-room or explicit images are rejected by a classifier. Faces and personal photos are blurred before storage. Raw video is deleted after processing.
