import { ANALYSIS_WIDTH, downsampleLuma } from "./downsample";
import { PAUSE_AFTER_MS } from "./guardrails";
import {
  canFinish,
  INITIAL_SCAN,
  rollFromGravity,
  rotationRateDegrees,
  type ScanEvent,
  scanReducer,
  type ScanState,
} from "./scan-session";

const reduce = scanReducer("standard");
const goodStats = { brightness: 120, glare: 0.01, sharpness: 400 };
const darkStats = { ...goodStats, brightness: 10 };

/** Points covering a strip of the screen `columns` wide, from the left. */
function strip(columns: number) {
  const points = [];
  for (let column = 0; column < columns; column += 1) {
    for (let row = 0; row < 20; row += 1) {
      points.push({ x: (column + 0.5) / 12, y: (row + 0.5) / 20, strength: 1 });
    }
  }
  return points;
}

const frame = (stats = goodStats, points = strip(6), elapsedMs = 120): ScanEvent => ({
  type: "frame",
  stats,
  points,
  elapsedMs,
});

const run = (state: ScanState, events: ScanEvent[]) => events.reduce(reduce, state);

describe("scan session", () => {
  it("grows the mesh as good frames arrive", () => {
    const state = run(INITIAL_SCAN, Array(8).fill(frame()));
    expect(state.mesh.points.length).toBeGreaterThan(50);
    expect(state.mesh.triangles.length).toBeGreaterThan(50);
    expect(state.usableFrames).toBe(8);
    expect(state.pause.paused).toBe(false);
  });

  it("pauses softly in the dark and keeps everything mapped so far", () => {
    const mapped = run(INITIAL_SCAN, Array(8).fill(frame()));
    const steps = Math.ceil(PAUSE_AFTER_MS / 120) + 1;
    const dark = run(mapped, Array(steps).fill(frame(darkStats, [])));

    expect(dark.guardrails.light).toBe("warn");
    expect(dark.pause).toMatchObject({ paused: true, reason: "light" });
    // Nothing lost: the mesh is exactly what it was when the pause began.
    const paused = run(dark, Array(50).fill(frame(darkStats, [])));
    expect(paused.mesh).toEqual(dark.mesh);
    expect(paused.mesh.points.length).toBeGreaterThan(50);
  });

  it("resumes by itself when the light comes back", () => {
    const steps = Math.ceil(PAUSE_AFTER_MS / 120) + 1;
    const paused = run(INITIAL_SCAN, Array(steps).fill(frame(darkStats, [])));
    expect(paused.pause.paused).toBe(true);
    const resumed = run(paused, [frame(), frame()]);
    expect(resumed.pause.paused).toBe(false);
    expect(resumed.usableFrames).toBeGreaterThan(0);
  });

  it("carries on in the dark after Scan anyway", () => {
    const steps = Math.ceil(PAUSE_AFTER_MS / 120) + 1;
    let state = run(INITIAL_SCAN, Array(steps).fill(frame(darkStats, [])));
    state = reduce(state, { type: "scanAnyway" });
    const before = state.usableFrames;
    state = run(state, Array(30).fill(frame(darkStats)));
    expect(state.pause.paused).toBe(false);
    expect(state.usableFrames - before).toBe(30);
  });

  it("skips frames taken while the phone is turning fast, without pausing at once", () => {
    let state = reduce(INITIAL_SCAN, { type: "motion", rotationRate: 200, rollDegrees: 0 });
    state = run(state, [frame(), frame()]);
    expect(state.guardrails.motion).toBe("warn");
    expect(state.usableFrames).toBe(0);
    expect(state.pause.paused).toBe(false);
    state = reduce(state, { type: "motion", rotationRate: 5, rollDegrees: 0 });
    state = run(state, [frame()]);
    expect(state.usableFrames).toBe(1);
  });

  it("allows Done only once enough has been mapped", () => {
    expect(canFinish(INITIAL_SCAN)).toBe(false);
    const little = run(INITIAL_SCAN, Array(12).fill(frame(goodStats, strip(1))));
    expect(canFinish(little)).toBe(false);
    const enough = run(INITIAL_SCAN, Array(12).fill(frame(goodStats, strip(6))));
    expect(canFinish(enough)).toBe(true);
  });

  it("tracks fewer points on a low-tier phone", () => {
    const low = Array(8)
      .fill(frame(goodStats, strip(12)))
      .reduce(scanReducer("low"), INITIAL_SCAN);
    const full = run(INITIAL_SCAN, Array(8).fill(frame(goodStats, strip(12))));
    expect(low.mesh.points.length).toBeLessThanOrEqual(60);
    expect(full.mesh.points.length).toBeGreaterThan(low.mesh.points.length);
  });

  it("starts over on reset", () => {
    const state = run(INITIAL_SCAN, [frame(), { type: "reset" }]);
    expect(state).toEqual(INITIAL_SCAN);
  });
});

describe("motion readings", () => {
  it("reads sideways tilt from gravity", () => {
    expect(rollFromGravity({ x: 0, y: -9.8 })).toBeCloseTo(0);
    expect(rollFromGravity({ x: 9.8, y: -9.8 })).toBeCloseTo(45);
    expect(rollFromGravity({ x: -9.8, y: 0 })).toBeCloseTo(-90);
  });

  it("converts turn rate to degrees per second", () => {
    expect(rotationRateDegrees({ x: Math.PI, y: 0, z: 0 })).toBeCloseTo(180);
    expect(rotationRateDegrees({ x: 0, y: 0, z: 0 })).toBe(0);
  });
});

describe("frame downsampling", () => {
  it("shrinks to the analysis width and keeps the shape", () => {
    const plane = new Uint8Array(1920 * 1080).fill(77).buffer;
    const gray = downsampleLuma(plane, { width: 1920, height: 1080, bytesPerRow: 1920 });
    expect([gray.width, gray.height]).toEqual([ANALYSIS_WIDTH, 54]);
    expect(gray.data.every((value) => value === 77)).toBe(true);
  });

  it("skips row padding in the camera buffer", () => {
    // 4 pixels per row, padded to 8 bytes per row. Padding bytes are 255.
    const padded = new Uint8Array(8 * 2).fill(255);
    padded.set([10, 20, 30, 40], 0);
    padded.set([50, 60, 70, 80], 8);
    const gray = downsampleLuma(padded.buffer, { width: 4, height: 2, bytesPerRow: 8 }, 4);
    expect([...gray.data]).toEqual([10, 20, 30, 40, 50, 60, 70, 80]);
  });

  it("never enlarges a small frame", () => {
    const gray = downsampleLuma(new Uint8Array(20 * 10).buffer, {
      width: 20,
      height: 10,
      bytesPerRow: 20,
    });
    expect([gray.width, gray.height]).toEqual([20, 10]);
  });
});
