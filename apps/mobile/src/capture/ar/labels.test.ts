import {
  type Detection,
  EMPTY_LABELS,
  FORGET_AFTER_MS,
  labelKindOf,
  type LabelState,
  MAX_RANGE_M,
  MAX_SHOWN,
  MIN_SCORE,
  rejectReason,
  SHOW_MIN_SCORE,
  shownLabels,
  sightingsAgree,
  trackedObjects,
  updateLabels,
} from "./labels";

const at = (x: number, y: number, z: number) => ({ x, y, z });
const seen = (detectorClass: string, world = at(0, 0, -2), score = 0.8): Detection => ({
  detectorClass,
  score,
  world,
});

function feed(batches: Detection[][], start: LabelState = EMPTY_LABELS): LabelState {
  return batches.reduce((state, batch, i) => updateLabels(state, batch, i * 300), start);
}

describe("live object labels", () => {
  it("tracks large objects only; small ones are left to the server twin", () => {
    expect(labelKindOf("refrigerator")).toBe("fridge");
    expect(labelKindOf("couch")).toBe("sofa");
    expect(labelKindOf("dining table")).toBe("table");
    expect(labelKindOf("bed")).toBe("bed");
    expect(labelKindOf("tv")).toBe("tv");
    expect(labelKindOf("potted plant")).toBeNull();
    expect(labelKindOf("chair")).toBeNull();
    expect(labelKindOf("microwave")).toBeNull();
    expect(labelKindOf("person")).toBeNull();
  });

  it("pins a label only after three sightings", () => {
    const twice = feed([[seen("refrigerator")], [seen("refrigerator", at(0.05, 0, -2))]]);
    expect(shownLabels(twice)).toEqual([]);
    const thrice = feed([
      [seen("refrigerator")],
      [seen("refrigerator", at(0.05, 0, -2))],
      [seen("refrigerator", at(0, 0.05, -2))],
    ]);
    expect(shownLabels(thrice)).toEqual([
      expect.objectContaining({ id: "label-1", kind: "fridge" }),
    ]);
  });

  it("never duplicates a label for the same object, however often it is seen", () => {
    const jitter = Array.from({ length: 30 }, (_, i) => [
      seen("couch", at(Math.sin(i) * 0.3, 0, -3 + Math.cos(i) * 0.3)),
    ]);
    const state = feed(jitter);
    expect(shownLabels(state)).toHaveLength(1);
  });

  it("keeps separate labels for separate objects of the same kind", () => {
    const state = feed([
      [seen("couch", at(0, 0, -2)), seen("couch", at(2, 0, -2))],
      [seen("couch", at(0, 0, -2)), seen("couch", at(2, 0, -2))],
      [seen("couch", at(0, 0, -2)), seen("couch", at(2, 0, -2))],
    ]);
    expect(shownLabels(state).map((label) => label.kind)).toEqual(["sofa", "sofa"]);
  });

  it("sticks: one stray sighting does not move a label", () => {
    let state = feed(Array.from({ length: 5 }, () => [seen("refrigerator", at(1, 1, -1))]));
    state = updateLabels(state, [seen("refrigerator", at(1.3, 1, -1))], 2000);
    const [label] = shownLabels(state);
    expect(label?.x).toBeCloseTo(1);
  });

  it("settles on the name seen most when the detector disagrees", () => {
    const state = feed([
      [seen("bed", at(0, 0, -2), 0.5)],
      [seen("couch", at(0.1, 0, -2), 0.9)],
      [seen("couch", at(0, 0, -2), 0.9)],
      [seen("couch", at(0, 0.1, -2), 0.9)],
    ]);
    expect(shownLabels(state)).toEqual([expect.objectContaining({ kind: "sofa" })]);
  });

  it("ignores weak detections and ones the raycast missed", () => {
    const state = feed([
      [seen("refrigerator", at(0, 0, -2), MIN_SCORE - 0.1), { ...seen("couch"), world: null }],
      [seen("refrigerator", at(0, 0, -2), MIN_SCORE - 0.1), { ...seen("couch"), world: null }],
    ]);
    expect(state.labels).toEqual([]);
  });

  it("is pure: the previous state is not changed", () => {
    const before = feed([[seen("tv")]]);
    const copy = JSON.parse(JSON.stringify(before));
    updateLabels(before, [seen("tv")], 999);
    expect(before).toEqual(copy);
  });

  describe("only a few confident labels are shown", () => {
    it("tracks a pinned object seen with middling confidence but does not show it", () => {
      const unsure = SHOW_MIN_SCORE - 0.1;
      const state = feed([
        [seen("bed", at(0, 0, -2), unsure)],
        [seen("bed", at(0, 0, -2), unsure)],
        [seen("bed", at(0, 0, -2), unsure)],
      ]);
      expect(shownLabels(state)).toEqual([]);
      expect(trackedObjects(state)).toEqual([expect.objectContaining({ kind: "bed" })]);
    });

    it(`shows at most ${MAX_SHOWN}, the most confident`, () => {
      const objects = Array.from({ length: 8 }, (_, i) =>
        seen("couch", at(i * 3, 0, -2), 0.62 + i * 0.04),
      );
      const state = feed([objects, objects, objects]);
      const shown = shownLabels(state);
      expect(shown).toHaveLength(MAX_SHOWN);
      // The three least confident (x = 0, 3, 6) are left out.
      expect(shown.map((label) => label.x)).toEqual([9, 12, 15, 18, 21]);
    });
  });

  describe("sightings that cannot be their object", () => {
    const three = (detection: Detection) => feed([[detection], [detection], [detection]]);

    it("drops a fridge whose ray ends flat on a door or wall", () => {
      const door = { ...seen("refrigerator"), surface: "wall" as const, gap: 0.02 };
      const state = three(door);
      expect(shownLabels(state)).toEqual([]);
      expect(state.rejected).toBe(3);
      expect(rejectReason("fridge", door)).toBe("onWall");
    });

    it("keeps a fridge that stands in front of the wall", () => {
      const fridge = { ...seen("refrigerator"), surface: "wall" as const, gap: 0.6 };
      expect(shownLabels(three(fridge))).toHaveLength(1);
    });

    it("keeps a TV on the wall", () => {
      const tv = { ...seen("tv"), surface: "wall" as const, gap: 0 };
      expect(shownLabels(three(tv))).toHaveLength(1);
    });

    it("drops a sofa on empty floor, keeps one standing there", () => {
      const empty = { ...seen("couch"), surface: "floor" as const, gap: 0.01 };
      expect(rejectReason("sofa", empty)).toBe("bareFloor");
      expect(shownLabels(three(empty))).toEqual([]);
      const sofa = { ...seen("couch"), surface: "floor" as const, gap: 0.5 };
      expect(shownLabels(three(sofa))).toHaveLength(1);
    });

    it("drops a sighting with no gap reading on a wall, the ceiling, or beyond range", () => {
      expect(rejectReason("sofa", { ...seen("couch"), surface: "wall", gap: null })).toBe("onWall");
      expect(rejectReason("bed", { ...seen("bed"), surface: "ceiling" })).toBe("ceiling");
      expect(rejectReason("table", { ...seen("dining table"), range: MAX_RANGE_M + 1 })).toBe(
        "tooFar",
      );
    });

    it("keeps sightings from older builds that send no surface", () => {
      expect(rejectReason("fridge", seen("refrigerator"))).toBeNull();
    });
  });

  it("does not pin sightings that disagree on where the object is", () => {
    const state = feed([
      [seen("refrigerator", at(0, 0, -2))],
      [seen("refrigerator", at(0.5, 0, -2))],
      [seen("refrigerator", at(0, 0.5, -2))],
    ]);
    expect(shownLabels(state)).toEqual([]);
    expect(sightingsAgree("fridge", [at(0, 0, -2), at(0.1, 0, -2), at(0, 0.1, -2)])).toBe(true);
  });

  it("forgets an unpinned label that is not seen again, keeps pinned ones", () => {
    const tentative = feed([[seen("refrigerator", at(0, 0, -2))]]);
    expect(updateLabels(tentative, [], FORGET_AFTER_MS + 1).labels).toEqual([]);
    const pinned = feed([[seen("refrigerator")], [seen("refrigerator")], [seen("refrigerator")]]);
    expect(shownLabels(updateLabels(pinned, [], 60_000))).toHaveLength(1);
  });
});
