import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import bundle from "../generated/v1.schema.json" with { type: "json" };
import { OBJECT_NAMES, type ObjectName } from "./index";
import { validate } from "./validate";

const fixtures = join(import.meta.dirname, "..", "fixtures", "v1");
const load = (path: string): unknown => JSON.parse(readFileSync(path, "utf8"));

// "space-profile.dimension-without-source.json" -> "SpaceProfile"
function objectName(file: string): ObjectName {
  const kebab = file.split(".")[0] ?? "";
  const name = kebab.replace(/(^|-)([a-z])/g, (_match, _dash, letter: string) =>
    letter.toUpperCase(),
  );
  if (!OBJECT_NAMES.includes(name as ObjectName)) throw new Error(`Unknown object in ${file}`);
  return name as ObjectName;
}

describe("contract v1", () => {
  it("lists exactly the objects the schemas define", () => {
    expect([...OBJECT_NAMES].sort()).toEqual([...bundle["x-top-level"]].sort());
  });

  const valid = readdirSync(join(fixtures, "valid"));
  it("has a valid fixture for every object", () => {
    expect(valid.map(objectName).sort()).toEqual([...OBJECT_NAMES].sort());
  });

  it.each(valid)("accepts valid/%s and survives a JSON round trip", (file) => {
    const data = load(join(fixtures, "valid", file));
    const result = validate(objectName(file), data);
    expect(result).toEqual({ ok: true, value: data });
    const again = validate(objectName(file), JSON.parse(JSON.stringify(data)));
    expect(again).toEqual(result);
  });

  it.each(readdirSync(join(fixtures, "invalid")))("rejects invalid/%s", (file) => {
    const result = validate(objectName(file), load(join(fixtures, "invalid", file)));
    expect(result.ok).toBe(false);
  });
});

describe("scan any space at any extent", () => {
  const whole = load(join(fixtures, "valid", "space-profile.json")) as Record<string, unknown>;

  it("accepts a corner of a balcony with two walls and a part to redo", () => {
    const corner = {
      ...whole,
      space_type: "balcony",
      space_type_source: "user",
      extent: "part",
      walls: (whole.walls as unknown[]).slice(0, 2),
      redo: { scope: "part", polygon: (whole.floor_polygon as unknown[]).slice(0, 3) },
    };
    expect(validate("SpaceProfile", corner).ok).toBe(true);
  });

  it("has no room type on a capture: the space type is detected, not picked", () => {
    expect(Object.keys(bundle.$defs.Capture.properties)).not.toContain("room_type");
    expect(Object.keys(bundle.$defs.Capture.properties)).not.toContain("space_type");
  });
});

describe("dimension honesty", () => {
  const dimension = bundle.$defs.Dimension;

  it("requires a value, a source and an error band on every dimension", () => {
    expect([...dimension.required].sort()).toEqual(["error_band_m", "source", "value_m"]);
  });

  it("uses the Dimension type for every length that is not a plain coordinate", () => {
    // Bare numbers in metres are allowed only for coordinates, derived plan
    // sizes, raw tape input, rule thresholds and viewing limits. Anything else must be a Dimension.
    const allowed = new Set([
      "Dimension.value_m",
      "Dimension.error_band_m",
      "Point2.x_m",
      "Point2.y_m",
      "Point3.x_m",
      "Point3.y_m",
      "Point3.z_m",
      "ArPoint.x_m",
      "ArPoint.y_m",
      "ArPoint.z_m",
      "PlanItem.width_m",
      "PlanItem.depth_m",
      "Clearance.minimum_m",
      "TapeMeasurement.value_m",
      "ViewOrbit.max_offset_m",
      "SafeRegion.radius_m",
    ]);
    const bare: string[] = [];
    const walk = (node: unknown, owner: string): void => {
      if (node === null || typeof node !== "object") return;
      const schema = node as { title?: string; properties?: Record<string, unknown> };
      const name = schema.title ?? owner;
      for (const [key, value] of Object.entries(schema.properties ?? {})) {
        if (key.endsWith("_m") && !allowed.has(`${name}.${key}`)) bare.push(`${name}.${key}`);
        walk(value, name);
      }
      for (const value of Object.values(node)) walk(value, name);
    };
    for (const [name, schema] of Object.entries(bundle.$defs)) walk(schema, name);
    expect(bare).toEqual([]);
  });
});
