import {
  cellOf,
  chosenKeyframes,
  type KeyframeCandidate,
  MAX_KEYFRAMES,
  NO_KEYFRAMES,
  offerKeyframe,
  PLACE_CELL_M,
} from "./keyframes";

const frame = (change: Partial<KeyframeCandidate>): KeyframeCandidate => ({
  uri: `file:///kf-${Math.random()}.jpg`,
  atMs: 0,
  sharpness: 50,
  yaw: 0,
  pitch: 0,
  x: 0.1,
  z: 0.1,
  ...change,
});

describe("keyframes by viewpoint", () => {
  it("names a viewpoint by the place stood and the direction looked, as the native gate does", () => {
    // Same strings as KeyframeGate.cellFor in CaptureFormats.kt and CaptureRecorder.swift.
    expect(cellOf(frame({ yaw: 10, x: 0.2, z: 0.4 }))).toBe("p0_0-d0-1");
    expect(cellOf(frame({ yaw: 10, x: 0.7, z: 0.4 }))).toBe("p1_0-d0-1");
    expect(cellOf(frame({ yaw: 10, x: -0.1, z: -1.2 }))).toBe("p-1_-3-d0-1");
    expect(PLACE_CELL_M).toBe(0.5);
  });

  it("time alone never adds a keyframe: standing still looking one way keeps one", () => {
    let set = NO_KEYFRAMES;
    for (let i = 0; i < 80; i += 1) set = offerKeyframe(set, frame({ atMs: i * 1500 }));
    expect(set.size).toBe(1);
  });

  it("turning on one spot is bounded; walking keeps adding viewpoints", () => {
    let spin = NO_KEYFRAMES;
    for (let turn = 0; turn < 3; turn += 1) {
      for (let yaw = 0; yaw < 360; yaw += 5) {
        spin = offerKeyframe(spin, frame({ yaw, atMs: turn * 72_000 + yaw * 200 }));
      }
    }
    expect(spin.size).toBe(12); // one per 30 degrees, however many times round

    let walk = spin;
    for (let step = 1; step <= 10; step += 1) {
      for (let yaw = 0; yaw < 360; yaw += 30) {
        walk = offerKeyframe(walk, frame({ yaw, x: step * 0.6, atMs: 300_000 + step * 1000 }));
      }
    }
    expect(walk.size).toBe(12 + 10 * 12);
  });

  it("the same viewpoint keeps its sharpest frame", () => {
    let set = offerKeyframe(NO_KEYFRAMES, frame({ uri: "a", sharpness: 50 }));
    set = offerKeyframe(set, frame({ uri: "b", sharpness: 52, x: 0.3 }));
    expect(chosenKeyframes(set).map((k) => k.uri)).toEqual(["a"]);
    set = offerKeyframe(set, frame({ uri: "c", sharpness: 80, x: 0.3 }));
    expect(chosenKeyframes(set).map((k) => k.uri)).toEqual(["c"]);
  });

  it("stops at 200 viewpoints", () => {
    expect(MAX_KEYFRAMES).toBe(200);
    let set = NO_KEYFRAMES;
    for (let i = 0; i < 260; i += 1) set = offerKeyframe(set, frame({ x: i * 0.6, atMs: i }));
    expect(set.size).toBe(200);
  });

  it("without AR tracking there is no place, so frames are still kept by time", () => {
    const lost = { yaw: null, pitch: null, x: null, z: null };
    expect(cellOf(frame({ ...lost, atMs: 3200 }))).toBe("t2");
    let set = NO_KEYFRAMES;
    for (let i = 0; i < 4; i += 1) set = offerKeyframe(set, frame({ ...lost, atMs: i * 1500 }));
    expect(set.size).toBe(4);
  });

  it("a pose without a position still falls back to direction", () => {
    expect(cellOf(frame({ yaw: 75, pitch: 25, x: undefined, z: undefined }))).toBe("d2-2");
  });
});
