// Live object labels for the AR scan. The on-device detector runs a few
// times a second; each detection is raycast into the AR scene natively and
// arrives here with a world position in metres. This tracker turns that
// noisy stream into one steady label per real object. A label is pinned only
// after three sightings that agree on where the object is; a sighting whose
// ray ends flat on a wall, a door or bare floor is dropped (a door is not a
// fridge); two labels never sit on the same object (class votes decide its
// name).
//
// The phone captures; the server understands. Live labels are decoration
// for the person scanning, not data: the authoritative object list comes
// from the server twin. So only large objects are tracked (capture guidance
// such as "walk around the sofa" needs them), and only a handful of
// confident labels are shown. Positions here never set a dimension.

export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

/**
 * Objects labelled during the scan, from the detector's COCO classes.
 * COCO has no wardrobe or almirah class; the server twin finds those.
 */
export const LABEL_KINDS = ["sofa", "bed", "table", "fridge", "tv", "chair", "microwave"] as const;

export type LabelKind = (typeof LABEL_KINDS)[number];

/** Large objects: capture guidance (step back, walk around it) works from these only. */
export const LARGE_KINDS: ReadonlySet<LabelKind> = new Set([
  "sofa",
  "bed",
  "table",
  "fridge",
  "tv",
]);

const FROM_COCO: Record<string, LabelKind> = {
  couch: "sofa",
  bed: "bed",
  "dining table": "table",
  refrigerator: "fridge",
  tv: "tv",
  chair: "chair",
  microwave: "microwave",
};

/** The label kind for a detector class, or null for classes we do not track (small objects, people). */
export function labelKindOf(detectorClass: string): LabelKind | null {
  return FROM_COCO[detectorClass.trim().toLowerCase()] ?? null;
}

/** How far apart two sightings can be and still be the same object, in metres. */
const MERGE_RADIUS: Record<LabelKind, number> = {
  sofa: 0.9,
  bed: 1.0,
  table: 0.8,
  fridge: 0.6,
  tv: 0.5,
  chair: 0.4,
  microwave: 0.3,
};

export function mergeRadius(kind: LabelKind): number {
  return MERGE_RADIUS[kind];
}

/** A pinned label is shown only when its sightings average at least this confidence. */
export const SHOW_MIN_SCORE = 0.6;
/** At most this many labels are shown at once: decoration, not a list. */
export const MAX_SHOWN = 8;

/**
 * Sightings below this confidence are ignored. Low enough that capture
 * guidance knows where large objects are; what is shown needs three agreeing
 * sightings and `SHOW_MIN_SCORE` on average.
 */
export const MIN_SCORE = 0.35;
/** A label is pinned once this many sightings agree on where its object is. */
export const SHOW_AFTER_HITS = 3;
/** Sightings kept per label, newest last. */
const MAX_SIGHTINGS = 9;
/** A label not yet pinned is forgotten after this long unseen. */
export const FORGET_AFTER_MS = 4000;
/** Farther than this, the raycast is guessing. */
export const MAX_RANGE_M = 6;
/** An object point closer than this to the wall or floor behind it is that wall or floor. */
export const ON_SURFACE_M = 0.12;

/** What the ray through a detection's centre meets in the AR scene's planes. */
export type SurfaceKind = "wall" | "floor" | "ceiling" | "raised" | "none";

export interface Detection {
  /** The detector's class name, for example "refrigerator". */
  detectorClass: string;
  score: number;
  /** The object's point on the ray through the box centre, or null when the ray met nothing. */
  world: Vec3 | null;
  /** The plane the same ray meets (iOS plane classes or plane size and height). Missing on older builds. */
  surface?: SurfaceKind;
  /** Metres from the object point to that plane along the ray; 0 when the point is the plane itself. */
  gap?: number | null;
  /** Distance from the camera to the object point, in metres. */
  range?: number | null;
  /**
   * How the native view placed the point: on the floor under the object,
   * from a plane or tracked points on its ray, or from how tall it looks.
   */
  placedBy?: "floor" | "plane" | "points" | "size" | "";
  /** The detection's box in the upright camera image, 0 to 1. */
  box?: { x: number; y: number; width: number; height: number } | null;
}

