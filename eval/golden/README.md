# Golden rooms: twin accuracy against the tape

One command takes an uploaded capture of a golden room and the tape measurements of the same room, builds the twin on Modal (depth, objects, splat, phone splats, shell) and writes an accuracy report.

```sh
M="uv run --with modal[api-proxy-support]==1.6.4 modal run services/workers/gpu/app.py"
$M::golden_room --capture path/to/capture-folder --tape path/to/sheet.json
```

## Inputs

- **Capture folder:** `capture.json` (a `Capture` from `packages/schemas`, with its `package`) and the files its storage keys name: the keyframe images and, from phones that have it, the depth file. Files are found by their storage key relative to the folder, or by the key's file name. The phone's upload writes exactly these files.
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
