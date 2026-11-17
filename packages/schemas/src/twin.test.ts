import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { Dimension, SpaceTwin, TwinEdit } from "./generated/v1";
import {
  applyEdits,
  clampToSafeRegion,
  heroKeyframes,
  insideSafeRegion,
  spaceProfileFromTwin,
} from "./twin";
import { validate } from "./validate";

const fixture = JSON.parse(
  readFileSync(
    join(import.meta.dirname, "..", "fixtures", "v1", "valid", "space-twin.json"),
    "utf8",
  ),
) as SpaceTwin;
const view = { id: "00000000-0000-4000-8000-0000000000b1", created_at: "2026-01-05T11:00:00Z" };
const size = (w: number, d: number, h: number) => {
  const dim = (value_m: number): Dimension => ({
    value_m,
    source: "measured",
    error_band_m: 0.005,
  });
  return { width: dim(w), depth: dim(d), height: dim(h) };
};

describe("twin edits", () => {
  it("applies move, rotate, replace, add and restyle as deltas, leaving the twin unchanged", () => {
    const before = structuredClone(fixture);
    const edits: TwinEdit[] = [
      {
        id: "e1",
        op: "move",
        by: "user",
        object_id: "sofa-1",
        to: { x_m: 2.4, y_m: 0.7, z_m: 0.42 },
      },
      { id: "e2", op: "rotate", by: "solver", object_id: "almirah-1", yaw_deg: 180 },
      {
        id: "e3",
        op: "replace",
        by: "user",
        object_id: "sofa-1",
        product_id: "prod-7",
        product_size: size(2.0, 0.85, 0.8),
      },
      {
        id: "e4",
        op: "add",
        by: "solver",
        product_id: "prod-8",
        product_size: size(0.5, 0.5, 0.45),
        to: { x_m: 1, y_m: 1.5, z_m: 0.22 },
        yaw_deg: 0,
        label: "Pouf",
      },
      {
        id: "e5",
        op: "restyle_surface",
        by: "user",
        surface_id: "w1",
        material: { kind: "paint", color: "#2f4f4f" },
      },
    ];
    const result = applyEdits(fixture, edits);
    expect(result.problems).toEqual([]);
    expect(fixture).toEqual(before);

    const sofa = result.twin.objects.find((object) => object.id === "sofa-1");
    expect(sofa?.state).toBe("replace");
    expect(sofa?.box.center).toEqual({ x_m: 2.4, y_m: 0.7, z_m: 0.42 });
    // A replacement takes the catalog size, with its source and band.
    expect(sofa?.box.width).toEqual({ value_m: 2.0, source: "measured", error_band_m: 0.005 });
    expect(result.replacements).toEqual({ "sofa-1": "prod-7" });
    expect(result.twin.objects.find((object) => object.id === "almirah-1")?.state).toBe("move");
    expect(result.added).toEqual(["e4"]);
    expect(result.twin.shell.surfaces[0]?.material).toEqual({ kind: "paint", color: "#2f4f4f" });
    expect(validate("SpaceTwin", result.twin).ok).toBe(true);
  });

  it("skips edits that cannot apply, without half applying them", () => {
    const result = applyEdits(fixture, [
      { id: "e1", op: "remove", by: "user", object_id: "sofa-1" },
      { id: "e2", op: "move", by: "user", object_id: "sofa-1", to: { x_m: 0, y_m: 0, z_m: 0 } },
      { id: "e3", op: "remove", by: "user", object_id: "missing" },
      { id: "e1", op: "remove", by: "user", object_id: "almirah-1" },
    ]);
    expect(result.problems.map((problem) => problem.edit_id)).toEqual(["e2", "e3", "e1"]);
    expect(result.twin.objects.find((object) => object.id === "sofa-1")?.box.center).toEqual(
      fixture.objects[0]?.box.center,
    );
    expect(result.twin.objects.find((object) => object.id === "almirah-1")?.state).toBe("keep");
  });

  it("undo is dropping an edit", () => {
    const edits: TwinEdit[] = [
      { id: "e1", op: "remove", by: "user", object_id: "almirah-1" },
      { id: "e2", op: "rotate", by: "user", object_id: "sofa-1", yaw_deg: 45 },
    ];
    expect(applyEdits(fixture, edits.slice(0, 1))).toEqual(
      applyEdits(applyEdits(fixture, []).twin, edits.slice(0, 1)),
    );
    expect(applyEdits(fixture, []).twin).toEqual(fixture);
  });
});

describe("SpaceProfile is a view of the twin", () => {
  it("derives a valid SpaceProfile with each item's choice and no catalog additions", () => {
    const profile = spaceProfileFromTwin(fixture, view, [
      { id: "e1", op: "remove", by: "user", object_id: "almirah-1" },
      {
        id: "e2",
        op: "add",
        by: "user",
        product_id: "p",
        product_size: size(1, 1, 1),
        to: { x_m: 1, y_m: 1, z_m: 0.5 },
        yaw_deg: 0,
        label: "Rug",
      },
    ]);
    const result = validate("SpaceProfile", profile);
    expect(result.ok ? [] : result.errors).toEqual([]);
    expect(profile.existing_items.map((item) => [item.id, item.action])).toEqual([
      ["sofa-1", "keep"],
      ["almirah-1", "remove"],
    ]);
    expect(profile.existing_items[0]?.width).toEqual(fixture.objects[0]?.box.width);
  });
});

