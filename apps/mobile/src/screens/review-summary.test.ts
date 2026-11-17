import { EMPTY_SURFACE_COVERAGE, type Wall } from "@/capture/ar/surface-coverage";
import { EMPTY_COVERAGE, HITS_TO_MAP, SECTOR_COUNT, sectorOf } from "@/capture/coverage";
import { EMPTY_MOTION_COVERAGE, MOVE_TARGET_M } from "@/capture/motion-coverage";
import { INITIAL_SCAN, type ScanState } from "@/capture/scan-session";
import {
  missingFromMeter,
  missingSides,
  roughSize,
  scanSummary,
  SIDE_DEGREES,
} from "./review-summary";

/** Directions mapped from `from` to `to` degrees (positive is a turn to the left). */
function mapped(...ranges: [number, number][]): boolean[] {
  const sectors = Array.from({ length: SECTOR_COUNT }, () => false);
  for (const [from, to] of ranges) {
    for (let yaw = from; yaw < to; yaw += 5) sectors[sectorOf(yaw)] = true;
  }
  return sectors;
}

const headings = (sectors: boolean[]) => ({
  ...EMPTY_COVERAGE,
  hits: sectors.map((on) => (on ? HITS_TO_MAP : 0)),
});

/** A wall with every cell of a 3 m by 2 m face mapped, or none. */
function wall(normalYaw: number, offset: number, covered = true): Wall {
  const cells: Record<string, number> = {};
  if (covered) {
    for (let along = 0; along < 6; along += 1) {
      for (let up = 0; up < 4; up += 1) cells[`${along},${up}`] = 5;
    }
  }
  return { normalYaw, offset, cells, minAlong: 0, maxAlong: 5 };
}

const floor = (cells: number) =>
  Object.fromEntries(Array.from({ length: cells }, (_, index) => [`${index},0`, 5]));

describe("sides of the room", () => {
  it("each side is a quarter turn, centred on its direction", () => {
    expect(SIDE_DEGREES).toBe(90);
    expect(missingSides(mapped([-45, 45]))).toEqual(["left", "behind", "right"]);
    expect(missingSides(mapped([45, 135]))).toEqual(["ahead", "behind", "right"]);
    expect(missingSides(mapped([135, 225]))).toEqual(["ahead", "left", "right"]);
    expect(missingSides(mapped([225, 315]))).toEqual(["ahead", "left", "behind"]);
  });

  it("a full turn misses nothing; no turn misses everything", () => {
    expect(missingSides(mapped([0, 360]))).toEqual([]);
    expect(missingSides(mapped())).toEqual(["ahead", "left", "behind", "right"]);
  });

  it("names sides from where you face when the review opens", () => {
    // Only the starting direction was scanned. Having turned left a quarter
    // turn, what is missing is in front, on the left and behind; the scanned
    // side is now on the right.
    expect(missingSides(mapped([-45, 45]), 90)).toEqual(["ahead", "left", "behind"]);
    expect(missingSides(mapped([-45, 45]), 180)).toEqual(["ahead", "left", "right"]);
    expect(missingSides(mapped([-45, 45]), -90)).toEqual(["ahead", "behind", "right"]);
    expect(missingSides(mapped([-45, 45]), 360 + 20)).toEqual(["left", "behind", "right"]);
  });

  it("half a side is enough to count it as seen", () => {
    expect(missingSides(mapped([-45, 45], [45, 90]))).toEqual(["behind", "right"]);
    expect(missingSides(mapped([-45, 45], [45, 75]))).toEqual(["left", "behind", "right"]);
  });
});

describe("rough size", () => {
  it("comes from two pairs of facing walls, longer side first, to 10 cm", () => {
    // Origin 1.5 m from the east and west walls' sides: 4.12 m by 3.38 m.
    const walls = [wall(0, -2.06), wall(180, -2.06), wall(90, -1.2), wall(270, -2.18)];
    expect(roughSize(walls)).toEqual({ longM: 4.1, shortM: 3.4 });
  });

  it("is not guessed from one pair, from walls at odd angles, or from no walls", () => {
    expect(roughSize([])).toBeNull();
    expect(roughSize([wall(0, -2), wall(180, -2)])).toBeNull();
    expect(roughSize([wall(0, -2), wall(180, -2), wall(40, -1), wall(220, -1)])).toBeNull();
  });

  it("ignores pairs that cannot be room walls", () => {
    // 30 cm apart (a pillar) and 40 m apart (tracking drift).
    expect(roughSize([wall(0, -0.1), wall(180, -0.2), wall(90, -20), wall(270, -20)])).toBeNull();
  });

  it("tolerates walls a few degrees off square", () => {
    const walls = [wall(3, -2), wall(178, -2), wall(95, -1.5), wall(268, -1.5)];
    expect(roughSize(walls)).toEqual({ longM: 4, shortM: 3 });
  });
});

