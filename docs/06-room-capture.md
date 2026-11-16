# Space understanding

You share 3 to 8 photos or a 10 to 30 second video; the server builds a Space Profile with a confidence on every number. Tape values are optional and turn "Estimated" into "Verified".

## Capture on the phone

You scan whatever you want redone: a whole room, a corner, a balcony or any area. There is no room-type picker.

**Live scan mesh.** While you pan, a frame processor finds real feature points in the camera frames on the phone (no AI, no server cost). They are triangulated and drawn with Skia as a glowing mesh that spreads over what has been mapped. Phones with ARKit or ARCore also use their detected planes. Low-tier phones draw dots and edges instead. The mesh is feedback only: nothing from it is stored or used for dimensions.

**Guardrails.** Live chips watch light, speed and shake, phone level, and mirrors and glare. When one fails the scan pauses softly with a fix ("A little more light") and keeps everything mapped so far; you can also scan anyway. Never a hard error.

**Two scan modes, one package.** The full scan counts coverage on walls and floor from AR planes and offers hints from live labels. The simple scan asks nothing of planes or the detector: it shows one clean progress ring and counts coverage from how the camera turned and moved (heading sectors covered while turning slowly with a sharp picture, plus metres walked from AR poses, or steady time when AR never tracks). Its hints come from motion alone: slow down, step back, walk around, Done. Android starts in the simple scan. Any phone turns simple when no plane is found or the detector has not loaded ten seconds into the scan, and it never switches back, so progress never jumps. The live mesh and labels still draw wherever the phone finds them (LiDAR, or once planes appear); they are a preview, and the complete inventory comes from the server. Both modes record the same capture package.

Works on any Android or iPhone. Translucent glass guides over the camera (level line, "step back", "include a corner", "turn on lights"), a coverage ring, and sharpness and blur checks running on the device without AI. Gallery upload is allowed. ARKit or ARCore poses are attached when the phone has them, but never required. Compass headings are averaged during capture for Vastu. Uploads are compressed on the phone and resumable in the background.

## Coverage meter (spec, not built yet)

The twin is sharp where the phone stood and falls apart away from it. On the first room measured, held-out views with a training camera within 30 cm scored 22.3 dB PSNR and views 50 to 80 cm from any training camera scored 16.1 dB, with twice the perceptual error (numbers: "Render quality" in the golden-room report; limits: "Where the twin can be shown from" in `docs/23-space-twin.md`). No trainer setting closes a gap like that; views from where the phone stood do. Today Done is offered after turning through most of a circle and walking about 3 m, which one spot by the door satisfies. The meter replaces that rule on phones with AR tracking, in both scan modes. It reads AR poses only: no model, nothing sent to a server, and it never sets a dimension.

**What you are asked to do**

1. **Loop.** Walk once around the space, near the walls, with the camera facing across the room at chest height.
2. **Sweeps.** Stand in the middle and turn slowly through a full circle. Then do the same from one or two more spots, at least a metre apart. A space too small for that needs one sweep.
3. **Done** unlocks when the loop and the sweeps are complete.

**What the meter counts**

A pose sample is accepted under the gates the simple scan already uses (tracking normal, turning slower than the limit, steady, sharp picture, pitch within 60 degrees of level, samples at least 90 ms apart, steps between 2 cm and 50 cm).

| Part | Rule | Complete when |
| --- | --- | --- |
| Loop | Accepted positions are binned by bearing from the centre of everything walked so far, in 12 sectors of 30 degrees. A sector counts when a position in it is at least 60% of the median distance from that centre, so standing in the middle and turning fills nothing | 10 of 12 sectors, and the walked path is at least 6 m |
| Sweep | Accepted samples within 40 cm of one spot, binned by heading in 12 sectors of 30 degrees | 10 of 12 sectors from that spot |
| Sweeps | Complete sweeps whose spots are at least 1 m apart and at least 80 cm inside the loop path | 2. A space under 2.5 m across needs 1 |
| Floor look | Share of sweep samples pitched 15 to 45 degrees down, so the floor and low furniture are seen from the middle | 25% of each sweep's samples |

Done is enabled when every row is complete and the scan has its minimum accepted samples. The centre of the loop moves as you walk, so loop sectors are recounted from the stored positions on every sample (at most a few thousand points).

**What you see**

- The progress ring in two parts: loop, then sweeps. It never goes backwards.
- The mini map draws the floor cells walked (50 cm cells), the loop sectors still missing, and a marker where the next sweep should be: the largest gap inside the loop.
- Hints, one at a time, from the motion state: "Walk along the walls", "Keep going round", "Now stand in the middle and turn slowly", "Tilt down a little", "One more spot, over there", "Done". The existing guardrail hints (light, speed, shake) take priority.
- A haptic tick per new sector, a success haptic when the loop closes and when a sweep completes. Theme, motion presets and reduced motion as on every screen; strings in English and Hindi.

