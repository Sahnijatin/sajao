// Everything the Space Profile card shows and every change it can make, as
// pure functions over the SpaceProfile contract. The card confirms what was
// detected; it never draws the space from scratch.
import type { Dimension, SpaceProfile } from "@sajao/schemas";

type Point = { x_m: number; y_m: number };
export type SpaceType = SpaceProfile["space_type"];
export type ItemAction = SpaceProfile["existing_items"][number]["action"];

export const SPACE_TYPES: readonly SpaceType[] = ["living_room", "bedroom", "balcony", "other"];

// --- What we found ---------------------------------------------------------------

/** Floor area in square metres (shoelace formula). */
export function floorArea(polygon: readonly Point[]): number {
  let twice = 0;
  for (let i = 0; i < polygon.length; i += 1) {
    const a = polygon[i] as Point;
    const b = polygon[(i + 1) % polygon.length] as Point;
    twice += a.x_m * b.y_m - b.x_m * a.y_m;
  }
  return Math.abs(twice) / 2;
}

export type LightTime = "morning" | "midday" | "evening" | "soft";

/**
 * When the space gets direct light, from the compass bearing the main
 * window faces: east is morning, south is midday, west is evening.
 */
export function lightTime(profile: SpaceProfile): LightTime | null {
  const direction = profile.light?.main_direction_deg;
  if (direction === undefined) return null;
  const bearing = (direction + profile.direction.north_deg) % 360;
  if (bearing >= 45 && bearing < 135) return "morning";
  if (bearing >= 135 && bearing < 225) return "midday";
  if (bearing >= 225 && bearing < 315) return "evening";
  return "soft";
}

export interface Found {
  spaceType: SpaceType;
  extent: SpaceProfile["extent"];
  areaM2: number;
  windows: number;
  doors: number;
  light: LightTime | null;
  /** The honesty badge: verified, or estimated with the widest error band shown. */
  badge: { kind: "verified" } | { kind: "estimated"; errorBandM: number };
}

function keyDimensions(profile: SpaceProfile): Dimension[] {
  return [...profile.walls.map((wall) => wall.length), profile.ceiling_height];
}

export function describeSpace(profile: SpaceProfile): Found {
  const widest = Math.max(...keyDimensions(profile).map((dimension) => dimension.error_band_m));
  return {
    spaceType: profile.space_type,
    extent: profile.extent,
    areaM2: floorArea(profile.floor_polygon),
    windows: profile.openings.filter((opening) => opening.kind === "window").length,
    doors: profile.openings.filter((opening) => opening.kind === "door").length,
    light: lightTime(profile),
    badge:
      profile.verification === "verified"
        ? { kind: "verified" }
        : { kind: "estimated", errorBandM: widest },
  };
}

// --- Changes the user can make -------------------------------------------------------

/** "Change": the user corrects what the scan detected. */
export function setSpaceType(profile: SpaceProfile, spaceType: SpaceType): SpaceProfile {
  return { ...profile, space_type: spaceType, space_type_source: "user" };
}

/** "What should we redo?": all of it, or just a part the user drew around. */
export function setRedo(
  profile: SpaceProfile,
  redo: { scope: "all" } | { scope: "part"; polygon: Point[] },
): SpaceProfile {
  if (redo.scope === "part" && redo.polygon.length < 3) {
    throw new RangeError("A part to redo needs at least three points");
  }
  // The length check above is what the tuple type in the contract asks for.
  return { ...profile, redo: redo as SpaceProfile["redo"] };
}

const NEXT_ACTION: Record<ItemAction, ItemAction> = {
  keep: "replace",
  replace: "remove",
  remove: "keep",
};

/** Tap an existing item to move it through keep, replace, remove. */
export function cycleItemAction(profile: SpaceProfile, itemId: string): SpaceProfile {
  return {
    ...profile,
    existing_items: profile.existing_items.map((item) =>
      item.id === itemId ? { ...item, action: NEXT_ACTION[item.action] } : item,
    ),
  };
}

/** Drag a door or window along its wall. It cannot leave the wall. */
export function moveOpening(
  profile: SpaceProfile,
  openingId: string,
  offsetM: number,
): SpaceProfile {
  return {
    ...profile,
    openings: profile.openings.map((opening) => {
      if (opening.id !== openingId) return opening;
      const wall = profile.walls.find((candidate) => candidate.id === opening.wall_id);
      const room = wall ? Math.max(0, wall.length.value_m - opening.width.value_m) : 0;
      return {
        ...opening,
        offset: {
          ...opening.offset,
          value_m: Math.min(room, Math.max(0, offsetM)),
          // The user placed it by eye: confirmed, but still not measured.
          source: "user_confirmed" as const,
        },
      };
    }),
  };
}

/** Error band of a tape reading: about a centimetre. */
export const TAPE_ERROR_BAND_M = 0.01;

const scaleDimension = (dimension: Dimension, factor: number): Dimension =>
  dimension.source === "measured"
    ? dimension
    : {
        ...dimension,
        value_m: dimension.value_m * factor,
        error_band_m: dimension.error_band_m * factor,
      };

