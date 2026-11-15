// Delaunay triangulation (Bowyer-Watson). Turns scattered feature points
// into the triangles of the scan mesh. Delaunay triangles avoid long thin
// slivers, which is what makes the mesh look like a surface.

export interface Point {
  x: number;
  y: number;
}

export type Triangle = readonly [number, number, number];

/** True when p is strictly inside the circle through a, b and c. */
export function inCircumcircle(p: Point, a: Point, b: Point, c: Point): boolean {
  "worklet";
  const ax = a.x - p.x;
  const ay = a.y - p.y;
  const bx = b.x - p.x;
  const by = b.y - p.y;
  const cx = c.x - p.x;
  const cy = c.y - p.y;
  const det =
    (ax * ax + ay * ay) * (bx * cy - cx * by) -
    (bx * bx + by * by) * (ax * cy - cx * ay) +
    (cx * cx + cy * cy) * (ax * by - bx * ay);
  // The sign depends on the triangle's winding.
  const orientation = (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
  return orientation > 0 ? det > 1e-12 : det < -1e-12;
}

/** Triangles as index triples into `points`. Fewer than three points give none. */
export function triangulate(points: readonly Point[]): Triangle[] {
  "worklet";
  const count = points.length;
  if (count < 3) return [];

  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const point of points) {
    minX = Math.min(minX, point.x);
    minY = Math.min(minY, point.y);
    maxX = Math.max(maxX, point.x);
    maxY = Math.max(maxY, point.y);
  }
  const span = Math.max(maxX - minX, maxY - minY, 1e-9) * 20;
  const midX = (minX + maxX) / 2;
  const midY = (minY + maxY) / 2;

  // A triangle that contains every point; its corners get indices count..count+2.
  const all: Point[] = [
    ...points,
    { x: midX - span, y: midY - span },
    { x: midX + span, y: midY - span },
    { x: midX, y: midY + span },
  ];
  let triangles: Triangle[] = [[count, count + 1, count + 2]];

  for (let index = 0; index < count; index += 1) {
    const point = all[index] as Point;
    const keep: Triangle[] = [];
    const edges = new Map<string, [number, number]>();
    for (const triangle of triangles) {
      const [a, b, c] = triangle;
      if (inCircumcircle(point, all[a] as Point, all[b] as Point, all[c] as Point)) {
        // This triangle is no longer valid; an edge shared by two such
        // triangles is interior to the hole and cancels out.
        for (const [from, to] of [
          [a, b],
          [b, c],
          [c, a],
        ] as const) {
          const key = from < to ? `${from}:${to}` : `${to}:${from}`;
          if (edges.has(key)) edges.delete(key);
          else edges.set(key, [from, to]);
        }
      } else {
        keep.push(triangle);
      }
    }
    for (const [from, to] of edges.values()) keep.push([from, to, index]);
    triangles = keep;
  }

  return triangles.filter(([a, b, c]) => a < count && b < count && c < count);
}
