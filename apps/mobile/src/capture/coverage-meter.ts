// The coverage meter: whether the scan has seen the space from enough places.
// The server's result is sharp where the phone stood and weak away from it,
// so Done waits for two things read from AR poses alone:
//
// - a loop: one walk around the space near the walls;
// - sweeps: a slow full turn from the middle, and from one more spot at
//   least a metre away (one sweep is enough in a small space);
// - wall tilts: one slow tilt up to the ceiling and down to the floor on
//   each wall. A phone cannot hold floor and ceiling in one picture, and a
//   wall only counts as a wall when it was seen from bottom to top. The
//   tilt up and the tilt down need not be in the same picture: each quarter
//   turn of the room needs both at some point in the scan.
//
// It reads positions and headings only. No model, nothing sent anywhere, and
// it never sets a dimension. Pure: samples in, state out, so every rule is
// tested without a phone. Spec: docs/06-room-capture.md, "Coverage meter".
import type { Point2 } from "./ar/guidance";
import { MAX_STEP_M, MIN_STEP_M, SAMPLE_INTERVAL_MS } from "./motion-coverage";

export const SECTORS = 12;
const SECTOR_DEGREES = 360 / SECTORS;
/** Sectors a loop or a sweep needs. */
export const SECTORS_NEEDED = 10;
/** The loop also needs this much walking, metres. */
export const LOOP_PATH_M = 6;
/** A loop position counts in its sector when at least this share of the median distance from the centre. */
export const LOOP_RADIUS_SHARE = 0.6;
/** Samples within this of a spot belong to its sweep, metres. */
export const SPOT_RADIUS_M = 0.4;
/** Sweeps that count are at least this far apart, metres. */
export const SWEEP_SPACING_M = 1;
/** ...and at least this far inside the loop path, metres, where the space allows it. */
export const INSIDE_LOOP_M = 0.8;
/** A space narrower than this needs one sweep, and its sweep need not be far inside the loop. */
export const SMALL_SPACE_M = 2.5;
/** A tilt up or down is at least this far from level, degrees. */
export const TILT_DEGREES = 20;
/** The room is four quarter turns; each needs a tilt up and a tilt down. */
export const QUARTERS = 4;
/** How much of the second half of the ring the wall tilts are. */
const TILT_SHARE = 0.4;
/** Accepted samples the scan needs before Done (about 5 s). */
export const MIN_SAMPLES = 50;
/** "Finish anyway" is offered after this long without progress. */
export const FINISH_ANYWAY_AFTER_MS = 60_000;
/** Positions closer together than this are one position, to bound what is stored. */
const POSITION_SPACING_M = 0.1;
const MAX_POSITIONS = 4000;
/** Floor cells drawn on the map, metres. */
export const MAP_CELL_M = 0.5;

/** One accepted pose: the gates (tracking, turn rate, steady, sharp) were already passed. */
export interface MeterSample {
  position: Point2;
  /** Degrees. */
  yaw: number;
  /** Degrees above level; negative looks down. */
  pitch: number;
  atMs: number;
}

interface Spot {
  centre: Point2;
  /** Samples per heading sector. */
  headings: readonly number[];
  samples: number;
}

export interface MeterState {
  /** Positions walked, thinned to one per 10 cm. */
  positions: readonly Point2[];
  pathM: number;
  lastPosition: Point2 | null;
  spots: readonly Spot[];
  /** Per heading sector: whether the phone has looked up and down that way. */
  looks: readonly { up: boolean; down: boolean }[];
  samples: number;
  lastSampleMs: number | null;
  /** The ring never goes backwards: the best each part has reached. */
  bestLoop: number;
  bestSweeps: number;
  /** When either part last moved forward, for "Finish anyway". */
  progressMs: number | null;
}

export const EMPTY_METER: MeterState = {
  positions: [],
  pathM: 0,
  lastPosition: null,
  spots: [],
  looks: Array.from({ length: SECTORS }, () => ({ up: false, down: false })),
  samples: 0,
  lastSampleMs: null,
  bestLoop: 0,
  bestSweeps: 0,
  progressMs: null,
};

const distance = (a: Point2, b: Point2) => Math.hypot(a.x - b.x, a.z - b.z);
const sectorOf = (degrees: number) =>
  Math.floor((((degrees % 360) + 360) % 360) / SECTOR_DEGREES) % SECTORS;
