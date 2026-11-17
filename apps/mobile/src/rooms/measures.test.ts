import type { SpaceTwin } from "@sajao/schemas";
import fixture from "../../../../packages/schemas/fixtures/v1/valid/space-twin.json";
import { BIG_ITEM_FROM_M, MAX_BIG_ITEMS, measuresFromTwin } from "./measures";

const twin = fixture as unknown as SpaceTwin;
const dimension = (value_m: number) => ({
  value_m,
  source: "estimated" as const,
  error_band_m: 0.05,
});
const object = (id: string, width: number, depth: number, height: number) => ({
  ...twin.objects[0]!,
  id,
  label: id,
  box: {
    ...twin.objects[0]!.box,
    width: dimension(width),
    depth: dimension(depth),
    height: dimension(height),
  },
});

describe("room measures from the twin", () => {
  const measures = measuresFromTwin(twin);

  it("numbers the walls in order and keeps each length with its source and band", () => {
    expect(measures.walls).toEqual([
      { id: "w1", number: 1, length: { value_m: 4.2, source: "measured", error_band_m: 0.01 } },
      { id: "w2", number: 2, length: { value_m: 3.4, source: "estimated", error_band_m: 0.12 } },
      { id: "w3", number: 3, length: { value_m: 4.2, source: "estimated", error_band_m: 0.15 } },
      {
        id: "w4",
        number: 4,
        length: { value_m: 3.4, source: "user_confirmed", error_band_m: 0.12 },
      },
    ]);
    expect(measures.ceiling).toEqual(twin.shell.ceiling_height);
  });

  it("works the floor area out from the floor polygon", () => {
    expect(measures.areaM2).toBeCloseTo(4.2 * 3.4, 6);
  });

  it("lists doors and windows with the wall each is in", () => {
    expect(measures.openings.map(({ id, kind, wallNumber }) => ({ id, kind, wallNumber }))).toEqual(
      [
        { id: "d1", kind: "door", wallNumber: 4 },
        { id: "win1", kind: "window", wallNumber: 1 },
      ],
    );
    expect(measures.openings[0]?.width).toEqual(twin.shell.openings[0]?.width);
  });

  it("copes with an opening on a wall the twin does not have", () => {
    const odd = {
      ...twin,
      shell: {
        ...twin.shell,
        openings: [{ ...twin.shell.openings[0]!, wall_id: "nowhere" }],
      },
    } as SpaceTwin;
    expect(measuresFromTwin(odd).openings[0]?.wallNumber).toBeNull();
  });

  it("lists the big items, biggest first, with the twin's own sizes", () => {
    expect(measures.bigItems.map((item) => item.label)).toEqual([
      "Grey three-seater sofa",
      "Steel almirah",
    ]);
    expect(measures.bigItems[0]?.width).toEqual(twin.objects[0]?.box.width);
  });

  it("leaves out small things, and stops at the limit", () => {
    const small = object("vase", 0.2, 0.2, BIG_ITEM_FROM_M - 0.01);
    const tall = object("lamp", 0.3, 0.3, BIG_ITEM_FROM_M);
    const many = Array.from({ length: 12 }, (_, index) => object(`bed-${index}`, 2, 1.5, 0.5));
    const result = measuresFromTwin({ ...twin, objects: [small, tall, ...many] } as SpaceTwin);
    expect(result.bigItems).toHaveLength(MAX_BIG_ITEMS);
    expect(result.bigItems.some((item) => item.id === "vase")).toBe(false);
    expect(
      measuresFromTwin({ ...twin, objects: [small, tall] } as SpaceTwin).bigItems.map((i) => i.id),
    ).toEqual(["lamp"]);
  });
});
