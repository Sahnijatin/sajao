import type { SpaceProfile } from "@sajao/schemas";
import { validate } from "@sajao/schemas/validate";
import fixture from "../../../../packages/schemas/fixtures/v1/valid/space-profile.json";
import {
  applyTapeToCeiling,
  applyTapeToWall,
  cycleItemAction,
  describeSpace,
  floorArea,
  isVerified,
  lightTime,
  moveOpening,
  planDrawing,
  setRedo,
  setSpaceType,
  TAPE_ERROR_BAND_M,
} from "./space-profile";

const profile = fixture as unknown as SpaceProfile;

/** Every change must leave a profile the contract still accepts. */
function expectValid(changed: SpaceProfile) {
  const result = validate("SpaceProfile", JSON.parse(JSON.stringify(changed)));
  expect(result.ok ? [] : result.errors).toEqual([]);
}

describe("what we found", () => {
  it("starts from a profile the contract accepts", () => expectValid(profile));

  it("describes the space: type, size, openings, light and an honest badge", () => {
    expect(describeSpace(profile)).toEqual({
      spaceType: "living_room",
      extent: "whole_room",
      areaM2: expect.closeTo(4.2 * 3.4, 6),
      windows: 1,
      doors: 1,
      light: "morning",
      // Estimated, showing the widest error band among the walls and ceiling.
      badge: { kind: "estimated", errorBandM: 0.15 },
    });
  });

  it("measures floor area for any polygon, in either winding", () => {
    const l = [
      { x_m: 0, y_m: 0 },
      { x_m: 4, y_m: 0 },
      { x_m: 4, y_m: 2 },
      { x_m: 2, y_m: 2 },
      { x_m: 2, y_m: 4 },
      { x_m: 0, y_m: 4 },
    ];
    expect(floorArea(l)).toBe(12);
    expect(floorArea([...l].reverse())).toBe(12);
  });

  it("reads when the light comes in from the window's compass bearing", () => {
    const facing = (deg: number) =>
      lightTime({
        ...profile,
        direction: { ...profile.direction, north_deg: 0 },
        light: { natural_light: "medium", main_direction_deg: deg },
      });
    expect([90, 180, 270, 0].map(facing)).toEqual(["morning", "midday", "evening", "soft"]);
    const { light: _light, ...noLight } = profile;
    expect(lightTime(noLight as SpaceProfile)).toBeNull();
  });
});

describe("changes on the card", () => {
  it("Change: the user corrects the detected space type", () => {
    const changed = setSpaceType(profile, "balcony");
    expect([changed.space_type, changed.space_type_source]).toEqual(["balcony", "user"]);
    expect(profile.space_type).toBe("living_room"); // the original is untouched
    expectValid(changed);
  });

  it("What should we redo: all of it, or just a part", () => {
    const part = setRedo(profile, {
      scope: "part",
      polygon: [
        { x_m: 0, y_m: 0 },
        { x_m: 2, y_m: 0 },
        { x_m: 0, y_m: 2 },
      ],
    });
    expect(part.redo.scope).toBe("part");
    expectValid(part);
    const all = setRedo(part, { scope: "all" });
    expect(all.redo).toEqual({ scope: "all" });
    expectValid(all);
    expect(() => setRedo(profile, { scope: "part", polygon: [{ x_m: 0, y_m: 0 }] })).toThrow();
  });

  it("tapping an item moves it through keep, replace, remove", () => {
    const id = profile.existing_items[0]!.id;
    const actions = [1, 2, 3].reduce<string[]>((seen, taps) => {
      let changed = profile;
      for (let i = 0; i < taps; i += 1) changed = cycleItemAction(changed, id);
      return [...seen, changed.existing_items[0]!.action];
    }, []);
    expect(profile.existing_items[0]!.action).toBe("replace");
    expect(actions).toEqual(["remove", "keep", "replace"]);
    expectValid(cycleItemAction(profile, id));
  });

  it("a dragged door stays on its wall and is marked confirmed, not measured", () => {
    const door = profile.openings.find((opening) => opening.kind === "door")!;
    const wall = profile.walls.find((candidate) => candidate.id === door.wall_id)!;
    const room = wall.length.value_m - door.width.value_m;

    const moved = moveOpening(profile, door.id, 1.1).openings.find((o) => o.id === door.id)!;
    expect(moved.offset).toMatchObject({ value_m: 1.1, source: "user_confirmed" });

    const tooFar = moveOpening(profile, door.id, 99).openings.find((o) => o.id === door.id)!;
    expect(tooFar.offset.value_m).toBeCloseTo(room);
    const negative = moveOpening(profile, door.id, -5).openings.find((o) => o.id === door.id)!;
    expect(negative.offset.value_m).toBe(0);
    expectValid(moveOpening(profile, door.id, 99));
  });
});

