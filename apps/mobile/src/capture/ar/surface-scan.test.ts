import { canFinish, INITIAL_SCAN, mappedShare, scanReducer, type ScanState } from "../scan-session";
import type { SurfaceHit } from "./surface-coverage";

const reduce = scanReducer("standard");

const floor = (x: number, z: number): SurfaceHit[] =>
  Array.from({ length: 12 }, (_, i) => ({
    kind: "floor" as const,
    normalYaw: 0,
    offset: 0,
    x: x + (i % 4) * 0.5,
    y: 0,
    z: z + Math.floor(i / 4) * 0.5,
  }));

/** Turns the AR camera at `degPerS` for `seconds`, sending a pose every 100 ms and a surface sample every 250 ms. */
function turn(start: ScanState, degPerS: number, seconds: number): ScanState {
  let state = start;
  const t0 = state.clockMs ?? 0;
  for (let ms = 100; ms <= seconds * 1000; ms += 50) {
    const atMs = t0 + ms;
    if (ms % 100 === 0) {
      const yaw = state.pose.yaw + (degPerS * 100) / 1000;
      state = reduce(state, { type: "arPose", yaw, pitch: -20, tracking: "normal", atMs });
    }
    if (ms % 250 === 0) {
      // A slow pan sees each patch of floor more than once.
      const cell = Math.floor(ms / 250) % 8;
      state = reduce(state, {
        type: "arSurfaces",
        sharpness: 100,
        hits: floor((cell % 4) * 2 - 4, Math.floor(cell / 4) * 1.5 - 4),
        atMs,
      });
    }
  }
  return state;
}

describe("AR scan coverage from surface samples", () => {
  it("measures the turn from AR poses", () => {
    expect(turn(INITIAL_SCAN, 90, 2).turnRate).toBeGreaterThan(80);
    expect(turn(INITIAL_SCAN, 10, 2).turnRate).toBeLessThan(15);
  });

  it("counts nothing while turning fast, and maps the floor at a slow pan", () => {
    const fast = turn(INITIAL_SCAN, 120, 6);
    expect(fast.surfaces.accepted).toBeLessThanOrEqual(1);
    expect(mappedShare(fast)).toBe(0);
    const slow = turn(INITIAL_SCAN, 15, 6);
    expect(slow.surfaces.accepted).toBeGreaterThan(20);
    expect(mappedShare(slow)).toBeGreaterThan(0);
  });

  it("does not count a direction just for facing it once surface samples arrive", () => {
    const state = turn(INITIAL_SCAN, 20, 30);
    // Floor only: a quarter at most, so Done is not offered yet.
    expect(mappedShare(state)).toBeLessThanOrEqual(0.25);
    expect(canFinish(state)).toBe(false);
  });
});

describe("one space per scan", () => {
  it("counts nothing beyond a doorway and resumes on coming back", () => {
    const outside = {
      ...INITIAL_SCAN,
      tracking: "normal" as const,
      doorway: { home: {}, beyond: { wall: true }, outside: true },
    };
    const sample = { type: "arSurfaces" as const, sharpness: 100, hits: floor(0, 0), atMs: 1 };
    expect(reduce(outside, sample).surfaces.accepted).toBe(0);
    const back = { ...outside, doorway: { home: {}, beyond: { wall: false }, outside: false } };
    expect(reduce(back, sample).surfaces.accepted).toBe(1);
  });
});