describe("scan summary", () => {
  const simple = (over: Partial<ScanState["motionCoverage"]>): ScanState => ({
    ...INITIAL_SCAN,
    poseSource: "ar",
    mode: { ...INITIAL_SCAN.mode, mode: "simple" },
    motionCoverage: { ...EMPTY_MOTION_COVERAGE, tracked: true, ...over },
  });

  it("simple scan: a full turn and a walk misses nothing", () => {
    const summary = scanSummary(
      simple({ headings: headings(mapped([0, 360])), pathM: MOVE_TARGET_M }),
    );
    expect(summary.missing).toEqual([]);
    expect(summary.share).toBe(1);
    expect(summary.size).toBeNull();
  });

  it("simple scan: names the side never faced, and standing in one spot", () => {
    const summary = scanSummary(simple({ headings: headings(mapped([-45, 135])), pathM: 0.5 }));
    expect(summary.missing).toEqual(["behind", "right", "walk"]);
    expect(summary.share).toBeGreaterThan(0);
    expect(summary.share).toBeLessThan(1);
  });

  it("full scan: asks for walls and floor that are not covered", () => {
    const state: ScanState = {
      ...INITIAL_SCAN,
      surfacesSeen: true,
      surfaces: {
        ...EMPTY_SURFACE_COVERAGE,
        walls: [wall(0, -2), wall(180, -2), wall(90, -1.5, false), wall(270, -1.5, false)],
        floor: floor(4),
      },
    };
    const summary = scanSummary(state);
    expect(summary.missing).toEqual(["walls", "floor"]);
    // The size still shows: all four walls were found, two just need more coverage.
    expect(summary.size).toEqual({ longM: 4, shortM: 3 });
  });

  it("full scan: three covered walls and the floor miss nothing", () => {
    const state: ScanState = {
      ...INITIAL_SCAN,
      surfacesSeen: true,
      surfaces: {
        ...EMPTY_SURFACE_COVERAGE,
        walls: [wall(0, -2), wall(180, -2), wall(90, -1.5)],
        floor: floor(16),
      },
    };
    expect(scanSummary(state)).toEqual({ share: 1, missing: [], size: null });
  });

  it("2D scan: sides come from the directions the gyroscope saw", () => {
    const state: ScanState = {
      ...INITIAL_SCAN,
      hasGyro: true,
      coverage: headings(mapped([-45, 45], [225, 315])),
    };
    expect(scanSummary(state).missing).toEqual(["left", "behind"]);
  });

  it("with no gyroscope there are no directions, so nothing is called out", () => {
    expect(scanSummary({ ...INITIAL_SCAN, hasGyro: false }).missing).toEqual([]);
  });
});

describe("what the coverage meter still wanted", () => {
  const nothing = { loopBearings: [], loopPathM: 0, sweepsNeeded: 0, floorLook: false };

  it("a complete scan misses nothing", () => {
    expect(missingFromMeter(nothing)).toEqual([]);
  });

  it("names the walk, the turn in the middle and the floor, in the order to do them", () => {
    expect(missingFromMeter({ ...nothing, loopBearings: [45, 75] })).toEqual(["walk"]);
    expect(missingFromMeter({ ...nothing, loopPathM: 2 })).toEqual(["walk"]);
    expect(missingFromMeter({ ...nothing, sweepsNeeded: 1 })).toEqual(["middle"]);
    expect(missingFromMeter({ ...nothing, floorLook: true })).toEqual(["floor"]);
    expect(
      missingFromMeter({ loopBearings: [15], loopPathM: 1, sweepsNeeded: 2, floorLook: true }),
    ).toEqual(["walk", "middle", "floor"]);
  });
});
