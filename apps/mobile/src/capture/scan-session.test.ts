import { DONE_DEGREES, FALLBACK_DONE_FRAMES } from "./coverage";
import { ANALYSIS_WIDTH, downsampleLuma } from "./downsample";
import { PAUSE_AFTER_MS } from "./guardrails";
import type { MotionSample } from "./pose";
import {
  canFinish,
  frameFov,
  INITIAL_SCAN,
  mappedShare,
  type ScanEvent,
  scanReducer,
  type ScanState,
} from "./scan-session";

const reduce = scanReducer("standard");
const goodStats = { brightness: 120, glare: 0.01, sharpness: 400 };
const darkStats = { ...goodStats, brightness: 10 };
const STEP_MS = 80;

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

const still: MotionSample = {
  rotationRate: 0,
  yawRate: 0,
  pitchRate: 0,
  acceleration: 0,
  rollDegrees: 0,
  pitchDegrees: 0,
  hasGyro: true,
};

/** Replays events on a shared clock, one step apart. */
function timeline() {
  let now = 1_000;
  return {
    frame(stats = goodStats, points = strip(6)): ScanEvent {
      now += STEP_MS;
      return { type: "frame", stats, points, aspect: 9 / 16, atMs: now };
    },
    motion(change: Partial<MotionSample> = {}): ScanEvent {
      now += STEP_MS;
      return { type: "motion", sample: { ...still, ...change }, atMs: now };
    },
  };
}

const run = (state: ScanState, events: ScanEvent[]) => events.reduce(reduce, state);
const repeat = (count: number, make: () => ScanEvent) => Array.from({ length: count }, make);
const pauseSteps = Math.ceil(PAUSE_AFTER_MS / STEP_MS) + 2;

