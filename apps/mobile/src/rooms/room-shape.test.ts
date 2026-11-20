import { confidenceOf, edgeKinds, fitClaimsAllowed, isWall } from "./room-shape";

const point = (x_m: number, y_m: number) => ({ x_m, y_m });
const wall = (
  id: string,
  start: { x_m: number; y_m: number },
  end: { x_m: number; y_m: number },
) => ({
  id,
  start,
  end,
  length: {
    value_m: Math.hypot(end.x_m - start.x_m, end.y_m - start.y_m),
    source: "estimated" as const,
    error_band_m: 0.05,
  },
});

// An L-shaped open-plan room: the short side at the top right has no wall.
const L = [point(0, 0), point(6, 0), point(6, 3), point(3, 3), point(3, 5), point(0, 5)];

describe("which edges of the floor are walls", () => {
  it("marks every edge of a closed box as a wall", () => {
    const box = [point(0, 0), point(4, 0), point(4, 3), point(0, 3)];
    const walls = box.map((from, i) => wall(`w${i}`, from, box[(i + 1) % 4]!));
    expect(edgeKinds({ floor_polygon: box, walls })).toEqual(["wall", "wall", "wall", "wall"]);
  });

  it("marks an edge no wall runs along as open, on an L-shaped room", () => {
    const walls = L.map((from, i) => wall(`w${i}`, from, L[(i + 1) % L.length]!)).filter(
      (_, i) => i !== 1 && i !== 3,
    );
    expect(edgeKinds({ floor_polygon: L, walls })).toEqual([
      "wall",
      "open",
      "wall",
      "open",
      "wall",
      "wall",
    ]);
  });

  it("takes a wall drawn the other way round, or a little off the edge", () => {
    const box = [point(0, 0), point(4, 0), point(4, 3), point(0, 3)];
    const walls = [wall("a", point(4.05, 0.1), point(0, -0.05))];
    expect(edgeKinds({ floor_polygon: box, walls })).toEqual(["wall", "open", "open", "open"]);
  });

  it("does not call an edge a wall for a short stub or a wall across the room", () => {
    const box = [point(0, 0), point(4, 0), point(4, 3), point(0, 3)];
    const stub = wall("stub", point(0, 0), point(1, 0));
    const across = wall("across", point(0, 1.5), point(4, 1.5));
    expect(edgeKinds({ floor_polygon: box, walls: [stub, across] })).toEqual([
      "open",
      "open",
      "open",
      "open",
    ]);
  });
});

describe("an edge the twin marks open", () => {
  it("is open even though it is listed among the walls", () => {
    const box = [point(0, 0), point(4, 0), point(4, 3), point(0, 3)];
    const walls = box.map((from, i) => ({
      ...wall(`w${i}`, from, box[(i + 1) % 4]!),
      ...(i === 2 ? { kind: "open" as const } : { kind: "wall" as const }),
    }));
    expect(edgeKinds({ floor_polygon: box, walls })).toEqual(["wall", "wall", "open", "wall"]);
    expect(walls.filter(isWall)).toHaveLength(3);
  });
});

describe("an edge no photo showed", () => {
  it("is unseen, never open, and is not a wall", () => {
    const box = [point(0, 0), point(4, 0), point(4, 3), point(0, 3)];
    const walls = box.map((from, i) => ({
      ...wall(`w${i}`, from, box[(i + 1) % 4]!),
      kind: i === 3 ? ("unseen" as const) : ("wall" as const),
    }));
    expect(edgeKinds({ floor_polygon: box, walls })).toEqual(["wall", "wall", "wall", "unseen"]);
    expect(walls.filter(isWall)).toHaveLength(3);
  });
});

describe("the room's confidence level", () => {
  it("is what the twin says, and nothing when it says nothing", () => {
    expect(confidenceOf({ confidence: { level: "taped" } })).toBe("taped");
    expect(confidenceOf({ confidence: { level: "ar_measured" } })).toBe("measured");
    expect(confidenceOf({ confidence: { level: "estimated" } })).toBe("estimated");
    expect(confidenceOf({})).toBeNull();
    expect(confidenceOf({ confidence: { level: "certain" } })).toBeNull();
  });

  it("allows fit claims for taped and measured rooms only", () => {
    expect(fitClaimsAllowed("taped")).toBe(true);
    expect(fitClaimsAllowed("measured")).toBe(true);
    expect(fitClaimsAllowed("estimated")).toBe(false);
  });
});
