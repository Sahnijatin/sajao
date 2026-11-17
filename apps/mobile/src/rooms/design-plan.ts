// The dimensioned 2D plan of a room with one design's furniture in place.
// Everything is worked out from the room's measured shell and the `Design`:
// each item's footprint is its product's own width and depth at the
// position and rotation the solver (or a person) gave it. Pure geometry;
// nothing here places, sizes or measures anything.
import type { Design, SpaceTwin } from "@sajao/schemas";
import { type EdgeKind, edgeKinds } from "./room-shape";

type Shell = SpaceTwin["shell"];
export type PlanShell = Pick<Shell, "floor_polygon" | "walls" | "openings">;

export interface Px {
  x: number;
  y: number;
}

interface Metres {
  x_m: number;
  y_m: number;
}

export interface DesignPlan {
  outline: Px[];
  /** The outline edge by edge: a wall, or an open side with no wall along it. */
  edges: { from: Px; to: Px; kind: EdgeKind }[];
  /**
   * Half-width in pixels of the soft band drawn round the outline: the widest
   * error band of a wall that is not tape-measured. 0 when every wall is.
   */
  haloPx: number;
  walls: { id: string; at: Px; metres: number }[];
  openings: { id: string; kind: "door" | "window"; from: Px; to: Px }[];
  items: { id: string; title: string; corners: [Px, Px, Px, Px]; centre: Px }[];
  /** The tightest gaps between an item and a wall, tightest first. */
  clearances: { itemId: string; from: Px; to: Px; metres: number }[];
  /** Pixels per metre. */
  scale: number;
}

/** A gap narrower than this is an item standing against the wall: not labelled. */
export const AGAINST_WALL_M = 0.05;
/** The plan labels at most this many clearances, so it stays readable. */
export const MAX_CLEARANCES = 3;
/** Wall lengths sit this far outside the outline, in pixels. */
const WALL_LABEL_OFFSET_PX = 14;

/** The four corners of an item on the floor, in metres. Rotation is anticlockwise. */
export function footprint(item: Design["items"][number]): [Metres, Metres, Metres, Metres] {
  const halfW = item.product.dimensions.width.value_m / 2;
  const halfD = item.product.dimensions.depth.value_m / 2;
  const turn = (item.rotation_deg * Math.PI) / 180;
  const cos = Math.cos(turn);
  const sin = Math.sin(turn);
  const corner = (dx: number, dy: number): Metres => ({
    x_m: item.position.x_m + dx * cos - dy * sin,
    y_m: item.position.y_m + dx * sin + dy * cos,
  });
  return [
    corner(-halfW, -halfD),
    corner(halfW, -halfD),
    corner(halfW, halfD),
    corner(-halfW, halfD),
  ];
}

/** The closest point to `p` on the segment from `a` to `b`. */
function closestOnSegment(p: Metres, a: Metres, b: Metres): Metres {
  const abX = b.x_m - a.x_m;
  const abY = b.y_m - a.y_m;
  const lengthSquared = abX * abX + abY * abY;
  if (lengthSquared === 0) return a;
  const t = Math.min(
    1,
    Math.max(0, ((p.x_m - a.x_m) * abX + (p.y_m - a.y_m) * abY) / lengthSquared),
  );
  return { x_m: a.x_m + abX * t, y_m: a.y_m + abY * t };
}

const distance = (a: Metres, b: Metres) => Math.hypot(a.x_m - b.x_m, a.y_m - b.y_m);

/**
 * The narrowest gap between an item's footprint and the room's walls: the
 * two points it runs between and its width in metres. Open edges are not
 * walls: with `kinds` given, only the wall edges are measured against.
 */
export function wallClearance(
  corners: readonly Metres[],
  polygon: readonly Metres[],
  kinds?: readonly EdgeKind[],
): { from: Metres; to: Metres; metres: number } | null {
  let best: { from: Metres; to: Metres; metres: number } | null = null;
  const consider = (from: Metres, to: Metres) => {
    const metres = distance(from, to);
    if (!best || metres < best.metres) best = { from, to, metres };
  };
  for (let w = 0; w < polygon.length; w += 1) {
    if (kinds && kinds[w] === "open") continue;
    const wallA = polygon[w] as Metres;
    const wallB = polygon[(w + 1) % polygon.length] as Metres;
    // A rectangle and a wall are closest at a corner of one or the other.
    for (const corner of corners) consider(corner, closestOnSegment(corner, wallA, wallB));
    for (let e = 0; e < corners.length; e += 1) {
      const edgeA = corners[e] as Metres;
      const edgeB = corners[(e + 1) % corners.length] as Metres;
      for (const end of [wallA, wallB]) consider(closestOnSegment(end, edgeA, edgeB), end);
    }
  }
  return best;
}

