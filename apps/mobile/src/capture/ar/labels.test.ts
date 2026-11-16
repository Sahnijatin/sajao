import {
  type Detection,
  EMPTY_LABELS,
  labelKindOf,
  type LabelState,
  MIN_SCORE,
  shownLabels,
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

  it("shows a label only after a second sighting", () => {
    const once = feed([[seen("refrigerator")]]);
    expect(shownLabels(once)).toEqual([]);
    const twice = feed([[seen("refrigerator")], [seen("refrigerator", at(0.05, 0, -2))]]);
    expect(shownLabels(twice)).toEqual([
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
    ]);
    expect(shownLabels(state).map((label) => label.kind)).toEqual(["chair", "chair"]);
  });

  it("sticks: a label moves only a little toward a stray sighting", () => {
    let state = feed(Array.from({ length: 5 }, () => [seen("microwave", at(1, 1, -1))]));
    state = updateLabels(state, [seen("microwave", at(1.3, 1, -1))], 2000);
    const [label] = shownLabels(state);
    expect(label?.x).toBeGreaterThan(1);
    expect(label?.x).toBeLessThan(1.1);
  });

  it("settles on the name seen most when the detector disagrees", () => {
    const state = feed([
      [seen("bench", at(0, 0, -2), 0.5)],
      [seen("couch", at(0.1, 0, -2), 0.9)],
      [seen("couch", at(0, 0, -2), 0.9)],
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
});
