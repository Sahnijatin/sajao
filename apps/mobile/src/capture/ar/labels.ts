// Live object labels for the AR scan. The on-device detector runs a few
// times a second; each detection is raycast into the AR scene natively and
// arrives here with a world position in metres. This tracker turns that
// noisy stream into one steady label per real object: labels stick where
// the object is, a new label appears only after two sightings, and two
// labels never sit on the same object (class votes decide its name).
//
// Labels are guidance for the person scanning. Positions here never set a
// dimension; the twin measures objects on the server.

export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

/** Objects we name during the scan, from the detector's COCO classes. */
export const LABEL_KINDS = [
  "fridge",
  "sofa",
  "chair",
  "table",
  "bed",
  "tv",
  "microwave",
  "oven",
  "sink",
  "toilet",
  "plant",
  "laptop",
  "clock",
  "vase",
  "bench",
  "toaster",
] as const;

export type LabelKind = (typeof LABEL_KINDS)[number];

const FROM_COCO: Record<string, LabelKind> = {
  refrigerator: "fridge",
  couch: "sofa",
  chair: "chair",
  "dining table": "table",
  bed: "bed",
  tv: "tv",
  microwave: "microwave",
  oven: "oven",
  sink: "sink",
  toilet: "toilet",
  "potted plant": "plant",
  laptop: "laptop",
  clock: "clock",
  vase: "vase",
  bench: "bench",
  toaster: "toaster",
};

/** The label kind for a detector class, or null for classes we do not name (people, cars). */
export function labelKindOf(detectorClass: string): LabelKind | null {
  return FROM_COCO[detectorClass.trim().toLowerCase()] ?? null;
}

/** How far apart two sightings can be and still be the same object, in metres. */
const MERGE_RADIUS: Partial<Record<LabelKind, number>> = {
  sofa: 0.9,
  bed: 1.0,
  table: 0.8,
  fridge: 0.6,
  tv: 0.5,
  bench: 0.7,
};
const DEFAULT_RADIUS = 0.4;

export function mergeRadius(kind: LabelKind): number {
  return MERGE_RADIUS[kind] ?? DEFAULT_RADIUS;
}

/** Detections below this confidence are ignored. */
export const MIN_SCORE = 0.45;
/** A label is shown once its object has been seen this many times. */
export const SHOW_AFTER_HITS = 2;
/** How far a label moves toward each new sighting: steady, not jumpy. */
const POSITION_EASING = 0.3;

export interface Detection {
  /** The detector's class name, for example "refrigerator". */
  detectorClass: string;
  score: number;
  /** Where the detection's centre hit the AR scene, or null when the raycast missed. */
  world: Vec3 | null;
}

export interface TrackedLabel {
  id: string;
  kind: LabelKind;
  position: Vec3;
  /** Summed detector confidence per kind: the name is the kind with the most. */
  votes: Partial<Record<LabelKind, number>>;
  hits: number;
  lastSeenMs: number;
}

export interface LabelState {
  labels: readonly TrackedLabel[];
  nextId: number;
}

export const EMPTY_LABELS: LabelState = { labels: [], nextId: 1 };

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
  const labels = state.labels.map((label) => ({ ...label, votes: { ...label.votes } }));
  let nextId = state.nextId;

  for (const detection of detections) {
    const kind = labelKindOf(detection.detectorClass);
    if (!kind || !detection.world || detection.score < MIN_SCORE) continue;
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
      match.position = {
        x: match.position.x + (world.x - match.position.x) * POSITION_EASING,
        y: match.position.y + (world.y - match.position.y) * POSITION_EASING,
        z: match.position.z + (world.z - match.position.z) * POSITION_EASING,
      };
      match.hits += 1;
      match.lastSeenMs = nowMs;
    } else {
      labels.push({
        id: `label-${nextId}`,
        kind,
        position: world,
        votes: { [kind]: detection.score },
        hits: 1,
        lastSeenMs: nowMs,
      });
      nextId += 1;
    }
  }

  return { labels: mergeOverlapping(labels), nextId };
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

/** Labels confirmed by enough sightings, ready to pin in the AR view. */
export function shownLabels(state: LabelState): ShownLabel[] {
  return state.labels
    .filter((label) => label.hits >= SHOW_AFTER_HITS)
    .map((label) => ({ id: label.id, kind: label.kind, ...label.position }));
}