/** Objects that hang flat on a wall: a label on the wall is right for these. */
const ON_WALL_KINDS: ReadonlySet<LabelKind> = new Set(["tv"]);
/** Objects that stand on the floor and rise well above it. */
const FLOOR_KINDS: ReadonlySet<LabelKind> = new Set(["fridge", "sofa", "table", "bed", "chair"]);

export type RejectReason = "onWall" | "bareFloor" | "ceiling" | "tooFar";

/**
 * Why a sighting cannot be its object, or null when it can. A fridge whose
 * ray ends flat on a wall or door is the door; a chair whose ray ends on the
 * floor with nothing standing there is the floor.
 */
export function rejectReason(kind: LabelKind, detection: Detection): RejectReason | null {
  if (detection.range != null && detection.range > MAX_RANGE_M) return "tooFar";
  // A distance estimated from how tall the object looks says nothing about
  // the wall or floor its ray happens to meet.
  if (detection.placedBy === "size") return detection.surface === "ceiling" ? "ceiling" : null;
  const surface = detection.surface;
  if (!surface || surface === "none" || surface === "raised") return null;
  if (surface === "ceiling") return "ceiling";
  const flat = detection.gap == null || detection.gap < ON_SURFACE_M;
  if (!flat) return null;
  if (surface === "wall" && !ON_WALL_KINDS.has(kind)) return "onWall";
  if (surface === "floor" && FLOOR_KINDS.has(kind)) return "bareFloor";
  return null;
}

/** How close sightings must be to agree, in metres: wider for big objects, whose centre moves as you pan. */
export function agreeRadius(kind: LabelKind): number {
  return Math.max(0.25, mergeRadius(kind) * 0.6);
}

export interface TrackedLabel {
  id: string;
  kind: LabelKind;
  /** The median of the recent sightings: one stray sighting cannot move it. */
  position: Vec3;
  /** Recent sighting positions, newest last. */
  sightings: readonly Vec3[];
  /** Summed detector confidence per kind: the name is the kind with the most. */
  votes: Partial<Record<LabelKind, number>>;
  hits: number;
  /** Set once enough sightings agree; a pinned label stays. */
  pinned: boolean;
  lastSeenMs: number;
}

export interface LabelState {
  labels: readonly TrackedLabel[];
  nextId: number;
  /** Sightings dropped by `rejectReason`, for the debug overlay. */
  rejected: number;
}

export const EMPTY_LABELS: LabelState = { labels: [], nextId: 1, rejected: 0 };

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  const upper = sorted[middle] ?? 0;
  return sorted.length % 2 ? upper : ((sorted[middle - 1] ?? upper) + upper) / 2;
}

function medianPoint(points: readonly Vec3[]): Vec3 {
  return {
    x: median(points.map((p) => p.x)),
    y: median(points.map((p) => p.y)),
    z: median(points.map((p) => p.z)),
  };
}

/** True when enough recent sightings sit close to their median. */
export function sightingsAgree(kind: LabelKind, sightings: readonly Vec3[]): boolean {
  if (sightings.length < SHOW_AFTER_HITS) return false;
  const centre = medianPoint(sightings);
  const radius = agreeRadius(kind);
  return sightings.filter((p) => distance(p, centre) <= radius).length >= SHOW_AFTER_HITS;
}

function distance(a: Vec3, b: Vec3): number {
  return Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
}

function leadingKind(votes: Partial<Record<LabelKind, number>>, fallback: LabelKind): LabelKind {
  let best = fallback;
  let bestVotes = -1;
  for (const kind of LABEL_KINDS) {
    const count = votes[kind] ?? 0;
    if (count > bestVotes) {
      best = kind;
      bestVotes = count;
    }
  }
  return bestVotes > 0 ? best : fallback;
}

