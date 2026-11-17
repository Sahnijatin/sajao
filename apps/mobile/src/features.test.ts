import { twinViewerEnabled } from "./features";

describe("feature flags", () => {
  it("the 3D view is off unless its value is exactly 1", () => {
    expect(twinViewerEnabled(undefined)).toBe(false);
    expect(twinViewerEnabled("")).toBe(false);
    expect(twinViewerEnabled("0")).toBe(false);
    expect(twinViewerEnabled("true")).toBe(false);
    expect(twinViewerEnabled("1")).toBe(true);
  });
});
