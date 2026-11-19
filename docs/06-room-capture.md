# Space understanding

Photos are the main way in. You take one to three landscape photos (or pick photos or a video already on the phone); the server builds a Space Profile with a confidence on every number, at the estimated level. The AR scan, or two tape values, is the upgrade to a measured room, and only a measured room gets fit claims.

## Take photos

"Add a room" opens Take photos. A short note comes first: step back so the floor shows, put away anything private, keep people out of the picture. The camera is landscape only. The app's screens stay upright, so the phone's own orientation decides: the shutter works only while the camera library reports the phone on its side, the hint turns to read upright, and each photo is checked once more after it is decoded upright and resized (2048 px on the long edge unless the server asks for less, JPEG quality 0.9, so a 4:3 photo goes up at 2048 by 1536); one that is not wider than tall is not kept. Each photo is reviewed ("Happy with the view and lighting?", Retake or Continue), then all of them are shown together, each with its own Retake, with "Add another view" up to three. The photos go up as a capture package with no AR data (`ar.tracking` is `none`), marked as from the camera, through the same uploader and registration as a scan. No library permission is needed: the camera writes to the app's own files.

## Measure: the AR scan

"Measure this room for exact fit" opens the scan. You scan whatever you want redone: a whole room, a corner, a balcony or any area. There is no room-type picker.

**Scan screen.** The person scanning sees the camera, one thin progress ring and one plain instruction at a time; the pieces below are how it works underneath. The mesh, guardrail chips, compass map and live labels are diagnostics behind the debug flag (three taps on the camera in a development or preview build). On AR phones the native view draws the camera image only (`overlay` off) unless the flag is on.

**Review before upload.** Done opens a review over the scan, which stays open underneath. The review reads the scan's own coverage: the share covered, the sides, walls or floor still missing, and a rough size from two pairs of facing walls (rounded to 10 cm, shown as "about", never stored or sent). "Rescan this part" returns to the same scan; only "Looks good" finishes the capture and starts the upload. The camera keeps running during the review, but nothing it sees then goes into the package: the screen tells the recorder when the review opens and closes, the native view pauses its keyframes, the review window is written into the package, and detections and sensor readings from that time are not recorded.

**Live scan mesh.** While you pan, a frame processor finds real feature points in the camera frames on the phone (no AI, no server cost). They are triangulated and drawn with Skia as a glowing mesh that spreads over what has been mapped. Phones with ARKit or ARCore also use their detected planes. Low-tier phones draw dots and edges instead. The mesh is feedback only: nothing from it is stored or used for dimensions.

**Guardrails.** Light, speed and shake, phone level, and mirrors and glare are watched all the time. When one fails the scan pauses softly with a plain nudge ("It's a bit dark. Switch on a light") and keeps everything mapped so far; you can also keep going anyway. Never a hard error.

**Two scan modes, one package.** The full scan counts coverage on walls and floor from AR planes and offers hints from live labels. The simple scan asks nothing of planes or the detector: it shows one clean progress ring and counts coverage from how the camera turned and moved (heading sectors covered while turning slowly with a sharp picture, plus metres walked from AR poses, or steady time when AR never tracks). Its hints come from motion alone: slow down, step back, walk around, Done. Android starts in the simple scan. Any phone turns simple when no plane is found or the detector has not loaded ten seconds into the scan, and it never switches back, so progress never jumps. The live mesh and labels still draw wherever the phone finds them (LiDAR, or once planes appear); they are a preview, and the complete inventory comes from the server. Both modes record the same capture package.

Scanning needs a phone that runs ARKit or ARCore, because the measurements come from AR. Before anything else the app checks for it: a phone without AR, or one whose AR session will not start, sees a friendly note and goes to photos, where the redesign and the shopping list still work at the estimated level. It is never an error screen, never a camera permission request, and never a scan that could not be measured. On phones that can scan: one instruction at a time, the coverage meter, and sharpness and blur checks running on the device without AI. Compass headings are averaged during capture for Vastu. Uploads are resumable.

## Coverage meter

The server's result is sharp where the phone stood and weak away from it, so on every phone whose AR gives positions, in both scan modes, Done waits for the coverage meter. It reads AR positions and headings only: no model, nothing sent to a server, and it never sets a dimension. Rules in `apps/mobile/src/capture/coverage-meter.ts`.

