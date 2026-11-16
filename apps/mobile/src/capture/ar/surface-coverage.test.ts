import {
  addSurfaceSample,
  EMPTY_SURFACE_COVERAGE,
  floorProgress,
  MAX_TURN_DEG_PER_S,
  shouldSlowDown,
  type SurfaceCoverage,
  surfaceFraction,
  type SurfaceHit,
  wallProgress,
} from "./surface-coverage";

// A 4 m by 4 m room centred on the origin: walls at x = +-2 and z = +-2.
// A wall facing +z (normal yaw 0) sits at z = -2, offset -2, and so on.
const WALLS = [
  { normalYaw: 0, offset: -2, point: (a: number, y: number) => ({ x: a, y, z: -2 }) },
  { normalYaw: 90, offset: -2, point: (a: number, y: number) => ({ x: -2, y, z: -a }) },
  { normalYaw: 180, offset: -2, point: (a: number, y: number) => ({ x: -a, y, z: 2 }) },
  { normalYaw: 270, offset: -2, point: (a: number, y: number) => ({ x: 2, y, z: a }) },
];

/** A 4 by 3 grid of rays landing on one wall, centred at `along` metres. */
function wallHits(wall: number, along: number): SurfaceHit[] {
  const w = WALLS[wall]!;
  const hits: SurfaceHit[] = [];
  for (let i = 0; i < 4; i += 1) {
    for (let j = 0; j < 3; j += 1) {
      hits.push({
        kind: "wall",
        normalYaw: w.normalYaw,
        offset: w.offset,
        ...w.point(along - 0.75 + i * 0.5, 0.25 + j * 0.6),
      });
    }
  }
  return hits;
}

function floorHits(x: number, z: number): SurfaceHit[] {
  const hits: SurfaceHit[] = [];
  for (let i = 0; i < 4; i += 1) {
    for (let j = 0; j < 3; j += 1) {
      hits.push({ kind: "floor", normalYaw: 0, offset: 0, x: x + i * 0.5, y: 0, z: z + j * 0.5 });
    }
  }
  return hits;
}

// Heights in these tests are above the floor.
const sample = (hits: SurfaceHit[], sharpness = 100) => ({ sharpness, hits, floorY: 0 });

/** A slow, sharp sweep: every wall across its width, then the floor, twice. */
function realSweep(): SurfaceCoverage {
  let state = EMPTY_SURFACE_COVERAGE;
  for (let pass = 0; pass < 2; pass += 1) {
    for (let wall = 0; wall < 4; wall += 1) {
      for (const along of [-1.25, -0.25, 0.75, 1.25]) {
        state = addSurfaceSample(state, sample(wallHits(wall, along)), 15, true);
      }
    }
    for (const [x, z] of [
      [-2, -2],
      [0, -2],
      [-2, -0.5],
      [0, -0.5],
      [-2, 1],
      [0, 1],
    ] as const) {
      state = addSurfaceSample(state, sample(floorHits(x, z)), 15, true);
    }
  }
  return state;
}

describe("surface coverage", () => {
  it("reaches 100% only after a slow, sharp sweep of the walls and floor", () => {
    const state = realSweep();
    expect(state.walls).toHaveLength(4);
    expect(surfaceFraction(state)).toBe(1);
  });

  it("gives nothing for spinning in place faster than 30 degrees a second", () => {
    let state = EMPTY_SURFACE_COVERAGE;
    for (let turn = 0; turn < 20; turn += 1) {
      for (let wall = 0; wall < 4; wall += 1) {
        state = addSurfaceSample(state, sample(wallHits(wall, 0)), 120, true);
      }
    }
    expect(surfaceFraction(state)).toBe(0);
    expect(state.rejected).toBe(80);
  });

  it("gives nothing for blurred frames, judged against this session's sharp ones", () => {
    let state = realSweep();
    const before = surfaceFraction(state);
    const fresh = addSurfaceSample(EMPTY_SURFACE_COVERAGE, sample(wallHits(0, 0), 100), 10, true);
    let blurred = fresh;
    for (let i = 0; i < 6; i += 1) {
      blurred = addSurfaceSample(blurred, sample(wallHits(0, 0), 100), 10, true);
    }
    for (let i = 0; i < 10; i += 1) {
      blurred = addSurfaceSample(blurred, sample(wallHits(1, 0), 20), 10, true);
    }
    expect(blurred.walls[1] && wallProgress(blurred.walls[1])).toBe(0);
    state = addSurfaceSample(state, sample(wallHits(2, 0), 10), 10, true);
    expect(surfaceFraction(state)).toBe(before);
  });

  it("gives nothing while tracking is lost", () => {
    const state = addSurfaceSample(EMPTY_SURFACE_COVERAGE, sample(floorHits(0, 0)), 5, false);
    expect(floorProgress(state)).toBe(0);
  });

  it("does not finish by pointing at one patch for a long time", () => {
    let state = EMPTY_SURFACE_COVERAGE;
    for (let i = 0; i < 200; i += 1) {
      state = addSurfaceSample(state, sample(wallHits(0, 0)), 5, true);
    }
    // One wall, one patch: a quarter of the walls-and-floor total at most.
    expect(surfaceFraction(state)).toBeLessThanOrEqual(0.25);
  });

  it("asks to slow down when recent samples are rejected, and stops once they count", () => {
    let state = EMPTY_SURFACE_COVERAGE;
    for (let i = 0; i < 3; i += 1) {
      state = addSurfaceSample(state, sample(wallHits(0, 0)), MAX_TURN_DEG_PER_S + 20, true);
    }
    expect(shouldSlowDown(state)).toBe(true);
    for (let i = 0; i < 6; i += 1) {
      state = addSurfaceSample(state, sample(wallHits(0, 0)), 10, true);
    }
    expect(shouldSlowDown(state)).toBe(false);
  });

  it("merges hits on the same wall even when its direction wobbles", () => {
    let state = EMPTY_SURFACE_COVERAGE;
    for (const wobble of [-8, 0, 8]) {
      const hits = wallHits(0, 0).map((hit) => ({ ...hit, normalYaw: wobble, offset: -2.1 }));
      state = addSurfaceSample(state, sample(hits), 10, true);
    }
    expect(state.walls).toHaveLength(1);
  });
});