describe("viewing limits", () => {
  it("gives the keyframe behind each hero view and skips a view whose keyframe is gone", () => {
    expect(heroKeyframes(fixture).map((keyframe) => keyframe.id)).toEqual(["k1"]);
    const orphan = structuredClone(fixture);
    orphan.viewing!.hero_views[0]!.keyframe_id = "k9";
    expect(heroKeyframes(orphan)).toEqual([]);
  });

  it("allows a camera within the radius of an anchor and nowhere else", () => {
    expect(insideSafeRegion(fixture, { x_m: 2.2, y_m: 2.8, z_m: 1.4 })).toBe(true);
    expect(insideSafeRegion(fixture, { x_m: 2.5, y_m: 2.8, z_m: 1.4 })).toBe(false);
  });

  it("pulls a camera outside the region back to its edge and leaves one inside alone", () => {
    const pulled = clampToSafeRegion(fixture, { x_m: 3.0, y_m: 2.8, z_m: 1.4 });
    expect(pulled?.x_m).toBeCloseTo(2.3);
    expect(insideSafeRegion(fixture, { ...pulled!, x_m: pulled!.x_m - 1e-9 })).toBe(true);
    const inside = { x_m: 2.1, y_m: 2.8, z_m: 1.4 };
    expect(clampToSafeRegion(fixture, inside)).toEqual(inside);
  });

  it("allows no free camera on a twin without viewing limits", () => {
    const bare = structuredClone(fixture);
    delete bare.viewing;
    expect(insideSafeRegion(bare, { x_m: 2.0, y_m: 2.8, z_m: 1.4 })).toBe(false);
    expect(clampToSafeRegion(bare, { x_m: 2.0, y_m: 2.8, z_m: 1.4 })).toBeUndefined();
    expect(heroKeyframes(bare)).toEqual([]);
  });
});

// Property tests with a seeded generator: no extra dependency, reproducible.
function random(seed: number) {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 2 ** 32;
  };
}

function randomTwin(next: () => number): SpaceTwin {
  const twin = structuredClone(fixture);
  const count = Math.floor(next() * 6);
  twin.objects = Array.from({ length: count }, (_, i) => {
    const dim = (): Dimension => ({
      value_m: Math.round(next() * 300) / 100,
      source: next() < 0.5 ? "estimated" : "measured",
      error_band_m: Math.round(next() * 20) / 100,
    });
    return {
      id: `obj-${i}`,
      category: "chair",
      label: `Chair ${i}`,
      box: {
        center: { x_m: next() * 4, y_m: next() * 3, z_m: next() },
        yaw_deg: Math.floor(next() * 360),
        width: dim(),
        depth: dim(),
        height: dim(),
      },
      detection: { source: "server_segmentation", confidence: next() },
      views: [],
      catalog_matches: [],
      state: "keep",
    };
  });
  return twin;
}

function randomEdits(next: () => number, twin: SpaceTwin): TwinEdit[] {
  const ids = [...twin.objects.map((object) => object.id), "missing"];
  const pick = () => ids[Math.floor(next() * ids.length)] ?? "missing";
  return Array.from({ length: Math.floor(next() * 8) }, (_, i): TwinEdit => {
    const id = `e${i}`;
    switch (Math.floor(next() * 5)) {
      case 0:
        return {
          id,
          op: "move",
          by: "user",
          object_id: pick(),
          to: { x_m: next() * 4, y_m: next() * 3, z_m: 0.4 },
        };
      case 1:
        return {
          id,
          op: "rotate",
          by: "solver",
          object_id: pick(),
          yaw_deg: Math.floor(next() * 360),
        };
      case 2:
        return { id, op: "remove", by: "user", object_id: pick() };
      case 3:
        return {
          id,
          op: "replace",
          by: "user",
          object_id: pick(),
          product_id: "p1",
          product_size: size(1, 0.5, 0.8),
        };
      default:
        return {
          id,
          op: "add",
          by: "solver",
          product_id: "p2",
          product_size: size(0.4, 0.4, 0.4),
          to: { x_m: 1, y_m: 1, z_m: 0.2 },
          yaw_deg: 90,
          label: "Stool",
        };
    }
  });
}

describe("twin properties", () => {
  const seeds = Array.from({ length: 200 }, (_, i) => i + 1);

  it.each(seeds)(
    "seed %i: edits never change the twin, results stay valid, views validate",
    (seed) => {
      const next = random(seed);
      const twin = randomTwin(next);
      const edits = randomEdits(next, twin);
      const frozen = structuredClone(twin);

      const applied = applyEdits(twin, edits);
      expect(twin).toEqual(frozen);
      // Deterministic.
      expect(applyEdits(twin, edits)).toEqual(applied);
      // Still a valid twin: every dimension keeps a source and an error band.
      const checked = validate("SpaceTwin", applied.twin);
      expect(checked.ok ? [] : checked.errors).toEqual([]);
      // Moves and rotations never change a measured size.
      const replaced = new Set(
        edits.flatMap((edit) => (edit.op === "replace" ? [edit.object_id] : [])),
      );
      for (const object of applied.twin.objects) {
        const original = twin.objects.find((candidate) => candidate.id === object.id);
        if (original && !replaced.has(object.id)) {
          expect(object.box.width).toEqual(original.box.width);
        }
      }
      const profile = spaceProfileFromTwin(twin, view, edits);
      const profileCheck = validate("SpaceProfile", profile);
      expect(profileCheck.ok ? [] : profileCheck.errors).toEqual([]);
      expect(profile.existing_items).toHaveLength(twin.objects.length);
    },
  );
});