- **Loop.** A walk round the space near the walls. Positions are binned by bearing from the middle of everything walked, in 12 sectors; a position counts only when it is at least 60% of the median distance from that middle, so turning in the middle fills nothing. Complete at 10 of 12 sectors and 6 m walked. The few centimetres a phone wanders while turning do not count as walking.
- **Sweeps.** A slow full turn from one spot: samples within 40 cm, 10 of 12 heading sectors. Two sweeps count when they are at least 1 m apart and at least 80 cm inside the loop; a space under 2.5 m across needs one, anywhere in it.
- A pose counts under the simple scan's gates: tracking normal, turning slowly, steady, a sharp picture, within 60 degrees of level.
- **Wall tilts.** One slow tilt up to the ceiling and down to the floor on each wall. A phone cannot hold the floor and the ceiling in one picture, and the measured shell only counts a wall that was seen from near the floor to near the ceiling. The room is taken as four quarter turns; each needs the phone tilted at least 20 degrees up and at least 20 degrees down somewhere in it, at any point in the scan and not in the same picture. Looking only down, as at the floor, tilts no wall.
- **What you see.** A ring in two halves, the loop then the sweeps and wall tilts, which never goes backwards; a map of the floor walked, the loop sectors still missing and where to stand for the next sweep; one hint at a time ("Walk along the walls", "Keep going round", "Now stand in the middle and turn slowly", "On each wall, tilt slowly up to the ceiling, then down to the floor", "One more spot, over there", "Done"), after the guardrail hints; a tick for each new sector and a success haptic when the loop closes and when a sweep counts.
- **Finish anyway.** A scan never traps you: after 60 seconds without the ring moving, "Finish anyway" appears. The scan then records what was still missing (loop sectors, metres, sweeps, wall tilts) for the review to name.
- A phone whose AR gives no positions keeps the simple scan's heading and steady-time rule.

## Capture package

An AR scan records one package for the twin (schema: `Capture.package`). The phone captures; the server understands.

- **No video.** The scan video is not recorded or uploaded at launch: no server step reads it, and it was most of every upload. The package field stays optional in the schema, so it can return later.
- **Keyframes.** Up to 200 full-resolution JPEGs (quality 80), the sharpest per viewpoint: a viewpoint is a place the phone stood (0.5 m squares of floor) and a direction it looked from there (30 degree yaw sectors, three pitch bands). Walking the room keeps adding keyframes; turning on one spot gives at most 36 and time alone gives none. While tracking is lost there is no place or direction, so one frame is kept per 1.5 s. Keyframes never depend on the detector or on tracking: a frame taken without tracking is kept without a pose, and the server solves it. The native view saves a candidate only when it is clearly sharper than the best for its cell; the app's recorder decides which are kept and the rest are deleted at once. Images are stored in sensor orientation.
- **Pose and intrinsics per keyframe.** ARKit or ARCore camera pose in the AR world frame (metres, gravity aligned, y up): position and a unit quaternion (x, y, z, w), with the camera's +X right, +Y up and -Z forward relative to the stored image. Intrinsics (fx, fy, cx, cy) are in the stored image's pixels.
- **Depth** where the phone has it (LiDAR scene depth; ARCore raw depth with its own confidence image, not the smoothed depth that fills blank walls by interpolation): one file, format SJDEPTH1, little endian: magic `SJDEPTH1`, `uint32` count, then per keyframe `uint16` id length, the keyframe id (`k1`, `k2`, ...), `uint32` width, `uint32` height, `uint16` millimetres per pixel (0 means no reading), `uint8` confidence per pixel (0 to 255). Each depth image is aligned to its keyframe; scale the keyframe's intrinsics by the width ratio. Reader: `sajao_workers.capture_depth`.
- **Planes** as JSON (`sajao-planes-1`): type, ARKit class where available, a column-major 4 by 4 transform, extent and the polygon in the plane's x and z. This file is the phone's measurement export: every wall, floor, ceiling, door and window plane the phone found, in metres. `sajao_workers.ar_measurements` turns it into the room's measurements by geometry alone: each wall's length corner to corner, the floor's size and area, the ceiling height, and each door and window with its width, height, sill and distance from the nearest corner. Every value is an estimated dimension with an error band, and a wall whose neighbour was not found is marked as seen only in part (a lower bound). Doors and windows are found in the keyframes by the vision model and measured by casting each mask from its keyframe's pose onto the measured wall planes (`sajao_workers.ar_openings`), so every phone has them and no model sets a dimension; ARKit's own door and window planes are a cross-check on iPhones. Before that, `sajao_workers.object_planes` removes the vertical planes that are faces of things in the room (a fridge's sides, a cabinet front, a table's edge): a plane is an object face when it lies against a cluster of the phone's confident live detections of a large kind, or inside a box the twin placed, and stays below it. A plane the phone classed as a wall, one reaching the ceiling, and one longer than any furniture are always kept. The golden-room report (`eval/golden`) scores these measurements against the tape. A scan through several spaces is split into areas by `sajao_workers.areas`: the measured floor polygon is cut where it narrows to a doorway (a chord of 0.6 to 1.4 m with a space of at least 2 m2 on each side, each deeper than the cut is wide), shortest cut first. An open-plan L is wide where its arms meet, so it stays one area. Each area gets its floor polygon, the objects whose footprints are in it, the keyframes taken in it and the photo that sees most of its floor. The app shows each area with that photo, taken from the pictures on the phone, and its own walls, doors, windows, items and confidence, and asks once which area to redesign. The golden-room report (`eval/golden`) scores these measurements against the tape.
- **LiDAR scene mesh** as binary PLY in the AR world frame with ARKit's surface class per face.
- **Live detections** with world points, and a **sensor log** as JSON lines: AR poses (`source: "ar_pose"`, at most five a second) and motion sensor readings (`source: "imu"`, about ten a second: turn rates in degrees a second as `gyro_alpha`, `gyro_beta`, `gyro_gamma`, and acceleration in m/s² without gravity as `accel_x`, `accel_y`, `accel_z` and with gravity as `gravity_accel_*`, on the axes the platform reports). Each line carries `t`, milliseconds since the scan started.