describe("scan session", () => {
  it("grows the mesh as good frames arrive", () => {
    const t = timeline();
    const state = run(
      INITIAL_SCAN,
      repeat(8, () => t.frame()),
    );
    expect(state.mesh.points.length).toBeGreaterThan(50);
    expect(state.mesh.triangles.length).toBeGreaterThan(50);
    expect(state.usableFrames).toBe(8);
    expect(state.pause.paused).toBe(false);
  });

  it("pauses softly in the dark and keeps everything mapped so far", () => {
    const t = timeline();
    const mapped = run(
      INITIAL_SCAN,
      repeat(8, () => t.frame()),
    );
    const dark = run(
      mapped,
      repeat(pauseSteps, () => t.frame(darkStats, [])),
    );

    expect(dark.guardrails.light).toBe("warn");
    expect(dark.pause).toMatchObject({ paused: true, reason: "light" });
    // Nothing lost: the mesh is exactly what it was when the pause began.
    const paused = run(
      dark,
      repeat(50, () => t.frame(darkStats, [])),
    );
    expect(paused.mesh).toEqual(dark.mesh);
    expect(paused.mesh.points.length).toBeGreaterThan(50);
  });

  it("resumes by itself when the light comes back", () => {
    const t = timeline();
    const paused = run(
      INITIAL_SCAN,
      repeat(pauseSteps, () => t.frame(darkStats, [])),
    );
    expect(paused.pause.paused).toBe(true);
    const resumed = run(paused, [t.frame(), t.frame()]);
    expect(resumed.pause.paused).toBe(false);
    expect(resumed.usableFrames).toBeGreaterThan(0);
  });

  it("turns the light chip amber when the camera's ISO is maxed out", () => {
    const t = timeline();
    let state = run(INITIAL_SCAN, [t.frame()]);
    state = reduce(state, { type: "exposure", isoRatio: 0.98 });
    expect(state.guardrails.light).toBe("warn");
  });

  it("carries on in the dark after Scan anyway", () => {
    const t = timeline();
    let state = run(
      INITIAL_SCAN,
      repeat(pauseSteps, () => t.frame(darkStats, [])),
    );
    state = reduce(state, { type: "scanAnyway" });
    const before = state.usableFrames;
    state = run(
      state,
      repeat(30, () => t.frame(darkStats)),
    );
    expect(state.pause.paused).toBe(false);
    expect(state.usableFrames - before).toBe(30);
  });

  it("turns the steady chip amber from motion alone, before any frame", () => {
    const t = timeline();
    const swung = run(
      INITIAL_SCAN,
      repeat(3, () => t.motion({ rotationRate: 220 })),
    );
    expect(swung.guardrails.motion).toBe("warn");
    const shaken = run(
      INITIAL_SCAN,
      repeat(3, () => t.motion({ acceleration: 8 })),
    );
    expect(shaken.guardrails.motion).toBe("warn");
    const calm = run(
      swung,
      repeat(6, () => t.motion()),
    );
    expect(calm.guardrails.motion).toBe("good");
  });

  it("skips frames taken while swinging, and pauses if it goes on", () => {
    const t = timeline();
    let state = run(
      INITIAL_SCAN,
      repeat(3, () => t.motion({ rotationRate: 220 })),
    );
    state = run(state, [t.frame(), t.frame()]);
    expect(state.usableFrames).toBe(0);
    expect(state.pause.paused).toBe(false);
    state = run(
      state,
      repeat(pauseSteps, () => t.motion({ rotationRate: 220 })),
    );
    expect(state.pause).toMatchObject({ paused: true, reason: "motion" });
    // Holding still resumes it, with no frame needed.
    state = run(
      state,
      repeat(6, () => t.motion()),
    );
    expect(state.pause.paused).toBe(false);
    state = run(state, [t.frame()]);
    expect(state.usableFrames).toBe(1);
  });

  it("nudges about tilt from the sensors but never pauses for it", () => {
    const t = timeline();
    const tilted = run(
      INITIAL_SCAN,
      repeat(40, () => t.motion({ rollDegrees: 25 })),
    );
    expect(tilted.guardrails.level).toBe("warn");
    expect(tilted.pause.paused).toBe(false);
    const pointedDown = run(INITIAL_SCAN, [t.motion({ pitchDegrees: 60 })]);
    expect(pointedDown.guardrails.level).toBe("warn");
  });

  it("moves the mesh with the view so it stays on the walls", () => {
    const t = timeline();
    const before = run(INITIAL_SCAN, [t.motion(), t.frame(goodStats, strip(2))]);
    const leftmost = Math.min(...before.mesh.points.map((point) => point.x));
    // Turn left by a few degrees (positive yaw): the scene slides right.
    const turned = run(before, [t.motion({ yawRate: 50 }), t.frame(goodStats, [])]);
    const shifted = Math.min(...turned.mesh.points.map((point) => point.x));
    // Two steps passed since the previous motion reading.
    const expected = (50 * ((2 * STEP_MS) / 1000)) / frameFov(9 / 16).across;
    expect(shifted - leftmost).toBeCloseTo(expected, 3);
  });

  it("measures coverage from where the phone pointed, and allows Done after a sweep", () => {
    const t = timeline();
    let state = run(INITIAL_SCAN, [t.motion()]);
    expect(canFinish(state)).toBe(false);
    // Looking at one wall for a while maps a little, not enough.
    state = run(
      state,
      repeat(20, () => t.frame()),
    );
    expect(canFinish(state)).toBe(false);
    expect(mappedShare(state)).toBeGreaterThan(0);
    // A slow pan (30 degrees a second) across the room, filming as it goes.
    for (let step = 0; step < 50 && !canFinish(state); step += 1) {
      state = run(state, [t.motion({ yawRate: 30, rotationRate: 30 }), t.frame()]);
    }
    expect(canFinish(state)).toBe(true);
    expect(mappedShare(state) * 180).toBeGreaterThanOrEqual(DONE_DEGREES);
  });

  it("counts a steady full turn even when every frame is thin", () => {
    const t = timeline();
    let state = run(INITIAL_SCAN, [t.motion()]);
    // 30 degrees a second for 12 seconds, frames with no feature points.
    for (let step = 0; step < 150; step += 1) {
      state = run(state, [t.motion({ yawRate: 30, rotationRate: 30 }), t.frame(goodStats, [])]);
    }
    expect(state.pose.yaw).toBeGreaterThan(355);
    expect(mappedShare(state)).toBe(1);
    // Done still needs frames that were usable, which these were.
    expect(canFinish(state)).toBe(true);
  });

  it("counts the sweep with no frames at all, but offers Done only with frames", () => {
    const t = timeline();
    let state = run(INITIAL_SCAN, [t.motion()]);
    for (let step = 0; step < 80; step += 1) {
      state = run(state, [t.motion({ yawRate: 30, rotationRate: 30 })]);
    }
    expect(mappedShare(state)).toBeGreaterThan(0.5);
    expect(canFinish(state)).toBe(false);
  });

  it("gives nothing for a fast swing", () => {
    const t = timeline();
    let state = run(INITIAL_SCAN, [t.motion()]);
    for (let step = 0; step < 40; step += 1) {
      state = run(state, [t.motion({ yawRate: 200, rotationRate: 200 })]);
    }
    expect(mappedShare(state)).toBeLessThan(0.1);
  });

  it("falls back to counting detailed frames on a phone with no gyroscope", () => {
    const t = timeline();
    let state = run(INITIAL_SCAN, [t.motion({ hasGyro: false })]);
    expect(state.hasGyro).toBe(false);
    state = run(
      state,
      repeat(FALLBACK_DONE_FRAMES, () => t.frame()),
    );
    expect(canFinish(state)).toBe(true);
  });

  it("tracks fewer points on a low-tier phone", () => {
    const t = timeline();
    const events = repeat(8, () => t.frame(goodStats, strip(12)));
    const low = events.reduce(scanReducer("low"), INITIAL_SCAN);
    const full = run(INITIAL_SCAN, events);
    expect(low.mesh.points.length).toBeLessThanOrEqual(60);
    expect(full.mesh.points.length).toBeGreaterThan(low.mesh.points.length);
  });

  it("starts over on reset", () => {
    const t = timeline();
    const state = run(INITIAL_SCAN, [t.frame(), { type: "reset" }]);
    expect(state).toEqual(INITIAL_SCAN);
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
