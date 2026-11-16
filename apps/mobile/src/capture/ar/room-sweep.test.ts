import { gridHits, type Room } from "./room-sweep";
import {
  addSurfaceSample,
  EMPTY_SURFACE_COVERAGE,
  MAX_TURN_DEG_PER_S,
  type SurfaceCoverage,
  surfaceFraction,
} from "./surface-coverage";

/** A sweep from where you stand: `degPerS` for `seconds`, a sample every 250 ms; returns coverage over time. */
function sweep(
  room: Room,
  degPerS: number,
  seconds: number,
  standAt = { x: 0, z: 0 },
): { at: number; share: number; coverage: SurfaceCoverage }[] {
  let coverage = EMPTY_SURFACE_COVERAGE;
  const timeline = [];
  for (let step = 1; step <= seconds * 4; step += 1) {
    const yaw = (step / 4) * degPerS;
    // Pan a little up and down as people do: between 25 and 5 degrees down.
    const pitch = -15 + 10 * Math.sin(step / 10);
    const hits = gridHits(room, { ...standAt, height: 1.4 }, yaw, pitch);
    coverage = addSurfaceSample(coverage, { sharpness: 100, hits, floorY: 0 }, degPerS, true);
    timeline.push({ at: step / 4, share: surfaceFraction(coverage), coverage });
  }
  return timeline;
}

const livingRoom: Room = { halfX: 2, halfZ: 2.5 };

describe("coverage of a real sweep", () => {
  it("reaches 100% in a slow one-minute sweep of a 4 by 5 m room", () => {
    const timeline = sweep(livingRoom, 6, 60);
    expect(timeline.at(-1)?.share).toBe(1);
    // Done (70%) comes well before the end.
    const done = timeline.find((point) => point.share >= 0.7);
    expect(done?.at).toBeLessThanOrEqual(40);
  });

  it("reaches 100% for a living and dining area, 4 by 7 m, from its middle", () => {
    expect(sweep({ halfX: 2, halfZ: 3.5 }, 6, 60).at(-1)?.share).toBe(1);
  });

  it("counts a pan at 40 degrees a second", () => {
    expect(sweep(livingRoom, 40, 20).at(-1)?.share).toBe(1);
  });

  it("gives nothing for spinning faster than the limit", () => {
    expect(sweep(livingRoom, MAX_TURN_DEG_PER_S + 15, 30).at(-1)?.share).toBe(0);
  });

  it("offers Done for a corner of a bigger room scanned from the doorway", () => {
    // Facing into one corner: yaw from 0 to 90 degrees, back and forth.
    let coverage = EMPTY_SURFACE_COVERAGE;
    for (let step = 1; step <= 240; step += 1) {
      const yaw = 45 + 45 * Math.sin(step / 20);
      const hits = gridHits({ halfX: 3, halfZ: 3 }, { x: 1.5, z: 1.5, height: 1.4 }, yaw, -15);
      coverage = addSurfaceSample(coverage, { sharpness: 100, hits, floorY: 0 }, 10, true);
    }
    expect(coverage.walls.length).toBeGreaterThanOrEqual(2);
    expect(surfaceFraction(coverage)).toBeGreaterThanOrEqual(0.7);
  });
});
