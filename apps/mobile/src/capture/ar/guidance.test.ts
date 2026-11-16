import {
  currentHint,
  isCutOff,
  NO_DOORWAY,
  updateDoorway,
  updateViews,
  walkAroundTarget,
} from "./guidance";
import type { ShownLabel } from "./labels";
import { CELL_M, type Wall } from "./surface-coverage";

// A mapped wall at z = -2 facing +z (into the room), 4 m wide (x from -2 to 2).
const wall: Wall = {
  normalYaw: 0,
  offset: -2,
  cells: Object.fromEntries(
    Array.from({ length: 12 }, (_, i) => [`${(i % 8) - 4},${Math.floor(i / 8)}`, 3]),
  ),
  minAlong: -4,
  maxAlong: 3,
};
const walk = (points: [number, number][]) =>
  points.reduce((state, [x, z]) => updateDoorway(state, [wall], { x, z }, CELL_M), NO_DOORWAY);

describe("doorway", () => {
  it("says nothing while you move about the room", () => {
    expect(
      walk([
        [0, 0],
        [1, -1],
        [-1.5, 1],
        [0, -1.5],
      ]).outside,
    ).toBe(false);
  });

  it("notices walking through the wall into another space, and clears on coming back", () => {
    const through = walk([
      [0, 0],
      [0.5, -1.5],
      [0.6, -2.8],
    ]);
    expect(through.outside).toBe(true);
    const back = updateDoorway(through, [wall], { x: 0.4, z: -1 }, CELL_M);
    expect(back.outside).toBe(false);
  });

  it("keeps the last reading while you stand in the doorway", () => {
    const through = walk([
      [0, 0],
      [0.5, -2.8],
    ]);
    expect(updateDoorway(through, [wall], { x: 0.5, z: -2.1 }, CELL_M).outside).toBe(true);
  });

  it("does not count walking round the end of a wall", () => {
    expect(
      walk([
        [0, 0],
        [4, -1],
        [4, -3],
      ]).outside,
    ).toBe(false);
  });

  it("ignores walls that are barely mapped", () => {
    const thin = { ...wall, cells: { "0,0": 2 } };
    const state = [
      { x: 0, z: 0 },
      { x: 0, z: -3 },
    ].reduce((s, p) => updateDoorway(s, [thin], p, CELL_M), NO_DOORWAY);
    expect(state.outside).toBe(false);
  });
});

describe("step back", () => {
  it("flags a large object that spans the frame", () => {
    expect(isCutOff({ x: 0, y: 0.2, width: 1, height: 0.5 })).toBe(true);
    expect(isCutOff({ x: 0.3, y: 0, width: 0.3, height: 1 })).toBe(true);
    expect(isCutOff({ x: 0.05, y: 0.05, width: 0.9, height: 0.9 })).toBe(true);
    expect(isCutOff({ x: 0.2, y: 0.3, width: 0.5, height: 0.4 })).toBe(false);
  });
});

describe("walk around it", () => {
  const sofa: ShownLabel = { id: "label-1", kind: "sofa", x: 0, y: 0, z: -2 };

  it("asks to walk around an object seen from one side only, once the room is half covered", () => {
    let views = updateViews({}, [sofa], { x: 0, z: 0 });
    views = updateViews(views, [sofa], { x: 0.2, z: 0 });
    expect(walkAroundTarget([sofa], views, 0.3)).toBeNull();
    expect(walkAroundTarget([sofa], views, 0.6)).toBe("sofa");
  });

  it("is satisfied once the object has been seen from around it", () => {
    let views = {};
    for (const [x, z] of [
      [0, 0],
      [2, -1],
      [2, -3],
      [0, -4],
    ] as const) {
      views = updateViews(views, [sofa], { x, z });
    }
    expect(walkAroundTarget([sofa], views, 0.8)).toBeNull();
  });
});

describe("one hint at a time", () => {
  it("puts the doorway first, then step back, then walk around", () => {
    expect(currentHint({ outside: true, stepBack: true, walkAround: "sofa" })).toEqual({
      id: "doorway",
    });
    expect(currentHint({ outside: false, stepBack: true, walkAround: "sofa" })).toEqual({
      id: "stepBack",
    });
    expect(currentHint({ outside: false, stepBack: false, walkAround: "bed" })).toEqual({
      id: "walkAround",
      kind: "bed",
    });
    expect(currentHint({ outside: false, stepBack: false, walkAround: null })).toBeNull();
  });
});