/** Fold one batch of detections into the labels. Pure: returns a new state. */
export function updateLabels(
  state: LabelState,
  detections: readonly Detection[],
  nowMs: number,
): LabelState {
  const labels = state.labels
    .filter((label) => label.pinned || nowMs - label.lastSeenMs <= FORGET_AFTER_MS)
    .map((label) => ({ ...label, votes: { ...label.votes } }));
  let nextId = state.nextId;
  let rejected = state.rejected;

  for (const detection of detections) {
    const kind = labelKindOf(detection.detectorClass);
    if (!kind || !detection.world || detection.score < MIN_SCORE) continue;
    if (rejectReason(kind, detection)) {
      rejected += 1;
      continue;
    }
    const world = detection.world;

    // The nearest label close enough to be this object, whatever its name.
    let match: (typeof labels)[number] | undefined;
    let nearest = Infinity;
    for (const label of labels) {
      const reach = Math.max(mergeRadius(kind), mergeRadius(label.kind));
      const d = distance(label.position, world);
      if (d <= reach && d < nearest) {
        match = label;
        nearest = d;
      }
    }

    if (match) {
      match.votes[kind] = (match.votes[kind] ?? 0) + detection.score;
      match.kind = leadingKind(match.votes, match.kind);
      match.sightings = [...match.sightings, world].slice(-MAX_SIGHTINGS);
      match.position = medianPoint(match.sightings);
      match.hits += 1;
      match.pinned = match.pinned || sightingsAgree(match.kind, match.sightings);
      match.lastSeenMs = nowMs;
    } else {
      labels.push({
        id: `label-${nextId}`,
        kind,
        position: world,
        sightings: [world],
        votes: { [kind]: detection.score },
        hits: 1,
        pinned: false,
        lastSeenMs: nowMs,
      });
      nextId += 1;
    }
  }

  return { labels: mergeOverlapping(labels), nextId, rejected };
}

/**
 * Labels can drift together as they ease toward new sightings. Two labels
 * that end up on the same object become one: the one seen more keeps its id.
 */
function mergeOverlapping(labels: TrackedLabel[]): TrackedLabel[] {
  const kept: TrackedLabel[] = [];
  const byHits = [...labels].sort((a, b) => b.hits - a.hits || a.id.localeCompare(b.id));
  for (const label of byHits) {
    const host = kept.find(
      (other) =>
        other.kind === label.kind &&
        distance(other.position, label.position) <= mergeRadius(label.kind),
    );
    if (!host) {
      kept.push(label);
      continue;
    }
    for (const kind of LABEL_KINDS) {
      const extra = label.votes[kind];
      if (extra) host.votes[kind] = (host.votes[kind] ?? 0) + extra;
    }
    host.hits += label.hits;
    host.sightings = [...host.sightings, ...label.sightings].slice(-MAX_SIGHTINGS);
    host.position = medianPoint(host.sightings);
    host.pinned = host.pinned || label.pinned || sightingsAgree(host.kind, host.sightings);
    host.lastSeenMs = Math.max(host.lastSeenMs, label.lastSeenMs);
    host.kind = leadingKind(host.votes, host.kind);
  }
  // Stable order for rendering: by id number.
  return kept.sort((a, b) => Number(a.id.slice(6)) - Number(b.id.slice(6)));
}

export interface ShownLabel {
  id: string;
  kind: LabelKind;
  x: number;
  y: number;
  z: number;
}

/** Average detector confidence of a label's own kind over its sightings. */
export function meanScore(label: TrackedLabel): number {
  return label.hits > 0 ? (label.votes[label.kind] ?? 0) / label.hits : 0;
}

/** Pinned labels that are confident on average: the few most confident, ready to show. */
export function shownLabels(state: LabelState): ShownLabel[] {
  return state.labels
    .filter((label) => label.pinned && meanScore(label) >= SHOW_MIN_SCORE)
    .sort((a, b) => meanScore(b) - meanScore(a) || a.id.localeCompare(b.id))
    .slice(0, MAX_SHOWN)
    .sort((a, b) => Number(a.id.slice(6)) - Number(b.id.slice(6)))
    .map((label) => ({ id: label.id, kind: label.kind, ...label.position }));
}

/** Every pinned large object, confident or not: what capture guidance works from. */
export function trackedObjects(state: LabelState): ShownLabel[] {
  return state.labels
    .filter((label) => label.pinned && LARGE_KINDS.has(label.kind))
    .map((label) => ({ id: label.id, kind: label.kind, ...label.position }));
}