- **Review windows** (`review_windows`): the times, from the start of the capture, when the review was open over the scan and the phone was lowered. The phone records no keyframe then.

The package works without AR (keyframes, no poses). Depth, planes and mesh are measurements from the phone's sensors; nothing in the package is set by a generative model, and tape still decides fit. Keyframes follow the same upload safety path as photos.

## Server pipeline

1. **Frame selection.** Best 8 to 20 frames by sharpness and coverage.
2. **Geometry.** Multi-view reconstruction (MapAnything Apache 2.0 release or the VGGT commercial checkpoint) when there are several views; single-image metric geometry (MoGe-2) for one photo. Output: camera poses, point cloud, floor and wall planes.
3. **Layout.** Walls, floor polygon, ceiling, doors and windows fitted from planes plus a layout model; SAM 3 masks for walls, floor, windows and existing furniture; a vision-language model names items and reads light direction.
4. **Scale, cross-checked from independent anchors.** The geometry model's metric estimate; standard Indian door height (about 2.0 to 2.1 m); switchboard height; ceiling height priors (2.7 to 3.1 m in typical flats); the vitrified tile grid (600 or 800 mm tiles, so counting tiles measures the floor). Anchors that agree tighten the band; disagreement widens it and triggers a request for one tape value.
5. **Space type and extent.** The pipeline detects what was scanned (living room, bedroom, balcony or other) and how much (a whole room or part of one). Both are shown to you and can be changed.
6. **Space Profile.** A JSON scene graph where every dimension carries a value, a source (measured, estimated, user-confirmed) and an error band.

Single-image models can shrink far-away geometry, which is why scale is cross-checked from anchors rather than trusted from one model.

## Confirm, never draw

The Space Profile card shows what we found (the space type and size, with a Change action) and the plan drawn over your photo. The whole of what was captured is redone. You can drag a door, mark each existing item keep, replace or remove, and add tape values. Each value snaps in with a haptic tick and re-fits the whole room.

## Upload and registration

On Done the phone uploads every file of the package with the resumable uploader (small files first), then registers the capture with the API (`POST /v1/captures`). The API validates the Capture object, checks that every storage key belongs to the caller, and stores it for the twin worker. The capture id is chosen on the phone when the scan starts, so both steps are safe to repeat after a lost connection or an app restart: finished files are skipped and registering again returns the stored capture.

The upload does not need the app to stay open. Several files go up at once. The scan is remembered on the phone until its upload is done, and an upload that stopped starts again by itself when the app opens or comes back to the front; no tap is needed. While the person is in another app:

- iPhone: each file that fits in one part is handed to the system's background transfer service, which carries on after the app is suspended. The files not yet handed over, and the registration, follow when the app next runs.
- Android: a foreground service with a quiet notification ("Uploading your scan") holds the app's process, so the upload runs to the end.

Force-closing the app stops the upload on both platforms; it resumes on the next open.

## Import from the gallery

Photos or one video the person already has go up through the same package and the same uploader (a picture under the server's minimum, 1024 px on the long edge and 576 px on the short edge, is refused on the phone before anything uploads), with no AR data (`ar.tracking` is `none`; no poses, planes or depth). "Use photos or a video" beside Take photos, on My home and on the note for phones without AR opens the phone's own picker, which hands the app only what was chosen, so no library permission is asked for.

- Up to 20 photos, resized like any other photo, or one video of 5 seconds to 2 minutes.
- A video is not uploaded. Up to 20 frames are taken from it on the phone, evenly through its length and never at its first or last moment, at most two a second; those are the keyframes.
- The pictures are marked as from the gallery and their sharpness is left at 0 (not measured on the phone).
- A room from imported pictures is at the estimated confidence level: nothing is claimed to fit until a measurement confirms it. Until the photos path is part of the pipeline, such a room's first stage ends with the reason `no_ar_data`, and the app says the pictures are uploaded and rooms from photos are not ready yet.
- On the server, `twin/photo_frames.py` turns imported pictures into the same frames manifest a scan gives: the pose model (MapAnything, Apache 2.0 checkpoint, through the gateway) gives each picture a camera; metric depth (MoGe-3, the depth step) sets the scale; and the floor in each picture's own depth stands the room up, since pictures are mostly taken looking down. Pictures with almost no depth are left out. The twin steps then run as for any phone without LiDAR, and the room is `estimated`.

## Upload safety and privacy

Non-room or explicit images are rejected by a classifier. Faces and personal photos are blurred before storage. Raw video is deleted after processing.
