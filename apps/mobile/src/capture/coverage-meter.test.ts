import {
  addMeterSample,
  canFinishAnyway,
  EMPTY_METER,
  FINISH_ANYWAY_AFTER_MS,
  loopOf,
  meterDone,
  meterFraction,
  meterHint,
  meterMissing,
  meterParts,
  type MeterState,
  nextSweepSpot,
  sweepsOf,
  walkedCells,
} from "./coverage-meter";

let clock = 0;
const tick = () => (clock += 100);

beforeEach(() => {
  clock = 0;
});

/** Walk the walls of a room `width` by `depth` metres, half a metre in from them. */
function loop(state: MeterState, width = 4, depth = 3.5, share = 1): MeterState {
  const inset = 0.5;
  const corners = [
    [inset, inset],
    [width - inset, inset],
    [width - inset, depth - inset],
    [inset, depth - inset],
    [inset, inset],
  ] as const;
  const points: { x: number; z: number }[] = [];
  for (let i = 0; i + 1 < corners.length; i += 1) {
    const [x0, z0] = corners[i] as readonly [number, number];
    const [x1, z1] = corners[i + 1] as readonly [number, number];
    const steps = Math.ceil(Math.hypot(x1 - x0, z1 - z0) / 0.1);
    for (let s = 0; s < steps; s += 1) {
      points.push({ x: x0 + ((x1 - x0) * s) / steps, z: z0 + ((z1 - z0) * s) / steps });
    }
  }
  let next = state;
  for (const position of points.slice(0, Math.round(points.length * share))) {
    // Facing across the room, level.
    const yaw = (Math.atan2(width / 2 - position.x, depth / 2 - position.z) * 180) / Math.PI;
    next = addMeterSample(next, { position, yaw, pitch: 0, atMs: tick() });
  }
  return next;
}

/** Stand on one spot and turn slowly through `degrees`, looking down for a share of it. */
function sweep(
  state: MeterState,
  spot: { x: number; z: number },
  degrees = 360,
  downShare = 0.4,
): MeterState {
  let next = state;
  const samples = Math.round(degrees / 3);
  for (let i = 0; i < samples; i += 1) {
    next = addMeterSample(next, {
      // The phone wanders a few centimetres as a person turns.
      position: { x: spot.x + 0.03 * Math.sin(i), z: spot.z + 0.03 * Math.cos(i) },
      yaw: i * 3,
      pitch: i % 10 < downShare * 10 ? -30 : 0,
      atMs: tick(),
    });
  }
  return next;
}

// Inside the loop and with room for a second sweep a metre away.
const MIDDLE = { x: 2.5, z: 1.75 };

