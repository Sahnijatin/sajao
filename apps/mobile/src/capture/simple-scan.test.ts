// The simple scan end to end through the reducer: what an Android phone with
// no planes and no detector reports, and what the screen shows for it.
import { simpleHint } from "./ar/guidance";
import { AUTO_SIMPLE_AFTER_MS } from "./capture-mode";
import { shouldWalk } from "./motion-coverage";
import type { MotionSample } from "./pose";
import {
  canFinish,
  initialScan,
  isSimple,
  mappedShare,
  type ScanEvent,
  scanReducer,
  type ScanState,
  shouldShowSlowDown,
  shouldStepBack,
  STEP_BACK_AFTER_MS,
} from "./scan-session";

const reduce = scanReducer("standard");
const run = (state: ScanState, events: ScanEvent[]) => events.reduce(reduce, state);

const NOTHING_WORKS = { planes: 0, meshTriangles: 0, detector: false, detectorFailed: true };
const ALL_WORKS = { planes: 4, meshTriangles: 0, detector: true, detectorFailed: false };

const arFrame = (
  atMs: number,
  change: Partial<Extract<ScanEvent, { type: "arFrame" }>> = {},
): ScanEvent => ({
  type: "arFrame",
  brightness: 120,
  lowLight: false,
  featureCount: 40,
  tracking: "normal",
  signals: NOTHING_WORKS,
  atMs,
  ...change,
});

const arPose = (
  yaw: number,
  atMs: number,
  change: Partial<Extract<ScanEvent, { type: "arPose" }>> = {},
): ScanEvent => ({ type: "arPose", yaw, pitch: 0, tracking: "normal", atMs, ...change });

const still: MotionSample = {
  rotationRate: 0,
  yawRate: 0,
  pitchRate: 0,
  acceleration: 0,
  rollDegrees: 0,
  pitchDegrees: 0,
  hasGyro: true,
};

/** Pan at 20 degrees a second, with the status the founder's Android showed: no planes, no detector. */
function slowPan(
  state: ScanState,
  degrees: number,
  startMs = 0,
  x = (_i: number) => 0,
  signals = NOTHING_WORKS,
) {
  let next = state;
  for (let i = 0; i * 2 <= degrees; i += 1) {
    const at = startMs + i * 100;
    next = run(next, [arPose(i * 2, at, { position: { x: x(i), z: 0 } })]);
    if (i % 3 === 0) next = run(next, [arFrame(at + 10, { signals })]);
  }
  return next;
}

