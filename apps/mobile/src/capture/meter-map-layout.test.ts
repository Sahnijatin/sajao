import { addMeterSample, EMPTY_METER, type MeterState } from "./coverage-meter";
import { meterMapLayout } from "./meter-map-layout";
import { HALF_GAP_DEGREES, ringHalves } from "./ring-geometry";

function walk(points: [number, number][], state: MeterState = EMPTY_METER): MeterState {
  let next = state;
  let at = (state.lastSampleMs ?? 0) + 100;
  for (let i = 0; i + 1 < points.length; i += 1) {
    const [x0, z0] = points[i] as [number, number];
    const [x1, z1] = points[i + 1] as [number, number];
    const steps = Math.ceil(Math.hypot(x1 - x0, z1 - z0) / 0.1);
    for (let s = 0; s <= steps; s += 1) {
      const position = { x: x0 + ((x1 - x0) * s) / steps, z: z0 + ((z1 - z0) * s) / steps };
      next = addMeterSample(next, { position, yaw: 0, pitch: 0, atMs: (at += 100) });
    }
  }
  return next;
}

const SQUARE: [number, number][] = [
  [0.5, 0.5],
  [3.5, 0.5],
  [3.5, 3.0],
  [0.5, 3.0],
  [0.5, 0.5],
];

describe("coverage meter map", () => {
  it("is empty before anything is walked", () => {
    expect(meterMapLayout(EMPTY_METER, 72, null)).toEqual({
      cells: [],
      missing: [],
      sweeps: [],
      next: null,
      phone: null,
    });
  });

  it("keeps everything walked inside the map", () => {
    const layout = meterMapLayout(walk(SQUARE), 72, { position: { x: 0.5, z: 0.5 }, yaw: 0 });
    expect(layout.cells.length).toBeGreaterThan(10);
    for (const cell of layout.cells) {
      expect(cell.x).toBeGreaterThanOrEqual(0);
      expect(cell.y).toBeGreaterThanOrEqual(0);
      expect(cell.x + cell.size).toBeLessThanOrEqual(72 + 1e-6);
      expect(cell.y + cell.size).toBeLessThanOrEqual(72 + 1e-6);
    }
    expect(layout.phone).not.toBeNull();
  });

  it("marks the loop sectors still missing, and none once the loop is closed", () => {
    const half = meterMapLayout(walk(SQUARE.slice(0, 3)), 72, null);
    expect(half.missing.length).toBeGreaterThanOrEqual(3);
    expect(half.next).toBeNull();
    const closed = meterMapLayout(walk(SQUARE), 72, null);
    expect(closed.missing).toEqual([]);
    // The first sweep is asked for in the middle of the map.
    expect(closed.next).not.toBeNull();
    expect(Math.abs((closed.next?.x ?? 0) - 36)).toBeLessThan(8);
    expect(Math.abs((closed.next?.y ?? 0) - 36)).toBeLessThan(8);
  });

  it("points the phone marker the way the phone faces", () => {
    const at = { position: { x: 1, z: 1 } };
    expect(meterMapLayout(walk(SQUARE), 72, { ...at, yaw: 0 }).phone?.headingDeg).toBe(0);
    // A turn to the left (positive yaw) is anticlockwise on the map.
    expect(meterMapLayout(walk(SQUARE), 72, { ...at, yaw: 90 }).phone?.headingDeg).toBe(270);
  });
});

describe("two-part ring", () => {
  it("draws the loop down the right side and the sweeps up the left, with gaps", () => {
    const [loop, sweeps] = ringHalves(1, 0.5);
    const span = 180 - HALF_GAP_DEGREES;
    expect(loop).toEqual({ start: -90 + HALF_GAP_DEGREES / 2, sweep: span });
    expect(sweeps).toEqual({ start: 90 + HALF_GAP_DEGREES / 2, sweep: span / 2 });
  });

  it("clamps bad values", () => {
    const [loop, sweeps] = ringHalves(Number.NaN, 7);
    expect(loop.sweep).toBe(0);
    expect(sweeps.sweep).toBe(180 - HALF_GAP_DEGREES);
  });
});