const median = (values: number[]) => {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted.length === 0 ? 0 : (sorted[Math.floor(sorted.length / 2)] ?? 0);
};

/** The middle of everything walked so far. */
export function centreOf(positions: readonly Point2[]): Point2 | null {
  if (positions.length === 0) return null;
  return {
    x: positions.reduce((sum, p) => sum + p.x, 0) / positions.length,
    z: positions.reduce((sum, p) => sum + p.z, 0) / positions.length,
  };
}

export interface Loop {
  /** Which of the 12 bearing sectors around the centre have been walked. */
  sectors: boolean[];
  count: number;
  centre: Point2 | null;
  /** Median distance of the walk from its centre: about how far the walls are. */
  radiusM: number;
  /** How wide the walked space is. */
  acrossM: number;
  complete: boolean;
}

/**
 * The loop, recounted from the stored positions because its centre moves as
 * you walk. Standing in the middle and turning fills nothing: a position
 * counts only when it is out near the path, not near the centre.
 */
export function loopOf(state: MeterState): Loop {
  const centre = centreOf(state.positions);
  const sectors = Array.from({ length: SECTORS }, () => false);
  if (!centre) return { sectors, count: 0, centre, radiusM: 0, acrossM: 0, complete: false };
  const distances = state.positions.map((p) => distance(p, centre));
  const radiusM = median(distances);
  state.positions.forEach((p, i) => {
    const d = distances[i] ?? 0;
    // Under 30 cm from the centre there is no bearing worth the name.
    if (d < 0.3 || d < LOOP_RADIUS_SHARE * radiusM) return;
    const bearing = (Math.atan2(p.x - centre.x, p.z - centre.z) * 180) / Math.PI;
    sectors[sectorOf(bearing)] = true;
  });
  const count = sectors.filter(Boolean).length;
  return {
    sectors,
    count,
    centre,
    radiusM,
    acrossM: 2 * Math.max(0, ...distances),
    complete: count >= SECTORS_NEEDED && state.pathM >= LOOP_PATH_M,
  };
}

export interface Sweep {
  centre: Point2;
  sectors: boolean[];
  count: number;
  /** Turned through enough of the circle. */
  complete: boolean;
  /** Complete, far enough inside the loop, and far enough from the other counted sweeps. */
  counted: boolean;
}

export interface Sweeps {
  all: Sweep[];
  /** Sweeps that count toward Done. */
  counted: number;
  needed: number;
  complete: boolean;
}

function sweepOf(spot: Spot): Sweep {
  const sectors = spot.headings.map((hits) => hits > 0);
  const count = sectors.filter(Boolean).length;
  return { centre: spot.centre, sectors, count, complete: count >= SECTORS_NEEDED, counted: false };
}

export interface WallTilts {
  /** For each quarter turn: tilted up and tilted down somewhere in it. */
  quarters: boolean[];
  count: number;
  complete: boolean;
}

/** Which quarter turns of the room have been tilted through, top and bottom. */
export function tiltsOf(state: MeterState): WallTilts {
  const perQuarter = SECTORS / QUARTERS;
  const quarters = Array.from({ length: QUARTERS }, (_, quarter) => {
    const looks = state.looks.slice(quarter * perQuarter, (quarter + 1) * perQuarter);
    return looks.some((look) => look.up) && looks.some((look) => look.down);
  });
  const count = quarters.filter(Boolean).length;
  return { quarters, count, complete: count >= QUARTERS };
}

export function sweepsOf(state: MeterState, loop: Loop = loopOf(state)): Sweeps {
  const small = loop.acrossM < SMALL_SPACE_M;
  const needed = small ? 1 : 2;
  const path = loop.centre
    ? state.positions.filter(
        (p) => distance(p, loop.centre as Point2) >= LOOP_RADIUS_SHARE * loop.radiusM,
      )
    : [];
  const all = state.spots.map(sweepOf);
  const counted: Sweep[] = [];
  // Fullest first, so the best sweep of a cluster of near spots is the one counted.
  for (const sweep of [...all].sort((a, b) => b.count - a.count)) {
    if (!sweep.complete) continue;
    // In a space wide enough, a sweep from beside the wall is the loop again, not a view from the middle.
    const inside =
      small || path.length === 0 || path.every((p) => distance(p, sweep.centre) >= INSIDE_LOOP_M);
    const apart = counted.every((other) => distance(other.centre, sweep.centre) >= SWEEP_SPACING_M);
    if (inside && apart) {
      sweep.counted = true;
      counted.push(sweep);
    }
  }
  return { all, counted: counted.length, needed, complete: counted.length >= needed };
}

