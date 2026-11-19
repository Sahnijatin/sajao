import { afterAdding, afterMeasured, flowRoute } from "./flow";

describe("from adding a room to its stages", () => {
  it("the first room is asked taste, with its budget; a later room only its budget", () => {
    expect(afterAdding({ hasTaste: false })).toBe("taste");
    expect(afterAdding({ hasTaste: true })).toBe("budget");
  });

  it("goes to the question's screen for that room", () => {
    expect(flowRoute("taste", "r")).toEqual({ pathname: "/taste", params: { room: "r" } });
    expect(flowRoute("budget", "r")).toEqual({ pathname: "/budget", params: { room: "r" } });
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
