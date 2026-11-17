import twinFixture from "../../../../packages/schemas/fixtures/v1/valid/space-twin.json";
import {
  apiGeneration,
  contentFromTwin,
  failureOf,
  finishedStages,
  isTwin,
  POLL_MS,
  type RoomApi,
  type RoomJob,
} from "./room-api";
import type { RoomContent } from "./room-content";

const job = (measure: string, inventory: string, detail?: string): RoomJob => ({
  id: "server-room",
  status: [measure, inventory].includes("failed")
    ? "failed"
    : measure === "done" && inventory === "done"
      ? "ready"
      : "working",
  stages: [
    { stage: "measure", status: measure, detail: measure === "failed" ? detail : null },
    { stage: "inventory", status: inventory, detail: inventory === "failed" ? detail : null },
  ],
});

describe("a room's job", () => {
  it("counts the stages done, in order", () => {
    expect(finishedStages(job("queued", "queued"))).toBe(0);
    expect(finishedStages(job("running", "queued"))).toBe(0);
    expect(finishedStages(job("done", "running"))).toBe(1);
    expect(finishedStages(job("done", "done"))).toBe(2);
    // A later stage never counts before an earlier one.
    expect(finishedStages(job("running", "done"))).toBe(0);
    expect(finishedStages({ id: "r", status: "working", stages: [] })).toBe(0);
  });

  it("gives the reason code when a stage failed", () => {
    expect(failureOf(job("done", "running"))).toBeNull();
    expect(failureOf(job("failed", "queued", "no_walls"))).toBe("no_walls");
    expect(failureOf(job("done", "failed"))).toBe("unknown");
    expect(failureOf({ id: "r", status: "failed", stages: [] })).toBe("unknown");
  });
});

describe("the twin from the server", () => {
  it("is accepted when it has the parts the app reads", () => {
    expect(isTwin(twinFixture)).toBe(true);
  });

  it("is refused when it is not a twin, or a part the app reads is missing or malformed", () => {
    const twin = twinFixture as Record<string, unknown>;
    const shell = twin.shell as Record<string, unknown>;
    for (const bad of [
      null,
      "twin",
      {},
      { ...twin, shell: undefined },
      { ...twin, space_type: 3 },
      { ...twin, objects: "none" },
      { ...twin, shell: { ...shell, walls: [] } },
      { ...twin, shell: { ...shell, floor_polygon: [{ x_m: 0, y_m: 0 }] } },
      { ...twin, shell: { ...shell, ceiling_height: { value_m: "high" } } },
      { ...twin, shell: { ...shell, walls: [{ id: "w1", length: { value_m: 4 } }] } },
    ]) {
      expect(isTwin(bad)).toBe(false);
    }
  });

  it("becomes real room content: measurements, outline and kind, no samples", () => {
    const content = contentFromTwin(twinFixture as never);
    expect(content.sample).toBe(false);
    expect(content.spaceType).toBe("living_room");
    expect(content.measures?.walls).toHaveLength(4);
    expect(content.shell?.floor_polygon).toHaveLength(4);
    expect(content.direction?.sources).toContain("compass");
    // Photos and designs are not in this read.
    expect(content.heroViews).toEqual([]);
    expect(content.looks).toEqual([]);
  });
});

describe("real progress for a room", () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  function setup(jobs: (RoomJob | Error)[], uploadedOk = true, twin: unknown = twinFixture) {
    const calls: string[] = [];
    let next = 0;
    const api: RoomApi = {
      createRoom: jest.fn(async (captureId: string) => {
        calls.push(`create:${captureId}`);
        return job("queued", "queued");
      }),
      getRoom: jest.fn(async (roomId: string) => {
        calls.push(`get:${roomId}`);
        const answer = jobs[Math.min(next, jobs.length - 1)] as RoomJob | Error;
        next += 1;
        if (answer instanceof Error) throw answer;
        return answer;
      }),
      getTwin: jest.fn(async () => twin),
    };
    const ready: [string, RoomContent][] = [];
    const finished: number[] = [];
    const failed: string[] = [];
    const source = apiGeneration(api, {
      captureIdOf: (roomId) => (roomId === "room-1" ? "capture-1" : null),
      uploaded: async () => uploadedOk,
      onReady: (roomId, content) => ready.push([roomId, content]),
    });
    const stop = source.watch(
      "room-1",
      (count) => finished.push(count),
      (reason) => failed.push(reason),
    );
    const tick = async (ms = POLL_MS) => {
      await jest.advanceTimersByTimeAsync(ms);
    };
    return { api, calls, ready, finished, failed, stop, tick };
  }

  it("waits for the upload, creates the room for the scan, then follows it to the end", async () => {
    const run = setup([job("running", "queued"), job("done", "running"), job("done", "done")]);
    await run.tick(0);
    expect(run.calls).toEqual(["create:capture-1", "get:server-room"]);
    expect(run.finished).toEqual([0]);
    await run.tick();
    expect(run.finished).toEqual([0, 1]);
    await run.tick();
    expect(run.finished).toEqual([0, 1, 2]);
    expect(run.ready).toHaveLength(1);
    expect(run.ready[0]?.[0]).toBe("room-1");
    expect(run.ready[0]?.[1].sample).toBe(false);
    // Done: it stops asking.
    await run.tick(POLL_MS * 5);
    expect(run.api.getRoom).toHaveBeenCalledTimes(3);
    expect(run.failed).toEqual([]);
  });

  it("stops with the server's reason when a stage fails", async () => {
    const run = setup([job("failed", "queued", "no_walls")]);
    await run.tick(0);
    expect(run.failed).toEqual(["no_walls"]);
    await run.tick(POLL_MS * 3);
    expect(run.api.getRoom).toHaveBeenCalledTimes(1);
    expect(run.ready).toEqual([]);
  });

  it("does not create a room for a scan that did not upload", async () => {
    const run = setup([job("done", "done")], false);
    await run.tick(0);
    expect(run.failed).toEqual(["upload"]);
    expect(run.api.createRoom).not.toHaveBeenCalled();
  });

  it("keeps trying through a dropped connection", async () => {
    const run = setup([new Error("offline"), new Error("offline"), job("done", "done")]);
    await run.tick(0);
    await run.tick();
    await run.tick();
    expect(run.failed).toEqual([]);
    expect(run.finished).toEqual([2]);
  });

  it("refuses a twin it cannot read rather than show it", async () => {
    const run = setup([job("done", "done")], true, { shell: {} });
    await run.tick(0);
    expect(run.failed).toEqual(["bad_twin"]);
    expect(run.ready).toEqual([]);
  });

  it("stops asking once nobody is watching", async () => {
    const run = setup([job("running", "queued")]);
    await run.tick(0);
    run.stop();
    await run.tick(POLL_MS * 4);
    expect(run.api.getRoom).toHaveBeenCalledTimes(1);
  });
});