const scalePoint = (point: Point, factor: number): Point => ({
  x_m: point.x_m * factor,
  y_m: point.y_m * factor,
});

/**
 * A tape value for one wall snaps in and re-fits the whole space: that wall
 * becomes measured, and every estimated length is rescaled by the same
 * factor, since scale is what a photo-only estimate gets wrong.
 *
 * This is the instant preview on the phone. It rescales error bands but
 * does not tighten them; the server pipeline re-fits with all its scale
 * anchors and is the source of truth. Heights are not rescaled by a floor
 * measurement.
 */
export function applyTapeToWall(
  profile: SpaceProfile,
  wallId: string,
  measuredM: number,
): SpaceProfile {
  const wall = profile.walls.find((candidate) => candidate.id === wallId);
  if (!wall) throw new RangeError(`Unknown wall ${wallId}`);
  if (!(measuredM > 0)) throw new RangeError("A tape value must be greater than zero");
  const factor = wall.length.value_m > 0 ? measuredM / wall.length.value_m : 1;

  const walls = profile.walls.map((candidate) => ({
    ...candidate,
    start: scalePoint(candidate.start, factor),
    end: scalePoint(candidate.end, factor),
    length:
      candidate.id === wallId
        ? { value_m: measuredM, source: "measured" as const, error_band_m: TAPE_ERROR_BAND_M }
        : scaleDimension(candidate.length, factor),
  }));
  const fitted: SpaceProfile = {
    ...profile,
    // Mapping keeps the number of walls and points, which the contract's tuple types need.
    walls: walls as SpaceProfile["walls"],
    floor_polygon: profile.floor_polygon.map((point) =>
      scalePoint(point, factor),
    ) as SpaceProfile["floor_polygon"],
    openings: profile.openings.map((opening) => ({
      ...opening,
      offset: scaleDimension(opening.offset, factor),
      width: scaleDimension(opening.width, factor),
    })),
    fixtures: profile.fixtures.map((fixture) => ({
      ...fixture,
      offset: scaleDimension(fixture.offset, factor),
    })),
    existing_items: profile.existing_items.map((item) => ({
      ...item,
      center: scalePoint(item.center, factor),
      width: scaleDimension(item.width, factor),
      depth: scaleDimension(item.depth, factor),
    })),
    ...(profile.redo.polygon
      ? {
          redo: {
            ...profile.redo,
            polygon: profile.redo.polygon.map((point) => scalePoint(point, factor)),
          } as SpaceProfile["redo"],
        }
      : {}),
  };
  return { ...fitted, verification: isVerified(fitted) ? "verified" : "estimated" };
}

/** A tape value for the ceiling height. */
export function applyTapeToCeiling(profile: SpaceProfile, measuredM: number): SpaceProfile {
  if (!(measuredM > 0)) throw new RangeError("A tape value must be greater than zero");
  const fitted: SpaceProfile = {
    ...profile,
    ceiling_height: { value_m: measuredM, source: "measured", error_band_m: TAPE_ERROR_BAND_M },
  };
  return { ...fitted, verification: isVerified(fitted) ? "verified" : "estimated" };
}

/** Verified only when tape values cover every wall and the ceiling height. */
export function isVerified(profile: SpaceProfile): boolean {
  return keyDimensions(profile).every((dimension) => dimension.source === "measured");
}

// --- Drawing the plan ---------------------------------------------------------------

export interface PlanDrawing {
  outline: { x: number; y: number }[];
  openings: {
    id: string;
    kind: "door" | "window";
    from: { x: number; y: number };
    to: { x: number; y: number };
  }[];
  items: {
    id: string;
    x: number;
    y: number;
    width: number;
    depth: number;
    rotationDeg: number;
    action: ItemAction;
  }[];
  /** Pixels per metre. */
  scale: number;
}

/** Fit the floor plan into a box, in pixels, keeping its shape. */
export function planDrawing(
  profile: SpaceProfile,
  box: { width: number; height: number; padding: number },
): PlanDrawing {
  const xs = profile.floor_polygon.map((point) => point.x_m);
  const ys = profile.floor_polygon.map((point) => point.y_m);
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
  const place = (point: Point) => ({
    x: offsetX + (point.x_m - minX) * scale,
    // Screen y grows downward; plan y grows upward.
    y: box.height - offsetY - (point.y_m - minY) * scale,
  });

  const openings = profile.openings.flatMap((opening) => {
    const wall = profile.walls.find((candidate) => candidate.id === opening.wall_id);
    if (!wall || wall.length.value_m <= 0) return [];
    const along = (distance: number): Point => {
      const t = distance / wall.length.value_m;
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

  return {
    outline: profile.floor_polygon.map(place),
    openings,
    items: profile.existing_items.map((item) => ({
      id: item.id,
      ...place(item.center),
      width: item.width.value_m * scale,
      depth: item.depth.value_m * scale,
      rotationDeg: item.rotation_deg,
      action: item.action,
    })),
    scale,
  };
}