**Keyframes for the twin**

Keyframes are kept today as the sharpest per direction (30 degree yaw sectors, three pitch bands), wherever the phone stood. A loop and three sweeps need the sharpest per place and direction: one keyframe per 50 cm floor cell, 30 degree yaw sector and pitch band, with the limit raised from 120 to 200. This is a change to the capture package and its upload size, so it is its own task and needs the founder's approval before it is built.

**The package records the result**

`Capture.package` gains a `coverage` summary (loop sectors, sweep spots with their sectors, metres walked, whether the gate passed), so the server and the golden-room report can relate twin quality to how the room was scanned. A schema change, in its own pull request.

**Phones without AR tracking** keep the simple scan's heading and steady-time rule. They have no poses, so they get no room splat today.

**Open questions for the founder**

- Whether a "Finish anyway" appears after a minute without progress (the twin would then be shown from hero views only). The guardrails already never block; this gate would be the first that does.
- The keyframe limit of 200: about two thirds more upload per scan.

**How we know it works**

Each golden room is scanned twice: once to the current rule and once to the meter. The meter passes when the second scan's far-from-path render scores are within 2 dB PSNR of its near-path scores, and a still from the middle of the room is usable in the review pack.

## Capture package

An AR scan records one package for the twin (schema: `Capture.package`). The phone captures; the server understands.

- **Video.** The whole scan from start to Done, whatever tracking says. On Android, ARCore's Recording API writes an MP4 with AR data tracks. On iOS, the AR session's own camera images are written as an H.264 MP4 at up to 30 frames a second, in sensor orientation like the keyframes, with the AR frames' own timestamps.
- **Keyframes.** Up to 120 full-resolution JPEGs, the sharpest per direction (30 degree yaw sectors, three pitch bands), or per 1.5 s while tracking is lost. Keyframes never depend on the detector or on tracking: a frame taken without tracking is kept without a pose, and the server solves it. The native view saves a candidate only when it is clearly sharper than the best for its cell; the app's recorder decides which are kept and the rest are deleted at once. Images are stored in sensor orientation.
- **Pose and intrinsics per keyframe.** ARKit or ARCore camera pose in the AR world frame (metres, gravity aligned, y up): position and a unit quaternion (x, y, z, w), with the camera's +X right, +Y up and -Z forward relative to the stored image. Intrinsics (fx, fy, cx, cy) are in the stored image's pixels.
- **Depth** where the phone has it (LiDAR scene depth; ARCore raw depth with its own confidence image, not the smoothed depth that fills blank walls by interpolation): one file, format SJDEPTH1, little endian: magic `SJDEPTH1`, `uint32` count, then per keyframe `uint16` id length, the keyframe id (`k1`, `k2`, ...), `uint32` width, `uint32` height, `uint16` millimetres per pixel (0 means no reading), `uint8` confidence per pixel (0 to 255). Each depth image is aligned to its keyframe; scale the keyframe's intrinsics by the width ratio. Reader: `sajao_workers.capture_depth`.
- **Planes** as JSON (`sajao-planes-1`): type, ARKit class where available, a column-major 4 by 4 transform, extent and the polygon in the plane's x and z.
- **LiDAR scene mesh** as binary PLY in the AR world frame with ARKit's surface class per face.
- **Live detections** with world points, and a **sensor log** as JSON lines: AR poses (`source: "ar_pose"`, at most five a second) and motion sensor readings (`source: "imu"`, about ten a second: turn rates in degrees a second as `gyro_alpha`, `gyro_beta`, `gyro_gamma`, and acceleration in m/s² without gravity as `accel_x`, `accel_y`, `accel_z` and with gravity as `gravity_accel_*`, on the axes the platform reports). Each line carries `t`, milliseconds since the scan started.

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

## Upload and registration

On Done the phone uploads every file of the package with the resumable uploader (small files first, the video last), then registers the capture with the API (`POST /v1/captures`). The API validates the Capture object, checks that every storage key belongs to the caller, and stores it for the twin worker. The capture id is chosen on the phone when the scan starts, so both steps are safe to repeat after a lost connection or an app restart: finished files are skipped and registering again returns the stored capture.

## Upload safety and privacy

Non-room or explicit images are rejected by a classifier. Faces and personal photos are blurred before storage. Raw video is deleted after processing.