describe("coverage meter", () => {
  it("Done needs the loop and two sweeps a metre apart", () => {
    let state = loop(EMPTY_METER);
    expect(loopOf(state).complete).toBe(true);
    expect(meterDone(state)).toBe(false);
    expect(meterHint(state)).toBe("standMiddle");

    state = sweep(state, MIDDLE);
    expect(sweepsOf(state).counted).toBe(1);
    expect(meterDone(state)).toBe(false);
    expect(meterHint(state)).toBe("oneMoreSpot");

    state = sweep(state, { x: 2.6, z: 2.0 }); // under a metre from the first
    expect(sweepsOf(state).counted).toBe(1);

    state = sweep(state, { x: 1.4, z: 1.75 }); // over a metre from the one that counted
    expect(sweepsOf(state).counted).toBe(2);
    expect(meterDone(state)).toBe(true);
    expect(meterHint(state)).toBe("meterDone");
    expect(meterFraction(state)).toBe(1);
  });

  it("turning in the middle fills no loop sector, however long", () => {
    let state = EMPTY_METER;
    for (let turn = 0; turn < 4; turn += 1) state = sweep(state, MIDDLE);
    expect(loopOf(state).count).toBe(0);
    expect(meterParts(state).loop).toBeLessThan(0.1);
    expect(meterDone(state)).toBe(false);
    expect(meterHint(state)).toBe("walkWalls");
  });

  it("one spot by the door no longer passes: a turn and three metres of pacing", () => {
    let state = sweep(EMPTY_METER, { x: 0.6, z: 0.6 });
    for (let i = 0; i < 30; i += 1) {
      state = addMeterSample(state, {
        position: { x: 0.6 + (i % 2) * 0.1, z: 0.6 },
        yaw: 0,
        pitch: 0,
        atMs: tick(),
      });
    }
    expect(meterDone(state)).toBe(false);
    expect(loopOf(state).count).toBe(0);
    expect(meterFraction(state)).toBeLessThanOrEqual(0.5);
  });

  it("a loop walked part of the way says to keep going and names what is missing", () => {
    const state = loop(EMPTY_METER, 4, 3.5, 0.5);
    expect(loopOf(state).complete).toBe(false);
    expect(meterHint(state)).toBe("keepGoing");
    const missing = meterMissing(state);
    expect(missing.loopBearings.length).toBeGreaterThanOrEqual(3);
    expect(missing.sweepsNeeded).toBe(2);
  });

  it("a sweep that never looks down asks for a tilt and does not count", () => {
    let state = loop(EMPTY_METER);
    state = sweep(state, MIDDLE, 360, 0);
    expect(sweepsOf(state).counted).toBe(0);
    expect(meterHint(state)).toBe("tiltDown");
    expect(meterMissing(state).floorLook).toBe(true);
    state = sweep(state, MIDDLE, 360, 0.6);
    expect(sweepsOf(state).counted).toBe(1);
  });

  it("a sweep beside the wall is the loop again, not a view from the middle", () => {
    let state = loop(EMPTY_METER);
    state = sweep(state, { x: 0.6, z: 1.75 });
    expect(sweepsOf(state).all.some((s) => s.complete)).toBe(true);
    expect(sweepsOf(state).counted).toBe(0);
  });

  it("a space under 2.5 m across needs one sweep", () => {
    let state = EMPTY_METER;
    // A balcony 1.8 by 1.6 m: round it three times to walk six metres.
    for (let i = 0; i < 3; i += 1) state = loop(state, 1.8, 1.6);
    expect(loopOf(state).acrossM).toBeLessThan(2.5);
    expect(loopOf(state).complete).toBe(true);
    state = sweep(state, { x: 0.9, z: 0.8 });
    expect(sweepsOf(state).needed).toBe(1);
    expect(meterDone(state)).toBe(true);
  });

  it("the ring never goes backwards as the centre of the walk moves", () => {
    const walk = loop(EMPTY_METER);
    // Replay the same walk a sample at a time and watch the ring.
    let state = EMPTY_METER;
    let last = 0;
    clock = 0;
    for (const position of walk.positions) {
      state = addMeterSample(state, { position, yaw: 0, pitch: 0, atMs: tick() });
      const now = meterFraction(state);
      expect(now).toBeGreaterThanOrEqual(last);
      last = now;
    }
    expect(meterParts(state).loop).toBe(1);
  });

  it("offers Finish anyway after a minute without progress, and not before", () => {
    let state = loop(EMPTY_METER, 4, 3.5, 0.5);
    const stalledAt = state.progressMs as number;
    // Standing still at the last place: samples arrive, nothing moves forward.
    const here = state.lastPosition as { x: number; z: number };
    for (let i = 0; i < 20; i += 1) {
      state = addMeterSample(state, { position: here, yaw: 0, pitch: 0, atMs: tick() });
    }
    expect(state.progressMs).toBe(stalledAt);
    expect(canFinishAnyway(state, stalledAt + FINISH_ANYWAY_AFTER_MS - 1)).toBe(false);
    expect(canFinishAnyway(state, stalledAt + FINISH_ANYWAY_AFTER_MS)).toBe(true);
    // Moving on again takes the offer away.
    clock = stalledAt + FINISH_ANYWAY_AFTER_MS;
    state = loop(state);
    expect(canFinishAnyway(state, clock)).toBe(false);
  });

  it("never offers Finish anyway on a finished scan or before anything was scanned", () => {
    expect(canFinishAnyway(EMPTY_METER, 10 * FINISH_ANYWAY_AFTER_MS)).toBe(false);
    let state = loop(EMPTY_METER);
    state = sweep(state, MIDDLE);
    state = sweep(state, { x: 1.4, z: 1.75 });
    expect(canFinishAnyway(state, clock + 10 * FINISH_ANYWAY_AFTER_MS)).toBe(false);
  });

  it("points at the middle for the first sweep, then away from it", () => {
    let state = loop(EMPTY_METER);
    const first = nextSweepSpot(state) as { x: number; z: number };
    expect(Math.hypot(first.x - 2, first.z - 1.75)).toBeLessThan(0.3); // the room's middle
    state = sweep(state, MIDDLE);
    const second = nextSweepSpot(state) as { x: number; z: number };
    expect(Math.hypot(second.x - MIDDLE.x, second.z - MIDDLE.z)).toBeGreaterThanOrEqual(0.5);
    state = sweep(state, { x: 1.4, z: 1.75 });
    expect(nextSweepSpot(state)).toBeNull();
    expect(nextSweepSpot(EMPTY_METER)).toBeNull();
  });

  it("ignores samples faster than ten a second and tracking jumps", () => {
    let state = EMPTY_METER;
    for (let i = 0; i < 50; i += 1) {
      state = addMeterSample(state, {
        position: { x: i * 0.01, z: 0 },
        yaw: 0,
        pitch: 0,
        atMs: i * 16,
      });
    }
    expect(state.samples).toBeLessThanOrEqual(9);
    const before = state.pathM;
    state = addMeterSample(state, { position: { x: 5, z: 5 }, yaw: 0, pitch: 0, atMs: 10_000 });
    expect(state.pathM).toBe(before);
  });

  it("lists the floor cells walked for the map", () => {
    const cells = walkedCells(loop(EMPTY_METER));
    expect(cells).toContain("1,1");
    expect(cells).toContain("7,5");
    expect(cells).not.toContain("3,3"); // the middle was not walked
  });
});
