// What the review screen says about a scan, worked out from what the scan
// session already holds when Done is tapped: how much is covered, what is
// missing, and a rough size when two pairs of facing walls were seen. Pure.
// Nothing here is stored or sent: the server measures the room properly.
import { floorProgress, type Wall, wallProgress } from "@/capture/ar/surface-coverage";
import { mappedSectors, SECTOR_COUNT, SECTOR_DEGREES } from "@/capture/coverage";
import { type MeterMissing, meterMissing } from "@/capture/coverage-meter";
import { moveShare } from "@/capture/motion-coverage";
import { isMeter, isSimple, mappedShare, type ScanState } from "@/capture/scan-session";

/** A side of the room, relative to the way you are facing now. */
export type Side = "ahead" | "left" | "behind" | "right";

export type MissingArea = "floor" | "walls" | "walk" | "middle" | Side;

/**
 * What the coverage meter still wanted, in the review's words: the walk
 * along the walls, the turn in the middle of the room, the walls not yet
 * tilted through from ceiling to floor.
 */
export function missingFromMeter(missing: MeterMissing): MissingArea[] {
  const areas: MissingArea[] = [];
  if (missing.loopBearings.length > 0 || missing.loopPathM > 0) areas.push("walk");
  if (missing.sweepsNeeded > 0) areas.push("middle");
  if (missing.wallTilts > 0) areas.push("walls");
  return areas;
}

export interface RoughSize {
  /** The longer side first, in metres, rounded to 10 cm. */
  longM: number;
  shortM: number;
}

export interface ScanSummary {
  /** 0 to 1. */
  share: number;
  /** In the order to fix them; empty when nothing is missing. */
  missing: MissingArea[];
  /** null when the scan did not see two pairs of facing walls. */
  size: RoughSize | null;
}

/** A wall or the floor counts as covered from this share of its cells. */
export const COVERED_SHARE = 0.6;
/** A side counts as seen when at least half of its directions are mapped. */
export const SIDE_SEEN_SHARE = 0.5;
/** Walls needed for a room to count as covered, as in the scan's own meter. */
const WALLS_NEEDED = 3;
/** Facing walls point opposite ways to within this many degrees. */
const FACING_TOLERANCE_DEGREES = 25;
/** Rooms are between these sizes; anything else is not a pair of room walls. */
const MIN_ROOM_M = 1;
const MAX_ROOM_M = 15;

const SIDES: readonly Side[] = ["ahead", "left", "behind", "right"];
const SECTORS_PER_SIDE = SECTOR_COUNT / SIDES.length;

/**
 * Sides with too few mapped directions, named from where you face now.
 * Directions are counted from the scan's start; positive yaw is a turn to the
 * left. `facingYaw` is where the phone points when the review opens.
 */
export function missingSides(mapped: readonly boolean[], facingYaw = 0): Side[] {
  const quarterTurns = Math.round(facingYaw / (SECTORS_PER_SIDE * SECTOR_DEGREES));
  const fromHere = (side: number) =>
    SIDES[(((side - quarterTurns) % SIDES.length) + SIDES.length) % SIDES.length] as Side;
  const missing = SIDES.map((_, side) => side).filter((side) => {
    // A side is centred on its direction: "ahead" runs from 45 degrees right to 45 left.
    const first = side * SECTORS_PER_SIDE - SECTORS_PER_SIDE / 2;
    let seen = 0;
    for (let offset = 0; offset < SECTORS_PER_SIDE; offset += 1) {
      const sector = (((first + offset) % SECTOR_COUNT) + SECTOR_COUNT) % SECTOR_COUNT;
      if (mapped[sector]) seen += 1;
    }
    return seen / SECTORS_PER_SIDE < SIDE_SEEN_SHARE;
  });
  // In front first, then left, behind and right.
  return missing.map(fromHere).sort((a, b) => SIDES.indexOf(a) - SIDES.indexOf(b));
}

const angleBetween = (a: number, b: number) => Math.abs(((((a - b) % 360) + 540) % 360) - 180);

/**
 * A rough room size from two pairs of facing walls. Each wall's offset is its
 * distance from the scan's origin along its own normal, so two walls that
 * face each other are |offset + offset| apart.
 */
export function roughSize(walls: readonly Wall[]): RoughSize | null {
  const spans: { yaw: number; metres: number; weight: number }[] = [];
  walls.forEach((wall, index) => {
    for (const other of walls.slice(index + 1)) {
      if (angleBetween(wall.normalYaw, other.normalYaw + 180) > FACING_TOLERANCE_DEGREES) continue;
      const metres = Math.abs(wall.offset + other.offset);
      if (metres < MIN_ROOM_M || metres > MAX_ROOM_M) continue;
      spans.push({
        yaw: wall.normalYaw,
        metres,
        weight: wallProgress(wall) + wallProgress(other),
      });
    }
  });
  // The best-seen pair, then the best-seen pair at right angles to it.
  spans.sort((a, b) => b.weight - a.weight);
  const first = spans[0];
  if (!first) return null;
  const second = spans.find((span) => {
    const turn = angleBetween(span.yaw, first.yaw);
    return Math.abs(turn - 90) <= FACING_TOLERANCE_DEGREES;
  });
  if (!second) return null;
  const round = (metres: number) => Math.round(metres * 10) / 10;
  const [longM, shortM] = [round(first.metres), round(second.metres)].sort((a, b) => b - a) as [
    number,
    number,
  ];
  return { longM, shortM };
}

export function scanSummary(state: ScanState): ScanSummary {
  const share = Math.min(1, Math.max(0, mappedShare(state)));
  const size = roughSize(state.surfaces.walls);
  let missing: MissingArea[];
  if (isMeter(state)) {
    // Where the meter runs it decides Done, so it also says what is missing.
    missing = missingFromMeter(meterMissing(state.meter));
  } else if (isSimple(state)) {
    missing = missingSides(mappedSectors(state.motionCoverage.headings), state.pose.yaw);
    if (moveShare(state.motionCoverage) < SIDE_SEEN_SHARE) missing.push("walk");
  } else if (state.surfacesSeen) {
    const covered = state.surfaces.walls.filter((wall) => wallProgress(wall) >= COVERED_SHARE);
    missing = [];
    if (covered.length < WALLS_NEEDED) missing.push("walls");
    if (floorProgress(state.surfaces) < COVERED_SHARE) missing.push("floor");
  } else {
    missing = state.hasGyro ? missingSides(mappedSectors(state.coverage), state.pose.yaw) : [];
  }
  return { share, missing, size };
}

/** Degrees covered by one side, for tests and drawing. */
export const SIDE_DEGREES = SECTORS_PER_SIDE * SECTOR_DEGREES;
