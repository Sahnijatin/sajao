// How much of the space has been seen, from where the phone pointed (pose)
// and whether the camera saw real detail there (feature points). The circle
// around the person scanning is split into sectors; a sector is mapped once
// a few steady frames with enough feature points were taken facing it.
//
// This is guidance for the person scanning, not a measurement: it never
// sets a dimension.

export const SECTOR_DEGREES = 15;
export const SECTOR_COUNT = 360 / SECTOR_DEGREES;
/** Half the width the preview shows across, so facing a sector also sees its neighbours. */
export const HALF_VIEW_DEGREES = 15;
/** A frame with fewer feature points than this saw too little detail to count. */
export const MIN_FEATURES = 8;
/** Frames needed facing a sector before it counts as mapped. */
export const HITS_TO_MAP = 2;
/** Turning through this much counts as a full sweep: what you see standing in a doorway. */
export const TARGET_DEGREES = 180;
/** Done is offered once this much is mapped: a corner of a room is about 90 degrees. */
export const DONE_DEGREES = 90;
/** Without a gyroscope, frames rich in detail stand in for pose. */
export const FALLBACK_TARGET_FRAMES = 60;
export const FALLBACK_DONE_FRAMES = 30;

export interface CoverageState {
  /** Feature-rich frames seen facing each sector. */
  hits: readonly number[];
  /** Feature-rich frames in total, used when there is no gyroscope. */
  richFrames: number;
}

export const EMPTY_COVERAGE: CoverageState = {
  hits: Array.from({ length: SECTOR_COUNT }, () => 0),
  richFrames: 0,
};

export function sectorOf(yawDegrees: number): number {
  const turned = ((yawDegrees % 360) + 360) % 360;
  return Math.floor(turned / SECTOR_DEGREES) % SECTOR_COUNT;
}

/** Record one usable frame taken facing `yawDegrees` with `featureCount` points. */
export function addFrame(
  state: CoverageState,
  yawDegrees: number,
  featureCount: number,
): CoverageState {
  if (featureCount < MIN_FEATURES) return state;
  const hits = [...state.hits];
  const reach = Math.floor(HALF_VIEW_DEGREES / SECTOR_DEGREES);
  const centre = sectorOf(yawDegrees);
  for (let offset = -reach; offset <= reach; offset += 1) {
    const sector = (centre + offset + SECTOR_COUNT) % SECTOR_COUNT;
    hits[sector] = (hits[sector] ?? 0) + 1;
  }
  return { hits, richFrames: state.richFrames + 1 };
}

export function mappedSectors(state: CoverageState): boolean[] {
  return state.hits.map((count) => count >= HITS_TO_MAP);
}

export function mappedDegrees(state: CoverageState): number {
  return mappedSectors(state).filter(Boolean).length * SECTOR_DEGREES;
}

/** 0 to 1: share of a full sweep mapped so far. */
export function coverageFraction(state: CoverageState, hasGyro: boolean): number {
  const fraction = hasGyro
    ? mappedDegrees(state) / TARGET_DEGREES
    : state.richFrames / FALLBACK_TARGET_FRAMES;
  return Math.min(1, fraction);
}

export function enoughCoverage(state: CoverageState, hasGyro: boolean): boolean {
  return hasGyro ? mappedDegrees(state) >= DONE_DEGREES : state.richFrames >= FALLBACK_DONE_FRAMES;
}

/** Drawing angle (0 is right, clockwise) for a direction `delta` degrees left of straight ahead. */
export function screenAngle(delta: number): number {
  return -90 - delta;
}
