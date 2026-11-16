import {
  type Detection,
  EMPTY_LABELS,
  FORGET_AFTER_MS,
  labelKindOf,
  type LabelState,
  MAX_RANGE_M,
  MIN_SCORE,
  rejectReason,
  shownLabels,
  sightingsAgree,
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
  it("names household objects and ignores the rest", () => {
    expect(labelKindOf("refrigerator")).toBe("fridge");
    expect(labelKindOf("couch")).toBe("sofa");
    expect(labelKindOf("potted plant")).toBe("plant");
    expect(labelKindOf("dining table")).toBe("table");
    expect(labelKindOf("person")).toBeNull();
    expect(labelKindOf("car")).toBeNull();
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
      [seen("chair", at(0, 0, -2)), seen("chair", at(1.5, 0, -2))],
      [seen("chair", at(0, 0, -2)), seen("chair", at(1.5, 0, -2))],
      [seen("chair", at(0, 0, -2)), seen("chair", at(1.5, 0, -2))],
    ]);
    expect(shownLabels(state).map((label) => label.kind)).toEqual(["chair", "chair"]);
  });

  it("sticks: one stray sighting does not move a label", () => {
    let state = feed(Array.from({ length: 5 }, () => [seen("microwave", at(1, 1, -1))]));
    state = updateLabels(state, [seen("microwave", at(1.3, 1, -1))], 2000);
    const [label] = shownLabels(state);
    expect(label?.x).toBeCloseTo(1);
  });

  it("settles on the name seen most when the detector disagrees", () => {
    const state = feed([
      [seen("bench", at(0, 0, -2), 0.5)],
      [seen("couch", at(0.1, 0, -2), 0.9)],
      [seen("couch", at(0, 0, -2), 0.9)],
      [seen("couch", at(0, 0.1, -2), 0.9)],
    ]);
    expect(shownLabels(state)).toEqual([expect.objectContaining({ kind: "sofa" })]);
  });

  it("ignores weak detections and ones the raycast missed", () => {
    const state = feed([
      [seen("refrigerator", at(0, 0, -2), MIN_SCORE - 0.1), { ...seen("chair"), world: null }],
      [seen("refrigerator", at(0, 0, -2), MIN_SCORE - 0.1), { ...seen("chair"), world: null }],
    ]);
    expect(state.labels).toEqual([]);
  });

  it("is pure: the previous state is not changed", () => {
    const before = feed([[seen("tv")]]);
    const copy = JSON.parse(JSON.stringify(before));
    updateLabels(before, [seen("tv")], 999);
    expect(before).toEqual(copy);
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

    it("drops a chair on empty floor, keeps one standing there", () => {
      const empty = { ...seen("chair"), surface: "floor" as const, gap: 0.01 };
      expect(rejectReason("chair", empty)).toBe("bareFloor");
      expect(shownLabels(three(empty))).toEqual([]);
      const chair = { ...seen("chair"), surface: "floor" as const, gap: 0.5 };
      expect(shownLabels(three(chair))).toHaveLength(1);
    });

    it("drops a sighting with no gap reading on a wall, the ceiling, or beyond range", () => {
      expect(rejectReason("sofa", { ...seen("couch"), surface: "wall", gap: null })).toBe("onWall");
      expect(rejectReason("plant", { ...seen("potted plant"), surface: "ceiling" })).toBe(
        "ceiling",
      );
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
      [seen("potted plant", at(0, 0, -2))],
      [seen("potted plant", at(0.35, 0, -2))],
      [seen("potted plant", at(0, 0.35, -2))],
    ]);
    expect(shownLabels(state)).toEqual([]);
    expect(sightingsAgree("plant", [at(0, 0, -2), at(0.1, 0, -2), at(0, 0.1, -2)])).toBe(true);
  });

  it("forgets an unpinned label that is not seen again, keeps pinned ones", () => {
    const tentative = feed([[seen("sink", at(0, 0, -2))]]);
    expect(updateLabels(tentative, [], FORGET_AFTER_MS + 1).labels).toEqual([]);
    const pinned = feed([[seen("sink")], [seen("sink")], [seen("sink")]]);
    expect(shownLabels(updateLabels(pinned, [], 60_000))).toHaveLength(1);
  });
});
