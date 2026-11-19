import type { Design, SpaceTwin } from "@sajao/schemas";
import twinFixture from "../../../../packages/schemas/fixtures/v1/valid/space-twin.json";
import {
  AGAINST_WALL_M,
  designPlan,
  footprint,
  MAX_CLEARANCES,
  wallClearance,
} from "./design-plan";
import { SAMPLE_DESIGNS } from "./sample-designs";

const twin = twinFixture as unknown as SpaceTwin;
const shell = twin.shell; // 4.2 m by 3.4 m
const box = { width: 320, height: 300, padding: 30 };
const [, bestMatch] = SAMPLE_DESIGNS;
type Item = Design["items"][number];
const sofa = bestMatch.items[0] as Item; // 1.95 by 0.85 at (2.1, 2.85), turned 180

const at = (item: Item, x_m: number, y_m: number, rotation_deg = 0): Item => ({
  ...item,
  position: { x_m, y_m },
  rotation_deg,
});
const round = (value: number) => Math.round(value * 1000) / 1000;

describe("an item's footprint", () => {
  it("is its product's own width and depth about its position", () => {
    const corners = footprint(at(sofa, 2, 1));
    expect(corners.map((c) => [round(c.x_m), round(c.y_m)])).toEqual([
      [1.025, 0.575],
      [2.975, 0.575],
      [2.975, 1.425],
      [1.025, 1.425],
    ]);
  });

  it("turns with the item: a quarter turn swaps width and depth", () => {
    const xs = footprint(at(sofa, 2, 1, 90)).map((c) => round(c.x_m));
    const ys = footprint(at(sofa, 2, 1, 90)).map((c) => round(c.y_m));
    expect(round(Math.max(...xs) - Math.min(...xs))).toBe(0.85);
    expect(round(Math.max(...ys) - Math.min(...ys))).toBe(1.95);
  });
});

describe("clearance to the walls", () => {
  const room = shell.floor_polygon;

  it("is the narrowest gap between the item and any wall", () => {
    // Sofa's back edge is at y = 3.275; the far wall is at y = 3.4.
    const gap = wallClearance(footprint(sofa), room);
    expect(round(gap?.metres ?? 0)).toBe(0.125);
  });

  it("is zero for an item touching a wall, and measured to the nearer wall", () => {
    expect(round(wallClearance(footprint(at(sofa, 0.975, 1)), room)?.metres ?? -1)).toBe(0);
    expect(round(wallClearance(footprint(at(sofa, 1.475, 1.7)), room)?.metres ?? 0)).toBe(0.5);
  });
});

