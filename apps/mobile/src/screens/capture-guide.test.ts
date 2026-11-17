import { coverageStep, scanInstruction, shouldTick } from "./capture-guide";

const base = { pausedFor: null, hint: null, share: 0, ready: false } as const;

describe("the scan's one instruction", () => {
  it("starts with moving slowly, then asks for the corners", () => {
    expect(scanInstruction(base)).toEqual({ id: "move", tone: "guide" });
    expect(scanInstruction({ ...base, share: 0.49 }).id).toBe("move");
    expect(scanInstruction({ ...base, share: 0.5 })).toEqual({ id: "corners", tone: "guide" });
  });

  it("says there is enough as soon as Done is ready, and when everything is covered", () => {
    expect(scanInstruction({ ...base, share: 0.75, ready: true })).toEqual({
      id: "enough",
      tone: "guide",
    });
    expect(
      scanInstruction({ ...base, share: 0.8, ready: true, hint: { id: "coverMore" } }).id,
    ).toBe("enough");
    // Nothing asks for more once there is enough.
    for (const id of ["slowDown", "stepBack", "walk", "keepGoing", "oneMoreSpot"] as const) {
      expect(scanInstruction({ ...base, share: 0.8, ready: true, hint: { id } }).id).toBe("enough");
    }
    for (const id of ["complete", "meterDone"] as const) {
      expect(scanInstruction({ ...base, share: 1, ready: true, hint: { id } })).toEqual({
        id: "complete",
        tone: "guide",
      });
    }
  });

  it("nudges only when the scan asks for it", () => {
    expect(scanInstruction({ ...base, hint: { id: "slowDown" } })).toEqual({
      id: "slowDown",
      tone: "nudge",
    });
    for (const id of ["doorway", "stepBack", "walk"] as const) {
      expect(scanInstruction({ ...base, hint: { id } }).tone).toBe("nudge");
    }
  });

  it("never names an object to walk around: the steady guide carries on", () => {
    const hint = { id: "walkAround", kind: "fridge" } as const;
    expect(scanInstruction({ ...base, hint })).toEqual({ id: "move", tone: "guide" });
    expect(scanInstruction({ ...base, share: 0.6, hint }).id).toBe("corners");
    expect(scanInstruction({ ...base, share: 0.8, ready: true, hint }).id).toBe("enough");
  });

  it("puts a pause ahead of every hint", () => {
    const paused = { ...base, hint: { id: "slowDown" } as const, share: 0.9, ready: true };
    expect(scanInstruction({ ...paused, pausedFor: "light" })).toEqual({ id: "dark", tone: "fix" });
    expect(scanInstruction({ ...paused, pausedFor: "motion" }).id).toBe("fast");
    expect(scanInstruction({ ...paused, pausedFor: "glare" }).id).toBe("glare");
  });

  it("never stops the scan for a tilted phone", () => {
    expect(scanInstruction({ ...base, pausedFor: "level" })).toEqual({ id: "move", tone: "guide" });
  });
});

describe("haptic ticks as coverage grows", () => {
  it("ticks once per tenth", () => {
    expect(coverageStep(0)).toBe(0);
    expect(coverageStep(0.09)).toBe(0);
    expect(coverageStep(0.1)).toBe(1);
    expect(coverageStep(0.3)).toBe(3);
    expect(coverageStep(1)).toBe(10);
    let step = 0;
    let ticks = 0;
    for (let share = 0; share <= 1.0001; share += 0.01) {
      if (shouldTick(step, share)) {
        ticks += 1;
        step = coverageStep(share);
      }
    }
    expect(ticks).toBe(10);
  });

  it("does not tick when coverage stands still or a reading is bad", () => {
    expect(shouldTick(3, 0.35)).toBe(false);
    expect(shouldTick(3, 0.2)).toBe(false);
    expect(coverageStep(Number.NaN)).toBe(0);
    expect(coverageStep(4)).toBe(10);
    expect(coverageStep(-1)).toBe(0);
  });
});