describe("simple scan", () => {
  it("Android with zero planes and a failed detector still fills and enables Done", () => {
    const start = initialScan("android");
    expect(start.mode).toMatchObject({ mode: "simple", reason: "android" });
    const state = slowPan(start, 280);
    expect(isSimple(state)).toBe(true);
    expect(state.surfaces.accepted).toBe(0);
    expect(mappedShare(state)).toBeCloseTo(0.7);
    expect(canFinish(state)).toBe(true);
  });

  it("surface samples never count in the simple scan, only their sharpness", () => {
    let state = slowPan(initialScan("android"), 20);
    const before = mappedShare(state);
    state = run(state, [
      {
        type: "arSurfaces",
        sharpness: 50,
        hits: [{ kind: "floor", normalYaw: 0, offset: 0, x: 0, y: -1.4, z: -1 }],
        atMs: 5000,
      },
    ]);
    expect(state.surfacesSeen).toBe(false);
    expect(state.surfaces.accepted).toBe(0);
    expect(state.sharp).toEqual({ ok: true, atMs: 5000 });
    expect(mappedShare(state)).toBe(before);
  });

  it("a blurred frame stops coverage until a sharp one arrives", () => {
    let state = initialScan("android");
    const surfaces = (sharpness: number, atMs: number): ScanEvent => ({
      type: "arSurfaces",
      sharpness,
      hits: [],
      atMs,
    });
    state = run(state, [arPose(0, 0)]);
    for (let i = 0; i < 8; i += 1) state = run(state, [surfaces(100, i * 10)]);
    state = run(state, [surfaces(5, 100)]);
    const accepted = state.motionCoverage.accepted;
    state = run(state, [arPose(2, 200), arPose(4, 300)]);
    expect(state.motionCoverage.accepted).toBe(accepted);
    state = run(state, [surfaces(100, 350), arPose(6, 400)]);
    expect(state.motionCoverage.accepted).toBe(accepted + 1);
  });

  it("an iPhone turns simple at ten seconds without planes and keeps what it earned", () => {
    let state = initialScan("ios");
    state = slowPan(state, 180, 0, () => 0, { ...ALL_WORKS, planes: 0 });
    expect(isSimple(state)).toBe(false);
    const earned = state.motionCoverage;
    state = run(state, [
      arFrame(AUTO_SIMPLE_AFTER_MS + 100, { signals: { ...ALL_WORKS, planes: 0 } }),
    ]);
    expect(state.mode).toMatchObject({ mode: "simple", reason: "noPlanes" });
    expect(isSimple(state)).toBe(true);
    expect(state.motionCoverage).toBe(earned);
    expect(mappedShare(state)).toBeGreaterThan(0.4);
  });

  it("an iPhone where planes and the detector work stays in the full scan", () => {
    let state = initialScan("ios");
    for (let at = 0; at <= AUTO_SIMPLE_AFTER_MS + 1000; at += 250) {
      state = run(state, [arFrame(at, { signals: ALL_WORKS })]);
    }
    expect(state.mode).toMatchObject({ mode: "full", decided: true });
  });

  it("carries the heading on from the gyroscope while AR tracking is lost", () => {
    let state = run(initialScan("android"), [arPose(30, 0)]);
    state = run(state, [arPose(999, 100, { tracking: "limited" })]);
    expect(state.pose.yaw).toBe(30);
    for (let i = 1; i <= 20; i += 1) {
      state = run(state, [
        {
          type: "motion",
          sample: { ...still, yawRate: 20, rotationRate: 20 },
          atMs: 100 + i * 100,
        },
      ]);
    }
    expect(state.pose.yaw).toBeGreaterThan(60);
    expect(state.motionCoverage.accepted).toBeGreaterThan(10);
    // Tracking returns: AR drives the pose again.
    state = run(state, [arPose(75, 2300)]);
    expect(state.pose.yaw).toBe(75);
  });

  it("asks to slow down on a fast turn", () => {
    let state = initialScan("android");
    for (let i = 0; i < 12; i += 1) state = run(state, [arPose(i * 12, i * 100)]);
    expect(shouldShowSlowDown(state)).toBe(true);
    expect(mappedShare(state)).toBeLessThan(0.1);
  });

  it("asks to step back when tracking sees too little for a while in good light", () => {
    let state = run(initialScan("android"), [arFrame(0)]);
    state = run(state, [arFrame(250, { featureCount: 3 })]);
    expect(shouldStepBack(state)).toBe(false);
    state = run(state, [arFrame(250 + STEP_BACK_AFTER_MS, { featureCount: 3 })]);
    expect(shouldStepBack(state)).toBe(true);
    state = run(state, [arFrame(3000, { featureCount: 60 })]);
    expect(shouldStepBack(state)).toBe(false);
  });

  it("asks to walk after turning on one spot, then says all covered after walking", () => {
    let state = slowPan(initialScan("android"), 360);
    expect(shouldWalk(state.motionCoverage)).toBe(true);
    expect(mappedShare(state)).toBeLessThan(1);
    state = slowPan(state, 140, 60_000, (i) => i * 0.05);
    expect(shouldWalk(state.motionCoverage)).toBe(false);
    expect(mappedShare(state)).toBeCloseTo(1);
  });

  it("shows one hint at a time: slow down, step back, walk, then Done", () => {
    const none = {
      slowDown: false,
      stepBack: false,
      walkAround: null,
      walk: false,
      doneReady: false,
      complete: false,
    };
    expect(simpleHint(none)).toBeNull();
    expect(simpleHint({ ...none, slowDown: true, stepBack: true, walk: true })).toEqual({
      id: "slowDown",
    });
    expect(simpleHint({ ...none, stepBack: true, walk: true })).toEqual({ id: "stepBack" });
    expect(simpleHint({ ...none, walk: true, doneReady: true })).toEqual({ id: "walk" });
    expect(simpleHint({ ...none, doneReady: true })).toEqual({ id: "coverMore" });
    expect(simpleHint({ ...none, doneReady: true, complete: true })).toEqual({ id: "complete" });
    expect(simpleHint({ ...none, walkAround: "sofa" })).toEqual({ id: "walkAround", kind: "sofa" });
  });
});