describe("the plan", () => {
  const plan = designPlan(bestMatch, shell, box);

  it("fits the room in the box at one scale, with y pointing up", () => {
    expect(round(plan.scale)).toBe(round(Math.min(260 / 4.2, 240 / 3.4)));
    const xs = plan.outline.map((p) => p.x);
    const ys = plan.outline.map((p) => p.y);
    expect(Math.min(...xs)).toBeGreaterThanOrEqual(box.padding - 1e-6);
    expect(Math.max(...xs)).toBeLessThanOrEqual(box.width - box.padding + 1e-6);
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(box.padding - 1e-6);
    // The room's first corner (0, 0) is bottom left on screen.
    expect(plan.outline[0]?.y).toBeGreaterThan(plan.outline[2]?.y ?? 0);
  });

  it("draws every item of the design to the room's scale", () => {
    expect(plan.items.map((item) => item.id)).toEqual(bestMatch.items.map((item) => item.id));
    const sofaOnPlan = plan.items[0];
    const xs = sofaOnPlan?.corners.map((c) => c.x) ?? [];
    expect(round(Math.max(...xs) - Math.min(...xs))).toBe(round(1.95 * plan.scale));
    expect(sofaOnPlan?.title).toBe("Oak frame three seater sofa");
  });

  it("labels every wall with its measured length, outside the room", () => {
    // The fourth side is open: drawn, not measured.
    expect(plan.walls.map((wall) => wall.metres)).toEqual([4.2, 3.4, 4.2]);
    expect(plan.edges.map((edge) => edge.kind)).toEqual(["wall", "wall", "wall", "open"]);
    const bottomWall = plan.walls[0];
    const lowestCorner = Math.max(...plan.outline.map((p) => p.y));
    expect(bottomWall?.at.y).toBeGreaterThan(lowestCorner);
  });

  it("puts doors and windows on their walls", () => {
    expect(plan.openings.map((opening) => opening.kind)).toEqual(["door", "window"]);
    const window = plan.openings[1];
    expect(round((window?.to.x ?? 0) - (window?.from.x ?? 0))).toBe(round(1.5 * plan.scale));
  });

  it("labels the tightest gaps, tightest first, and not items against a wall", () => {
    expect(plan.clearances.length).toBeLessThanOrEqual(MAX_CLEARANCES);
    const metres = plan.clearances.map((gap) => gap.metres);
    expect(metres).toEqual([...metres].sort((a, b) => a - b));
    expect(plan.clearances[0]?.itemId).toBe("sofa");
    expect(round(plan.clearances[0]?.metres ?? 0)).toBe(0.125);

    const flush = { ...bestMatch, items: [at(sofa, 2, 0.425)] } as Design;
    expect(designPlan(flush, shell, box).clearances).toEqual([]);
    expect(AGAINST_WALL_M).toBe(0.05);
  });

  it("labels only the picked item's gap, and no gaps at all when they are off", () => {
    const picked = designPlan(bestMatch, shell, box, { selectedId: "sofa" });
    expect(picked.clearances.map((gap) => gap.itemId)).toEqual(["sofa"]);
    expect(picked.selected).toMatchObject({ id: "sofa", widthM: 1.95, depthM: 0.85 });
    const off = designPlan(bestMatch, shell, box, { selectedId: "sofa", gaps: false });
    expect(off.clearances).toEqual([]);
    // The size is the product's own and shows either way.
    expect(off.selected?.widthM).toBe(1.95);
    const unknown = designPlan(bestMatch, shell, box, { selectedId: "nope" });
    expect(unknown.selected).toBeNull();
    expect(unknown.clearances).toEqual(designPlan(bestMatch, shell, box).clearances);
  });

  it("the halo is the widest band of a wall that is not tape-measured", () => {
    // Wall w3 is estimated to within 15 cm.
    expect(round(plan.haloPx)).toBe(round(0.15 * plan.scale));
    const measured = {
      ...shell,
      walls: shell.walls.map((wall) => ({
        ...wall,
        length: { ...wall.length, source: "measured" as const },
      })),
    } as typeof shell;
    expect(designPlan(bestMatch, measured, box).haloPx).toBe(0);
  });

  it("draws the room alone when there is no design", () => {
    const empty = designPlan(null, shell, box);
    expect(empty.items).toEqual([]);
    expect(empty.clearances).toEqual([]);
    expect(empty.walls).toHaveLength(3);
  });
});

describe("a room that is not a closed box", () => {
  const point = (x_m: number, y_m: number) => ({ x_m, y_m });
  // An L-shaped open-plan room, 6 m by 5 m, open along its right-hand side.
  const polygon = [point(0, 0), point(6, 0), point(6, 3), point(3, 3), point(3, 5), point(0, 5)];
  const walls = polygon
    .map((start, i) => {
      const end = polygon[(i + 1) % polygon.length]!;
      return {
        id: `w${i}`,
        start,
        end,
        length: {
          value_m: Math.hypot(end.x_m - start.x_m, end.y_m - start.y_m),
          source: "estimated" as const,
          error_band_m: 0.05,
        },
      };
    })
    .filter((_, i) => i !== 1);
  const open = { floor_polygon: polygon, walls, openings: [] } as unknown as typeof shell;

  it("draws the floor polygon edge by edge, walls and open sides apart", () => {
    const plan = designPlan(null, open, box);
    expect(plan.outline).toHaveLength(6);
    expect(plan.edges.map((edge) => edge.kind)).toEqual([
      "wall",
      "open",
      "wall",
      "wall",
      "wall",
      "wall",
    ]);
    // Only walls carry a length.
    expect(plan.walls).toHaveLength(5);
  });

  it("measures clearance to walls, never to an open side", () => {
    // 0.3 m from the open side at x = 6, 0.6 m from the wall along y = 0.
    const item = at(sofa, 6 - 0.3 - 1.95 / 2, 0.6 + 0.85 / 2);
    const plan = designPlan({ ...bestMatch, items: [item] } as Design, open, box);
    expect(plan.clearances).toHaveLength(1);
    expect(round(plan.clearances[0]!.metres)).toBe(0.6);
  });
});
