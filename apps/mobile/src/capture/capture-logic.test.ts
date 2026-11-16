import { DEFAULT_FEATURE_OPTIONS, detectFeaturePoints } from "./feature-points";
import { frameStats, type GrayFrame } from "./frame-stats";
import {
  ALL_GOOD,
  evaluateGuardrails,
  NOT_PAUSED,
  PAUSE_AFTER_MS,
  scanAnyway,
  type ScanReading,
  shouldUseFrame,
  updatePause,
} from "./guardrails";
import {
  DEFAULT_TRACKER_OPTIONS,
  EMPTY_MESH,
  LOW_TIER_TRACKER_OPTIONS,
  toScreen,
  updateMesh,
} from "./mesh-tracker";
import { inCircumcircle, type Point, triangulate } from "./triangulate";

// --- helpers -------------------------------------------------------------------

function frame(width: number, height: number, paint: (x: number, y: number) => number): GrayFrame {
  const data = new Uint8Array(width * height);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) data[y * width + x] = paint(x, y);
  }
  return { data, width, height };
}

/** A small deterministic random generator, so property tests are repeatable. */
function seeded(seed: number) {
  let state = seed;
  return () => {
    state = (state * 1664525 + 1013904223) % 4294967296;
    return state / 4294967296;
  };
}

function randomPoints(count: number, seed: number): Point[] {
  const random = seeded(seed);
  return Array.from({ length: count }, () => ({ x: random(), y: random() }));
}

const area = (a: Point, b: Point, c: Point) =>
  Math.abs((b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)) / 2;