/** 0 to 1 for each part of the ring, as counted right now. */
function partsNow(state: MeterState): { loop: number; sweeps: number } {
  const loop = loopOf(state);
  const sweeps = sweepsOf(state, loop);
  // Walking only counts as far as the sectors do: pacing on one spot, or the
  // few centimetres a phone wanders while turning, is not a loop.
  const sectorShare = Math.min(1, loop.count / SECTORS_NEEDED);
  const pathShare = Math.min(1, state.pathM / LOOP_PATH_M);
  const loopShare = loop.complete ? 1 : 0.5 * sectorShare + 0.5 * Math.min(pathShare, sectorShare);
  // The sweep in hand shows as it fills, so the ring moves while you turn.
  const inHand = Math.max(
    0,
    ...sweeps.all.filter((s) => !s.counted).map((s) => Math.min(0.95, s.count / SECTORS_NEEDED)),
  );
  const turnShare = sweeps.complete ? 1 : Math.min(1, (sweeps.counted + inHand) / sweeps.needed);
  const tilts = tiltsOf(state);
  const sweepShare = (1 - TILT_SHARE) * turnShare + TILT_SHARE * (tilts.count / QUARTERS);
  return {
    loop: Math.min(loopShare, loop.complete ? 1 : 0.99),
    sweeps: sweeps.complete && tilts.complete ? 1 : Math.min(0.99, sweepShare),
  };
}

/** Fold one accepted pose in. Pure: returns a new state. */
export function addMeterSample(state: MeterState, sample: MeterSample): MeterState {
  if (
    state.lastSampleMs !== null &&
    sample.atMs - state.lastSampleMs >= 0 &&
    sample.atMs - state.lastSampleMs < SAMPLE_INTERVAL_MS
  ) {
    return state;
  }
  let { pathM, lastPosition } = state;
  let positions = state.positions;
  const step = lastPosition ? distance(sample.position, lastPosition) : Infinity;
  if (step >= MIN_STEP_M) {
    // A jump is tracking finding itself again, not a step.
    if (step <= MAX_STEP_M) pathM += step;
    lastPosition = sample.position;
  }
  const lastKept = positions[positions.length - 1];
  if (
    positions.length < MAX_POSITIONS &&
    (!lastKept || distance(lastKept, sample.position) >= POSITION_SPACING_M)
  ) {
    positions = [...positions, sample.position];
  }

  const index = state.spots.findIndex((s) => distance(s.centre, sample.position) <= SPOT_RADIUS_M);
  const heading = sectorOf(sample.yaw);
  const up = sample.pitch >= TILT_DEGREES;
  const down = sample.pitch <= -TILT_DEGREES;
  const looks =
    up || down
      ? state.looks.map((look, i) =>
          i === heading ? { up: look.up || up, down: look.down || down } : look,
        )
      : state.looks;
  const spot: Spot =
    index >= 0
      ? (state.spots[index] as Spot)
      : {
          centre: sample.position,
          headings: Array.from({ length: SECTORS }, () => 0),
          samples: 0,
        };
  const updated: Spot = {
    centre: spot.centre,
    headings: spot.headings.map((hits, i) => (i === heading ? hits + 1 : hits)),
    samples: spot.samples + 1,
  };
  const spots =
    index >= 0 ? state.spots.map((s, i) => (i === index ? updated : s)) : [...state.spots, updated];

  const next: MeterState = {
    ...state,
    positions,
    pathM,
    lastPosition,
    spots,
    looks,
    samples: state.samples + 1,
    lastSampleMs: sample.atMs,
  };
  const now = partsNow(next);
  const bestLoop = Math.max(state.bestLoop, now.loop);
  const bestSweeps = Math.max(state.bestSweeps, now.sweeps);
  const moved = bestLoop > state.bestLoop + 1e-9 || bestSweeps > state.bestSweeps + 1e-9;
  return {
    ...next,
    bestLoop,
    bestSweeps,
    progressMs: moved || state.progressMs === null ? sample.atMs : state.progressMs,
  };
}

/** The ring's two parts, 0 to 1 each. They never go backwards. */
export function meterParts(state: MeterState): { loop: number; sweeps: number } {
  return { loop: state.bestLoop, sweeps: state.bestSweeps };
}

