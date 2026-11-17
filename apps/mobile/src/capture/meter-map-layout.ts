// Where things go on the coverage meter's map: the floor walked so far, the
// parts of the loop still missing, where to stand for the next sweep, and
// where the phone is now. Pure, so the drawing component only draws.
import type { Point2 } from "./ar/guidance";
import {
  loopOf,
  MAP_CELL_M,
  type MeterState,
  nextSweepSpot,
  SECTORS,
  sweepsOf,
  walkedCells,
} from "./coverage-meter";

/** The map always shows at least this much floor across, so a first step does not fill it. */
export const MIN_SPAN_M = 3;

export interface MeterMapLayout {
  /** Walked floor cells as squares, in map pixels. */
  cells: { x: number; y: number; size: number }[];
  /** Middles of the loop sectors not walked yet, on a ring round the centre; empty before a loop takes shape. */
  missing: { x: number; y: number }[];
  /** Counted sweeps, and where the next one should be (null when none is needed yet or any more). */
  sweeps: { x: number; y: number }[];
  next: { x: number; y: number } | null;
  /** The phone now, and the way it points (degrees clockwise from up on the map). */
  phone: { x: number; y: number; headingDeg: number } | null;
}

export function meterMapLayout(
  meter: MeterState,
  size: number,
  phone: { position: Point2; yaw: number } | null,
): MeterMapLayout {
  const loop = loopOf(meter);
  const points = [...meter.positions, ...(phone ? [phone.position] : [])];
  if (points.length === 0 || !loop.centre) {
    return { cells: [], missing: [], sweeps: [], next: null, phone: null };
  }
  const centre = loop.centre;
  const reach = Math.max(
    MIN_SPAN_M / 2,
    ...points.map((p) => Math.max(Math.abs(p.x - centre.x), Math.abs(p.z - centre.z))),
  );
  // A margin of one cell round what was walked.
  const scale = size / (2 * (reach + MAP_CELL_M));
  const place = (p: Point2) => ({
    x: size / 2 + (p.x - centre.x) * scale,
    // AR's -z is forward: forward from where the scan began is up on the map.
    y: size / 2 + (p.z - centre.z) * scale,
  });
  const cells = walkedCells(meter).map((key) => {
    const [column, row] = key.split(",").map(Number) as [number, number];
    const corner = place({ x: column * MAP_CELL_M, z: row * MAP_CELL_M });
    return { x: corner.x, y: corner.y, size: MAP_CELL_M * scale };
  });
  const missing =
    loop.complete || loop.count === 0
      ? []
      : loop.sectors.flatMap((walked, i) => {
          if (walked) return [];
          const bearing = ((i + 0.5) * (360 / SECTORS) * Math.PI) / 180;
          return [
            place({
              x: centre.x + Math.sin(bearing) * loop.radiusM,
              z: centre.z + Math.cos(bearing) * loop.radiusM,
            }),
          ];
        });
  const spot = nextSweepSpot(meter);
  return {
    cells,
    missing,
    sweeps: sweepsOf(meter, loop)
      .all.filter((sweep) => sweep.counted)
      .map((sweep) => place(sweep.centre)),
    next: spot ? place(spot) : null,
    phone: phone
      ? { ...place(phone.position), headingDeg: ((-phone.yaw % 360) + 360) % 360 }
      : null,
  };
}