describe("tape values", () => {
  // Wall w2 is estimated at 3.4 m. The tape says 3.57 m: everything was 5% too small.
  const fitted = applyTapeToWall(profile, "w2", 3.57);
  const factor = 3.57 / 3.4;

  it("snap the measured wall in with a tape-sized error band", () => {
    const wall = fitted.walls.find((candidate) => candidate.id === "w2")!;
    expect(wall.length).toEqual({
      value_m: 3.57,
      source: "measured",
      error_band_m: TAPE_ERROR_BAND_M,
    });
  });

  it("re-fit every estimated length by the same factor, bands included", () => {
    const before = profile.walls.find((candidate) => candidate.id === "w3")!.length;
    const after = fitted.walls.find((candidate) => candidate.id === "w3")!.length;
    expect(after.value_m).toBeCloseTo(before.value_m * factor);
    expect(after.error_band_m).toBeCloseTo(before.error_band_m * factor);
    expect(after.source).toBe("estimated");
    expect(floorArea(fitted.floor_polygon)).toBeCloseTo(
      floorArea(profile.floor_polygon) * factor ** 2,
    );
  });

  it("never tighten an error band from one tape value", () => {
    for (const wall of fitted.walls.filter((candidate) => candidate.id !== "w2")) {
      const before = profile.walls.find((candidate) => candidate.id === wall.id)!.length;
      expect(wall.length.error_band_m).toBeGreaterThanOrEqual(before.error_band_m);
    }
  });

  it("leave walls that were already measured exactly as they were", () => {
    const measured = profile.walls.find((candidate) => candidate.id === "w1")!.length;
    expect(measured.source).toBe("measured");
    expect(fitted.walls.find((candidate) => candidate.id === "w1")!.length).toEqual(measured);
  });

  it("do not change heights: a floor measurement says nothing about the ceiling", () => {
    expect(fitted.ceiling_height).toEqual(profile.ceiling_height);
    expect(fitted.openings[0]!.height).toEqual(profile.openings[0]!.height);
  });

  it("keep the profile valid and estimated until every wall and the ceiling are measured", () => {
    expectValid(fitted);
    expect(fitted.verification).toBe("estimated");

    let all = profile;
    for (const wall of profile.walls) all = applyTapeToWall(all, wall.id, wall.length.value_m);
    expect(isVerified(all)).toBe(false); // the ceiling is still estimated
    expect(all.verification).toBe("estimated");
    all = applyTapeToCeiling(all, 2.92);
    expect(all.verification).toBe("verified");
    expect(describeSpace(all).badge).toEqual({ kind: "verified" });
    expectValid(all);
  });

  it("reject values that cannot be a length, and unknown walls", () => {
    expect(() => applyTapeToWall(profile, "w2", 0)).toThrow(RangeError);
    expect(() => applyTapeToWall(profile, "w2", Number.NaN)).toThrow(RangeError);
    expect(() => applyTapeToWall(profile, "nope", 3)).toThrow(RangeError);
    expect(() => applyTapeToCeiling(profile, -1)).toThrow(RangeError);
  });
});

describe("plan drawing", () => {
  const box = { width: 390, height: 300, padding: 20 };
  const drawing = planDrawing(profile, box);

  it("fits inside the box with padding and keeps the shape", () => {
    for (const point of drawing.outline) {
      expect(point.x).toBeGreaterThanOrEqual(box.padding - 1e-6);
      expect(point.x).toBeLessThanOrEqual(box.width - box.padding + 1e-6);
      expect(point.y).toBeGreaterThanOrEqual(box.padding - 1e-6);
      expect(point.y).toBeLessThanOrEqual(box.height - box.padding + 1e-6);
    }
    const xs = drawing.outline.map((point) => point.x);
    const ys = drawing.outline.map((point) => point.y);
    const ratio = (Math.max(...xs) - Math.min(...xs)) / (Math.max(...ys) - Math.min(...ys));
    expect(ratio).toBeCloseTo(4.2 / 3.4);
  });

  it("draws to one scale: openings and items are sized in the same pixels per metre", () => {
    const window = drawing.openings.find((opening) => opening.kind === "window")!;
    const length = Math.hypot(window.to.x - window.from.x, window.to.y - window.from.y);
    expect(length).toBeCloseTo(1.5 * drawing.scale);
    expect(drawing.items[0]).toMatchObject({ width: 2.0 * drawing.scale, action: "replace" });
  });

  it("puts north-up plan coordinates the right way up on screen", () => {
    // The plan's y axis points up; the screen's points down.
    const [origin, , topRight] = drawing.outline;
    expect(topRight!.y).toBeLessThan(origin!.y);
  });
});
