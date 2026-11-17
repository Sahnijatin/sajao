// Capture guidance during the AR scan: short hints that make the capture
// better for the server, which does the understanding. Pure, so each rule is
// tested without a phone.
//
// - Doorway: walking through a wall the scan has mapped means a new space.
//   One space per scan: the scan asks you to finish this space first, and
//   counts nothing on the other side until you come back.
// - Step back: a large object fills the frame edge to edge, so part of it
//   is cut off.
// - Walk around it: a large object has been seen from one side only.
import type { LabelKind, ShownLabel } from "./labels";
import { type Wall, wallProgress } from "./surface-coverage";

export interface Point2 {
  x: number;
  z: number;
}

/** Further than this from a wall, in metres, you are clearly on one side of it. */
export const SIDE_MARGIN_M = 0.3;
/** Only walls mapped at least this much count as the room's walls. */
export const MAPPED_WALL = 0.25;
/** Crossing a wall this far beyond its mapped ends is going round it, not through it. */
const WALL_END_MARGIN_M = 0.5;

/** For each mapped wall: the side it was mapped from (the room), and whether the camera is now clearly beyond it. */
export interface DoorwayState {
  home: Readonly<Record<string, 1 | -1>>;
  beyond: Readonly<Record<string, boolean>>;
  /** Through a wall into another space. */
  outside: boolean;
}

export const NO_DOORWAY: DoorwayState = { home: {}, beyond: {}, outside: false };

const wallKey = (wall: Wall) => `${Math.round(wall.normalYaw)}:${wall.offset.toFixed(2)}`;

/** Position along a wall's face, matching `surface-coverage`. */
function along(wall: Wall, p: Point2): number {
  const r = (wall.normalYaw * Math.PI) / 180;
  return p.x * Math.cos(r) - p.z * Math.sin(r);
}

/** Signed distance from a wall's plane, in metres. */
function signedDistance(wall: Wall, p: Point2): number {
  const r = (wall.normalYaw * Math.PI) / 180;
  return p.x * Math.sin(r) + p.z * Math.cos(r) - wall.offset;
}

/**
 * Track which side of each mapped wall the camera is on. A wall is mapped
 * from inside the room, so the side the camera is on when it first counts
 * is home. Being clearly on the other side, within the wall's mapped width,
 * means you walked through a doorway; coming back clears it. Near a wall
 * the last clear reading stands.
 */
export function updateDoorway(
  state: DoorwayState,
  walls: readonly Wall[],
  camera: Point2,
  cellMetres: number,
): DoorwayState {
  const home: Record<string, 1 | -1> = { ...state.home };
  const beyond: Record<string, boolean> = { ...state.beyond };
  for (const wall of walls) {
    if (wallProgress(wall) < MAPPED_WALL) continue;
    const key = wallKey(wall);
    const d = signedDistance(wall, camera);
    if (Math.abs(d) < SIDE_MARGIN_M) continue;
    const side: 1 | -1 = d > 0 ? 1 : -1;
    const homeSide = home[key] ?? side;
    home[key] = homeSide;
    const a = along(wall, camera);
    const within =
      a >= wall.minAlong * cellMetres - WALL_END_MARGIN_M &&
      a <= (wall.maxAlong + 1) * cellMetres + WALL_END_MARGIN_M;
    // Past the wall's ends you walked round it, not through it.
    beyond[key] = within && side !== homeSide;
  }
  return { home, beyond, outside: Object.values(beyond).some(Boolean) };
}

/** A detection's box in the upright camera image, 0 to 1. */
export interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Within this of an image edge counts as touching it. */
const EDGE = 0.03;

/** A large object touching both side edges, or top and bottom, or filling most of the frame, is cut off. */
export function isCutOff(box: Box): boolean {
  const left = box.x <= EDGE;
  const right = box.x + box.width >= 1 - EDGE;
  const top = box.y <= EDGE;
  const bottom = box.y + box.height >= 1 - EDGE;
  return (left && right) || (top && bottom) || box.width * box.height >= 0.8;
}

/** Directions an object has been seen from, in 30 degree bins around it. */
export type ViewBins = Readonly<Record<string, readonly number[]>>;
const VIEW_BIN_DEGREES = 30;
/** Seen from a spread narrower than this, an object needs walking around. */
export const WALK_AROUND_DEGREES = 60;
/** Closer than this, the direction to the object jumps about. */
const MIN_VIEW_DISTANCE_M = 0.5;

/** Record the direction each tracked object is seen from, from the camera's position. */
export function updateViews(
  views: ViewBins,
  objects: readonly ShownLabel[],
  camera: Point2,
): ViewBins {
  const next: Record<string, readonly number[]> = { ...views };
  for (const object of objects) {
    const dx = camera.x - object.x;
    const dz = camera.z - object.z;
    if (Math.hypot(dx, dz) < MIN_VIEW_DISTANCE_M) continue;
    const degrees = ((Math.atan2(dx, dz) * 180) / Math.PI + 360) % 360;
    const bin = Math.floor(degrees / VIEW_BIN_DEGREES);
    const seen = next[object.id] ?? [];
    if (!seen.includes(bin)) next[object.id] = [...seen, bin];
  }
  return next;
}

/** The first tracked large object seen only from one side, once the room is reasonably covered. */
export function walkAroundTarget(
  objects: readonly ShownLabel[],
  views: ViewBins,
  coverage: number,
): LabelKind | null {
  if (coverage < 0.5) return null;
  for (const object of objects) {
    const bins = views[object.id]?.length ?? 0;
    if (bins * VIEW_BIN_DEGREES < WALK_AROUND_DEGREES) return object.kind;
  }
  return null;
}

export type Hint =
  | { id: "doorway" }
  | { id: "slowDown" }
  | { id: "stepBack" }
  | { id: "walkAround"; kind: LabelKind }
  | { id: "walk" }
  | { id: "coverMore" }
  | { id: "complete" }
  // The coverage meter's next step.
  | { id: "walkWalls" }
  | { id: "keepGoing" }
  | { id: "standMiddle" }
  | { id: "tiltWall" }
  | { id: "oneMoreSpot" }
  | { id: "meterDone" }
  | null;

/** One hint at a time: a doorway first, then step back, walk around, and last cover a bit more. */
export function currentHint(input: {
  outside: boolean;
  stepBack: boolean;
  walkAround: LabelKind | null;
  /** Done is on but the space is not fully covered yet. */
  coverMore?: boolean;
}): Hint {
  if (input.outside) return { id: "doorway" };
  if (input.stepBack) return { id: "stepBack" };
  if (input.walkAround) return { id: "walkAround", kind: input.walkAround };
  if (input.coverMore) return { id: "coverMore" };
  return null;
}

/**
 * The simple scan's hint, from camera motion alone: slow down, step back,
 * walk, then Done. A large object seen from one side still asks to be walked
 * around when the phone happens to have labels; nothing here needs them.
 */
export function simpleHint(input: {
  slowDown: boolean;
  stepBack: boolean;
  walkAround: LabelKind | null;
  /** Enough turning, too little walking. */
  walk: boolean;
  /** Done is on. */
  doneReady: boolean;
  /** Everything the ring counts is covered. */
  complete: boolean;
}): Hint {
  if (input.slowDown) return { id: "slowDown" };
  if (input.stepBack) return { id: "stepBack" };
  if (input.walkAround) return { id: "walkAround", kind: input.walkAround };
  if (input.complete) return { id: "complete" };
  if (input.walk) return { id: "walk" };
  if (input.doneReady) return { id: "coverMore" };
  return null;
}
