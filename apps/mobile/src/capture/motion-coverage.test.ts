import {
  addMotionSample,
  EMPTY_MOTION_COVERAGE,
  headingShare,
  type MotionCoverage,
  motionDone,
  motionFraction,
  type MotionSampleInput,
  moveShare,
  shouldWalk,
} from "./motion-coverage";
import { tooManyRejected } from "./ar/surface-coverage";

const sample = (change: Partial<MotionSampleInput>): MotionSampleInput => ({
  yaw: 0,
  pitch: 0,
  turnDegPerS: 20,
  steady: true,
  sharp: true,
  position: null,
  atMs: 0,
  ...change,
});

/** A slow pan at 20 degrees a second through `degrees`, ten samples a second. */
function pan(
  from: MotionCoverage,
  degrees: number,
  change: (i: number) => Partial<MotionSampleInput> = () => ({}),
  startMs = 0,
): MotionCoverage {
  let coverage = from;
  for (let i = 0; i * 2 <= degrees; i += 1) {
    coverage = addMotionSample(
      coverage,
      sample({ yaw: i * 2, atMs: startMs + i * 100, ...change(i) }),
    );
  }
  return coverage;
}

describe("motion coverage", () => {
  it("fills with a slow, steady turn and offers Done at 270 degrees without planes or a detector", () => {
    const quarter = pan(EMPTY_MOTION_COVERAGE, 90);
    expect(headingShare(quarter)).toBeGreaterThan(0.3);
    expect(motionDone(quarter)).toBe(false);
    const most = pan(EMPTY_MOTION_COVERAGE, 270);
    expect(headingShare(most)).toBe(1);
    expect(motionDone(most)).toBe(true);
  });

  it("earns nothing from spinning fast, shaking or blurred frames, and asks to slow down", () => {
    for (const bad of [{ turnDegPerS: 120 }, { steady: false }, { sharp: false }]) {
      const coverage = pan(EMPTY_MOTION_COVERAGE, 360, () => bad);
      expect(motionFraction(coverage)).toBe(0);
      expect(coverage.accepted).toBe(0);
      expect(tooManyRejected(coverage.recent)).toBe(true);
    }
  });

  it("does not count headings while pointing at the floor or ceiling", () => {
    const coverage = pan(EMPTY_MOTION_COVERAGE, 360, () => ({ pitch: -75 }));
    expect(headingShare(coverage)).toBe(0);
  });

  it("holding still on one heading stays far from Done", () => {
    let coverage = EMPTY_MOTION_COVERAGE;
    for (let i = 0; i < 600; i += 1) {
      coverage = addMotionSample(coverage, sample({ atMs: i * 100, position: { x: 0, z: 0 } }));
    }
    expect(motionFraction(coverage)).toBeLessThan(0.2);
    expect(motionDone(coverage)).toBe(false);
  });

  it("counts metres walked from AR positions and reaches 100% only with walking", () => {
    const turned = pan(EMPTY_MOTION_COVERAGE, 360, () => ({ position: { x: 0, z: 0 } }));
    expect(moveShare(turned)).toBe(0);
    expect(motionFraction(turned)).toBeCloseTo(0.7);
    expect(shouldWalk(turned)).toBe(true);
    // Walk 3 m in 5 cm steps.
    let walked = turned;
    for (let i = 1; i <= 60; i += 1) {
      walked = addMotionSample(
        walked,
        sample({ yaw: 0, atMs: 100_000 + i * 100, position: { x: i * 0.05, z: 0 } }),
      );
    }
    expect(walked.pathM).toBeCloseTo(3, 1);
    expect(motionFraction(walked)).toBeCloseTo(1);
    expect(shouldWalk(walked)).toBe(false);
  });

  it("ignores tracking jitter and tracking jumps as walking", () => {
    let coverage = addMotionSample(EMPTY_MOTION_COVERAGE, sample({ position: { x: 0, z: 0 } }));
    coverage = addMotionSample(coverage, sample({ atMs: 100, position: { x: 0.005, z: 0 } }));
    coverage = addMotionSample(coverage, sample({ atMs: 200, position: { x: 4, z: 0 } }));
    expect(coverage.pathM).toBe(0);
    coverage = addMotionSample(coverage, sample({ atMs: 300, position: { x: 4.1, z: 0 } }));
    expect(coverage.pathM).toBeCloseTo(0.1);
  });

  it("earns the movement share from steady time when AR never tracks", () => {
    let coverage = EMPTY_MOTION_COVERAGE;
    for (let i = 0; i < 250; i += 1) {
      coverage = addMotionSample(coverage, sample({ yaw: i * 2, atMs: i * 100 }));
    }
    expect(coverage.tracked).toBe(false);
    expect(moveShare(coverage)).toBe(1);
    expect(shouldWalk(coverage)).toBe(false);
  });

  it("a faster pose stream earns no more than ten samples a second", () => {
    let coverage = EMPTY_MOTION_COVERAGE;
    for (let i = 0; i < 100; i += 1) {
      coverage = addMotionSample(coverage, sample({ atMs: i * 16 }));
    }
    expect(coverage.accepted).toBeLessThanOrEqual(18);
  });
});
