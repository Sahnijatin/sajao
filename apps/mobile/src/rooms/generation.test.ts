import { GENERATION_STAGES, progressOf, SAMPLE_STAGE_MS, timedGeneration } from "./generation";

describe("generation progress", () => {
  it("names the stage in hand and knows when all three are finished", () => {
    expect(GENERATION_STAGES).toEqual(["walls", "furniture", "looks"]);
    expect(progressOf(0)).toEqual({ finished: 0, current: "walls", done: false });
    expect(progressOf(1)).toEqual({ finished: 1, current: "furniture", done: false });
    expect(progressOf(2)).toEqual({ finished: 2, current: "looks", done: false });
    expect(progressOf(3)).toEqual({ finished: 3, current: null, done: true });
  });

  it("stays in range whatever a source reports", () => {
    expect(progressOf(-2).finished).toBe(0);
    expect(progressOf(9)).toEqual({ finished: 3, current: null, done: true });
    expect(progressOf(1.7).finished).toBe(1);
  });
});

describe("the timed stand-in", () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  it("finishes one stage at a time, then stops", () => {
    const seen: number[] = [];
    timedGeneration().watch("room", (finished) => seen.push(finished));
    jest.advanceTimersByTime(SAMPLE_STAGE_MS - 1);
    expect(seen).toEqual([]);
    jest.advanceTimersByTime(1);
    expect(seen).toEqual([1]);
    jest.advanceTimersByTime(SAMPLE_STAGE_MS * 10);
    expect(seen).toEqual([1, 2, 3]);
  });

  it("stops reporting once nobody is watching", () => {
    const seen: number[] = [];
    const stop = timedGeneration(100).watch("room", (finished) => seen.push(finished));
    jest.advanceTimersByTime(100);
    stop();
    jest.advanceTimersByTime(1000);
    expect(seen).toEqual([1]);
  });
});