/** 0 to 1 for the whole ring: the loop is the first half, the sweeps the second. */
export function meterFraction(state: MeterState): number {
  return 0.5 * state.bestLoop + 0.5 * state.bestSweeps;
}

/** Every part is complete and the scan has its minimum of accepted samples. */
export function meterDone(state: MeterState): boolean {
  const loop = loopOf(state);
  return (
    loop.complete &&
    sweepsOf(state, loop).complete &&
    tiltsOf(state).complete &&
    state.samples >= MIN_SAMPLES
  );
}

/** Nothing has moved forward for a minute: the person may finish with what there is. */
export function canFinishAnyway(state: MeterState, nowMs: number): boolean {
  return (
    !meterDone(state) &&
    state.progressMs !== null &&
    state.samples >= MIN_SAMPLES &&
    nowMs - state.progressMs >= FINISH_ANYWAY_AFTER_MS
  );
}

export type MeterHint =
  "walkWalls" | "keepGoing" | "standMiddle" | "tiltWall" | "oneMoreSpot" | "meterDone";

/** What to do next, one thing at a time. */
export function meterHint(state: MeterState): MeterHint {
  const loop = loopOf(state);
  // Until part of the loop is walked, pacing or turning on one spot is not "keep going".
  if (!loop.complete) return loop.count < 2 ? "walkWalls" : "keepGoing";
  const sweeps = sweepsOf(state, loop);
  if (!sweeps.complete) return sweeps.counted === 0 ? "standMiddle" : "oneMoreSpot";
  // Everything is turned through; what is left is a wall not seen top to bottom.
  return tiltsOf(state).complete ? "meterDone" : "tiltWall";
}

/** What is still missing, for the review to name after "Finish anyway". */
export interface MeterMissing {
  /** Loop sectors not walked, as bearings from the centre in degrees (sector middles). */
  loopBearings: number[];
  /** Metres of walking the loop still needs. */
  loopPathM: number;
  sweepsNeeded: number;
  /** Quarter turns of the room not yet tilted through top and bottom. */
  wallTilts: number;
}

export function meterMissing(state: MeterState): MeterMissing {
  const loop = loopOf(state);
  const sweeps = sweepsOf(state, loop);
  return {
    loopBearings: loop.complete
      ? []
      : loop.sectors.flatMap((walked, i) => (walked ? [] : [(i + 0.5) * SECTOR_DEGREES])),
    loopPathM: loop.complete ? 0 : Math.max(0, LOOP_PATH_M - state.pathM),
    sweepsNeeded: Math.max(0, sweeps.needed - sweeps.counted),
    wallTilts: QUARTERS - tiltsOf(state).count,
  };
}

/**
 * Where the next sweep should be: the middle for the first, then the place
 * inside the loop furthest from the sweeps already counted. Null until the
 * loop is complete or once enough sweeps are.
 */
export function nextSweepSpot(state: MeterState): Point2 | null {
  const loop = loopOf(state);
  if (!loop.complete || !loop.centre) return null;
  const sweeps = sweepsOf(state, loop);
  if (sweeps.complete) return null;
  const done = sweeps.all.filter((s) => s.counted).map((s) => s.centre);
  if (done.length === 0) return loop.centre;
  let best: Point2 = loop.centre;
  let bestGap = -1;
  const reach = Math.max(0, loop.radiusM - INSIDE_LOOP_M);
  for (let dx = -reach; dx <= reach + 1e-9; dx += MAP_CELL_M) {
    for (let dz = -reach; dz <= reach + 1e-9; dz += MAP_CELL_M) {
      if (Math.hypot(dx, dz) > reach + 1e-9) continue;
      const candidate = { x: loop.centre.x + dx, z: loop.centre.z + dz };
      const gap = Math.min(...done.map((spot) => distance(spot, candidate)));
      if (gap > bestGap) {
        bestGap = gap;
        best = candidate;
      }
    }
  }
  return best;
}

/** Floor cells walked, for the map: "column,row" of 50 cm cells. */
export function walkedCells(state: MeterState): string[] {
  const cells = new Set<string>();
  for (const p of state.positions) {
    cells.add(`${Math.floor(p.x / MAP_CELL_M)},${Math.floor(p.z / MAP_CELL_M)}`);
  }
  return [...cells];
}
