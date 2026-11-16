import {
  addFrame,
  coverageFraction,
  EMPTY_COVERAGE,
  enoughCoverage,
  mappedDegrees,
  MIN_FEATURES,
  screenAngle,
  sectorOf,
} from "./coverage";
import { coverToScreen, uprightAspect, uprightPoint } from "./orientation";
import { motionSample, wrapDegrees } from "./pose";

describe("frame orientation", () => {
  it("turns raw frame points upright like the camera library does", () => {
    expect(uprightPoint(0.2, 0.1, "up", false)).toEqual({ x: 0.2, y: 0.1 });
    expect(uprightPoint(0.2, 0.1, "right", false)).toEqual({ x: 0.1, y: 0.8 });
    expect(uprightPoint(0.2, 0.1, "left", false)).toEqual({ x: 0.9, y: 0.2 });
    const down = uprightPoint(0.2, 0.1, "down", false);
    expect(down.x).toBeCloseTo(0.8);
    expect(down.y).toBeCloseTo(0.9);
    expect(uprightPoint(0.2, 0.1, "up", true).x).toBeCloseTo(0.8);
  });

  it("swaps width and height for sideways frames", () => {
    expect(uprightAspect(1280, 720, "right")).toBeCloseTo(9 / 16);
    expect(uprightAspect(1280, 720, "up")).toBeCloseTo(16 / 9);
  });

  it("crops the top and bottom when the frame is taller than the screen", () => {
    const point = coverToScreen({ x: 0.5, y: 0 }, 0.4, { width: 400, height: 800 });
    expect(point.x).toBe(200);
    expect(point.y).toBe(-100);
  });
});

describe("motion readings", () => {
  const upright = { x: 0, y: -9.81, z: 0 };

  it("reads the vertical-axis turn the same way on both platforms", () => {
    const rate = { alpha: 4, beta: 30, gamma: 7 };
    expect(motionSample({ rotationRate: rate }, "ios")).toMatchObject({
      yawRate: 30,
      pitchRate: 7,
    });
    expect(motionSample({ rotationRate: rate }, "android")).toMatchObject({
      yawRate: 30,
      pitchRate: 4,
    });
  });

  it("reads tilt from gravity whatever its sign", () => {
    expect(motionSample({ accelerationIncludingGravity: upright }, "ios").rollDegrees).toBeCloseTo(
      0,
    );
    const sideways = { x: 9.81 * Math.sin(0.3), y: 9.81 * Math.cos(0.3), z: 0 };
    expect(
      motionSample({ accelerationIncludingGravity: sideways }, "android").rollDegrees,
    ).toBeCloseTo((0.3 * 180) / Math.PI);
    const down = { x: 0, y: -9.81 * Math.cos(0.5), z: 9.81 * Math.sin(0.5) };
    expect(motionSample({ accelerationIncludingGravity: down }, "ios").pitchDegrees).toBeCloseTo(
      (0.5 * 180) / Math.PI,
    );
  });

  it("measures shake and total turn, and notices a missing gyroscope", () => {
    const sample = motionSample(
      { rotationRate: { alpha: 0, beta: 30, gamma: 40 }, acceleration: { x: 3, y: 4, z: 0 } },
      "ios",
    );
    expect(sample.rotationRate).toBeCloseTo(50);
    expect(sample.acceleration).toBeCloseTo(5);
    expect(sample.hasGyro).toBe(true);
    expect(motionSample({}, "android").hasGyro).toBe(false);
  });

  it("wraps angles", () => {
    expect(wrapDegrees(190)).toBe(-170);
    expect(wrapDegrees(-190)).toBe(170);
    expect(wrapDegrees(30)).toBe(30);
  });
});

describe("coverage", () => {
  it("maps a sector and its neighbours after a few detailed frames", () => {
    let state = addFrame(EMPTY_COVERAGE, 0, MIN_FEATURES);
    expect(mappedDegrees(state)).toBe(0);
    state = addFrame(state, 0, MIN_FEATURES);
    expect(mappedDegrees(state)).toBe(45);
  });

  it("ignores frames with too little detail", () => {
    const state = addFrame(addFrame(EMPTY_COVERAGE, 0, 2), 0, 2);
    expect(state).toEqual(EMPTY_COVERAGE);
  });

  it("handles turning past a full circle either way", () => {
    expect(sectorOf(-1)).toBe(23);
    expect(sectorOf(361)).toBe(0);
  });

  it("caps the share at a full sweep and offers Done at a corner's worth", () => {
    let state = EMPTY_COVERAGE;
    for (let yaw = 0; yaw <= 60; yaw += 5) state = addFrame(addFrame(state, yaw, 20), yaw, 20);
    expect(mappedDegrees(state)).toBeGreaterThanOrEqual(90);
    expect(enoughCoverage(state, true)).toBe(true);
    for (let yaw = 0; yaw < 360; yaw += 5) state = addFrame(addFrame(state, yaw, 20), yaw, 20);
    expect(coverageFraction(state, true)).toBe(1);
  });
});

describe("mini-map", () => {
  it("draws straight ahead at the top and turning left anticlockwise", () => {
    expect(screenAngle(0)).toBe(-90);
    expect(screenAngle(90)).toBe(-180);
  });
});
