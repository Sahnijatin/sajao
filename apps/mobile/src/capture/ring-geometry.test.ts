import { ringSweepDegrees } from "./ring-geometry";

describe("progress ring", () => {
  it("sweeps in proportion and never draws an empty full circle", () => {
    expect(ringSweepDegrees(0)).toBe(0);
    expect(ringSweepDegrees(-1)).toBe(0);
    expect(ringSweepDegrees(Number.NaN)).toBe(0);
    expect(ringSweepDegrees(0.5)).toBe(180);
    expect(ringSweepDegrees(1)).toBe(359.9);
    expect(ringSweepDegrees(3)).toBe(359.9);
  });
});