function hullArea(points: Point[]): number {
  const sorted = [...points].sort((a, b) => a.x - b.x || a.y - b.y);
  const cross = (o: Point, a: Point, b: Point) =>
    (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
  const half = (list: Point[]) => {
    const hull: Point[] = [];
    for (const point of list) {
      while (hull.length >= 2 && cross(hull.at(-2)!, hull.at(-1)!, point) <= 0) hull.pop();
      hull.push(point);
    }
    return hull.slice(0, -1);
  };
  const hull = [...half(sorted), ...half([...sorted].reverse())];
  return Math.abs(
    hull.reduce((sum, p, i) => {
      const q = hull[(i + 1) % hull.length]!;
      return sum + p.x * q.y - q.x * p.y;
    }, 0) / 2,
  );
}

// --- frame stats ---------------------------------------------------------------

describe("frame stats", () => {
  it("measures brightness", () => {
    expect(frameStats(frame(20, 20, () => 0)).brightness).toBe(0);
    expect(frameStats(frame(20, 20, () => 200)).brightness).toBe(200);
  });

  it("measures the share of blown-out pixels", () => {
    const halfGlare = frame(20, 20, (x) => (x < 10 ? 255 : 100));
    expect(frameStats(halfGlare).glare).toBeCloseTo(0.5);
    expect(frameStats(frame(20, 20, () => 100)).glare).toBe(0);
  });

  it("scores a detailed frame sharper than a flat or smooth one", () => {
    const flat = frameStats(frame(40, 40, () => 120)).sharpness;
    const smooth = frameStats(frame(40, 40, (x) => x * 4)).sharpness;
    const detailed = frameStats(frame(40, 40, (x, y) => ((x + y) % 2 ? 220 : 30))).sharpness;
    expect(flat).toBe(0);
    expect(detailed).toBeGreaterThan(smooth + 1000);
  });

  it("handles an empty frame", () => {
    expect(frameStats({ data: new Uint8Array(0), width: 0, height: 0 })).toEqual({
      brightness: 0,
      glare: 0,
      sharpness: 0,
    });
  });
});

// --- feature points -------------------------------------------------------------

describe("feature points", () => {
  const WIDTH = 96;
  const HEIGHT = 72;
  // A bright rectangle on a dark wall: its four corners are the features.
  const rectangle = frame(WIDTH, HEIGHT, (x, y) =>
    x >= 30 && x < 66 && y >= 20 && y < 50 ? 230 : 25,
  );

  it("finds the corners of a shape", () => {
    const points = detectFeaturePoints(rectangle);
    const corners = [
      [30, 20],
      [66, 20],
      [30, 50],
      [66, 50],
    ];
    for (const [cx, cy] of corners) {
      const near = points.some(
        (point) => Math.abs(point.x * WIDTH - cx!) <= 3 && Math.abs(point.y * HEIGHT - cy!) <= 3,
      );
      expect(near).toBe(true);
    }
  });

  it("finds nothing on a flat wall", () => {
    expect(detectFeaturePoints(frame(WIDTH, HEIGHT, () => 128))).toEqual([]);
  });

  it("ignores a straight edge: an edge is not a corner", () => {
    const edge = frame(WIDTH, HEIGHT, (x) => (x < WIDTH / 2 ? 30 : 220));
    expect(detectFeaturePoints(edge)).toEqual([]);
  });

  it("returns positions as fractions of the frame, strongest first, within the cap", () => {
    const busy = frame(WIDTH, HEIGHT, (x, y) =>
      (Math.floor(x / 8) + Math.floor(y / 8)) % 2 ? 220 : 30,
    );
    const points = detectFeaturePoints(busy, { ...DEFAULT_FEATURE_OPTIONS, maxPoints: 10 });
    expect(points).toHaveLength(10);
    expect(points.every((p) => p.x >= 0 && p.x <= 1 && p.y >= 0 && p.y <= 1)).toBe(true);
    const strengths = points.map((point) => point.strength);
    expect(strengths).toEqual([...strengths].sort((a, b) => b - a));
  });

  it("spreads points out: at most one per cell", () => {
    const busy = frame(WIDTH, HEIGHT, (x, y) =>
      (Math.floor(x / 4) + Math.floor(y / 4)) % 2 ? 220 : 30,
    );
    const points = detectFeaturePoints(busy, { ...DEFAULT_FEATURE_OPTIONS, maxPoints: 1000 });
    const cells = points.map(
      (p) => `${Math.floor((p.x * WIDTH - 2) / 12)}:${Math.floor((p.y * HEIGHT - 2) / 12)}`,
    );
    expect(new Set(cells).size).toBe(cells.length);
  });

  it("handles frames too small to analyse", () => {
    expect(detectFeaturePoints(frame(3, 3, () => 255))).toEqual([]);
  });
});

// --- triangulation ---------------------------------------------------------------

describe("triangulation", () => {
  it("needs three points", () => {
    expect(triangulate([])).toEqual([]);
    expect(triangulate(randomPoints(2, 1))).toEqual([]);
  });

  it("makes one triangle from three points and two from a square", () => {
    expect(
      triangulate([
        { x: 0, y: 0 },
        { x: 1, y: 0 },
        { x: 0, y: 1 },
      ]),
    ).toHaveLength(1);
    const square = [
      { x: 0, y: 0 },
      { x: 1, y: 0 },
      { x: 1, y: 1.01 },
      { x: 0, y: 1 },
    ];
    expect(triangulate(square)).toHaveLength(2);
  });

  it.each([5, 12, 40, 120])("is Delaunay for %d random points", (count) => {
    for (const seed of [1, 2, 3]) {
      const points = randomPoints(count, seed * 97 + count);
      const triangles = triangulate(points);
      for (const [a, b, c] of triangles) {
        const inside = points.some(
          (point, index) =>
            index !== a &&
            index !== b &&
            index !== c &&
            inCircumcircle(point, points[a]!, points[b]!, points[c]!),
        );
        expect(inside).toBe(false);
      }
    }
  });

  it.each([6, 30, 100])("covers the convex hull exactly once for %d points", (count) => {
    const points = randomPoints(count, count * 31);
    const triangles = triangulate(points);
    const covered = triangles.reduce(
      (sum, [a, b, c]) => sum + area(points[a]!, points[b]!, points[c]!),
      0,
    );
    expect(covered).toBeCloseTo(hullArea(points), 6);
    expect(new Set(triangles.flat()).size).toBe(count);
  });

  it("is deterministic", () => {
    const points = randomPoints(50, 7);
    expect(triangulate(points)).toEqual(triangulate(points));
  });
});

// --- mesh tracker ----------------------------------------------------------------

describe("mesh tracker", () => {
  const seen = (points: Point[]) => points.map((point) => ({ ...point, strength: 1 }));
  const corner = seen([
    { x: 0.1, y: 0.1 },
    { x: 0.5, y: 0.15 },
    { x: 0.3, y: 0.6 },
    { x: 0.8, y: 0.7 },
  ]);

  it("starts empty", () => {
    expect(updateMesh(EMPTY_MESH, [])).toEqual(EMPTY_MESH);
  });

  it("fades new points in instead of popping them", () => {
    let mesh = updateMesh(EMPTY_MESH, corner);
    expect(mesh.points.map((p) => p.confidence)).toEqual([0.25, 0.25, 0.25, 0.25]);
    for (let i = 0; i < 6; i += 1) mesh = updateMesh(mesh, corner);
    expect(mesh.points.every((p) => p.confidence === 1)).toBe(true);
    expect(mesh.triangles.length).toBeGreaterThanOrEqual(2);
  });

  it("keeps a point through a few missed frames, then forgets it", () => {
    let mesh = EMPTY_MESH;
    for (let i = 0; i < 6; i += 1) mesh = updateMesh(mesh, corner);
    for (let i = 0; i < 5; i += 1) mesh = updateMesh(mesh, []);
    expect(mesh.points).toHaveLength(4);
    for (let i = 0; i < 30; i += 1) mesh = updateMesh(mesh, []);
    expect(mesh.points).toHaveLength(0);
    expect(mesh.triangles).toEqual([]);
  });

  it("holds one steady point per cell when detections jitter", () => {
    let mesh = EMPTY_MESH;
    const random = seeded(5);
    for (let i = 0; i < 20; i += 1) {
      mesh = updateMesh(mesh, seen([{ x: 0.52 + random() * 0.01, y: 0.52 + random() * 0.01 }]));
    }
    expect(mesh.points).toHaveLength(1);
    expect(mesh.points[0]!.x).toBeCloseTo(0.525, 1);
  });

  it("spreads: coverage grows as new areas are seen and never exceeds 1", () => {
    let mesh = EMPTY_MESH;
    const coverage: number[] = [];
    for (let column = 0; column < 12; column += 1) {
      const strip = Array.from({ length: 20 }, (_, row) => ({
        x: (column + 0.5) / 12,
        y: (row + 0.5) / 20,
      }));
      for (let i = 0; i < 4; i += 1) mesh = updateMesh(mesh, seen(strip));
      coverage.push(mesh.coverage);
    }
    expect(coverage[0]).toBeLessThan(coverage[5]!);
    expect(Math.max(...coverage)).toBeLessThanOrEqual(1);
    expect(mesh.points.length).toBeLessThanOrEqual(DEFAULT_TRACKER_OPTIONS.maxPoints);
  });

  it("tracks fewer points on low-tier phones", () => {
    const everywhere = seen(randomPoints(400, 11));
    let full = EMPTY_MESH;
    let lite = EMPTY_MESH;
    for (let i = 0; i < 5; i += 1) {
      full = updateMesh(full, everywhere);
      lite = updateMesh(lite, everywhere, LOW_TIER_TRACKER_OPTIONS);
    }
    expect(lite.points.length).toBeLessThanOrEqual(60);
    expect(full.points.length).toBeGreaterThan(lite.points.length);
  });

  it("maps points to screen pixels for drawing", () => {
    const mesh = updateMesh(EMPTY_MESH, seen([{ x: 0.5, y: 0.25 }]));
    expect(toScreen(mesh, { width: 390, height: 844 })).toEqual([{ x: 195, y: 211 }]);
  });
});

// --- guardrails ------------------------------------------------------------------

describe("scan guardrails", () => {
  const good: ScanReading = {
    brightness: 120,
    glare: 0.01,
    sharpness: 500,
    rotationRate: 10,
    rollDegrees: 2,
  };

  it("are all good in a well-lit, steady, level scan", () => {
    expect(evaluateGuardrails(ALL_GOOD, good)).toEqual(ALL_GOOD);
  });

  it.each([
    ["light", { brightness: 20 }],
    ["motion", { rotationRate: 140 }],
    ["level", { rollDegrees: -25 }],
    ["glare", { glare: 0.4 }],
  ] as const)("warns about %s", (id, change) => {
    const state = evaluateGuardrails(ALL_GOOD, { ...good, ...change });
    expect(state[id]).toBe("warn");
    expect(Object.values(state).filter((status) => status === "warn")).toHaveLength(1);
  });

  it("does not flicker when a reading hovers at the limit", () => {
    let state = evaluateGuardrails(ALL_GOOD, { ...good, brightness: 44 });
    expect(state.light).toBe("warn");
    // Just over the limit is not enough to clear a warning...
    state = evaluateGuardrails(state, { ...good, brightness: 47 });
    expect(state.light).toBe("warn");
    // ...it has to clear it with a margin.
    state = evaluateGuardrails(state, { ...good, brightness: 60 });
    expect(state.light).toBe("good");
  });

  const dark = evaluateGuardrails(ALL_GOOD, { ...good, brightness: 10 });

  it("ignores a brief wobble and pauses softly on a sustained problem", () => {
    let pause = updatePause(NOT_PAUSED, dark, 500);
    expect(pause.paused).toBe(false);
    pause = updatePause(pause, ALL_GOOD, 500);
    expect(pause.failingForMs).toBe(0);

    pause = NOT_PAUSED;
    for (let elapsed = 0; elapsed < PAUSE_AFTER_MS; elapsed += 500) {
      pause = updatePause(pause, dark, 500);
    }
    expect(pause).toMatchObject({ paused: true, reason: "light" });
  });

  it("resumes on its own once the problem is fixed", () => {
    let pause = updatePause(NOT_PAUSED, dark, PAUSE_AFTER_MS);
    expect(pause.paused).toBe(true);
    pause = updatePause(pause, dark, 500);
    expect(pause.paused).toBe(true);
    pause = updatePause(pause, ALL_GOOD, 500);
    expect(pause).toMatchObject({ paused: false, reason: null });
  });

  it("explains the most useful fix first when several things are wrong", () => {
    const darkAndFast = evaluateGuardrails(ALL_GOOD, {
      ...good,
      brightness: 10,
      rotationRate: 200,
    });
    expect(updatePause(NOT_PAUSED, darkAndFast, PAUSE_AFTER_MS).reason).toBe("light");
  });

  it("never pauses for a tilted phone: level is only a nudge", () => {
    const tilted = evaluateGuardrails(ALL_GOOD, { ...good, rollDegrees: 30 });
    expect(updatePause(NOT_PAUSED, tilted, 10 * PAUSE_AFTER_MS).paused).toBe(false);
  });

  it("lets the user scan anyway, and does not pause for that reason again", () => {
    let pause = updatePause(NOT_PAUSED, dark, PAUSE_AFTER_MS);
    pause = scanAnyway(pause);
    expect(pause).toMatchObject({ paused: false, overridden: ["light"] });
    pause = updatePause(pause, dark, 10 * PAUSE_AFTER_MS);
    expect(pause.paused).toBe(false);
    // A different problem can still pause.
    const fast = evaluateGuardrails(ALL_GOOD, { ...good, rotationRate: 200 });
    expect(updatePause(pause, fast, PAUSE_AFTER_MS).reason).toBe("motion");
  });

  it("uses frames only while scanning and steady", () => {
    expect(shouldUseFrame(NOT_PAUSED, ALL_GOOD)).toBe(true);
    expect(shouldUseFrame(updatePause(NOT_PAUSED, dark, PAUSE_AFTER_MS), dark)).toBe(false);
    const fast = evaluateGuardrails(ALL_GOOD, { ...good, rotationRate: 200 });
    expect(shouldUseFrame(NOT_PAUSED, fast)).toBe(false);
  });
});