/** Fit the room and one design's items into a box, in pixels, keeping its shape. */
export function designPlan(
  design: Design | null,
  shell: PlanShell,
  box: { width: number; height: number; padding: number },
): DesignPlan {
  const xs = shell.floor_polygon.map((point) => point.x_m);
  const ys = shell.floor_polygon.map((point) => point.y_m);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const spanX = Math.max(Math.max(...xs) - minX, 1e-6);
  const spanY = Math.max(Math.max(...ys) - minY, 1e-6);
  const scale = Math.min(
    (box.width - 2 * box.padding) / spanX,
    (box.height - 2 * box.padding) / spanY,
  );
  const offsetX = (box.width - spanX * scale) / 2;
  const offsetY = (box.height - spanY * scale) / 2;
  const place = (point: Metres): Px => ({
    x: offsetX + (point.x_m - minX) * scale,
    // Screen y grows downward; plan y grows upward.
    y: box.height - offsetY - (point.y_m - minY) * scale,
  });

  const outline = shell.floor_polygon.map(place);
  const kinds = edgeKinds(shell);
  const edges = outline.map((from, index) => ({
    from,
    to: outline[(index + 1) % outline.length] as Px,
    kind: kinds[index] as EdgeKind,
  }));
  const centre = {
    x: outline.reduce((sum, point) => sum + point.x, 0) / outline.length,
    y: outline.reduce((sum, point) => sum + point.y, 0) / outline.length,
  };

  const walls = shell.walls.map((wall) => {
    const from = place(wall.start);
    const to = place(wall.end);
    const mid = { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 };
    // Push the label out of the room, away from its centre.
    const away = Math.hypot(mid.x - centre.x, mid.y - centre.y) || 1;
    return {
      id: wall.id,
      at: {
        x: mid.x + ((mid.x - centre.x) / away) * WALL_LABEL_OFFSET_PX,
        y: mid.y + ((mid.y - centre.y) / away) * WALL_LABEL_OFFSET_PX,
      },
      metres: wall.length.value_m,
    };
  });

  const openings = shell.openings.flatMap((opening) => {
    const wall = shell.walls.find((candidate) => candidate.id === opening.wall_id);
    if (!wall || wall.length.value_m <= 0) return [];
    const along = (metres: number): Metres => {
      const t = metres / wall.length.value_m;
      return {
        x_m: wall.start.x_m + (wall.end.x_m - wall.start.x_m) * t,
        y_m: wall.start.y_m + (wall.end.y_m - wall.start.y_m) * t,
      };
    };
    return [
      {
        id: opening.id,
        kind: opening.kind,
        from: place(along(opening.offset.value_m)),
        to: place(along(opening.offset.value_m + opening.width.value_m)),
      },
    ];
  });

  const placed = (design?.items ?? []).map((item) => ({ item, corners: footprint(item) }));
  const items = placed.map(({ item, corners }) => ({
    id: item.id,
    title: item.product.title,
    corners: corners.map(place) as [Px, Px, Px, Px],
    centre: place(item.position),
  }));

  const clearances = placed
    .flatMap(({ item, corners }) => {
      const gap = wallClearance(corners, shell.floor_polygon, kinds);
      return gap && gap.metres >= AGAINST_WALL_M
        ? [{ itemId: item.id, from: place(gap.from), to: place(gap.to), metres: gap.metres }]
        : [];
    })
    .sort((a, b) => a.metres - b.metres)
    .slice(0, MAX_CLEARANCES);

  const widestBand = shell.walls
    .filter((wall) => wall.length.source !== "measured")
    .reduce((widest, wall) => Math.max(widest, wall.length.error_band_m), 0);

  return { outline, edges, haloPx: widestBand * scale, walls, openings, items, clearances, scale };
}
