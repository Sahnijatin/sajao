import { afterMeasured, afterReview, afterSpace } from "./flow";

describe("from Looks good to the stages", () => {
  it("the first room goes through the space profile, then taste, then the stages", () => {
    expect(afterReview({ hasSpaceProfile: true, hasTaste: false })).toBe("space");
    expect(afterSpace({ hasTaste: false })).toBe("taste");
  });

  it("a later room skips taste: it was asked once", () => {
    expect(afterReview({ hasSpaceProfile: true, hasTaste: true })).toBe("space");
    expect(afterSpace({ hasTaste: true })).toBe("generating");
  });

  it("with no space profile yet, the flow does not stop on an empty screen", () => {
    expect(afterReview({ hasSpaceProfile: false, hasTaste: false })).toBe("taste");
    expect(afterReview({ hasSpaceProfile: false, hasTaste: true })).toBe("generating");
  });
});

describe("once the room is measured", () => {
  it("a scan of one area goes straight on", () => {
    expect(afterMeasured({ areas: 0, chosen: false })).toBe("on");
    expect(afterMeasured({ areas: 1, chosen: false })).toBe("on");
  });

  it("a scan of several areas asks which to redesign, once", () => {
    expect(afterMeasured({ areas: 3, chosen: false })).toBe("areas");
    expect(afterMeasured({ areas: 3, chosen: true })).toBe("on");
  });
});
