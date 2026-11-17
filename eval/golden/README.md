# Golden rooms: twin accuracy against the tape

One command takes an uploaded capture of a golden room and the tape measurements of the same room, builds the twin on Modal (depth, objects, splat, phone splats, shell) and writes an accuracy report.

```sh
M="uv run --with modal[api-proxy-support]==1.6.4 modal run services/workers/gpu/app.py"
$M::golden_room --capture path/to/capture-folder --tape path/to/sheet.json
```

Add `--no-splat` to build the twin without the splat: the shell, objects, inventory, hero views and the AR measurements do not need it, and it is the launch shape. A sparse scan fails the splat's quality gate only after minutes of GPU training, and with the splat on that stops the whole run.

## AR measurements against the tape

Fit is checked against what the phone measured, so the first question of a golden room is how far the phone's own walls, floor, ceiling, doors and windows are from the tape. That needs no GPU and no twin:

```sh
uv run python -m sajao_workers.golden_ar --capture path/to/capture-folder --tape path/to/sheet.json --out golden-runs/room
```

It reads the capture's planes file, turns the planes into measurements (`sajao_workers.ar_measurements`: wall patches in one plane are joined into a wall, neighbouring walls are intersected to find the corners, and a wall's length is the distance between its corners) and scores them against the sheet. `golden_room` below runs the same step and writes the same files next to the twin's report.

- A wall with both neighbours found is measured **corner to corner**. A wall with a neighbour missing is only **seen in part**: a lower bound, listed with how much is short and kept out of the error figures.
- The floor size is the room between the corners, compared with the mean of the tape's opposite walls (four-wall rooms). If the walls do not close into a room there is no floor size, only the floor the phone saw.
- Ceiling height is from the floor plane to the ceiling plane, when the phone found one.
- Doors and windows are found in the keyframes by the vision model (a mask in each picture, nothing more), and the rays through each mask are cast from that keyframe's AR pose onto the walls the phone measured; code then works out width, height, sill and distance from the nearest corner (`sajao_workers.ar_openings`). An opening must be seen in at least two keyframes. This needs the model, so it runs in `golden_room`, on every phone. The command above has no model and reports only the planes the phone classed itself.
- ARKit classes door and window planes; ARCore does not. On an iPhone the report scores both readings against the tape and lists the difference between them as a cross-check.
- A scan in which the phone found no planes reports nothing measured, and says so.

Files: `ar-measurements.json` (every value an estimated dimension with an error band), `ar-report.json` and `ar-report.md`.

## Inputs

- **Capture folder:** `capture.json` (a `Capture` from `packages/schemas`, with its `package`) and the files its storage keys name: the keyframe images, the planes file and, from phones that have it, the depth file. Files are found by their storage key relative to the folder, or by the key's file name. The phone's upload writes exactly these files.
- **Measurement sheet:** JSON in centimetres, following the golden set capture protocol in Notion. Walls W1, W2, ... clockwise from the door; ceiling height in one or more places; each door and window with its wall, width, height, sill (windows) and distance from the nearest corner along the wall; big furniture with width, depth and height. Start from `sheet-template.json`. A sheet that is incomplete or not in centimetres stops the command before any GPU runs.

## Outputs

Written to `golden-runs/<room>/` (not committed), or to `--out`:

| File | What |
| --- | --- |
| `report.md` | The report to read: dimension error, walls and ceiling against the tape (with the twin's error band and whether the tape value falls inside it), doors and windows found, furniture size errors |
| `report.json` | The same, for the accuracy evals (SJ-118) |
| `twin.json` | The SpaceTwin built from the capture |
| `run.json` | What ran: depth source, detector and segmenter, splat quality, GPU charge |

The report's "Dimension error %" is the value for the Golden set row in Notion.

## How walls are matched

The twin's walls are paired with W1, W2, ... in the turn and direction that fit the lengths best, preferring the pairing that puts the tape's doors and windows on twin walls that have them. If the room has more or fewer walls than the twin (an L-shaped room against a rectangular shell), walls are not compared one by one and the report says so.

## Pipeline test

`golden_fixture` writes an ARKitScenes room as a capture folder (capture.json, keyframe JPEGs, SJDEPTH1 depth) so the command can be tested before real rooms are scanned. Its sheet is made up, so its numbers say nothing about accuracy.
