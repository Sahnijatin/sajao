// Every function that runs on the camera thread is checked two ways: its
// compiled code reads nothing outside what was captured, and it runs with
// no module scope. A phone failing with "Property 'X' doesn't exist" on
// every frame fails here first.
import { isolate, isWorklet, unsafeReferences } from "@/test-utils/isolated-worklet";
import { downsampleLuma } from "./downsample";
import { detectFeaturePoints } from "./feature-points";
import { analyseFrame, type FrameLike } from "./frame-analysis";
import { frameStats } from "./frame-stats";
import { uprightAspect, uprightPoint } from "./orientation";
import { inCircumcircle, triangulate } from "./triangulate";

const cameraThreadWorklets = {
  analyseFrame,
  downsampleLuma,
  detectFeaturePoints,
  frameStats,
  uprightPoint,
  uprightAspect,
  triangulate,
  inCircumcircle,
};

/** A 1280 by 720 landscape frame of a checkerboard: plenty of corners. */
function fakeFrame(): FrameLike {
  const width = 1280;
  const height = 720;
  const bytesPerRow = 1312; // padded rows, as cameras deliver them
  const pixels = new Uint8Array(bytesPerRow * height);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      pixels[y * bytesPerRow + x] = (Math.floor(x / 80) + Math.floor(y / 80)) % 2 ? 200 : 40;
    }
  }
  return {
    orientation: "right",
    isMirrored: false,
    getPlanes: () => [{ width, height, bytesPerRow, getPixelBuffer: () => pixels.buffer }],
  };
}

describe("camera thread worklets", () => {
  it.each(Object.entries(cameraThreadWorklets))("%s is compiled as a worklet", (_, fn) => {
    expect(isWorklet(fn)).toBe(true);
  });

  it.each(Object.entries(cameraThreadWorklets))(
    "%s reads only captured values and runtime built-ins",
    (_, fn) => {
      expect(unsafeReferences(fn)).toEqual([]);
    },
  );

  it("analyses a frame with no module scope, as on the camera thread", () => {
    const result = isolate(analyseFrame)(fakeFrame());
    expect(result).not.toBeNull();
    expect(result!.points.length).toBeGreaterThan(10);
    expect(result!.stats.brightness).toBeGreaterThan(100);
    expect(result!.aspect).toBeCloseTo(9 / 16);
    // Upright: every point inside the frame.
    for (const point of result!.points) {
      expect(point.x).toBeGreaterThanOrEqual(0);
      expect(point.x).toBeLessThanOrEqual(1);
      expect(point.y).toBeGreaterThanOrEqual(0);
      expect(point.y).toBeLessThanOrEqual(1);
    }
    // Same answer as running it normally.
    expect(result).toEqual(analyseFrame(fakeFrame()));
  });

  it("would have caught a default parameter that reads a captured constant", () => {
    const LIMIT = 96;
    function broken(value?: number) {
      "worklet";
      return value ?? LIMIT;
    }
    function brokenDefault(value: number = LIMIT) {
      "worklet";
      return value;
    }
    expect(isolate(broken)()).toBe(96);
    expect(unsafeReferences(brokenDefault)).toContain("default parameter reads LIMIT");
    expect(() => isolate(brokenDefault)()).toThrow(/LIMIT/);
  });

  it("would have caught a call to a plain module function", () => {
    const helper = (value: number) => value * 2;
    function callsHelper(value: number) {
      "worklet";
      return helper(value);
    }
    expect(() => isolate(callsHelper)(2)).toThrow(/non-worklet function/);
  });
});
