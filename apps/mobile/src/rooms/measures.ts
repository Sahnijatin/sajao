// The measured facts of a room, as the Room tab shows them: each wall, the
// ceiling, doors and windows, and the big things already in the room. All
// of it is read from the room's `SpaceTwin`; every value keeps its source
// and error band. Pure. Nothing here estimates or rounds a dimension.
import type { Dimension, SpaceTwin } from "@sajao/schemas";
import { floorArea } from "@/space/space-profile";

export interface WallMeasure {
  id: string;
  /** 1 for the first wall, going round the room in the twin's order. */
  number: number;
  length: Dimension;
}

export interface OpeningMeasure {
  id: string;
  kind: "door" | "window";
  /** The number of the wall it is in; null if the twin names a wall it does not have. */
  wallNumber: number | null;
  width: Dimension;
  height: Dimension;
}

export interface ItemMeasure {
  id: string;
  /** The name the twin gives it, for example "Grey three-seater sofa". */
  label: string;
  width: Dimension;
  depth: Dimension;
  height: Dimension;
}

export interface RoomMeasures {
  /** Floor area in square metres, from the twin's floor polygon. */
  areaM2: number;
  walls: WallMeasure[];
  ceiling: Dimension;
  openings: OpeningMeasure[];
  /** Biggest first. */
  bigItems: ItemMeasure[];
}

/** An item is big when its longest side is at least this long. */
export const BIG_ITEM_FROM_M = 0.8;
/** The Room tab lists at most this many big items. */
export const MAX_BIG_ITEMS = 8;

const longestSide = (item: ItemMeasure) =>
  Math.max(item.width.value_m, item.depth.value_m, item.height.value_m);
const volume = (item: ItemMeasure) => item.width.value_m * item.depth.value_m * item.height.value_m;

export function measuresFromTwin(twin: SpaceTwin): RoomMeasures {
  const { shell } = twin;
  const walls = shell.walls.map((wall, index) => ({
    id: wall.id,
    number: index + 1,
    length: wall.length,
  }));
  const numberOf = new Map(walls.map((wall) => [wall.id, wall.number]));
  return {
    areaM2: floorArea(shell.floor_polygon),
    walls,
    ceiling: shell.ceiling_height,
    openings: shell.openings.map((opening) => ({
      id: opening.id,
      kind: opening.kind,
      wallNumber: numberOf.get(opening.wall_id) ?? null,
      width: opening.width,
      height: opening.height,
    })),
    bigItems: twin.objects
      .map((object) => ({
        id: object.id,
        label: object.label,
        width: object.box.width,
        depth: object.box.depth,
        height: object.box.height,
      }))
      .filter((item) => longestSide(item) >= BIG_ITEM_FROM_M)
      .sort((a, b) => volume(b) - volume(a))
      .slice(0, MAX_BIG_ITEMS),
  };
}

/** Walls are named by letter, going round the room: A, B, C. Past Z they are numbered. */
export function wallName(number: number): string {
  return number >= 1 && number <= 26 ? String.fromCharCode(64 + number) : String(number);
}

/** A value whose error band is wider than this is marked "approx." where it shows. */
export const APPROX_ABOVE_M = 0.05;

/** Of the dimensions on one line (a door's width and height), the one with the widest band. */
export function leastCertain(...dimensions: [Dimension, ...Dimension[]]): Dimension {
  return dimensions.reduce((a, b) => (b.error_band_m > a.error_band_m ? b : a));
}

export function isApprox(dimension: Dimension): boolean {
  // A small allowance, so a band of exactly 5 cm stored as 0.05000001 is not marked.
  return dimension.error_band_m > APPROX_ABOVE_M + 1e-6;
}
