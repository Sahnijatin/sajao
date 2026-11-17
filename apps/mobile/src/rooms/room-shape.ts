// The shape of a room and how far its numbers can be trusted. A room is a
// floor polygon; each edge is either a wall or open (an open-plan side, a
// wide archway). Pure: nothing here measures or estimates anything.
interface Metres {
  x_m: number;
  y_m: number;
}

/** The part of a twin's shell the shape is read from. */
interface Shell {
  floor_polygon: readonly Metres[];
  /** The twin lists every edge it knows; one marked open is not a wall. */
  walls: readonly { start: Metres; end: Metres; kind?: EdgeKind }[];
}

export type EdgeKind = "wall" | "open";

/** A wall end may sit this far off the floor edge and still be that edge's wall. */
export const EDGE_TOLERANCE_M = 0.15;
/** A wall must run along at least this share of an edge for the edge to be a wall. */
export const WALL_SHARE = 0.5;

/** True for an entry of the twin's walls that is a wall, not an open side. */
export function isWall(wall: { kind?: EdgeKind }): boolean {
  return wall.kind !== "open";
}

/**
 * Whether each edge of the floor polygon is a wall or open, in polygon
 * order (edge i runs from point i to point i + 1). An edge is a wall where
 * one of the twin's walls runs along it and is not marked open; an edge
 * marked open, or one nothing runs along, is open.
 */
export function edgeKinds(shell: Shell): EdgeKind[] {
  const points = shell.floor_polygon;
  return points.map((a, index) => {
    const b = points[(index + 1) % points.length] as Metres;
    const dx = b.x_m - a.x_m;
    const dy = b.y_m - a.y_m;
    const length = Math.hypot(dx, dy);
    if (length === 0) return "open";
    // How far along the edge (0 to 1) a point is, and how far off its line.
    const along = (p: Metres) => ((p.x_m - a.x_m) * dx + (p.y_m - a.y_m) * dy) / (length * length);
    const off = (p: Metres) => Math.abs((p.x_m - a.x_m) * dy - (p.y_m - a.y_m) * dx) / length;
    const covered = shell.walls.filter(isWall).reduce((most, wall) => {
      if (off(wall.start) > EDGE_TOLERANCE_M || off(wall.end) > EDGE_TOLERANCE_M) return most;
      const from = Math.max(0, Math.min(along(wall.start), along(wall.end)));
      const to = Math.min(1, Math.max(along(wall.start), along(wall.end)));
      return Math.max(most, to - from);
    }, 0);
    return covered >= WALL_SHARE ? "wall" : "open";
  });
}

/**
 * How a room's numbers were got. taped: checked with a tape measure.
 * measured: measured by the scan. estimated: worked out from photos or a
 * video, to be confirmed by measuring.
 */
export type ConfidenceLevel = "taped" | "measured" | "estimated";

const LEVELS: Record<string, ConfidenceLevel> = {
  taped: "taped",
  ar_measured: "measured",
  estimated: "estimated",
};

/**
 * The room's confidence level as its twin gives it; null when the twin has
 * none. The app never works a level out for itself.
 */
export function confidenceOf(twin: {
  confidence?: { level?: string } | null;
}): ConfidenceLevel | null {
  const level = twin.confidence?.level;
  return typeof level === "string" ? (LEVELS[level] ?? null) : null;
}

/** "This fits" is only said of a room that was taped or measured by the scan. */
export function fitClaimsAllowed(level: ConfidenceLevel | null): boolean {
  return level !== "estimated";
}
